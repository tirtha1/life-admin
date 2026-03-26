"""
Gmail ingestion service.
Fetches unread emails, filters bill-related ones, returns raw content.
"""
import base64
import re
import structlog
from typing import Optional
from email import message_from_bytes
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import html2text

from app.core.config import get_settings

log = structlog.get_logger()
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Keywords that strongly suggest a bill/invoice email
BILL_KEYWORDS = [
    "bill", "invoice", "payment due", "amount due", "pay now", "statement",
    "receipt", "subscription", "renewal", "outstanding", "overdue",
    "electricity bill", "water bill", "gas bill", "internet bill",
    "credit card", "emi", "recharge", "due date", "minimum payment",
    "बिल", "भुगतान",  # Hindi
]

_h2t = html2text.HTML2Text()
_h2t.ignore_links = True
_h2t.ignore_images = True


def _build_gmail_service():
    """Build authenticated Gmail API service using stored refresh token."""
    if not settings.google_refresh_token:
        raise ValueError(
            "GOOGLE_REFRESH_TOKEN not set. Complete OAuth flow first via "
            "GET /api/ingestion/oauth/start"
        )

    creds = Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )

    # Auto-refresh if expired
    if not creds.valid:
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _is_bill_email(subject: str, body_preview: str) -> bool:
    """Quick keyword heuristic before sending to LLM."""
    text = (subject + " " + body_preview).lower()
    return any(kw in text for kw in BILL_KEYWORDS)


def _decode_part(part: dict) -> str:
    """Decode a single MIME part body."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        return decoded
    except Exception:
        return ""


def _extract_body(payload: dict) -> str:
    """Recursively extract text body from Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    if mime_type == "text/plain":
        return _decode_part(payload)
    elif mime_type == "text/html":
        html = _decode_part(payload)
        return _h2t.handle(html)
    elif parts:
        # Prefer plain text, fall back to html
        plain = next(
            (p for p in parts if p.get("mimeType") == "text/plain"), None
        )
        html = next(
            (p for p in parts if p.get("mimeType") == "text/html"), None
        )
        target = plain or html
        if target:
            text = _decode_part(target)
            if target.get("mimeType") == "text/html":
                text = _h2t.handle(text)
            return text
        # Try nested multipart
        for part in parts:
            text = _extract_body(part)
            if text:
                return text
    return ""


class EmailMessage:
    """Parsed email data ready for bill extraction."""

    def __init__(
        self,
        message_id: str,
        subject: str,
        sender: str,
        body: str,
        snippet: str,
    ):
        self.message_id = message_id
        self.subject = subject
        self.sender = sender
        self.body = body
        self.snippet = snippet

    def text_for_extraction(self) -> str:
        """Return a clean text block for Claude to process."""
        body_truncated = self.body[:4000]  # Keep context window sane
        return (
            f"Subject: {self.subject}\n"
            f"From: {self.sender}\n\n"
            f"{body_truncated}"
        )


async def fetch_bill_emails(
    max_results: int = 50,
    query: str = "is:unread",
    days_back: int = 30,
) -> list[EmailMessage]:
    """
    Fetch emails from Gmail that look like bills.

    Args:
        max_results: Maximum emails to scan
        query: Gmail search query
        days_back: Only look at emails this many days old

    Returns:
        List of EmailMessage objects that passed keyword filter
    """
    try:
        service = _build_gmail_service()
    except ValueError as e:
        log.warning("Gmail not configured", error=str(e))
        return []

    try:
        # Build search query
        full_query = f"{query} newer_than:{days_back}d"
        log.info("Fetching emails", query=full_query, max_results=max_results)

        result = (
            service.users()
            .messages()
            .list(userId="me", q=full_query, maxResults=max_results)
            .execute()
        )

        messages_meta = result.get("messages", [])
        log.info("Found emails", count=len(messages_meta))

        bill_emails: list[EmailMessage] = []

        for meta in messages_meta:
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=meta["id"], format="full")
                    .execute()
                )

                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }

                subject = headers.get("subject", "(no subject)")
                sender_raw = headers.get("from", "")
                _, sender_email = parseaddr(sender_raw)
                snippet = msg.get("snippet", "")

                # Quick keyword filter before full body parse
                if not _is_bill_email(subject, snippet):
                    continue

                body = _extract_body(msg.get("payload", {}))

                bill_emails.append(
                    EmailMessage(
                        message_id=meta["id"],
                        subject=subject,
                        sender=sender_email or sender_raw,
                        body=body,
                        snippet=snippet,
                    )
                )
                log.debug("Bill candidate found", subject=subject, sender=sender_email)

            except HttpError as e:
                log.error("Failed to fetch email", message_id=meta["id"], error=str(e))
                continue

        log.info("Bill candidates found", count=len(bill_emails))
        return bill_emails

    except HttpError as e:
        log.error("Gmail API error", error=str(e))
        return []


def get_oauth_url() -> str:
    """Generate Gmail OAuth2 authorization URL."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def exchange_oauth_code(code: str) -> str:
    """Exchange OAuth code for refresh token. Returns the refresh token."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )

    flow.fetch_token(code=code)
    return flow.credentials.refresh_token
