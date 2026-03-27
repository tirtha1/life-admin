"""
Celery tasks for the ingestion service.
Entry point: poll_inbox — fetches Gmail, deduplicates, uploads to S3, publishes to Kafka.
"""
import asyncio
import os
import structlog
from datetime import datetime, timezone
from typing import Optional

import redis as sync_redis
from celery import Celery
from sqlalchemy import text

from shared.db.session import get_db_session_system
from shared.db.models import RawEmail, User
from shared.telemetry.setup import setup_telemetry
from shared.vault.client import VaultClient

from services.ingestion.gmail_client import GmailClient, ParsedEmail, describe_gmail_exception
from services.ingestion.token_manager import TokenManager
from services.ingestion.deduplicator import is_duplicate, mark_processed
from services.ingestion.s3_uploader import upload_email, ensure_bucket_exists
from services.ingestion.publisher import EmailPublisher

log = structlog.get_logger()

# ─── Celery app ───────────────────────────────────────────────────────────────

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

app = Celery("ingestion", broker=BROKER_URL, backend=RESULT_BACKEND)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="ingestion",
    task_routes={
        "services.ingestion.tasks.*": {"queue": "ingestion"},
    },
)

# Celery Beat schedule: poll every 15 minutes
app.conf.beat_schedule = {
    "poll-all-active-users": {
        "task": "services.ingestion.tasks.poll_all_users",
        "schedule": 900,  # 15 minutes in seconds
    },
}

# ─── Redis sync client for historyId tracking ─────────────────────────────────

_sync_redis: sync_redis.Redis | None = None


def _get_sync_redis() -> sync_redis.Redis:
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = sync_redis.from_url(REDIS_URL, decode_responses=True)
    return _sync_redis


def _history_key(user_id: str) -> str:
    return f"gmail:history_id:{user_id}"


def _get_last_history_id(user_id: str) -> str | None:
    return _get_sync_redis().get(_history_key(user_id))


def _set_history_id(user_id: str, history_id: str) -> None:
    _get_sync_redis().set(_history_key(user_id), history_id, ex=60 * 60 * 24 * 30)


# ─── Helpers ──────────────────────────────────────────────────────────────────

class GmailAPIError(Exception):
    """Raised when Gmail API calls fail after retries."""


async def _persist_raw_email(
    user_id: str, email: ParsedEmail, s3_key: str
) -> Optional[str]:
    """Insert a record into raw_emails (using system session — no RLS).
    Returns the raw_email UUID, or None if it already existed.
    """
    async for session in get_db_session_system():
        # Check if already exists (DB-level dedup backstop)
        existing = await session.execute(
            text(
                "SELECT id FROM raw_emails WHERE user_id = :uid AND message_id = :mid"
            ),
            {"uid": user_id, "mid": email.message_id},
        )
        row = existing.fetchone()
        if row:
            log.debug(
                "DB dedup hit", user_id=user_id, message_id=email.message_id
            )
            return str(row[0])

        # Parse received_at to timestamptz
        received_at = None
        if email.received_at:
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(email.received_at)
            except Exception:
                pass

        raw = RawEmail(
            user_id=user_id,
            message_id=email.message_id,
            thread_id=email.thread_id,
            subject=email.subject,
            sender=email.sender,
            received_at=received_at,
            s3_key=s3_key,
            processed=False,
        )
        session.add(raw)
        try:
            await session.flush()
            raw_email_id = str(raw.id)
            await session.commit()
            return raw_email_id
        except Exception as exc:
            await session.rollback()
            # Unique constraint violation means another worker beat us — OK
            if "unique" in str(exc).lower():
                log.debug(
                    "Race condition on insert — already exists",
                    user_id=user_id,
                    message_id=email.message_id,
                )
                return None
            else:
                raise


