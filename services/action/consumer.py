"""
Action service Kafka consumer.
Consumes from life-admin.actions, executes notifications with idempotency guard.
"""
import asyncio
import structlog
from typing import Any

from shared.kafka.consumer import BaseConsumer
from shared.db.session import get_db_session_system
from shared.telemetry.decorators import traced

from services.action.idempotency import claim_action, complete_action
from services.action.handlers.email_reminder import send_email_reminder
from services.action.handlers.sms_reminder import send_sms_reminder, send_whatsapp_reminder
from services.action.handlers.optimize_suggest import send_optimize_suggestion

log = structlog.get_logger()

TOPIC_ACTIONS = "life-admin.actions"
GROUP_ID = "action-group"


class ActionConsumer(BaseConsumer):
    """Executes action events (email/SMS/WhatsApp/optimize)."""

    def __init__(self) -> None:
        super().__init__(
            topics=[TOPIC_ACTIONS],
            group_id=GROUP_ID,
        )

    @traced("action.handle_action")
    def handle_message(self, message_data: dict[str, Any]) -> None:
        asyncio.get_event_loop().run_until_complete(
            self._handle_async(message_data)
        )

    async def _handle_async(self, message_data: dict[str, Any]) -> None:
        idempotency_key = (
            f"agent:{message_data.get('bill_id')}:{message_data.get('decision')}"
        )
        action_type = message_data.get("action_type", "")
        payload = message_data.get("payload", {})

        async for session in get_db_session_system():
            claimed, action = await claim_action(session, idempotency_key)

            if not claimed:
                log.info(
                    "Action already processed or locked",
                    idempotency_key=idempotency_key,
                )
                await session.commit()
                return

            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self._execute_action, action_type, payload
                )
                await complete_action(session, action, success=True, result=result)
                await session.commit()
                log.info(
                    "Action executed",
                    action_type=action_type,
                    idempotency_key=idempotency_key,
                    result=result,
                )

            except Exception as exc:
                log.error(
                    "Action execution failed",
                    action_type=action_type,
                    idempotency_key=idempotency_key,
                    error=str(exc),
                    exc_info=True,
                )
                await complete_action(
                    session, action, success=False, error=str(exc)
                )
                await session.commit()
                raise  # Let BaseConsumer handle retry/DLQ

    def _execute_action(self, action_type: str, payload: dict) -> dict:
        """Dispatch to the correct notification handler."""
        to_email = payload.get("to_email", "")
        to_phone = payload.get("to_phone", "")
        user_name = payload.get("user_name")
        provider = payload.get("provider", "")
        bill_type = payload.get("bill_type", "other")
        amount = payload.get("amount")
        currency = payload.get("currency", "INR")
        due_date = payload.get("due_date")
        due_in_days = payload.get("due_in_days")
        account_number = payload.get("account_number")
        market_context = payload.get("market_context")
        is_recurring = payload.get("is_recurring", False)

        if action_type == "reminder_email":
            if not to_email:
                return {"skipped": True, "reason": "no_email"}
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
            )

        elif action_type == "reminder_sms":
            if not to_phone:
                return {"skipped": True, "reason": "no_phone"}
            return send_sms_reminder(
                to_phone=to_phone,
                provider=provider,
                amount=amount,
                currency=currency,
                due_date=due_date,
                due_in_days=due_in_days,
            )

        elif action_type == "reminder_whatsapp":
            if not to_phone:
                return {"skipped": True, "reason": "no_phone"}
            return send_whatsapp_reminder(
                to_phone=to_phone,
                provider=provider,
                amount=amount,
                currency=currency,
                due_date=due_date,
                due_in_days=due_in_days,
            )

        elif action_type == "optimize_suggestion":
            if not to_email:
                return {"skipped": True, "reason": "no_email"}
            return send_optimize_suggestion(
                to_email=to_email,
                user_name=user_name,
                provider=provider,
                bill_type=bill_type,
                amount=amount,
                currency=currency,
                due_date=due_date,
                due_in_days=due_in_days,
                account_number=account_number,
                market_context=market_context,
                is_recurring=is_recurring,
            )

        elif action_type == "payment_initiated":
            # Placeholder — actual payment integration is out of scope
            log.info(
                "Payment initiated (stub)",
                provider=provider,
                amount=amount,
            )
            return {"stub": True, "reason": "payment_integration_not_implemented"}

        else:
            log.warning("Unknown action_type", action_type=action_type)
            return {"skipped": True, "reason": f"unknown_action_type:{action_type}"}


def run() -> None:
    """Entry point: start the action consumer loop."""
    from shared.telemetry.setup import setup_telemetry
    setup_telemetry("action")

    log.info("Starting action consumer")
    consumer = ActionConsumer()
    consumer.run()
