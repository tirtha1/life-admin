"""
Ingestion router — trigger Gmail sync for the authenticated user.
"""
import asyncio
import os
import structlog
from datetime import date
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, text

from shared.db.models import Transaction, TransactionType, TransactionCategory
from shared.db.session import get_db_session
from services.api.security import CurrentUser, get_current_user
from services.api.transaction_extractor import (
    TransactionExtraction,
    extract_transaction,
    parse_transaction_date,
)

log = structlog.get_logger()

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class SyncResponse(BaseModel):
    message: str
    user_id: str


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Trigger an immediate Gmail poll for the authenticated user.
    Dispatches a Celery task asynchronously.
    """
    try:
        from services.ingestion.tasks import poll_inbox
        poll_inbox.delay(current_user.user_id)
        log.info("Sync triggered", user_id=current_user.user_id)
    except Exception as exc:
        log.error("Failed to dispatch sync task", error=str(exc))
        raise HTTPException(status_code=503, detail="Ingestion service unavailable")

    return SyncResponse(
        message="Sync triggered — processing in background",
        user_id=current_user.user_id,
    )


# ─── Transaction sync ─────────────────────────────────────────────────────────

class TransactionSyncResponse(BaseModel):
    emails_scanned: int
    transactions_found: int
    transactions_new: int
    transactions_skipped: int
    errors: int


@router.post("/transactions/sync", response_model=TransactionSyncResponse)
async def sync_transactions(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Fetch transaction alert emails (bank debits, UPI payments) from Gmail,
    extract structured data with Claude, and store in the transactions table.
    """
    from services.ingestion.token_manager import TokenManager
    from services.ingestion.gmail_client import GmailClient

    uid = current_user.user_id
    result = TransactionSyncResponse(
        emails_scanned=0,
        transactions_found=0,
        transactions_new=0,
        transactions_skipped=0,
        errors=0,
    )

    # Get OAuth credentials
    try:
        tm = TokenManager(user_id=uid)
        creds = await asyncio.to_thread(tm.get_valid_credentials)
    except Exception as exc:
        log.warning("No OAuth tokens for transaction sync", user_id=uid, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Gmail not connected. Complete OAuth flow via /api/v1/ingestion/oauth/start first.",
        )

    # Fetch transaction emails
    gmail = GmailClient(
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    )

    try:
        emails = await asyncio.to_thread(gmail.fetch_transaction_emails, 100, 30)
    except Exception as exc:
        log.error("Gmail transaction fetch failed", user_id=uid, error=str(exc))
        raise HTTPException(status_code=503, detail=f"Gmail fetch failed: {exc}")

    result.emails_scanned = len(emails)
    log.info("Transaction emails fetched", user_id=uid, count=len(emails))

    async for session in get_db_session(uid):
        for email in emails:
            try:
                # Deduplication: check if this email_id was already processed for this user
                existing = await session.execute(
                    text("SELECT id FROM transactions WHERE user_id = :uid AND email_id = :eid"),
                    {"uid": uid, "eid": email.message_id},
                )
                if existing.fetchone():
                    result.transactions_skipped += 1
                    continue

                # Extract with Claude
                extraction: TransactionExtraction = await extract_transaction(email.combined_text())

                if not extraction.is_transaction or extraction.amount is None:
                    log.debug("Not a transaction, skipping", subject=email.subject)
                    continue

                result.transactions_found += 1

                # Normalise enums
                try:
                    txn_type = TransactionType(extraction.type or "debit")
                except ValueError:
                    txn_type = TransactionType.DEBIT
                try:
                    category = TransactionCategory(extraction.category or "other")
                except ValueError:
                    category = TransactionCategory.OTHER

                txn = Transaction(
                    user_id=uid,
                    email_id=email.message_id,
                    amount=extraction.amount,
                    type=txn_type,
                    merchant=extraction.merchant,
                    category=category,
                    date=parse_transaction_date(extraction.date),
                    source=extraction.source,
                    raw_text=email.combined_text()[:2000],
                    extraction_confidence=extraction.confidence,
                )
                session.add(txn)
                result.transactions_new += 1
                log.info(
                    "Transaction stored",
                    user_id=uid,
                    amount=txn.amount,
                    merchant=txn.merchant,
                    category=txn.category,
                )

            except Exception as exc:
                log.error("Error processing transaction email", subject=email.subject, error=str(exc))
                result.errors += 1
                continue

    log.info(
        "Transaction sync complete",
        user_id=uid,
        scanned=result.emails_scanned,
        new=result.transactions_new,
        skipped=result.transactions_skipped,
    )
    return result
