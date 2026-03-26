"""
Node: decide_action
Core decision logic: PAY_NOW | REMIND | OPTIMIZE | IGNORE | ESCALATE
"""
import structlog

from services.agent.state import AgentState

log = structlog.get_logger()


def decide_action(state: AgentState) -> dict:
    """
    Determine the best action for this bill based on urgency, pricing, and review status.

    Decision matrix:
    ┌──────────────────────────┬──────────────────────────────┐
    │ Condition                │ Decision                     │
    ├──────────────────────────┼──────────────────────────────┤
    │ needs_review = True      │ ESCALATE (human review)      │
    │ urgency=critical AND     │ PAY_NOW                      │
    │   pricing=fair/unknown   │                              │
    │ urgency=critical AND     │ OPTIMIZE (then pay)          │
    │   pricing=overpriced     │                              │
    │ urgency=high/medium      │ REMIND                       │
    │ urgency=low AND          │ OPTIMIZE                     │
    │   pricing=overpriced     │                              │
    │ urgency=low/none AND     │ REMIND (low priority)        │
    │   pricing=fair           │                              │
    │ urgency=none AND         │ IGNORE                       │
    │   no amount              │                              │
    └──────────────────────────┴──────────────────────────────┘
    """
    urgency = state.get("urgency_level", "none")
    pricing = state.get("pricing_verdict", "unknown")
    needs_review = state.get("needs_review", False)
    amount = state.get("amount")
    is_overdue = state.get("is_overdue", False)

    # Rule 1: Human review required
    if needs_review:
        decision = "ESCALATE"
        reason = "Bill flagged for human review (low extraction confidence or high value)"

    # Rule 2: Critical urgency
    elif urgency == "critical":
        if pricing == "overpriced":
            decision = "OPTIMIZE"
            reason = (
                f"Bill is overdue/critical but appears overpriced — "
                f"suggest optimization before payment"
            )
        else:
            decision = "PAY_NOW"
            reason = f"Critical urgency ({state.get('due_in_days')} days) — immediate action required"

    # Rule 3: High urgency
    elif urgency == "high":
        decision = "REMIND"
        reason = f"High urgency — due in {state.get('due_in_days')} days, send reminder now"

    # Rule 4: Medium urgency
    elif urgency == "medium":
        decision = "REMIND"
        reason = f"Medium urgency — due in {state.get('due_in_days')} days, schedule reminder"

    # Rule 5: Low urgency + overpriced
    elif urgency == "low" and pricing == "overpriced":
        decision = "OPTIMIZE"
        reason = "Low urgency but bill appears overpriced — good time to explore alternatives"

    # Rule 6: Low urgency + fair/unknown pricing
    elif urgency == "low":
        decision = "REMIND"
        reason = f"Low urgency — due in {state.get('due_in_days')} days, schedule reminder"

    # Rule 7: No urgency, no amount — probably informational
    elif urgency == "none" and amount is None:
        decision = "IGNORE"
        reason = "No due date or amount found — likely an informational email"

    # Rule 8: No urgency but has amount
    elif urgency == "none":
        if pricing == "overpriced":
            decision = "OPTIMIZE"
            reason = "No imminent due date but bill appears overpriced"
        else:
            decision = "IGNORE"
            reason = "No due date within 30 days — monitoring only"

    else:
        decision = "IGNORE"
        reason = "No matching decision rule — defaulting to ignore"

    log.info(
        "Decision made",
        bill_id=state["bill_id"],
        decision=decision,
        urgency=urgency,
        pricing=pricing,
        reason=reason,
    )

    # Map decision to action_type for DB
    decision_to_action = {
        "PAY_NOW": "payment_initiated",
        "REMIND": "reminder_email",
        "OPTIMIZE": "optimize_suggestion",
        "ESCALATE": None,  # No automated action — surface to user
        "IGNORE": None,
    }

    return {
        "decision": decision,
        "decision_reason": reason,
        "action_type": decision_to_action.get(decision),
        "action_payload": {},
        "action_queued": False,
        "execution_notes": [f"Decision: {decision} — {reason}"],
    }
