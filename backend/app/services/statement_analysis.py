"""
Bank statement parsing and spending leak analysis.
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from app.core.config import get_settings
from app.models.transaction import TransactionCategory
from app.schemas.statement import (
    StatementAction,
    StatementAnalysisResponse,
    StatementLeakInsight,
    StatementRecurringPayment,
    StatementSummary,
    StatementTransaction,
)

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency
    pd = None

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None


log = structlog.get_logger()
settings = get_settings()

DATE_PATTERN = r"\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{2,4}|\d{2}[-/][A-Za-z]{3}[-/]\d{2,4}"
AMOUNT_TOKEN_PATTERN = re.compile(
    r"[+-]?(?:INR|Rs\.?|USD|\$|EUR|GBP|AED|SGD|₹)?\s*\(?[0-9,]+(?:\.\d{1,2})?\)?",
    re.IGNORECASE,
)
MAX_REASONABLE_STATEMENT_AMOUNT = 100_000_000.0
BALANCE_HINT_PATTERN = re.compile(r"\b(?:bal|balance|closing|available|ledger|closing balance)\b", re.IGNORECASE)
AMOUNT_HINT_PATTERN = re.compile(
    r"\b(?:amt|amount|debit|credit|withdrawal|deposit|dr|cr|spent|paid|received)\b",
    re.IGNORECASE,
)

DATE_KEYS = (
    "date",
    "txn_date",
    "transaction_date",
    "posting_date",
    "posted_date",
    "value_date",
)
DESCRIPTION_KEYS = (
    "description",
    "narration",
    "details",
    "remarks",
    "remark",
    "particulars",
    "merchant",
    "transaction_details",
    "transaction_description",
)
AMOUNT_KEYS = (
    "amount",
    "transaction_amount",
    "txn_amount",
    "withdrawal_deposit",
    "value",
)
DEBIT_KEYS = (
    "debit",
    "debit_amount",
    "withdrawal",
    "withdrawal_amt",
    "money_out",
    "paid_out",
)
CREDIT_KEYS = (
    "credit",
    "credit_amount",
    "deposit",
    "deposit_amt",
    "money_in",
    "paid_in",
)
TYPE_KEYS = (
    "type",
    "dr_cr",
    "drcr",
    "cr_dr",
    "transaction_type",
)

CATEGORY_KEYWORDS: dict[TransactionCategory, tuple[str, ...]] = {
    TransactionCategory.SUBSCRIPTIONS: (
        "netflix",
        "spotify",
        "youtube premium",
        "amazon prime",
        "prime video",
        "adobe",
        "chatgpt",
        "icloud",
        "apple services",
        "hotstar",
        "jiosaavn",
        "gaana",
        "zee5",
    ),
    TransactionCategory.FOOD: (
        "swiggy",
        "zomato",
        "dominos",
        "pizza hut",
        "mcdonald",
        "kfc",
        "starbucks",
        "blinkit",
        "zepto",
        "bigbasket",
        "instamart",
        "restaurant",
        "cafe",
        "eatfit",
    ),
    TransactionCategory.TRANSPORT: (
        "uber",
        "ola",
        "rapido",
        "fuel",
        "petrol",
        "diesel",
        "metro",
        "irctc",
        "parking",
        "fastag",
    ),
    TransactionCategory.SHOPPING: (
        "amazon",
        "flipkart",
        "myntra",
        "ajio",
        "nykaa",
        "meesho",
        "croma",
        "reliance digital",
        "ikea",
    ),
    TransactionCategory.ENTERTAINMENT: (
        "pvr",
        "bookmyshow",
        "inox",
        "gaming",
        "steam",
        "playstation",
    ),
    TransactionCategory.UTILITIES: (
        "electricity",
        "water",
        "gas",
        "broadband",
        "wifi",
        "internet",
        "airtel",
        "jio",
        "bsnl",
        "dth",
        "recharge",
    ),
    TransactionCategory.HEALTHCARE: (
        "apollo",
        "pharmeasy",
        "1mg",
        "netmeds",
        "hospital",
        "clinic",
        "pharmacy",
    ),
    TransactionCategory.EDUCATION: (
        "udemy",
        "coursera",
        "unacademy",
        "byju",
        "school",
        "college",
        "tuition",
    ),
    TransactionCategory.TRAVEL: (
        "makemytrip",
        "airbnb",
        "oyo",
        "flight",
        "hotel",
        "booking.com",
        "indigo",
        "vistara",
        "air india",
    ),
}

CANONICAL_MERCHANTS = {
    "amazon prime": "Amazon Prime",
    "prime video": "Prime Video",
    "amazon": "Amazon",
    "swiggy": "Swiggy",
    "zomato": "Zomato",
    "uber": "Uber",
    "ola": "Ola",
    "rapido": "Rapido",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "youtube premium": "YouTube Premium",
    "apple services": "Apple Services",
    "icloud": "iCloud",
    "adobe": "Adobe",
    "chatgpt": "ChatGPT",
    "airtel": "Airtel",
    "jio": "Jio",
    "blinkit": "Blinkit",
    "zepto": "Zepto",
    "bigbasket": "BigBasket",
    "myntra": "Myntra",
    "flipkart": "Flipkart",
    "nykaa": "Nykaa",
    "bookmyshow": "BookMyShow",
    "pvr": "PVR",
}

KNOWN_SUBSCRIPTION_MERCHANTS = {
    "Amazon Prime",
    "Prime Video",
    "Netflix",
    "Spotify",
    "YouTube Premium",
    "Apple Services",
    "iCloud",
    "Adobe",
    "ChatGPT",
    "Hotstar",
    "JioSaavn",
    "Gaana",
    "Zee5",
}

DEBIT_HINTS = (
    "debit",
    "debited",
    "purchase",
    "spent",
    "paid",
    "payment",
    "dr",
    "upi",
    "pos",
    "ecs",
)
CREDIT_HINTS = (
    "credit",
    "credited",
    "salary",
    "refund",
    "cashback",
    "interest",
    "deposit",
    "received",
    "cr",
)
EMBEDDED_CREDIT_PATTERN = re.compile(
    r"(?:^|[\s/_-])(?:neft|rtgs|imps|upi|ach|ecs)\s*cr\b|(?:neft|rtgs|imps|upi|ach|ecs)cr\b",
    re.IGNORECASE,
)
EMBEDDED_DEBIT_PATTERN = re.compile(
    r"(?:^|[\s/_-])(?:neft|rtgs|imps|upi|ach|ecs)\s*dr\b|(?:neft|rtgs|imps|upi|ach|ecs)dr\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedStatementTransaction:
    date: date
    description: str
    amount: float
    signed_amount: float
    type: str
    merchant: Optional[str]
    category: TransactionCategory


async def analyze_statement_file(filename: str, content: bytes) -> StatementAnalysisResponse:
    file_type = Path(filename or "statement").suffix.lower().lstrip(".")
    transactions, parser_used, warnings = _parse_statement_file(filename, content)
    transactions = _dedupe_transactions(transactions)

    if not transactions:
        raise ValueError(
            "No transactions could be extracted. Check that the file has statement rows with dates and amounts."
        )

    transactions.sort(key=lambda txn: (txn.date, txn.description))
    recurring = _detect_recurring_payments(transactions)
    leak_insights, suggested_actions = _build_leaks_and_actions(transactions, recurring)
    summary = _build_summary(transactions, recurring, suggested_actions)
    assistant_summary = _build_fallback_summary(summary, recurring, leak_insights)
    llm_summary = await _generate_llm_summary(summary, recurring, leak_insights, suggested_actions)

    llm_enhanced = llm_summary is not None
    if llm_summary:
        assistant_summary = llm_summary

    return StatementAnalysisResponse(
        file_name=filename or "statement",
        file_type=file_type if file_type in {"csv", "pdf"} else "csv",
        parser_used=parser_used,
        llm_enhanced=llm_enhanced,
        assistant_summary=assistant_summary,
        warnings=warnings,
        summary=summary,
        recurring_payments=recurring,
        leak_insights=leak_insights,
        suggested_actions=suggested_actions,
        transactions=[
            StatementTransaction(
                date=txn.date,
                description=txn.description,
                amount=txn.amount,
                signed_amount=txn.signed_amount,
                type=txn.type,
                merchant=txn.merchant,
                category=txn.category,
            )
            for txn in transactions
        ],
    )


def _parse_statement_file(
    filename: str,
    content: bytes,
) -> tuple[list[ParsedStatementTransaction], str, list[str]]:
    suffix = Path(filename or "statement").suffix.lower()
    warnings: list[str] = []

    if suffix == ".csv":
        transactions, parser_used = _parse_csv_statement(content)
        return transactions, parser_used, warnings

    if suffix == ".pdf":
        transactions, parser_used, pdf_warnings = _parse_pdf_statement(content)
        warnings.extend(pdf_warnings)
        return transactions, parser_used, warnings

    raise ValueError("Unsupported file type. Upload a PDF or CSV bank statement.")


def _parse_csv_statement(content: bytes) -> tuple[list[ParsedStatementTransaction], str]:
    text = _decode_bytes(content)

    if pd is not None:
        try:
            frame = pd.read_csv(io.StringIO(text))
            rows = frame.fillna("").to_dict(orient="records")
            return _rows_to_transactions(rows), "pandas"
        except Exception as exc:
            log.warning("pandas csv parse failed, falling back to csv module", error=str(exc))

    sample = text[:4096]
    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        pass

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = [dict(row) for row in reader]
    return _rows_to_transactions(rows), "csv"


def _parse_pdf_statement(
    content: bytes,
) -> tuple[list[ParsedStatementTransaction], str, list[str]]:
    warnings: list[str] = []
    text = ""
    parser_used = "pdf-text-fallback"

    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(page for page in pages if page.strip())
            parser_used = "pdfplumber"
        except Exception as exc:
            warnings.append("pdfplumber could not read this PDF cleanly, so the fallback parser was used.")
            log.warning("pdfplumber parse failed, falling back", error=str(exc))

    if not text.strip():
        text = _extract_pdf_text_fallback(content)
        if not text.strip():
            warnings.append("The PDF looked image-based or encrypted. A CSV export will parse more reliably.")

    transactions = _parse_text_statement(text)
    return transactions, parser_used, warnings


def _rows_to_transactions(rows: list[dict[str, Any]]) -> list[ParsedStatementTransaction]:
    transactions: list[ParsedStatementTransaction] = []

    for row in rows:
        normalized = {
            _normalize_header(str(key)): value
            for key, value in row.items()
            if key is not None
        }

        raw_date = _first_value(normalized, DATE_KEYS)
        raw_description = _first_value(normalized, DESCRIPTION_KEYS)
        raw_type = _first_value(normalized, TYPE_KEYS)
        signed_amount = _extract_signed_amount(normalized, raw_description, raw_type)

        txn_date = _parse_date(raw_date)
        description = _clean_description(raw_description)

        if txn_date is None or not description or signed_amount is None:
            continue

        category = _categorize_transaction(description)
        merchant = _extract_merchant(description)
        transactions.append(
            ParsedStatementTransaction(
                date=txn_date,
                description=description,
                amount=round(abs(signed_amount), 2),
                signed_amount=round(signed_amount, 2),
                type="credit" if signed_amount > 0 else "debit",
                merchant=merchant,
                category=category,
            )
        )

    return transactions


def _parse_text_statement(text: str) -> list[ParsedStatementTransaction]:
    transactions: list[ParsedStatementTransaction] = []
    lines = _prepare_statement_lines(text)

    for line in lines:
        parsed = _parse_transaction_line(line)
        if parsed is not None:
            transactions.append(parsed)

    return transactions


def _prepare_statement_lines(text: str) -> list[str]:
    cleaned_lines = []
    current = ""

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.replace("\x00", " ")).strip()
        if not line or len(line) < 8:
            continue
        if re.search(DATE_PATTERN, line):
            if current:
                cleaned_lines.append(current)
            current = line
        elif current:
            current = f"{current} {line}".strip()
        else:
            cleaned_lines.append(line)

    if current:
        cleaned_lines.append(current)

    return cleaned_lines


def _parse_transaction_line(line: str) -> Optional[ParsedStatementTransaction]:
    match = re.search(DATE_PATTERN, line)
    if match is None:
        return None

    txn_date = _parse_date(match.group(0))
    if txn_date is None:
        return None

    after_date = line[match.end():].strip(" |:-")
    if not after_date:
        return None

    marker_match = re.search(
        r"(?P<amount>[0-9,]+(?:\.\d{1,2})?)\s+(?P<marker>DR|CR|DEBIT|CREDIT)\b",
        after_date,
        flags=re.IGNORECASE,
    )
    if marker_match:
        description = after_date[:marker_match.start()].strip(" |-")
        signed_amount = _parse_amount(marker_match.group("amount"))
        if signed_amount is None:
            return None
        signed_amount = abs(signed_amount) if _is_credit_text(marker_match.group("marker")) else -abs(signed_amount)
    else:
        amount_tokens = list(AMOUNT_TOKEN_PATTERN.finditer(after_date))
        if not amount_tokens:
            return None
        selected_candidate = _select_best_amount_candidate(after_date, amount_tokens)
        if selected_candidate is None:
            return None
        description, signed_amount = selected_candidate

        signed_amount = abs(signed_amount) if _infer_transaction_type(after_date) == "credit" else -abs(signed_amount)

    description = _clean_description(description)
    if not description:
        return None

    category = _categorize_transaction(description)
    merchant = _extract_merchant(description)
    return ParsedStatementTransaction(
        date=txn_date,
        description=description,
        amount=round(abs(signed_amount), 2),
        signed_amount=round(signed_amount, 2),
        type="credit" if signed_amount > 0 else "debit",
        merchant=merchant,
        category=category,
    )


def _extract_pdf_text_fallback(content: bytes) -> str:
    chunks: list[str] = []

    printable_chunks = re.findall(rb"[A-Za-z0-9/.,:()\- ]{8,}", content)
    chunks.extend(chunk.decode("latin-1", errors="ignore") for chunk in printable_chunks)

    for stream_match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content, flags=re.DOTALL):
        stream = stream_match.group(1).strip()
        candidates = [stream]
        try:
            candidates.append(zlib.decompress(stream))
        except Exception:
            pass

        for candidate in candidates:
            decoded = candidate.decode("latin-1", errors="ignore")
            literal_strings = re.findall(r"\(([^()]*)\)", decoded)
            if literal_strings:
                chunks.extend(literal_strings)
            chunks.append(decoded)

    text = "\n".join(chunks)
    return re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", text)


def _dedupe_transactions(
    transactions: list[ParsedStatementTransaction],
) -> list[ParsedStatementTransaction]:
    deduped: list[ParsedStatementTransaction] = []
    seen: set[tuple[date, str, float, str]] = set()

    for txn in transactions:
        key = (
            txn.date,
            (txn.merchant or txn.description).lower(),
            txn.signed_amount,
            txn.type,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(txn)

    return deduped


def _select_best_amount_candidate(
    line_after_date: str,
    amount_tokens: list[re.Match[str]],
) -> Optional[tuple[str, float]]:
    candidates: list[tuple[int, str, float]] = []

    for amount_match in amount_tokens:
        token = amount_match.group(0)
        candidate_amount = _parse_amount(token)
        candidate_description = _clean_description(line_after_date[:amount_match.start()].strip(" |-"))
        if candidate_amount is None or not candidate_description:
            continue

        integer_digits = re.sub(r"\D", "", token.split(".", 1)[0])
        before = line_after_date[max(0, amount_match.start() - 24):amount_match.start()]
        after = line_after_date[amount_match.end():amount_match.end() + 24]
        score = 0

        if "." in token:
            score += 6
        if re.search(r"(?:INR|Rs\.?|₹|\$|EUR|GBP|AED|SGD)", token, flags=re.IGNORECASE):
            score += 4
        if AMOUNT_HINT_PATTERN.search(before) or AMOUNT_HINT_PATTERN.search(after):
            score += 4
        if BALANCE_HINT_PATTERN.search(before) or BALANCE_HINT_PATTERN.search(after):
            score -= 8
        if len(integer_digits) >= 6 and "." not in token:
            score -= 4
        if token.count(",") >= 3 and "." not in token:
            score -= 4

        candidates.append((score, candidate_description, candidate_amount))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def _detect_recurring_payments(
    transactions: list[ParsedStatementTransaction],
) -> list[StatementRecurringPayment]:
    grouped: dict[str, list[ParsedStatementTransaction]] = defaultdict(list)
    recurring: list[StatementRecurringPayment] = []

    for txn in transactions:
        if txn.type != "debit":
            continue
        key = (txn.merchant or txn.description).lower()
        grouped[key].append(txn)

    for merchant_txns in grouped.values():
        merchant_txns.sort(key=lambda txn: txn.date)
        merchant_name = merchant_txns[0].merchant or merchant_txns[0].description
        amount_values = [txn.amount for txn in merchant_txns]
        average_amount = statistics.fmean(amount_values)
        last_seen = merchant_txns[-1].date
        intervals = [
            (merchant_txns[idx].date - merchant_txns[idx - 1].date).days
            for idx in range(1, len(merchant_txns))
        ]
        monthly_like = any(21 <= interval <= 40 for interval in intervals)
        amount_stable = all(
            abs(value - average_amount) <= max(50.0, average_amount * 0.15)
            for value in amount_values
        )
        is_known_subscription = merchant_name in KNOWN_SUBSCRIPTION_MERCHANTS

        if len(merchant_txns) >= 2 and monthly_like and amount_stable:
            recurring.append(
                StatementRecurringPayment(
                    merchant=merchant_name,
                    category=merchant_txns[0].category,
                    monthly_estimate=round(average_amount, 2),
                    occurrences=len(merchant_txns),
                    cadence="monthly",
                    confidence=0.92,
                    last_seen=last_seen,
                    reason=f"{merchant_name} appears {len(merchant_txns)} times with similar amounts.",
                )
            )
        elif is_known_subscription:
            cadence = "likely monthly" if len(merchant_txns) == 1 else "monthly"
            confidence = 0.72 if len(merchant_txns) == 1 else 0.86
            recurring.append(
                StatementRecurringPayment(
                    merchant=merchant_name,
                    category=TransactionCategory.SUBSCRIPTIONS,
                    monthly_estimate=round(average_amount, 2),
                    occurrences=len(merchant_txns),
                    cadence=cadence,
                    confidence=confidence,
                    last_seen=last_seen,
                    reason=f"{merchant_name} matches a common subscription merchant.",
                )
            )

    recurring.sort(key=lambda item: item.monthly_estimate, reverse=True)
    return recurring[:8]


def _build_leaks_and_actions(
    transactions: list[ParsedStatementTransaction],
    recurring: list[StatementRecurringPayment],
) -> tuple[list[StatementLeakInsight], list[StatementAction]]:
    debit_transactions = [txn for txn in transactions if txn.type == "debit"]
    total_spent = sum(txn.amount for txn in debit_transactions)
    by_category: dict[TransactionCategory, list[ParsedStatementTransaction]] = defaultdict(list)
    by_merchant: dict[str, list[ParsedStatementTransaction]] = defaultdict(list)

    for txn in debit_transactions:
        by_category[txn.category].append(txn)
        by_merchant[txn.merchant or txn.description].append(txn)

    leak_insights: list[StatementLeakInsight] = []
    actions: list[StatementAction] = []
    action_keys: set[tuple[str, Optional[str], Optional[TransactionCategory]]] = set()

    for recurring_payment in recurring:
        if recurring_payment.category not in {
            TransactionCategory.SUBSCRIPTIONS,
            TransactionCategory.ENTERTAINMENT,
        }:
            continue

        severity = "high" if recurring_payment.monthly_estimate >= 500 else "medium"
        leak_insights.append(
            StatementLeakInsight(
                title=f"{recurring_payment.merchant} looks like a recurring charge",
                severity=severity,
                amount=recurring_payment.monthly_estimate,
                merchant=recurring_payment.merchant,
                category=recurring_payment.category,
                rationale=(
                    f"{recurring_payment.merchant} is showing up as {recurring_payment.cadence} "
                    f"at about INR {recurring_payment.monthly_estimate:,.0f}."
                ),
                suggested_action="Pause or cancel it if it is no longer worth the monthly cost.",
            )
        )
        _append_action(
            actions,
            action_keys,
            StatementAction(
                title=f"Review {recurring_payment.merchant}",
                priority=severity,
                action_type="cancel_subscription",
                description=(
                    f"Check whether {recurring_payment.merchant} is still useful. "
                    f"If not, cancel or pause it to save INR {recurring_payment.monthly_estimate:,.0f} each month."
                ),
                estimated_monthly_savings=round(recurring_payment.monthly_estimate, 2),
                merchant=recurring_payment.merchant,
                category=recurring_payment.category,
            ),
        )

    food_total = sum(txn.amount for txn in by_category.get(TransactionCategory.FOOD, []))
    food_orders = len(by_category.get(TransactionCategory.FOOD, []))
    if total_spent > 0 and food_total >= max(3000.0, total_spent * 0.18):
        target_budget = _round_to_nearest_100(max(2000.0, food_total * 0.7))
        monthly_savings = max(0.0, food_total - target_budget)
        share = round(food_total / total_spent * 100)
        leak_insights.append(
            StatementLeakInsight(
                title="Food delivery is taking a large share of spend",
                severity="high" if food_total >= max(5000.0, total_spent * 0.25) else "medium",
                amount=round(food_total, 2),
                category=TransactionCategory.FOOD,
                rationale=(
                    f"Food-related transactions total INR {food_total:,.0f} across {food_orders} purchases, "
                    f"about {share}% of outflows in this statement."
                ),
                suggested_action=f"Set a monthly food budget near INR {target_budget:,.0f}.",
            )
        )
        _append_action(
            actions,
            action_keys,
            StatementAction(
                title="Cap food delivery spend",
                priority="high" if share >= 25 else "medium",
                action_type="set_budget",
                description=(
                    f"Set a food budget around INR {target_budget:,.0f} and shift some orders to planned groceries or home meals."
                ),
                estimated_monthly_savings=round(monthly_savings, 2),
                category=TransactionCategory.FOOD,
            ),
        )

    for merchant, merchant_txns in by_merchant.items():
        merchant_total = sum(txn.amount for txn in merchant_txns)
        merchant_count = len(merchant_txns)
        merchant_category = merchant_txns[0].category
        if merchant_category == TransactionCategory.FOOD and merchant_count >= 4 and merchant_total >= 1500:
            leak_insights.append(
                StatementLeakInsight(
                    title=f"{merchant} is a frequent spend merchant",
                    severity="medium",
                    amount=round(merchant_total, 2),
                    merchant=merchant,
                    category=merchant_category,
                    rationale=(
                        f"{merchant} appears {merchant_count} times in this statement for a combined INR {merchant_total:,.0f}."
                    ),
                    suggested_action="Add a weekly order cap or move repeat orders into a fixed budget bucket.",
                )
            )
            _append_action(
                actions,
                action_keys,
                StatementAction(
                    title=f"Put a weekly cap on {merchant}",
                    priority="medium",
                    action_type="set_budget",
                    description=(
                        f"{merchant} drove repeated spend. A weekly cap can reduce autopilot ordering without fully cutting it out."
                    ),
                    estimated_monthly_savings=round(min(merchant_total * 0.2, 1000.0), 2),
                    merchant=merchant,
                    category=merchant_category,
                ),
            )

    shopping_total = sum(txn.amount for txn in by_category.get(TransactionCategory.SHOPPING, []))
    if total_spent > 0 and shopping_total >= max(4000.0, total_spent * 0.2):
        target_budget = _round_to_nearest_100(max(2500.0, shopping_total * 0.75))
        monthly_savings = max(0.0, shopping_total - target_budget)
        leak_insights.append(
            StatementLeakInsight(
                title="Shopping spend spiked",
                severity="medium",
                amount=round(shopping_total, 2),
                category=TransactionCategory.SHOPPING,
                rationale=(
                    f"Shopping transactions reached INR {shopping_total:,.0f}, which is elevated versus the rest of the statement."
                ),
                suggested_action=f"Use a shopping budget near INR {target_budget:,.0f} and delay non-urgent purchases by 24 hours.",
            )
        )
        _append_action(
            actions,
            action_keys,
            StatementAction(
                title="Tighten shopping budget",
                priority="medium",
                action_type="set_budget",
                description=(
                    f"Move shopping into a capped budget of about INR {target_budget:,.0f} and review impulse purchases once a week."
                ),
                estimated_monthly_savings=round(monthly_savings, 2),
                category=TransactionCategory.SHOPPING,
            ),
        )

    largest_debit = max(debit_transactions, key=lambda txn: txn.amount, default=None)
    average_debit = statistics.fmean(txn.amount for txn in debit_transactions) if debit_transactions else 0.0
    if (
        largest_debit is not None
        and average_debit > 0
        and largest_debit.amount >= max(2000.0, average_debit * 2.5)
    ):
        leak_insights.append(
            StatementLeakInsight(
                title=f"One {largest_debit.category.value} transaction was unusually large",
                severity="medium",
                amount=round(largest_debit.amount, 2),
                merchant=largest_debit.merchant,
                category=largest_debit.category,
                rationale=(
                    f"{largest_debit.merchant or largest_debit.description} at INR {largest_debit.amount:,.0f} is much larger than the typical debit in this file."
                ),
                suggested_action="Review whether this was planned, one-off, or worth splitting into installments.",
            )
        )
        _append_action(
            actions,
            action_keys,
            StatementAction(
                title="Review the largest debit",
                priority="medium",
                action_type="review_spike",
                description=(
                    f"Revisit the INR {largest_debit.amount:,.0f} spend for {largest_debit.merchant or largest_debit.description} and confirm it was intentional."
                ),
                estimated_monthly_savings=0.0,
                merchant=largest_debit.merchant,
                category=largest_debit.category,
            ),
        )

    leak_insights.sort(key=lambda insight: (_severity_rank(insight.severity), insight.amount), reverse=True)
    actions.sort(key=lambda action: (_severity_rank(action.priority), action.estimated_monthly_savings), reverse=True)
    return leak_insights[:8], actions[:8]


def _append_action(
    actions: list[StatementAction],
    action_keys: set[tuple[str, Optional[str], Optional[TransactionCategory]]],
    action: StatementAction,
) -> None:
    key = (action.title.lower(), action.merchant, action.category)
    if key not in action_keys:
        action_keys.add(key)
        actions.append(action)


def _build_summary(
    transactions: list[ParsedStatementTransaction],
    recurring: list[StatementRecurringPayment],
    actions: list[StatementAction],
) -> StatementSummary:
    debit_transactions = [txn for txn in transactions if txn.type == "debit"]
    credit_transactions = [txn for txn in transactions if txn.type == "credit"]
    total_spent = sum(txn.amount for txn in debit_transactions)
    total_income = sum(txn.amount for txn in credit_transactions)
    net_cashflow = total_income - total_spent
    period_start = min(txn.date for txn in transactions)
    period_end = max(txn.date for txn in transactions)
    top_category = None

    if debit_transactions:
        category_totals: Counter[TransactionCategory] = Counter()
        for txn in debit_transactions:
            category_totals[txn.category] += txn.amount
        top_category = category_totals.most_common(1)[0][0]

    return StatementSummary(
        period_start=period_start,
        period_end=period_end,
        transaction_count=len(transactions),
        total_spent=round(total_spent, 2),
        total_income=round(total_income, 2),
        net_cashflow=round(net_cashflow, 2),
        recurring_spend=round(sum(item.monthly_estimate for item in recurring), 2),
        potential_monthly_savings=round(sum(item.estimated_monthly_savings for item in actions), 2),
        top_category=top_category,
    )


def _build_fallback_summary(
    summary: StatementSummary,
    recurring: list[StatementRecurringPayment],
    leak_insights: list[StatementLeakInsight],
) -> str:
    parts = [
        (
            f"This statement covers {summary.period_start.isoformat()} to {summary.period_end.isoformat()} "
            f"with INR {summary.total_spent:,.0f} of outflow across {summary.transaction_count} transactions."
        )
    ]
    if summary.top_category is not None:
        parts.append(f"The biggest spend area was {summary.top_category.value}.")
    if recurring:
        top_recurring = recurring[0]
        parts.append(
            f"The clearest recurring charge is {top_recurring.merchant} at roughly INR {top_recurring.monthly_estimate:,.0f}."
        )
    if leak_insights:
        parts.append(f"Top opportunity: {leak_insights[0].suggested_action}")
    return " ".join(parts)


async def _generate_llm_summary(
    summary: StatementSummary,
    recurring: list[StatementRecurringPayment],
    leak_insights: list[StatementLeakInsight],
    actions: list[StatementAction],
) -> Optional[str]:
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:  # pragma: no cover - depends on runtime environment
        return None

    payload = {
        "summary": summary.model_dump(mode="json"),
        "recurring_payments": [item.model_dump(mode="json") for item in recurring[:4]],
        "leak_insights": [item.model_dump(mode="json") for item in leak_insights[:4]],
        "suggested_actions": [item.model_dump(mode="json") for item in actions[:4]],
    }

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=220,
            system=(
                "You are a careful personal finance assistant. "
                "Write a short paragraph that highlights savings opportunities. "
                "Use INR, stay practical, and do not claim a subscription is unused because usage data is unavailable. "
                "Return JSON: {\"assistant_summary\": \"...\"}."
            ),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=True),
                }
            ],
        )
        content = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        data = json.loads(content[start:end] if start != -1 else content)
        assistant_summary = data.get("assistant_summary")
        if assistant_summary:
            return str(assistant_summary).strip()
    except Exception as exc:  # pragma: no cover - network and API dependent
        log.warning("statement llm summary failed", error=str(exc))

    return None


def _extract_signed_amount(
    row: dict[str, Any],
    raw_description: Optional[str],
    raw_type: Optional[str],
) -> Optional[float]:
    debit_amount = _parse_amount(_first_value(row, DEBIT_KEYS))
    credit_amount = _parse_amount(_first_value(row, CREDIT_KEYS))

    if debit_amount not in (None, 0.0):
        return -abs(debit_amount)
    if credit_amount not in (None, 0.0):
        return abs(credit_amount)

    amount = _parse_amount(_first_value(row, AMOUNT_KEYS))
    if amount is None:
        return None
    if amount < 0:
        return amount

    inferred = _infer_transaction_type(" ".join(filter(None, [raw_type, raw_description])))
    return abs(amount) if inferred == "credit" else -abs(amount)


def _first_value(row: dict[str, Any], candidates: tuple[str, ...]) -> Optional[str]:
    for candidate in candidates:
        value = row.get(candidate)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            return text
    return None


def _parse_amount(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    negative = False
    lowered = text.lower()
    if "(" in text and ")" in text:
        negative = True
    if text.startswith("-"):
        negative = True
    if re.search(r"\b(?:debit|debited|purchase|spent|paid|payment|dr|upi|pos|ecs)\b", lowered):
        negative = True

    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in {"", "-", "."}:
        return None

    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) >= 11 and "." not in text:
        return None

    try:
        amount = float(cleaned)
    except ValueError:
        return None

    if abs(amount) > MAX_REASONABLE_STATEMENT_AMOUNT:
        return None

    if amount < 0:
        return amount
    return -amount if negative else amount


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%d/%b/%Y",
        "%d-%b-%y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        from dateutil import parser as date_parser

        return date_parser.parse(text, dayfirst=True).date()
    except Exception:
        return None


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _decode_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _clean_description(value: Optional[str]) -> str:
    if value is None:
        return ""

    text = str(value)
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    text = re.sub(
        r"\b(?:upi|imps|neft|rtgs|pos|ecs|txn|ref|reference|vpa|utr)\b[: ]*[\w/-]*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def _categorize_transaction(description: str) -> TransactionCategory:
    lowered = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return TransactionCategory.OTHER


def _extract_merchant(description: str) -> Optional[str]:
    lowered = description.lower()
    for keyword, merchant in CANONICAL_MERCHANTS.items():
        if keyword in lowered:
            return merchant

    cleaned = re.sub(r"[^A-Za-z ]+", " ", description)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None

    words = [word for word in cleaned.split() if len(word) > 1][:3]
    if not words:
        return None
    return " ".join(word.capitalize() for word in words)


def _infer_transaction_type(value: str) -> str:
    lowered = value.lower()
    if EMBEDDED_CREDIT_PATTERN.search(lowered):
        return "credit"
    if EMBEDDED_DEBIT_PATTERN.search(lowered):
        return "debit"
    if re.search(r"\b(?:credited|salary|refund|cashback|interest|deposit|received|cr)\b", lowered):
        return "credit"
    if re.search(r"\b(?:debit|debited|purchase|spent|paid|payment|dr|upi|pos|ecs)\b", lowered):
        return "debit"
    return "debit"


def _is_credit_text(value: str) -> bool:
    lowered = value.lower()
    return EMBEDDED_CREDIT_PATTERN.search(lowered) is not None or re.search(
        r"\b(?:credited|salary|refund|cashback|interest|deposit|received|cr)\b",
        lowered,
    ) is not None


def _round_to_nearest_100(value: float) -> float:
    return round(value / 100.0) * 100.0


def _severity_rank(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value, 0)
