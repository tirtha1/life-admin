"""
Life Admin Bill Agent — built with LangGraph.

Flow:
  load_bill → check_urgency → analyze_pricing → decide_action → execute_action → END

Each node reads/writes BillState. Conditional edges route
based on the state after each node.
"""
import structlog
from datetime import date
from typing import Optional, TypedDict, Annotated
from operator import add

from langgraph.graph import StateGraph, END

from app.core.config import get_settings
from app.models.bill import Bill, BillStatus, AgentAction
from app.services.notification_service import send_bill_reminder

log = structlog.get_logger()
settings = get_settings()


# ─── State ────────────────────────────────────────────────────────────────────

class BillState(TypedDict):
    # Input
    bill_id: int
    provider: str
    amount: Optional[float]
    due_date: Optional[date]
    bill_type: str
    status: str
    is_overpriced: bool

    # Computed during run
    due_in_days: Optional[int]
    urgency_level: str          # "critical" | "urgent" | "normal" | "no_date"
    pricing_verdict: str        # "overpriced" | "normal" | "unknown"

    # Decision
    action: str                 # AgentAction value
    action_reason: str

    # Execution results
    notification_sent: bool
    execution_notes: Annotated[list[str], add]
    error: Optional[str]


# ─── Nodes ────────────────────────────────────────────────────────────────────

def load_bill_context(state: BillState) -> BillState:
    """Enrich state with computed context."""
    log.debug("Agent: loading context", bill_id=state["bill_id"])

    due_date = state.get("due_date")
    if due_date:
        due_in_days = (due_date - date.today()).days
        state["due_in_days"] = due_in_days
    else:
        state["due_in_days"] = None

    state["execution_notes"] = [f"Processing bill from {state['provider']}"]
    state["error"] = None
    return state


def check_urgency(state: BillState) -> BillState:
    """Classify urgency based on due date."""
    due_in_days = state.get("due_in_days")

    if due_in_days is None:
        state["urgency_level"] = "no_date"
        state["execution_notes"] = [f"No due date found — scheduling reminder"]
    elif due_in_days < 0:
        state["urgency_level"] = "critical"
        state["execution_notes"] = [f"OVERDUE by {abs(due_in_days)} day(s)!"]
    elif due_in_days <= settings.urgent_days_threshold:
        state["urgency_level"] = "urgent"
        state["execution_notes"] = [f"Due in {due_in_days} day(s) — URGENT"]
    else:
        state["urgency_level"] = "normal"
        state["execution_notes"] = [f"Due in {due_in_days} days"]

    log.debug(
        "Agent: urgency checked",
        bill_id=state["bill_id"],
        level=state["urgency_level"],
        due_in_days=due_in_days,
    )
    return state


def analyze_pricing(state: BillState) -> BillState:
    """
    Check if the bill amount seems overpriced.
    Phase 1: simple threshold check.
    Phase 2 (TODO): compare to historical average for this provider.
    """
    amount = state.get("amount")

    if amount is None:
        state["pricing_verdict"] = "unknown"
        state["execution_notes"] = ["Amount not extracted — cannot check pricing"]
    elif state["is_overpriced"] or amount > settings.overpriced_threshold:
        state["pricing_verdict"] = "overpriced"
        state["is_overpriced"] = True
        state["execution_notes"] = [
            f"Amount ₹{amount:,.2f} exceeds threshold ₹{settings.overpriced_threshold:,.2f}"
        ]
    else:
        state["pricing_verdict"] = "normal"
        state["execution_notes"] = [f"Amount ₹{amount:,.2f} is within normal range"]

    log.debug(
        "Agent: pricing analyzed",
        bill_id=state["bill_id"],
        verdict=state["pricing_verdict"],
    )
    return state


def decide_action(state: BillState) -> BillState:
    """
    Core decision logic.

    Critical/Overdue  → PAY_NOW
    Urgent            → PAY_NOW
    Overpriced        → OPTIMIZE
    Normal            → REMIND
    No date           → REMIND
    Already paid      → IGNORE
    """
    # Already handled
    if state.get("status") in ("paid", "ignored"):
        state["action"] = AgentAction.IGNORE.value
        state["action_reason"] = f"Bill already {state['status']}"
        return state

    urgency = state["urgency_level"]
    pricing = state["pricing_verdict"]

    if urgency in ("critical", "urgent"):
        action = AgentAction.PAY_NOW.value
        reason = f"Payment urgent — {urgency} priority"
    elif pricing == "overpriced":
        action = AgentAction.OPTIMIZE.value
        reason = "Bill exceeds normal threshold — flagged for review"
    elif urgency == "normal":
        action = AgentAction.REMIND.value
        reason = f"Due in {state['due_in_days']} days — sending reminder"
    else:
        action = AgentAction.REMIND.value
        reason = "No due date — sending general reminder"

    state["action"] = action
    state["action_reason"] = reason
    state["execution_notes"] = [f"Decision: {action} — {reason}"]

    log.info(
        "Agent: decision made",
        bill_id=state["bill_id"],
        action=action,
        reason=reason,
    )
    return state


