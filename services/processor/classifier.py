"""
Bill classifier — fast keyword + heuristic pre-filter before Claude extraction.
Avoids wasting LLM tokens on clearly non-bill emails.
"""
import re
import structlog

log = structlog.get_logger()

# Primary bill signals (subject / snippet match)
BILL_KEYWORDS = [
    "bill", "invoice", "payment due", "amount due", "pay now", "statement",
    "receipt", "subscription renewal", "outstanding balance", "overdue",
    "minimum due", "total due", "due date", "emi", "recharge",
    "auto-pay", "auto pay", "direct debit", "charge", "fee",
    # Hindi
    "बिल", "भुगतान", "राशि",
]

# Hard negative signals — these almost never contain actionable bills
NEGATIVE_KEYWORDS = [
    "unsubscribe from our marketing",
    "you have been removed",
    "password reset",
    "verify your email",
    "welcome to",
    "newsletter",
    "promotional offer",
    "sale ends",
    "limited time",
    "earn rewards",
    "refer a friend",
]

# Patterns that strongly indicate an amount/due-date is present
AMOUNT_PATTERN = re.compile(
    r"(?:₹|rs\.?|inr|usd|\$|€|£)\s*[\d,]+(?:\.\d{1,2})?",
    re.IGNORECASE,
)
DUE_DATE_PATTERN = re.compile(
    r"(?:due|pay by|due date|payment date)[:\s]+\w",
    re.IGNORECASE,
)


def is_bill_candidate(subject: str, snippet: str, body: str = "") -> bool:
    """
    Returns True if the email is likely a bill/invoice worth extracting.

    Applies a three-pass filter:
    1. Negative keyword veto (fast reject)
    2. Primary keyword match (subject + snippet)
    3. Amount/due-date pattern match in body (fallback)
    """
    combined = f"{subject} {snippet}".lower()

    # Pass 1: veto obvious non-bills
    for neg in NEGATIVE_KEYWORDS:
        if neg in combined:
            log.debug("Negative keyword veto", keyword=neg, subject=subject[:60])
            return False

    # Pass 2: primary keyword in subject/snippet
    for kw in BILL_KEYWORDS:
        if kw in combined:
            return True

    # Pass 3: body contains amount + due-date signals
    if body and AMOUNT_PATTERN.search(body) and DUE_DATE_PATTERN.search(body):
        return True

    return False


def classify_bill_type(subject: str, sender: str) -> str:
    """
    Heuristic pre-classification for extraction prompt context.
    Returns a bill_type hint string (not authoritative — LLM may override).
    """
    text = f"{subject} {sender}".lower()

    if any(kw in text for kw in ["electric", "electricity", "power", "energy"]):
        return "electricity"
    if any(kw in text for kw in ["water", "sewage", "municipal"]):
        return "water"
    if any(kw in text for kw in ["internet", "broadband", "wifi", "fiber"]):
        return "internet"
    if any(kw in text for kw in ["mobile", "phone", "postpaid", "prepaid", "telecom", "airtel", "jio", "vi ", "vodafone"]):
        return "mobile"
    if any(kw in text for kw in ["insurance", "premium", "policy"]):
        return "insurance"
    if any(kw in text for kw in ["credit card", "card statement", "hdfc", "icici", "sbi card", "axis"]):
        return "credit_card"
    if any(kw in text for kw in ["loan", "emi", "mortgage", "home loan", "personal loan"]):
        return "loan"
    if any(kw in text for kw in ["subscription", "netflix", "spotify", "amazon prime", "hotstar", "youtube"]):
        return "subscription"
    if any(kw in text for kw in ["rent", "lease", "landlord"]):
        return "rent"
    if any(kw in text for kw in ["gas", "lpg", "cylinder", "petroleum"]):
        return "gas"

    return "other"
