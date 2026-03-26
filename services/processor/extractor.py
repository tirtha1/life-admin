"""
Claude Opus 4.6 bill extractor.
Uses client.messages.parse() with Pydantic structured output + adaptive thinking.
PROMPT_VERSION = "v1.2"
"""
import os
import structlog
from datetime import date
from typing import Optional

import anthropic
from pydantic import BaseModel, Field, field_validator

from services.processor.classifier import classify_bill_type

log = structlog.get_logger()

PROMPT_VERSION = "v1.2"
ANTHROPIC_MODEL = "claude-opus-4-6"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
    return _client


# ─── Pydantic extraction schema ───────────────────────────────────────────────

class BillExtraction(BaseModel):
    """Structured output schema for Claude bill extraction."""

    provider: str = Field(
        description="Company/utility name that sent the bill (e.g., 'Airtel', 'HDFC Bank')"
    )
    bill_type: str = Field(
        description=(
            "Category: electricity | water | internet | mobile | insurance | "
            "credit_card | loan | subscription | rent | gas | other"
        )
    )
    amount: Optional[float] = Field(
        default=None,
        description="Total amount due as a number. Null if not found.",
    )
    currency: str = Field(
        default="INR",
        description="3-letter ISO currency code (INR, USD, EUR, GBP, etc.)",
    )
    due_date: Optional[str] = Field(
        default=None,
        description="Due date in ISO 8601 format YYYY-MM-DD. Null if not found.",
    )
    billing_period_start: Optional[str] = Field(
        default=None,
        description="Billing period start date YYYY-MM-DD. Null if not found.",
    )
    billing_period_end: Optional[str] = Field(
        default=None,
        description="Billing period end date YYYY-MM-DD. Null if not found.",
    )
    account_number: Optional[str] = Field(
        default=None,
        description="Account or customer ID. Null if not found.",
    )
    is_overdue: bool = Field(
        default=False,
        description="True if the email explicitly states the payment is overdue.",
    )
    is_recurring: bool = Field(
        default=False,
        description="True if this appears to be a recurring monthly/quarterly bill.",
    )
    confidence: float = Field(
        description=(
            "Your confidence in the extraction accuracy (0.0–1.0). "
            "Use 0.9+ only when all key fields are clearly present."
        )
    )
    extraction_notes: Optional[str] = Field(
        default=None,
        description="Brief notes on ambiguities, missing data, or assumptions made.",
    )

    @field_validator("bill_type")
    @classmethod
    def validate_bill_type(cls, v: str) -> str:
        valid = {
            "electricity", "water", "internet", "mobile", "insurance",
            "credit_card", "loan", "subscription", "rent", "gas", "other",
        }
        return v if v in valid else "other"

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()[:3] if v else "INR"

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


# ─── Prompt builder ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a financial document parser specializing in Indian and international bills, \
invoices, and payment statements. Extract structured billing information precisely.

Rules:
- Extract only information explicitly present in the email — do not infer or guess
- For amounts: use the TOTAL DUE / MINIMUM DUE / AMOUNT DUE field, not the full balance
- For dates: prefer explicit due dates over estimated periods
- Currency defaults to INR unless another currency is clearly stated
- Set confidence < 0.5 if core fields (amount, due_date) are missing
- Set needs_review hint in extraction_notes if amount > 50000 INR or data is contradictory
"""


def _build_user_prompt(
    subject: str,
    sender: str,
    body_text: str,
    snippet: str,
    bill_type_hint: str,
) -> str:
    return f"""\
Extract billing information from this email.

Bill type hint (from heuristics, may be wrong): {bill_type_hint}

--- EMAIL ---
Subject: {subject}
From: {sender}
Snippet: {snippet}

Body:
{body_text[:3000]}
--- END EMAIL ---

Extract all available billing fields. If a field is not present, use null."""


# ─── Main extraction function ─────────────────────────────────────────────────

def extract_bill(
    subject: str,
    sender: str,
    body_text: str,
    snippet: str,
    message_id: str,
) -> BillExtraction:
    """
    Extract structured billing data from email content using Claude Opus 4.6.

    Args:
        subject: Email subject
        sender: Sender email/name
        body_text: Parsed plain-text body
        snippet: Gmail snippet (first ~200 chars)
        message_id: Gmail message ID (for logging)

    Returns:
        BillExtraction Pydantic model

    Raises:
        anthropic.BadRequestError: On invalid input
        Exception: On unexpected Claude errors
    """
    client = _get_client()
    bill_type_hint = classify_bill_type(subject, sender)

    log.info(
        "Extracting bill",
        message_id=message_id,
        bill_type_hint=bill_type_hint,
        prompt_version=PROMPT_VERSION,
    )

    response = client.messages.parse(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(
                    subject, sender, body_text, snippet, bill_type_hint
                ),
            }
        ],
        output_format=BillExtraction,
    )

    result: BillExtraction = response.parsed_output
    log.info(
        "Extraction complete",
        message_id=message_id,
        provider=result.provider,
        amount=result.amount,
        due_date=result.due_date,
        confidence=result.confidence,
        model=ANTHROPIC_MODEL,
        prompt_version=PROMPT_VERSION,
    )
    return result
