"""
Transaction extractor — uses Claude Opus 4.6 to parse bank/UPI/payment emails
into structured transaction data. Falls back to regex on failure.
"""
import os
import re
import structlog
from datetime import date, datetime
from typing import Optional

import anthropic
from pydantic import BaseModel

log = structlog.get_logger()

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ─── Extraction schema (Claude structured output) ─────────────────────────────

class TransactionExtraction(BaseModel):
    is_transaction: bool
    amount: Optional[float] = None
    type: Optional[str] = None        # "debit" or "credit"
    merchant: Optional[str] = None
    category: Optional[str] = None   # food/transport/shopping/entertainment/utilities/healthcare/education/travel/subscriptions/other
    date: Optional[str] = None        # YYYY-MM-DD
    source: Optional[str] = None      # bank or payment app name
    confidence: float = 0.0


_SYSTEM_PROMPT = """You are a financial transaction parser specialising in Indian bank and payment app alert emails.

Extract transaction details from the email text.

Rules:
- Set is_transaction=true ONLY for clear debit/credit transaction notifications (not OTPs, promotions, balance enquiry, or login alerts)
- amount: numeric value only, no currency symbol (e.g. 250.0 not "₹250")
- type: "debit" if money was spent/sent, "credit" if money was received/deposited/refunded
- merchant: business/person money went to or came from — clean it up (e.g. "SWIGGY*ORDER123" → "Swiggy")
- category: exactly one of: food, transport, shopping, entertainment, utilities, healthcare, education, travel, subscriptions, other
  - food: Swiggy, Zomato, restaurants, groceries, BigBasket, Blinkit
  - transport: Uber, Ola, Rapido, petrol, metro, parking
  - shopping: Amazon, Flipkart, Myntra, Meesho, clothing, electronics
  - entertainment: Netflix, Prime, Spotify, PVR, BookMyShow, gaming
  - utilities: electricity, water, Jio, Airtel, DTH, phone recharge
  - healthcare: Apollo, PharmEasy, 1mg, hospitals, pharmacy
  - education: Coursera, Udemy, Byju's, school fees
  - travel: flights, hotels, MakeMyTrip, Oyo, IRCTC
  - subscriptions: recurring services not covered above
- date: transaction date in YYYY-MM-DD (look for it in the email, do NOT use today's date)
- source: bank or payment app (e.g. "HDFC Bank", "Axis Bank", "SBI", "GPay", "Paytm", "PhonePe")
- confidence: 0.0–1.0 based on clarity of the transaction details

Return null for any field you cannot determine with confidence."""


# ─── Regex fallback ───────────────────────────────────────────────────────────

_AMOUNT_PATTERNS = [
    r'(?:Rs\.?|INR|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)',
    r'([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:rupees?|INR)',
    r'(?:amount|debited|credited|payment of)\s*(?:Rs\.?|INR|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)',
]
_DEBIT_KW = ['debited', 'debit', 'spent', 'paid', 'payment of', 'withdrawn', 'sent']
_CREDIT_KW = ['credited', 'credit', 'received', 'deposited', 'refund', 'cashback']
_BANK_MAP = {
    'HDFC Bank': r'hdfc', 'ICICI Bank': r'icici', 'Axis Bank': r'axis',
    'SBI': r'\bsbi\b|state bank', 'Kotak Bank': r'kotak',
    'GPay': r'gpay|google pay', 'Paytm': r'paytm', 'PhonePe': r'phonepe',
}


def _regex_fallback(text: str) -> TransactionExtraction:
    lower = text.lower()
    amount = None
    for pat in _AMOUNT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                amount = float(m.group(1).replace(',', ''))
                break
            except ValueError:
                pass
    txn_type = None
    if any(k in lower for k in _DEBIT_KW):
        txn_type = 'debit'
    elif any(k in lower for k in _CREDIT_KW):
        txn_type = 'credit'
    source = None
    for name, pat in _BANK_MAP.items():
        if re.search(pat, lower):
            source = name
            break
    is_txn = amount is not None and txn_type is not None
    return TransactionExtraction(
        is_transaction=is_txn,
        amount=amount,
        type=txn_type,
        merchant=None,
        category='other',
        date=date.today().isoformat(),
        source=source,
        confidence=0.3 if is_txn else 0.0,
    )


# ─── Date parsing ─────────────────────────────────────────────────────────────

def parse_transaction_date(date_str: Optional[str]) -> date:
    if not date_str:
        return date.today()
    formats = [
        '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y',
        '%d-%b-%Y', '%d %b %Y', '%d %B %Y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            pass
    try:
        from dateutil import parser as dp
        return dp.parse(date_str, dayfirst=True).date()
    except Exception:
        return date.today()


# ─── Main extraction ──────────────────────────────────────────────────────────

async def extract_transaction(email_text: str) -> TransactionExtraction:
    """Parse raw email text into a TransactionExtraction using Claude Opus 4.6."""
    text = email_text[:3000]
    try:
        client = _get_client()
        response = await client.messages.parse(
            model="claude-opus-4-6",
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Parse this email:\n\n{text}"}],
            output_format=TransactionExtraction,
        )
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            parsed = getattr(response, "parsed", None)
        if parsed is None:
            raise ValueError("Claude parse response did not include parsed output")
        result = (
            parsed
            if isinstance(parsed, TransactionExtraction)
            else TransactionExtraction.model_validate(parsed)
        )
        log.debug(
            "transaction extracted",
            is_txn=result.is_transaction,
            amount=result.amount,
            merchant=result.merchant,
            confidence=result.confidence,
        )
        return result
    except Exception as e:
        log.warning("Claude extraction failed, using regex fallback", error=str(e))
        return _regex_fallback(email_text)
