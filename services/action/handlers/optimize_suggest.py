"""
Optimization suggestion handler.
Uses Claude to generate actionable cost-reduction suggestions for a bill.
Sends the suggestion via email.
"""
import os
import structlog
from typing import Optional

import anthropic

from services.action.handlers.email_reminder import send_email_reminder

log = structlog.get_logger()

ANTHROPIC_MODEL = "claude-opus-4-6"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _client


def generate_optimize_suggestion(
    provider: str,
    bill_type: str,
    amount: Optional[float],
    currency: str,
    market_context: Optional[str],
    is_recurring: bool,
) -> str:
    """
    Ask Claude for actionable cost-reduction advice specific to this bill.
    Returns a 1-3 sentence suggestion string.
    """
    client = _get_client()

    prompt = (
        f"A user has a {bill_type} bill from '{provider}' "
        f"for {currency} {amount:,.2f}. "
        f"{'This is a recurring monthly bill.' if is_recurring else ''} "
        f"{'Market context: ' + market_context if market_context else ''}\n\n"
        f"Give 1-3 concise, actionable suggestions to reduce this bill cost in India. "
        f"Be specific to the provider and bill type. No generic advice."
    )

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    suggestion = response.content[0].text.strip()
    log.info(
        "Optimization suggestion generated",
        provider=provider,
        bill_type=bill_type,
        suggestion_len=len(suggestion),
    )
    return suggestion


def send_optimize_suggestion(
    to_email: str,
    user_name: Optional[str],
    provider: str,
    bill_type: str,
    amount: Optional[float],
    currency: str,
    due_date: Optional[str],
    due_in_days: Optional[int],
    account_number: Optional[str],
    market_context: Optional[str],
    is_recurring: bool,
) -> dict:
    """
    Generate an optimization tip and send it in the reminder email.
    """
    optimize_tip = None
    try:
        if amount and amount > 0:
            optimize_tip = generate_optimize_suggestion(
                provider, bill_type, amount, currency, market_context, is_recurring
            )
    except Exception as exc:
        log.warning("Could not generate optimize tip", error=str(exc))

    return send_email_reminder(
        to_email=to_email,
        user_name=user_name,
        provider=provider,
        bill_type=bill_type,
        amount=amount,
        currency=currency,
        due_date=due_date,
        due_in_days=due_in_days,
        account_number=account_number,
        optimize_tip=optimize_tip,
    )
