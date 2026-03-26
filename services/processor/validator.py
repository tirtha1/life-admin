"""
Validates Claude extraction output.
Applies CONFIDENCE_THRESHOLD and business rules to decide:
  - ACCEPT: write bill to DB normally
  - REVIEW: write bill with needs_review=True, status='review_required'
  - REJECT: discard (low-confidence junk)
"""
import re
import structlog
from datetime import date, datetime, timezone
from typing import Optional
from enum import Enum

from services.processor.extractor import BillExtraction

log = structlog.get_logger()

CONFIDENCE_THRESHOLD = 0.75
HIGH_VALUE_THRESHOLD = 50_000.0  # INR — flag for human review
MIN_AMOUNT = 1.0  # Amounts below this are likely parsing errors


class ValidationOutcome(str, Enum):
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


class ValidationResult:
    def __init__(
        self,
        outcome: ValidationOutcome,
        extraction: BillExtraction,
        due_date: Optional[date],
        billing_period_start: Optional[date],
        billing_period_end: Optional[date],
        reasons: list[str],
    ):
        self.outcome = outcome
        self.extraction = extraction
        self.due_date = due_date
        self.billing_period_start = billing_period_start
        self.billing_period_end = billing_period_end
        self.reasons = reasons
        self.needs_review = outcome == ValidationOutcome.REVIEW


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    """Parse YYYY-MM-DD string to date. Returns None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        # Try common formats
        for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def validate(extraction: BillExtraction, message_id: str) -> ValidationResult:
    """
    Validate a BillExtraction and return a ValidationResult.

    Decision logic:
    - confidence < 0.4                → REJECT
    - confidence < CONFIDENCE_THRESHOLD → REVIEW
    - missing provider or bill_type   → REVIEW
    - amount > HIGH_VALUE_THRESHOLD   → REVIEW (human approval for large payments)
    - amount < MIN_AMOUNT             → REVIEW (likely parse error)
    - due date in the past (>30 days) → REVIEW
    - otherwise                       → ACCEPT
    """
    reasons: list[str] = []
    outcome = ValidationOutcome.ACCEPT

    # Parse date fields
    due_date = _parse_iso_date(extraction.due_date)
    billing_period_start = _parse_iso_date(extraction.billing_period_start)
    billing_period_end = _parse_iso_date(extraction.billing_period_end)

    # ── Confidence checks ──────────────────────────────────────────────────────
    if extraction.confidence < 0.4:
        log.info(
            "Extraction rejected — confidence too low",
            message_id=message_id,
            confidence=extraction.confidence,
        )
        return ValidationResult(
            outcome=ValidationOutcome.REJECT,
            extraction=extraction,
            due_date=due_date,
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            reasons=[f"Confidence {extraction.confidence:.2f} < 0.4 (reject threshold)"],
        )

    if extraction.confidence < CONFIDENCE_THRESHOLD:
        reasons.append(
            f"Confidence {extraction.confidence:.2f} < {CONFIDENCE_THRESHOLD} (review threshold)"
        )
        outcome = ValidationOutcome.REVIEW

    # ── Required field checks ──────────────────────────────────────────────────
    if not extraction.provider or extraction.provider.strip() == "":
        reasons.append("Missing provider name")
        outcome = ValidationOutcome.REVIEW

    if not extraction.bill_type or extraction.bill_type == "other":
        reasons.append("Bill type is 'other' — may need manual categorisation")
        # Don't escalate to REVIEW for 'other' alone — it's valid

    # ── Amount checks ──────────────────────────────────────────────────────────
    if extraction.amount is not None:
        if extraction.amount < MIN_AMOUNT:
            reasons.append(f"Amount {extraction.amount} below minimum threshold ({MIN_AMOUNT})")
            outcome = ValidationOutcome.REVIEW

        if extraction.amount > HIGH_VALUE_THRESHOLD:
            reasons.append(
                f"High-value bill ({extraction.currency} {extraction.amount:,.2f}) — human approval recommended"
            )
            outcome = ValidationOutcome.REVIEW
    else:
        # No amount at all — acceptable but flag for review if confidence is borderline
        if extraction.confidence < 0.85:
            reasons.append("Amount not found and confidence < 0.85")
            outcome = ValidationOutcome.REVIEW

    # ── Due date checks ────────────────────────────────────────────────────────
    if due_date is not None:
        today = date.today()
        days_overdue = (today - due_date).days
        if days_overdue > 30:
            reasons.append(f"Due date {due_date} is {days_overdue} days in the past")
            outcome = ValidationOutcome.REVIEW
    else:
        # Missing due date with low confidence → review
        if extraction.confidence < 0.9:
            reasons.append("Due date not found")
            # Don't escalate if confidence is high — some receipts legitimately lack due dates

    # ── Date coherence ─────────────────────────────────────────────────────────
    if billing_period_start and billing_period_end:
        if billing_period_start > billing_period_end:
            reasons.append(
                f"Billing period start {billing_period_start} > end {billing_period_end}"
            )
            outcome = ValidationOutcome.REVIEW

    if reasons:
        log.info(
            "Validation issues",
            message_id=message_id,
            outcome=outcome,
            reasons=reasons,
        )
    else:
        log.info("Validation passed", message_id=message_id, outcome=outcome)

    return ValidationResult(
        outcome=outcome,
        extraction=extraction,
        due_date=due_date,
        billing_period_start=billing_period_start,
        billing_period_end=billing_period_end,
        reasons=reasons,
    )
