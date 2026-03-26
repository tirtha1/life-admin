"""
Bill extraction service using Claude Opus 4.6.
Uses structured outputs (Pydantic) to extract bill data from email text.
"""
import re
import structlog
from datetime import date, datetime
from typing import Optional

import anthropic

from app.core.config import get_settings
from app.schemas.bill import BillExtraction
from app.models.bill import BillType

log = structlog.get_logger()
settings = get_settings()

_client: Optional[anthropic.Anthropic] = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM_PROMPT = """You are a financial document analyzer specialized in extracting bill and invoice information from emails.

Your job is to analyze email content and extract structured billing information.

Rules:
- Only mark is_bill=true if the email clearly contains a bill, invoice, or payment request
- Extract the exact amount (numeric only, no currency symbols)
- Always return dates in YYYY-MM-DD format
- For Indian bills, default currency to INR
- bill_type must be one of: electricity, water, gas, internet, phone, credit_card, insurance, subscription, rent, other
- Set confidence based on how clear the information is (0.0-1.0)
- If information is not present, use null for optional fields"""


def _regex_prefill(text: str) -> dict:
    """
    Fast regex extraction as a fallback / double-check for Claude.
    Extracts amount and due date patterns common in Indian bills.
    """
    result = {}

    # Amount patterns: ₹1,234.56 / Rs. 1234 / INR 1234 / Total Due: 1234
    amount_patterns = [
        r"(?:₹|Rs\.?|INR)\s*([\d,]+\.?\d*)",
        r"(?:total|amount|due|pay)\s+(?:due|amount|payable)?[\s:]+(?:₹|Rs\.?|INR)?\s*([\d,]+\.?\d*)",
        r"([\d,]+\.?\d*)\s*(?:₹|Rs\.?|INR)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                result["amount"] = float(amount_str)
                break
            except ValueError:
                pass

    # Due date patterns
    date_patterns = [
        r"due\s+(?:date|by|on)?[\s:]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"pay\s+by[\s:]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"last\s+date[\s:]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["due_date_raw"] = match.group(1)
            break

    return result


async def extract_bill_from_email(email_text: str) -> BillExtraction:
    """
    Use Claude Opus 4.6 with structured output to extract bill info.
    Falls back to regex hints if LLM is unavailable.

    Args:
        email_text: Combined subject + body text of the email

    Returns:
        BillExtraction pydantic model with all extracted fields
    """
    client = get_anthropic_client()

    # Regex prefill for hints
    regex_hints = _regex_prefill(email_text)
    hint_text = ""
    if regex_hints:
        hint_text = f"\n\nHint from regex pre-processing: {regex_hints}"

    try:
        log.debug("Calling Claude for bill extraction")

        response = client.messages.parse(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Analyze this email and extract bill information:\n\n"
                        f"---\n{email_text[:3000]}\n---"
                        f"{hint_text}"
                    ),
                }
            ],
            output_format=BillExtraction,
        )

        extraction = response.parsed_output
        if extraction is None:
            log.warning("Claude returned null parsed output, using defaults")
            return BillExtraction(is_bill=False)

        log.info(
            "Bill extracted",
            is_bill=extraction.is_bill,
            provider=extraction.provider,
            amount=extraction.amount,
            due_date=extraction.due_date,
            confidence=extraction.confidence,
        )
        return extraction

    except anthropic.APIError as e:
        log.error("Anthropic API error during extraction", error=str(e))
        # Fallback: use regex results
        return BillExtraction(
            is_bill=bool(regex_hints.get("amount")),
            amount=regex_hints.get("amount"),
            confidence=0.3 if regex_hints else 0.0,
        )


def parse_due_date(date_str: Optional[str]) -> Optional[date]:
    """Parse various date string formats into a date object."""
    if not date_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
        "%d-%b-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    # Try dateutil as last resort
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(date_str, dayfirst=True).date()
    except Exception:
        log.warning("Could not parse date", date_str=date_str)
        return None


def normalize_bill_type(raw_type: str) -> BillType:
    """Normalize extracted bill type string to BillType enum."""
    mapping = {
        "electricity": BillType.ELECTRICITY,
        "water": BillType.WATER,
        "gas": BillType.GAS,
        "internet": BillType.INTERNET,
        "broadband": BillType.INTERNET,
        "wifi": BillType.INTERNET,
        "phone": BillType.PHONE,
        "mobile": BillType.PHONE,
        "prepaid": BillType.PHONE,
        "postpaid": BillType.PHONE,
        "credit_card": BillType.CREDIT_CARD,
        "credit card": BillType.CREDIT_CARD,
        "insurance": BillType.INSURANCE,
        "subscription": BillType.SUBSCRIPTION,
        "netflix": BillType.SUBSCRIPTION,
        "spotify": BillType.SUBSCRIPTION,
        "amazon": BillType.SUBSCRIPTION,
        "rent": BillType.RENT,
    }

    normalized = raw_type.lower().strip()
    return mapping.get(normalized, BillType.OTHER)
