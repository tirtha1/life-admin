"""
Transaction extractor — uses Claude Opus 4.6 to parse bank/UPI/payment emails
into structured transaction data. Falls back to regex if Claude is unavailable.
"""
import re
import structlog
from datetime import date, datetime
from typing import Optional

import anthropic

from app.core.config import get_settings
from app.schemas.transaction import TransactionExtraction

log = structlog.get_logger()
settings = get_settings()

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


_SYSTEM_PROMPT = """You are a financial transaction parser specialising in Indian bank and payment app alert emails.

Extract transaction details from the email text provided.

Rules:
- Set is_transaction=true ONLY for clear debit/credit transaction notifications (not promotional emails, OTP, balance enquiry, etc.)
- amount: numeric value only, no currency symbol (e.g. 250.0, not "₹250")
- type: "debit" if money was spent/sent/debited, "credit" if money was received/deposited
- merchant: the business or person the money went to or came from. Clean it up (e.g. "SWIGGY*ORDER123" → "Swiggy", "POS TXN AMAZON" → "Amazon")
- category: pick the best fit from exactly these values:
    food, transport, shopping, entertainment, utilities, healthcare, education, travel, subscriptions, other
  Category hints:
    food → restaurants, Swiggy, Zomato, Domino's, McDonald's, groceries, BigBasket, Blinkit
    transport → Uber, Ola, Rapido, fuel, petrol, parking, metro, IRCTC trains
    shopping → Amazon, Flipkart, Myntra, Meesho, Ajio, clothing, electronics
    entertainment → PVR, BookMyShow, Netflix, Prime Video, Spotify, gaming
    utilities → electricity, water, gas, internet, Jio, Airtel, BSNL, DTH, phone recharge
    healthcare → hospitals, PharmEasy, 1mg, Apollo, Netmeds, doctor, pharmacy
    education → Coursera, Udemy, school fees, Byju's, Unacademy
    travel → flights, MakeMyTrip, hotels, Oyo, Airbnb
    subscriptions → recurring monthly/yearly services not covered above
- date: transaction date in YYYY-MM-DD format (NOT today's date — look for it in the email body)
- source: the bank or payment app name (e.g. "HDFC Bank", "Axis Bank", "SBI", "GPay", "Paytm", "PhonePe", "ICICI Bank")
- confidence: 0.0–1.0 based on how clearly the transaction details are stated

Return null for any field you cannot determine. If this is clearly not a transaction email, set is_transaction=false."""


# ─── Regex pre-processing (fast path / fallback) ──────────────────────────────

_AMOUNT_PATTERNS = [
    r'(?:Rs\.?|INR|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)',
    r'([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:rupees?|INR)',
    r'(?:amount|debited|credited|payment of)\s*(?:Rs\.?|INR|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)',
]

_DEBIT_KEYWORDS = ['debited', 'debit', 'spent', 'paid', 'payment of', 'withdrawn', 'sent to']
_CREDIT_KEYWORDS = ['credited', 'credit', 'received', 'deposited', 'refund', 'cashback']

_BANK_PATTERNS = {
    'HDFC Bank': r'hdfc',
    'ICICI Bank': r'icici',
    'Axis Bank': r'axis',
    'SBI': r'\bsbi\b|state bank',
    'Kotak Bank': r'kotak',
    'Yes Bank': r'yes bank',
    'GPay': r'gpay|google pay',
    'Paytm': r'paytm',
    'PhonePe': r'phonepe|phone pe',
}


def _regex_extract(text: str) -> TransactionExtraction:
    lower = text.lower()

    # Amount
    amount = None
    for pat in _AMOUNT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                amount = float(m.group(1).replace(',', ''))
                break
            except ValueError:
                pass

    # Type
    txn_type = None
    if any(k in lower for k in _DEBIT_KEYWORDS):
        txn_type = 'debit'
    elif any(k in lower for k in _CREDIT_KEYWORDS):
        txn_type = 'credit'

    # Source (bank/app)
    source = None
    for name, pat in _BANK_PATTERNS.items():
        if re.search(pat, lower):
            source = name
            break

    # Date (today as fallback — regex can't reliably parse)
    today = date.today().isoformat()

    is_txn = amount is not None and txn_type is not None
    return TransactionExtraction(
        is_transaction=is_txn,
        amount=amount,
        type=txn_type,
        merchant=None,
        category='other',
        date=today,
        source=source,
        confidence=0.3 if is_txn else 0.0,
    )


# ─── Date normalisation ───────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    formats = [
        '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y',
        '%d-%b-%Y', '%d %b %Y', '%d %B %Y', '%Y/%m/%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            pass
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(date_str, dayfirst=True).date()
    except Exception:
        return None


# ─── Main extraction function ─────────────────────────────────────────────────

async def extract_transaction_from_email(email_text: str) -> TransactionExtraction:
    """
    Parse a raw email string into a structured TransactionExtraction.
    Uses Claude Opus 4.6 with structured output; falls back to regex on failure.
    """
    text = email_text[:3000]  # keep within context limits

    try:
        client = _get_client()
        response = await client.messages.parse(
            model="claude-opus-4-6",
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Parse this email:\n\n{text}"}],
            output_format=TransactionExtraction,
        )
        result: TransactionExtraction = response.parsed
        log.debug(
            "transaction extracted",
            is_txn=result.is_transaction,
            amount=result.amount,
            merchant=result.merchant,
            confidence=result.confidence,
        )
        return result

    except Exception as e:
        log.warning("claude extraction failed, falling back to regex", error=str(e))
        return _regex_extract(email_text)


def parse_transaction_date(date_str: Optional[str]) -> date:
    """Return parsed date or today as fallback."""
    parsed = _parse_date(date_str)
    return parsed if parsed else date.today()
