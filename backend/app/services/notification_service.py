"""
Notification service — email reminders via SMTP.
WhatsApp / Telegram can be added as additional channels later.
"""
import smtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date

from app.core.config import get_settings
from app.models.bill import Bill

log = structlog.get_logger()
settings = get_settings()


def _build_reminder_email(bill: Bill) -> tuple[str, str]:
    """Build subject and HTML body for a bill reminder."""
    amount_str = f"₹{bill.amount:,.2f}" if bill.amount else "Amount unknown"
    due_str = bill.due_date.strftime("%B %d, %Y") if bill.due_date else "Unknown"

    days_left = None
    if bill.due_date:
        days_left = (bill.due_date - date.today()).days

    urgency = ""
    if days_left is not None:
        if days_left < 0:
            urgency = f'<p style="color:#dc2626;font-weight:bold;">⚠️ OVERDUE by {abs(days_left)} days!</p>'
        elif days_left == 0:
            urgency = '<p style="color:#dc2626;font-weight:bold;">⚠️ Due TODAY!</p>'
        elif days_left <= 2:
            urgency = f'<p style="color:#ea580c;font-weight:bold;">🔔 Due in {days_left} day(s)!</p>'
        else:
            urgency = f'<p style="color:#2563eb;">📅 Due in {days_left} days</p>'

    subject = f"[Life Admin] Bill Reminder: {bill.provider} — {amount_str}"

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f9fafb; padding: 20px; }}
    .card {{ background: white; border-radius: 12px; padding: 24px; max-width: 500px; margin: 0 auto; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .header {{ border-bottom: 2px solid #e5e7eb; padding-bottom: 16px; margin-bottom: 16px; }}
    .label {{ color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .value {{ color: #111827; font-size: 16px; font-weight: 600; margin-top: 2px; }}
    .amount {{ font-size: 32px; font-weight: 700; color: #1f2937; }}
    .footer {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h2 style="margin:0;color:#111827;">💳 Bill Reminder</h2>
      <p style="margin:4px 0 0;color:#6b7280;">Life Admin Autonomous System</p>
    </div>

    {urgency}

    <div style="margin: 16px 0;">
      <div class="label">Provider</div>
      <div class="value">{bill.provider}</div>
    </div>

    <div style="margin: 16px 0;">
      <div class="label">Bill Type</div>
      <div class="value">{bill.bill_type.value.replace('_', ' ').title()}</div>
    </div>

    <div style="margin: 16px 0;">
      <div class="label">Amount Due</div>
      <div class="amount">{amount_str}</div>
    </div>

    <div style="margin: 16px 0;">
      <div class="label">Due Date</div>
      <div class="value">{due_str}</div>
    </div>

    {"<div style='margin:16px 0;background:#fef3c7;border-radius:8px;padding:12px;'><strong>⚡ Optimization Tip:</strong> This bill appears higher than usual. Consider reviewing your plan.</div>" if bill.is_overpriced else ""}

    <div class="footer">
      This reminder was sent automatically by Life Admin.<br>
      View all bills at <a href="http://localhost:3000">your dashboard</a>.
    </div>
  </div>
</body>
</html>
"""
    return subject, html


async def send_bill_reminder(bill: Bill) -> bool:
    """
    Send an email reminder for a bill.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not settings.smtp_username or not settings.notification_email:
        log.warning("SMTP not configured, skipping notification")
        return False

    subject, html_body = _build_reminder_email(bill)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_username
        msg["To"] = settings.notification_email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(
                settings.smtp_username,
                settings.notification_email,
                msg.as_string(),
            )

        log.info(
            "Reminder sent",
            bill_id=bill.id,
            provider=bill.provider,
            to=settings.notification_email,
        )
        return True

    except smtplib.SMTPException as e:
        log.error("Failed to send reminder", bill_id=bill.id, error=str(e))
        return False
    except Exception as e:
        log.error("Unexpected error sending reminder", error=str(e))
        return False