async def execute_action(state: BillState) -> BillState:
    """Execute the chosen action — send notifications, log, etc."""
    action = state["action"]
    state["notification_sent"] = False

    log.info("Agent: executing action", bill_id=state["bill_id"], action=action)

    if action == AgentAction.IGNORE.value:
        state["execution_notes"] = ["No action taken"]
        return state

    # For PAY_NOW, REMIND, OPTIMIZE — all send a notification
    # (Future: PAY_NOW could trigger autopay, OPTIMIZE could call comparison API)

    # We need the full Bill object for the notification service.
    # Since this graph runs outside DB session context, we import lazily.
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.bill import Bill

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Bill).where(Bill.id == state["bill_id"])
            )
            bill = result.scalar_one_or_none()

            if bill:
                sent = await send_bill_reminder(bill)
                state["notification_sent"] = sent

                # Update bill in DB
                bill.agent_action = AgentAction(action)
                bill.notification_sent = sent
                bill.agent_notes = state["action_reason"]

                if state["urgency_level"] == "critical":
                    bill.status = BillStatus.OVERDUE
                elif action == AgentAction.REMIND.value:
                    bill.status = BillStatus.REMINDED
                elif action == AgentAction.OPTIMIZE.value:
                    bill.status = BillStatus.OPTIMIZING

                bill.is_overpriced = state["is_overpriced"]
                await session.commit()

                note = "Notification sent" if sent else "Notification failed (check SMTP config)"
                state["execution_notes"] = [note]
            else:
                state["error"] = f"Bill {state['bill_id']} not found in DB"

    except Exception as e:
        log.error("Agent: execution error", error=str(e), bill_id=state["bill_id"])
        state["error"] = str(e)
        state["execution_notes"] = [f"Execution error: {str(e)[:100]}"]

    return state


# ─── Conditional Edges ────────────────────────────────────────────────────────

def should_skip(state: BillState) -> str:
    """Skip processing if bill is already handled."""
    if state.get("status") in ("paid", "ignored"):
        return "skip"
    return "continue"


# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_bill_agent() -> StateGraph:
    graph = StateGraph(BillState)

    # Add nodes
    graph.add_node("load_bill_context", load_bill_context)
    graph.add_node("check_urgency", check_urgency)
    graph.add_node("analyze_pricing", analyze_pricing)
    graph.add_node("decide_action", decide_action)
    graph.add_node("execute_action", execute_action)

    # Entry point
    graph.set_entry_point("load_bill_context")

    # Conditional: skip paid/ignored bills
    graph.add_conditional_edges(
        "load_bill_context",
        should_skip,
        {
            "skip": "decide_action",   # Jump straight to IGNORE decision
            "continue": "check_urgency",
        },
    )

    # Linear flow
    graph.add_edge("check_urgency", "analyze_pricing")
    graph.add_edge("analyze_pricing", "decide_action")
    graph.add_edge("decide_action", "execute_action")
    graph.add_edge("execute_action", END)

    return graph.compile()


# Singleton compiled agent
_agent = None


def get_bill_agent():
    global _agent
    if _agent is None:
        _agent = build_bill_agent()
    return _agent


async def run_bill_agent(bill: Bill) -> BillState:
    """
    Run the bill agent for a single bill.

    Args:
        bill: SQLAlchemy Bill model instance

    Returns:
        Final BillState after agent run
    """
    agent = get_bill_agent()

    initial_state = BillState(
        bill_id=bill.id,
        provider=bill.provider,
        amount=bill.amount,
        due_date=bill.due_date,
        bill_type=bill.bill_type.value,
        status=bill.status.value,
        is_overpriced=bill.is_overpriced,
        due_in_days=None,
        urgency_level="",
        pricing_verdict="",
        action=AgentAction.NONE.value,
        action_reason="",
        notification_sent=False,
        execution_notes=[],
        error=None,
    )

    log.info("Running bill agent", bill_id=bill.id, provider=bill.provider)
    final_state = await agent.ainvoke(initial_state)
    log.info(
        "Bill agent complete",
        bill_id=bill.id,
        action=final_state["action"],
        notification_sent=final_state["notification_sent"],
    )
    return final_state
