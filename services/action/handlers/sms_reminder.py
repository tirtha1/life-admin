"""
SMS and WhatsApp reminder handler via Twilio.
"""
import os
import structlog
from typing import Optional

log = structlog.get_logger()

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
TWILIO_WHATSAPP_FROM = os.environ.get(
    "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"
)  # Twilio sandbox default


def _get_twilio_client():
    from twilio.rest import Client
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _build_sms_body(
    provider: str,
    amount: Optional[float],
    currency: str,
    due_date: Optional[str],
    due_in_days: Optional[int],
) -> str:
    amount_str = f"{currency} {amount:,.2f}" if amount else "amount unknown"
    urgency = ""
    if due_in_days is not None:
        if due_in_days < 0:
            urgency = f" ({-due_in_days}d OVERDUE)"
        elif due_in_days == 0:
            urgency = " (DUE TODAY)"
        elif due_in_days <= 3:
            urgency = f" (in {due_in_days}d)"

    due_str = f" due {due_date}{urgency}" if due_date else ""
    return f"LifeAdmin: {provider} bill of {amount_str}{due_str}. Pay on time to avoid penalties."


def send_sms_reminder(
    to_phone: str,
    provider: str,
    amount: Optional[float],
    currency: str,
    due_date: Optional[str],
    due_in_days: Optional[int],
) -> dict:
    """Send SMS reminder via Twilio."""
    if not TWILIO_ACCOUNT_SID:
        log.warning("Twilio not configured — SMS skipped", to=to_phone)
        return {"success": False, "reason": "twilio_not_configured"}

    body = _build_sms_body(provider, amount, currency, due_date, due_in_days)
    client = _get_twilio_client()
    message = client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=to_phone,
    )
    log.info("SMS sent", to=to_phone, sid=message.sid, provider=provider)
    return {"success": True, "to": to_phone, "sid": message.sid, "method": "sms"}


def send_whatsapp_reminder(
    to_phone: str,
    provider: str,
    amount: Optional[float],
    currency: str,
    due_date: Optional[str],
    due_in_days: Optional[int],
) -> dict:
    """Send WhatsApp reminder via Twilio."""
    if not TWILIO_ACCOUNT_SID:
        log.warning("Twilio not configured — WhatsApp skipped", to=to_phone)
        return {"success": False, "reason": "twilio_not_configured"}

    body = _build_sms_body(provider, amount, currency, due_date, due_in_days)
    # WhatsApp requires "whatsapp:+NNNNNNN" format
    whatsapp_to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

    client = _get_twilio_client()
    message = client.messages.create(
        body=body,
        from_=TWILIO_WHATSAPP_FROM,
        to=whatsapp_to,
    )
    log.info("WhatsApp sent", to=to_phone, sid=message.sid, provider=provider)
    return {"success": True, "to": to_phone, "sid": message.sid, "method": "whatsapp"}
