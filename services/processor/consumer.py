"""
Processor service Kafka consumer.
Consumes from life-admin.emails.raw, extracts bills via Claude, writes to DB.
"""
import asyncio
import json
import structlog
from typing import Any

from shared.kafka.consumer import BaseConsumer
from shared.db.session import get_db_session_system
from shared.telemetry.decorators import traced

from services.processor.classifier import is_bill_candidate
from services.processor.extractor import extract_bill
from services.processor.validator import validate, ValidationOutcome
from services.processor.bill_repository import upsert_bill, mark_email_processed
from services.processor.publisher import BillPublisher

log = structlog.get_logger()

TOPIC_EMAILS_RAW = "life-admin.emails.raw"
GROUP_ID = "processor-group"


class ProcessorConsumer(BaseConsumer):
    """Consumes raw email events and extracts bills."""

    def __init__(self) -> None:
        super().__init__(
            topics=[TOPIC_EMAILS_RAW],
            group_id=GROUP_ID,
        )
        self._publisher = BillPublisher()

    @traced("processor.handle_email")
    def process_message(self, message_data: dict[str, Any]) -> None:
        """
        Process a single raw email event.

        Flow:
        1. Re-classify (full body available via S3 — currently uses snippet)
        2. Extract bill via Claude Opus 4.6
        3. Validate extraction
        4. Write bill to DB (or mark as review_required)
        5. Publish bill.extracted to Kafka
        6. Mark raw_email.processed = TRUE
        """
        user_id = message_data.get("user_id", "")
        message_id = message_data.get("message_id", "")
        subject = message_data.get("subject", "")
        sender = message_data.get("sender", "")
        snippet = message_data.get("snippet", "")
        raw_email_id = message_data.get("raw_email_id", "")
        s3_key = message_data.get("s3_key", "")

        log.info(
            "Processing email",
            user_id=user_id,
            message_id=message_id,
            subject=subject[:60],
        )

        # Step 1: classifier check (fast, free)
        # Note: full body would be fetched from S3 in production.
        # Using snippet here; S3 fetch adds latency that may not be worth it
        # for the classifier (the LLM will see the full body from S3 anyway).
        if not is_bill_candidate(subject, snippet):
            log.info(
                "Email failed classifier — skipping",
                message_id=message_id,
                subject=subject[:60],
            )
            # Still mark as processed to avoid reprocessing
            asyncio.get_event_loop().run_until_complete(
                self._mark_processed_if_exists(raw_email_id)
            )
            return

        # Step 2: Claude extraction (uses snippet as body — full body from S3 is TODO)
        try:
            extraction = extract_bill(
                subject=subject,
                sender=sender,
                body_text=snippet,  # In production: fetch full body from S3
                snippet=snippet,
                message_id=message_id,
            )
        except Exception as exc:
            log.error(
                "Extraction failed",
                message_id=message_id,
                error=str(exc),
                exc_info=True,
            )
            raise  # Let BaseConsumer handle retry/DLQ

        # Step 3: Validate
        validation = validate(extraction, message_id)

        if validation.outcome == ValidationOutcome.REJECT:
            log.info("Extraction rejected by validator", message_id=message_id)
            asyncio.get_event_loop().run_until_complete(
                self._mark_processed_if_exists(raw_email_id)
            )
            return

        # Steps 4–6: DB write + Kafka publish
        asyncio.get_event_loop().run_until_complete(
            self._persist_and_publish(user_id, raw_email_id, message_id, validation)
        )

    async def _persist_and_publish(
        self,
        user_id: str,
        raw_email_id: str,
        message_id: str,
        validation,
    ) -> None:
        """Write bill to DB and publish extracted event."""
        async for session in get_db_session_system():
            try:
                bill = await upsert_bill(
                    session=session,
                    user_id=user_id,
                    raw_email_id=raw_email_id,
                    validation=validation,
                    message_id=message_id,
                )
                await mark_email_processed(session, str(bill.raw_email_id))
                await session.commit()

                # Publish to Kafka after DB commit (at-least-once)
                self._publisher.publish_bill_extracted(
                    user_id=user_id,
                    bill_id=str(bill.id),
                    provider=bill.provider,
                    bill_type=bill.bill_type,
                    amount=float(bill.amount) if bill.amount else None,
                    currency=bill.currency,
                    due_date=bill.due_date,
                    status=bill.status.value,
                    needs_review=bill.needs_review,
                )
                self._publisher.flush()

            except Exception as exc:
                await session.rollback()
                log.error(
                    "DB write failed",
                    message_id=message_id,
                    error=str(exc),
                    exc_info=True,
                )
                raise

    async def _mark_processed_if_exists(self, raw_email_id: str) -> None:
        """Mark email processed without creating a bill."""
        if not raw_email_id:
            return
        async for session in get_db_session_system():
            try:
                await mark_email_processed(session, raw_email_id)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                log.warning(
                    "Could not mark email processed",
                    raw_email_id=raw_email_id,
                    error=str(exc),
                )


def run() -> None:
    """Entry point: start the processor consumer loop."""
    import os
    from shared.telemetry.setup import setup_telemetry

    setup_telemetry("processor")

    log.info("Starting processor consumer")
    consumer = ProcessorConsumer()
    consumer.run()
