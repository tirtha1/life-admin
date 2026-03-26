"""
Node: queue_action
Publishes the decided action to Kafka life-admin.actions topic.
Also updates the bill status in DB.
"""
import asyncio
import structlog

from shared.kafka.producer import BaseProducer
from shared.db.session import get_db_session_system
from shared.db.models import Bill, BillStatus, BillTransition, Action, ActionType, ActionStatus

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent.state import AgentState

log = structlog.get_logger()

TOPIC_ACTIONS = "life-admin.actions"

_publisher: BaseProducer | None = None


def _get_publisher() -> BaseProducer:
    global _publisher
    if _publisher is None:
        _publisher = BaseProducer()
    return _publisher


def _decision_to_bill_status(decision: str) -> BillStatus:
    return {
        "PAY_NOW": BillStatus.CONFIRMED,
        "REMIND": BillStatus.CONFIRMED,
        "OPTIMIZE": BillStatus.CONFIRMED,
        "ESCALATE": BillStatus.REVIEW_REQUIRED,
        "IGNORE": BillStatus.CONFIRMED,
    }.get(decision, BillStatus.CONFIRMED)


async def _update_bill_and_queue(state: AgentState) -> dict:
    decision = state.get("decision", "IGNORE")
    action_type = state.get("action_type")
    bill_id = state["bill_id"]
    user_id = state["user_id"]

    async for session in get_db_session_system():
        try:
            # Load bill
            result = await session.execute(
                select(Bill).where(Bill.id == bill_id)
            )
            bill = result.scalar_one_or_none()
            if not bill:
                log.error("Bill not found", bill_id=bill_id)
                return {
                    "action_queued": False,
                    "errors": [f"Bill {bill_id} not found in DB"],
                }

            old_status = bill.status
            new_status = _decision_to_bill_status(decision)

            # Update bill status
            bill.status = new_status
            bill.needs_review = decision == "ESCALATE"

            # Write state transition
            if old_status != new_status:
                transition = BillTransition(
                    bill_id=bill.id,
                    from_status=old_status,
                    to_status=new_status,
                    reason=state.get("decision_reason", "")[:500],
                    actor="agent",
                )
                session.add(transition)

            # Create Action record if we have an action_type
            if action_type and decision not in ("IGNORE", "ESCALATE"):
                import uuid as uuid_mod
                idempotency_key = f"agent:{bill_id}:{decision}"

                # Check for existing action (idempotency)
                existing = await session.execute(
                    select(Action).where(Action.idempotency_key == idempotency_key)
                )
                if not existing.scalar_one_or_none():
                    action = Action(
                        user_id=user_id,
                        bill_id=bill.id,
                        action_type=ActionType(action_type),
                        status=ActionStatus.PENDING,
                        idempotency_key=idempotency_key,
                        payload={
                            "provider": state.get("provider"),
                            "amount": state.get("amount"),
                            "currency": state.get("currency"),
                            "due_date": state.get("due_date").isoformat() if state.get("due_date") else None,
                            "urgency_level": state.get("urgency_level"),
                            "pricing_verdict": state.get("pricing_verdict"),
                            "decision_reason": state.get("decision_reason"),
                            "market_context": state.get("market_context"),
                        },
                    )
                    session.add(action)
                    await session.flush()
                    action_id = str(action.id)
                else:
                    action_id = str(existing.scalar_one().id)

                # Publish to Kafka
                publisher = _get_publisher()
                publisher.publish(
                    topic=TOPIC_ACTIONS,
                    key=f"{user_id}:{bill_id}",
                    data={
                        "user_id": user_id,
                        "bill_id": bill_id,
                        "action_id": action_id,
                        "action_type": action_type,
                        "decision": decision,
                        "payload": action.payload,
                    },
                )
                publisher.flush()
                log.info(
                    "Action queued",
                    bill_id=bill_id,
                    action_type=action_type,
                    decision=decision,
                )

            await session.commit()
            return {
                "action_queued": action_type is not None and decision not in ("IGNORE", "ESCALATE"),
                "execution_notes": [
                    f"Bill status updated: {old_status.value} → {new_status.value}",
                    f"Action queued: {action_type or 'none'}",
                ],
            }

        except Exception as exc:
            await session.rollback()
            log.error(
                "queue_action failed",
                bill_id=bill_id,
                error=str(exc),
                exc_info=True,
            )
            return {
                "action_queued": False,
                "errors": [str(exc)],
            }


def queue_action(state: AgentState) -> dict:
    """Publish action to Kafka and update bill status in DB."""
    return asyncio.get_event_loop().run_until_complete(_update_bill_and_queue(state))
