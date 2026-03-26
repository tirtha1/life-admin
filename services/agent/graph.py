"""
LangGraph decision graph for the Life Admin agent service.

Graph topology:
  assess_urgency → check_overpriced → decide_action → queue_action
                           ↑
                     (always runs)

Conditional edges:
  - After decide_action: if IGNORE → skip queue_action (no-op end)
"""
import structlog
from datetime import date
from typing import Optional

from langgraph.graph import StateGraph, END

from services.agent.state import AgentState
from services.agent.nodes.assess_urgency import assess_urgency
from services.agent.nodes.check_overpriced import check_overpriced
from services.agent.nodes.decide_action import decide_action
from services.agent.nodes.queue_action import queue_action

log = structlog.get_logger()


def _should_queue(state: AgentState) -> str:
    """
    Conditional edge: after decide_action.
    Route to queue_action unless decision is IGNORE.
    """
    decision = state.get("decision", "IGNORE")
    if decision == "IGNORE":
        log.debug("Decision IGNORE — skipping queue_action", bill_id=state["bill_id"])
        return "end"
    return "queue_action"


def build_graph() -> StateGraph:
    """Build and compile the LangGraph agent graph."""
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("assess_urgency", assess_urgency)
    graph.add_node("check_overpriced", check_overpriced)
    graph.add_node("decide_action", decide_action)
    graph.add_node("queue_action", queue_action)

    # Linear edges
    graph.add_edge("assess_urgency", "check_overpriced")
    graph.add_edge("check_overpriced", "decide_action")
    graph.add_edge("queue_action", END)

    # Conditional edge after decide_action
    graph.add_conditional_edges(
        "decide_action",
        _should_queue,
        {
            "queue_action": "queue_action",
            "end": END,
        },
    )

    # Entry point
    graph.set_entry_point("assess_urgency")

    return graph.compile()


# Singleton compiled graph
_compiled_graph = None


def get_graph():
    """Return the compiled graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_agent(
    bill_id: str,
    user_id: str,
    provider: str,
    bill_type: str,
    amount: Optional[float],
    currency: str,
    due_date: Optional[date],
    is_overdue: bool,
    is_recurring: bool,
    needs_review: bool,
    status: str,
) -> AgentState:
    """
    Run the full agent decision pipeline for a bill.

    Args:
        bill_id: Bill UUID
        user_id: User UUID
        provider: Bill provider name
        bill_type: Bill category
        amount: Amount due (may be None)
        currency: ISO currency code
        due_date: Payment due date (may be None)
        is_overdue: Whether the bill is overdue
        is_recurring: Whether this is a recurring bill
        needs_review: Whether extraction flagged for human review
        status: Current bill status

    Returns:
        Final AgentState after all nodes have run
    """
    initial_state: AgentState = {
        "bill_id": bill_id,
        "user_id": user_id,
        "provider": provider,
        "bill_type": bill_type,
        "amount": amount,
        "currency": currency,
        "due_date": due_date,
        "is_overdue": is_overdue,
        "is_recurring": is_recurring,
        "needs_review": needs_review,
        "status": status,
        # Computed — will be filled by nodes
        "due_in_days": None,
        "urgency_level": "none",
        "market_context": None,
        "pricing_verdict": "unknown",
        "decision": "IGNORE",
        "decision_reason": "",
        "action_type": None,
        "action_payload": {},
        "action_queued": False,
        "execution_notes": [],
        "errors": [],
    }

    log.info("Running agent graph", bill_id=bill_id, provider=provider)
    graph = get_graph()
    final_state = graph.invoke(initial_state)
    log.info(
        "Agent graph complete",
        bill_id=bill_id,
        decision=final_state.get("decision"),
        action_queued=final_state.get("action_queued"),
    )
    return final_state
