"""
LangGraph agent state definition.
AgentState is the TypedDict that flows through all graph nodes.
"""
from typing import Annotated, Optional
from datetime import date

from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


def _append(existing: list, new: list) -> list:
    """Reducer that appends new items to existing list."""
    return existing + new


class AgentState(TypedDict):
    # Input fields — set at graph entry
    bill_id: str
    user_id: str
    provider: str
    bill_type: str
    amount: Optional[float]
    currency: str
    due_date: Optional[date]
    is_overdue: bool
    is_recurring: bool
    needs_review: bool
    status: str

    # Computed fields — filled by assess_urgency node
    due_in_days: Optional[int]
    urgency_level: str  # "critical" | "high" | "medium" | "low" | "none"

    # Computed fields — filled by check_overpriced node
    market_context: Optional[str]
    pricing_verdict: str  # "overpriced" | "fair" | "unknown"

    # Decision fields — filled by decide_action node
    decision: str  # "PAY_NOW" | "REMIND" | "OPTIMIZE" | "IGNORE" | "ESCALATE"
    decision_reason: str

    # Action fields — filled by execute_* nodes
    action_type: Optional[str]  # Maps to ActionType enum in DB
    action_payload: dict
    action_queued: bool

    # Audit trail — accumulated across nodes
    execution_notes: Annotated[list[str], _append]
    errors: Annotated[list[str], _append]
