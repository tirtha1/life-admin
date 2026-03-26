"""
Node: assess_urgency
Computes due_in_days and urgency_level from due_date.
"""
from datetime import date
import structlog

from services.agent.state import AgentState

log = structlog.get_logger()


def assess_urgency(state: AgentState) -> dict:
    """
    Compute urgency from due_date relative to today.

    urgency_level:
      critical  — overdue or due within 1 day
      high      — due in 2-3 days
      medium    — due in 4-7 days
      low       — due in 8-30 days
      none      — due > 30 days away or no due date
    """
    due_date = state.get("due_date")
    is_overdue = state.get("is_overdue", False)

    if due_date is None:
        log.debug(
            "No due date — urgency unknown",
            bill_id=state["bill_id"],
            provider=state["provider"],
        )
        return {
            "due_in_days": None,
            "urgency_level": "none",
            "execution_notes": ["No due date available — urgency set to none"],
        }

    today = date.today()
    due_in_days = (due_date - today).days

    if is_overdue or due_in_days < 0:
        level = "critical"
    elif due_in_days <= 1:
        level = "critical"
    elif due_in_days <= 3:
        level = "high"
    elif due_in_days <= 7:
        level = "medium"
    elif due_in_days <= 30:
        level = "low"
    else:
        level = "none"

    log.info(
        "Urgency assessed",
        bill_id=state["bill_id"],
        due_in_days=due_in_days,
        urgency_level=level,
        provider=state["provider"],
    )

    return {
        "due_in_days": due_in_days,
        "urgency_level": level,
        "execution_notes": [
            f"Due in {due_in_days} days — urgency: {level}"
        ],
    }
