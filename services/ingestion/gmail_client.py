"""
Gmail API client with OAuth2 refresh, incremental polling via historyId,
exponential backoff, and keyword pre-filter.
"""
import base64
import structlog
from email.utils import parseaddr
from dataclasses import dataclass
from typing import Optional

import html2text
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    RetryError,
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
)

log = structlog.get_logger()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

TRANSACTION_KEYWORDS = [
    "debited", "credited", "upi", "transaction", "payment", "spent",
    "transferred", "withdrawn", "deposited", "refund", "cashback",
    "bank alert", "account alert", "neft", "imps", "rtgs",
    "डेबिट", "क्रेडिट",
]

TRANSACTION_SENDERS = [
    "axisbank", "hdfcbank", "icicibank", "sbi", "kotakbank", "yesbank",
    "paytm", "phonepe", "gpay", "googlepay", "amazonpay",
    "alerts", "notify",
]

BILL_KEYWORDS = [
    "bill", "invoice", "payment due", "amount due", "pay now", "statement",
    "receipt", "subscription renewal", "outstanding balance", "overdue",
    "minimum due", "total due", "due date", "emi", "recharge",
    "बिल", "भुगतान",  # Hindi
]

_h2t = html2text.HTML2Text()
_h2t.ignore_links = True
_h2t.ignore_images = True


@dataclass
class ParsedEmail:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    received_at: Optional[str]
    body_text: str
    snippet: str

    def combined_text(self) -> str:
        """Return text for LLM extraction (truncated to 3000 chars)."""
        body = bleach_clean(self.body_text)[:2800]
        return f"Subject: {self.subject}\nFrom: {self.sender}\n\n{body}"


def bleach_clean(text: str) -> str:
    """Strip any residual HTML tags from extracted body text."""
    try:
        import bleach
        return bleach.clean(text, tags=[], strip=True)
    except ImportError:
        import re
        return re.sub(r"<[^>]+>", " ", text)


def _is_bill_email(subject: str, snippet: str) -> bool:
    combined = (subject + " " + snippet).lower()
    return any(kw in combined for kw in BILL_KEYWORDS)


def _is_transaction_email(subject: str, snippet: str, sender: str) -> bool:
    combined = (subject + " " + snippet).lower()
    keyword_match = any(kw in combined for kw in TRANSACTION_KEYWORDS)
    sender_match = any(s in sender.lower() for s in TRANSACTION_SENDERS)
    return keyword_match or sender_match


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    if mime == "text/plain":
        return _decode_part(payload)
    if mime == "text/html":
        return _h2t.handle(_decode_part(payload))

    for part in parts:
        if part.get("mimeType") == "text/plain":
            return _decode_part(part)

    for part in parts:
        if part.get("mimeType") == "text/html":
            return _h2t.handle(_decode_part(part))

    for part in parts:
        text = _extract_body(part)
        if text:
            return text

    return ""


def _is_retryable_http_error(exc: Exception) -> bool:
    if not isinstance(exc, HttpError):
        return False
    status = getattr(exc.resp, "status", None)
    return status in {408, 429, 500, 502, 503, 504}


def describe_gmail_exception(exc: Exception) -> str:
    if isinstance(exc, RetryError):
        last_exc = exc.last_attempt.exception()
        if last_exc is not None:
            return describe_gmail_exception(last_exc)
        return "Gmail request failed after retries."

    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", "unknown")
        details = str(exc)
        error_details = getattr(exc, "error_details", None)
        if isinstance(error_details, list) and error_details:
            first_detail = error_details[0]
            if isinstance(first_detail, dict):
                details = first_detail.get("message") or first_detail.get("reason") or details
        return f"Gmail API error ({status}): {details}"

    return str(exc)


