"""
Agent service Kafka consumer.
Consumes from life-admin.bills.extracted, runs the LangGraph decision graph.
"""
import asyncio
import structlog
from datetime import date
from typing import Any

from shared.kafka.consumer import BaseConsumer
from shared.telemetry.decorators import traced

from services.agent.graph import run_agent

log = structlog.get_logger()

TOPIC_BILLS_EXTRACTED = "life-admin.bills.extracted"
GROUP_ID = "agent-group"


class AgentConsumer(BaseConsumer):
    """Consumes extracted bill events and runs the decision agent."""

    def __init__(self) -> None:
        super().__init__(
            topics=[TOPIC_BILLS_EXTRACTED],
            group_id=GROUP_ID,
        )

    @traced("agent.handle_bill")
    def handle_message(self, message_data: dict[str, Any]) -> None:
        """
        Process a bill-extracted event through the LangGraph decision pipeline.
        """
        bill_id = message_data.get("bill_id", "")
        user_id = message_data.get("user_id", "")
        provider = message_data.get("provider", "")
        bill_type = message_data.get("bill_type", "other")
        amount = message_data.get("amount")
        currency = message_data.get("currency", "INR")
        status = message_data.get("status", "extracted")
        needs_review = message_data.get("needs_review", False)
        is_overdue = message_data.get("is_overdue", False)
        is_recurring = message_data.get("is_recurring", False)

        # Parse due_date
        due_date = None
        due_date_str = message_data.get("due_date")
        if due_date_str:
            try:
                due_date = date.fromisoformat(due_date_str)
            except ValueError:
                log.warning(
                    "Invalid due_date format",
                    bill_id=bill_id,
                    due_date=due_date_str,
                )

        log.info(
            "Running agent for bill",
            bill_id=bill_id,
            user_id=user_id,
            provider=provider,
        )

        try:
            final_state = run_agent(
                bill_id=bill_id,
                user_id=user_id,
                provider=provider,
                bill_type=bill_type,
                amount=float(amount) if amount is not None else None,
                currency=currency,
                due_date=due_date,
                is_overdue=is_overdue,
                is_recurring=is_recurring,
                needs_review=needs_review,
                status=status,
            )
            log.info(
                "Agent complete",
                bill_id=bill_id,
                decision=final_state.get("decision"),
                action_queued=final_state.get("action_queued"),
                notes=final_state.get("execution_notes"),
            )
        except Exception as exc:
            log.error(
                "Agent graph failed",
                bill_id=bill_id,
                error=str(exc),
                exc_info=True,
            )
            raise  # Let BaseConsumer handle retry/DLQ


def run() -> None:
    """Entry point: start the agent consumer loop."""
    from shared.telemetry.setup import setup_telemetry
    setup_telemetry("agent")

    log.info("Starting agent consumer")
    consumer = AgentConsumer()
    consumer.run()
