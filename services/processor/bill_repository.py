"""
Bill repository — DB write layer for the processor service.
Writes extracted bills and updates raw_email.processed flag.
"""
import structlog
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Bill, RawEmail, BillTransition, BillStatus
from services.processor.extractor import BillExtraction
from services.processor.validator import ValidationResult, ValidationOutcome
from services.processor.extractor import PROMPT_VERSION, ANTHROPIC_MODEL

log = structlog.get_logger()


async def upsert_bill(
    session: AsyncSession,
    user_id: str,
    raw_email_id: str,
    validation: ValidationResult,
    message_id: str,
) -> Bill:
    """
    Insert a new bill row from validated extraction.
    If a bill with the same raw_email_id already exists, skip (idempotent).

    Returns the created or existing Bill.
    """
    extraction = validation.extraction

    # If raw_email_id is missing, look it up from the raw_emails table
    if not raw_email_id:
        result = await session.execute(
            text("SELECT id FROM raw_emails WHERE user_id = :uid AND message_id = :mid"),
            {"uid": user_id, "mid": message_id},
        )
        row = result.fetchone()
        if row:
            raw_email_id = str(row[0])
        else:
            raise ValueError(f"raw_email not found for message_id={message_id}")

    # Check for existing bill from this raw email
    existing = await session.execute(
        select(Bill).where(
            Bill.user_id == user_id,
            Bill.raw_email_id == raw_email_id,
        )
    )
    existing_bill = existing.scalar_one_or_none()
    if existing_bill:
        log.debug(
            "Bill already exists for raw_email",
            raw_email_id=raw_email_id,
            bill_id=str(existing_bill.id),
        )
        return existing_bill

    # Determine initial status
    if validation.outcome == ValidationOutcome.REVIEW:
        initial_status = BillStatus.REVIEW_REQUIRED
    else:
        initial_status = BillStatus.EXTRACTED

    bill = Bill(
        user_id=user_id,
        raw_email_id=raw_email_id,
        provider=extraction.provider,
        bill_type=extraction.bill_type,
        amount=extraction.amount,
        currency=extraction.currency,
        due_date=validation.due_date,
        billing_period_start=validation.billing_period_start,
        billing_period_end=validation.billing_period_end,
        account_number=extraction.account_number,
        status=initial_status,
        extraction_confidence=extraction.confidence,
        extraction_model=ANTHROPIC_MODEL,
        extraction_raw={
            "prompt_version": PROMPT_VERSION,
            "provider": extraction.provider,
            "bill_type": extraction.bill_type,
            "amount": extraction.amount,
            "currency": extraction.currency,
            "due_date": extraction.due_date,
            "billing_period_start": extraction.billing_period_start,
            "billing_period_end": extraction.billing_period_end,
            "account_number": extraction.account_number,
            "is_overdue": extraction.is_overdue,
            "is_recurring": extraction.is_recurring,
            "confidence": extraction.confidence,
            "extraction_notes": extraction.extraction_notes,
            "validation_reasons": validation.reasons,
        },
        is_overdue=extraction.is_overdue,
        is_recurring=extraction.is_recurring,
        needs_review=validation.needs_review,
    )
    session.add(bill)
    await session.flush()  # Get bill.id without committing

    # Write initial state transition
    transition = BillTransition(
        bill_id=bill.id,
        from_status=BillStatus.DETECTED,
        to_status=initial_status,
        reason="Extracted by processor service",
        actor="processor",
    )
    session.add(transition)

    log.info(
        "Bill created",
        bill_id=str(bill.id),
        user_id=user_id,
        provider=bill.provider,
        amount=bill.amount,
        status=initial_status.value,
        needs_review=bill.needs_review,
        message_id=message_id,
    )
    return bill


async def mark_email_processed(session: AsyncSession, raw_email_id: str) -> None:
    """Mark a raw_email row as processed = TRUE."""
    await session.execute(
        update(RawEmail)
        .where(RawEmail.id == raw_email_id)
        .values(processed=True)
    )
    log.debug("Marked raw_email processed", raw_email_id=raw_email_id)