async def _process_user_inbox(user_id: str) -> dict:
    """
    Core async logic for polling a user's inbox.

    Returns stats dict with counts of new, skipped, failed emails.
    """
    log.info("Polling inbox", user_id=user_id)

    # 1. Get valid credentials via TokenManager
    tm = TokenManager(user_id=user_id)
    try:
        creds = tm.get_valid_credentials()
    except ValueError as exc:
        log.warning("No OAuth tokens for user", user_id=user_id, error=str(exc))
        return {"new": 0, "skipped": 0, "failed": 0, "reason": "no_tokens"}

    # 2. Build Gmail client
    gmail = GmailClient(
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    )

    # 3. Fetch emails (last 30 days, up to 50)
    try:
        emails = gmail.fetch_recent_emails(max_results=50, days_back=30)
    except Exception as exc:
        error_message = describe_gmail_exception(exc)
        log.error("Gmail fetch failed", user_id=user_id, error=error_message)
        raise GmailAPIError(error_message) from exc

    log.info("Fetched bill candidates", user_id=user_id, count=len(emails))

    # 4. Ensure S3 bucket exists (no-op in production)
    ensure_bucket_exists()

    # 5. Process each email
    publisher = EmailPublisher()
    stats = {"new": 0, "skipped": 0, "failed": 0}

    for email in emails:
        try:
            # Redis SETNX dedup
            if await is_duplicate(user_id, email.message_id):
                stats["skipped"] += 1
                continue

            # Upload raw JSON to S3
            s3_key = await upload_email(user_id, email)

            # Persist to raw_emails table
            raw_email_id = await _persist_raw_email(user_id, email, s3_key)

            # Publish to Kafka
            publisher.publish_email(user_id, email, s3_key, raw_email_id or "")

            # Extend Redis TTL on success
            await mark_processed(user_id, email.message_id)

            stats["new"] += 1
            log.info(
                "Email ingested",
                user_id=user_id,
                message_id=email.message_id,
                subject=email.subject[:60],
            )

        except Exception as exc:
            stats["failed"] += 1
            log.error(
                "Failed to process email",
                user_id=user_id,
                message_id=email.message_id,
                error=str(exc),
                exc_info=True,
            )

    publisher.flush()
    log.info("Inbox poll complete", user_id=user_id, **stats)
    return stats


# ─── Celery tasks ─────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(GmailAPIError,),
    retry_backoff=True,
    retry_jitter=True,
    name="services.ingestion.tasks.poll_inbox",
)
def poll_inbox(self, user_id: str) -> dict:
    """
    Poll a single user's Gmail inbox for bill emails.

    Steps:
    1. Load valid OAuth credentials via TokenManager (auto-refresh)
    2. Fetch unread emails matching bill keywords (last 30 days)
    3. For each new email: deduplicate → upload S3 → persist DB → publish Kafka
    4. On retryable error: retry with exponential backoff (max 3 attempts)
    5. On exhausted retries: publish to DLQ via Kafka producer
    """
    log.info("poll_inbox task started", user_id=user_id, attempt=self.request.retries)

    try:
        stats = asyncio.get_event_loop().run_until_complete(
            _process_user_inbox(user_id)
        )
        return stats
    except GmailAPIError:
        raise  # autoretry_for handles this
    except Exception as exc:
        log.error(
            "Unrecoverable error in poll_inbox",
            user_id=user_id,
            error=str(exc),
            exc_info=True,
        )
        # Publish to DLQ
        try:
            publisher = EmailPublisher()
            publisher.publish_to_dlq(
                original_topic="life-admin.emails.raw",
                original_message={"user_id": user_id},
                error_type=type(exc).__name__,
                error_message=str(exc),
                retry_count=self.request.retries,
            )
            publisher.flush()
        except Exception as dlq_exc:
            log.error("DLQ publish failed", error=str(dlq_exc))
        raise


@app.task(name="services.ingestion.tasks.poll_all_users")
def poll_all_users() -> None:
    """
    Fan out poll_inbox tasks for every active user with OAuth tokens.
    Runs on Celery Beat schedule (every 15 minutes).
    """
    log.info("Fanning out inbox polls to all active users")

    async def _get_active_user_ids() -> list[str]:
        user_ids = []
        async for session in get_db_session_system():
            result = await session.execute(
                text(
                    "SELECT DISTINCT u.id::text FROM users u "
                    "JOIN oauth_tokens ot ON ot.user_id = u.id "
                    "WHERE u.is_active = TRUE AND ot.provider = 'google'"
                )
            )
            user_ids = [row[0] for row in result.fetchall()]
        return user_ids

    try:
        user_ids = asyncio.get_event_loop().run_until_complete(_get_active_user_ids())
    except Exception as exc:
        log.error("Failed to fetch active users", error=str(exc))
        return

    log.info("Dispatching poll_inbox tasks", user_count=len(user_ids))
    for uid in user_ids:
        poll_inbox.delay(uid)
