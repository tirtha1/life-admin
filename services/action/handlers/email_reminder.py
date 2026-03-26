"""
Email reminder handler — sends bill reminders via SendGrid.
Falls back to SMTP if SendGrid key is not set (dev mode).
"""
import os
import smtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

log = structlog.get_logger()

# Template directory
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@lifeadmin.app")
FROM_NAME = os.environ.get("FROM_NAME", "LifeAdmin")
APP_URL = os.environ.get("APP_URL", "http://localhost:5173")

# Jinja2 environment
_jinja_env: Environment | None = None


def _get_jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


def _render_html(context: dict) -> str:
    env = _get_jinja()
    template = env.get_template("bill_reminder.html")
    return template.render(**context)


def send_email_reminder(
    to_email: str,
    user_name: Optional[str],
    provider: str,
    bill_type: str,
    amount: Optional[float],
    currency: str,
    due_date: Optional[str],
    due_in_days: Optional[int],
    account_number: Optional[str] = None,
    optimize_tip: Optional[str] = None,
) -> dict:
    """
    Send a bill reminder email.

    Returns:
        dict with keys: success (bool), provider (str), to (str), method (str)

    Raises:
        Exception on delivery failure (caller handles retry/DLQ)
    """
    context = {
        "user_name": user_name,
        "provider": provider,
        "bill_type": bill_type,
        "amount": amount,
        "currency": currency,
        "due_date": due_date,
        "due_in_days": due_in_days,
        "account_number": account_number,
        "optimize_tip": optimize_tip,
        "app_url": APP_URL,
        "unsubscribe_url": f"{APP_URL}/unsubscribe",
    }
    html_body = _render_html(context)
    subject = f"Payment Reminder: {provider} bill due {due_date or 'soon'}"

    if SENDGRID_API_KEY:
        return _send_via_sendgrid(to_email, subject, html_body)
    else:
        return _send_via_smtp(to_email, subject, html_body)


def _send_via_sendgrid(to_email: str, subject: str, html_body: str) -> dict:
    """Send via SendGrid API."""
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content

    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    mail = Mail(
        from_email=Email(FROM_EMAIL, FROM_NAME),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content("text/html", html_body),
    )
    response = sg.client.mail.send.post(request_body=mail.get())

    if response.status_code not in (200, 202):
        raise RuntimeError(
            f"SendGrid error {response.status_code}: {response.body}"
        )

    log.info("Email sent via SendGrid", to=to_email, subject=subject[:60])
    return {"success": True, "to": to_email, "method": "sendgrid"}


def _send_via_smtp(to_email: str, subject: str, html_body: str) -> dict:
    """Send via SMTP (dev/fallback)."""
    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "1025"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_user:
            server.login(smtp_user, smtp_pass)
        server.sendmail(FROM_EMAIL, [to_email], msg.as_string())

    log.info("Email sent via SMTP", to=to_email, host=smtp_host)
    return {"success": True, "to": to_email, "method": "smtp"}