def _build_transaction_query(days_back: int) -> str:
    # Gmail search accepts braces as OR groups and handles this more reliably than nested parentheses.
    terms = [
        "subject:debited",
        "subject:credited",
        'subject:"UPI"',
        "subject:transaction",
        "subject:payment",
        "subject:alert",
        "from:alerts",
        "from:notify",
        "from:axisbank",
        "from:hdfcbank",
        "from:icicibank",
        "from:sbi",
        "from:kotakbank",
        "from:yesbank",
        "from:paytm",
        "from:phonepe",
        "from:gpay",
        "from:googlepay",
        "from:amazonpay",
    ]
    return f"newer_than:{days_back}d " + "{" + " ".join(terms) + "}"


class GmailClient:
    """
    Gmail API wrapper.
    - Auto-refreshes access token using stored refresh token
    - Uses historyId for incremental fetching (not full re-scan)
    - Keyword pre-filter before returning emails
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ):
        self._creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        self._service = None

    def _get_service(self):
        if not self._creds.valid:
            log.info("Refreshing Gmail access token")
            self._creds.refresh(Request())
        if self._service is None:
            self._service = build("gmail", "v1", credentials=self._creds, cache_discovery=False)
        return self._service

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30),
        retry=retry_if_exception(_is_retryable_http_error),
    )
    def fetch_recent_emails(
        self,
        max_results: int = 50,
        query: str = "is:unread",
        days_back: int = 30,
    ) -> list[ParsedEmail]:
        """
        Fetch unread emails, pre-filter by bill keywords.
        Returns list of ParsedEmail objects.
        """
        service = self._get_service()
        full_query = f"{query} newer_than:{days_back}d"

        log.info("Fetching Gmail", query=full_query, max_results=max_results)
        result = (
            service.users()
            .messages()
            .list(userId="me", q=full_query, maxResults=max_results)
            .execute()
        )

        messages_meta = result.get("messages", [])
        log.info("Emails found", count=len(messages_meta))

        parsed: list[ParsedEmail] = []
        for meta in messages_meta:
            try:
                email = self._fetch_and_parse(service, meta["id"])
                if email and _is_bill_email(email.subject, email.snippet):
                    parsed.append(email)
                    log.debug("Bill candidate", subject=email.subject, sender=email.sender)
            except HttpError as e:
                log.error("Failed to fetch message", message_id=meta["id"], error=str(e))
                continue

        log.info("Bill emails found", count=len(parsed))
        return parsed

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30),
        retry=retry_if_exception(_is_retryable_http_error),
    )
    def fetch_transaction_emails(
        self,
        max_results: int = 100,
        days_back: int = 30,
    ) -> list[ParsedEmail]:
        """
        Fetch bank / UPI / payment alert emails.
        Uses targeted Gmail search and transaction keyword pre-filter.
        """
        service = self._get_service()
        query = _build_transaction_query(days_back)

        log.info("Fetching transaction emails", query=query, max_results=max_results)
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages_meta = result.get("messages", [])
        log.info("Transaction email candidates", count=len(messages_meta))

        parsed: list[ParsedEmail] = []
        for meta in messages_meta:
            try:
                email = self._fetch_and_parse(service, meta["id"])
                if email and _is_transaction_email(email.subject, email.snippet, email.sender):
                    parsed.append(email)
                    log.debug("Transaction candidate", subject=email.subject, sender=email.sender)
            except HttpError as e:
                log.error("Failed to fetch transaction message", message_id=meta["id"], error=str(e))
                continue

        log.info("Transaction emails after filter", count=len(parsed))
        return parsed

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception(_is_retryable_http_error),
    )
    def _fetch_and_parse(self, service, message_id: str) -> Optional[ParsedEmail]:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        subject = headers.get("subject", "(no subject)")
        sender_raw = headers.get("from", "")
        _, sender = parseaddr(sender_raw)
        date_str = headers.get("date", "")
        snippet = msg.get("snippet", "")
        body = _extract_body(msg.get("payload", {}))

        return ParsedEmail(
            message_id=message_id,
            thread_id=msg.get("threadId", ""),
            subject=subject,
            sender=sender or sender_raw,
            received_at=date_str or None,
            body_text=body,
            snippet=snippet,
        )
