"""
Unit tests for the agent decision nodes.
"""
import pytest
from datetime import date, timedelta

from services.agent.nodes.assess_urgency import assess_urgency
from services.agent.nodes.decide_action import decide_action


def make_state(**overrides):
    base = {
        "bill_id": "test-bill-001",
        "user_id": "test-user-001",
        "provider": "Airtel",
        "bill_type": "mobile",
        "amount": 599.0,
        "currency": "INR",
        "due_date": date.today() + timedelta(days=10),
        "is_overdue": False,
        "is_recurring": True,
        "needs_review": False,
        "status": "extracted",
        "due_in_days": None,
        "urgency_level": "none",
        "pricing_verdict": "unknown",
        "market_context": None,
        "decision": "IGNORE",
        "decision_reason": "",
        "action_type": None,
        "action_payload": {},
        "action_queued": False,
        "execution_notes": [],
        "errors": [],
    }
    base.update(overrides)
    return base


class TestAssessUrgency:
    def test_critical_overdue(self):
        state = make_state(is_overdue=True, due_date=date.today() - timedelta(days=2))
        result = assess_urgency(state)
        assert result["urgency_level"] == "critical"

    def test_critical_due_today(self):
        state = make_state(due_date=date.today())
        result = assess_urgency(state)
        assert result["urgency_level"] == "critical"

    def test_high_urgency(self):
        state = make_state(due_date=date.today() + timedelta(days=2))
        result = assess_urgency(state)
        assert result["urgency_level"] == "high"

    def test_medium_urgency(self):
        state = make_state(due_date=date.today() + timedelta(days=5))
        result = assess_urgency(state)
        assert result["urgency_level"] == "medium"

    def test_low_urgency(self):
        state = make_state(due_date=date.today() + timedelta(days=15))
        result = assess_urgency(state)
        assert result["urgency_level"] == "low"

    def test_no_urgency_far_future(self):
        state = make_state(due_date=date.today() + timedelta(days=45))
        result = assess_urgency(state)
        assert result["urgency_level"] == "none"

    def test_no_due_date(self):
        state = make_state(due_date=None)
        result = assess_urgency(state)
        assert result["urgency_level"] == "none"
        assert result["due_in_days"] is None


class TestDecideAction:
    def test_escalate_when_needs_review(self):
        state = make_state(needs_review=True, urgency_level="critical")
        result = decide_action(state)
        assert result["decision"] == "ESCALATE"

    def test_pay_now_critical_fair(self):
        state = make_state(
            urgency_level="critical",
            pricing_verdict="fair",
            due_in_days=0,
        )
        result = decide_action(state)
        assert result["decision"] == "PAY_NOW"
        assert result["action_type"] == "payment_initiated"

    def test_optimize_critical_overpriced(self):
        state = make_state(
            urgency_level="critical",
            pricing_verdict="overpriced",
            due_in_days=0,
        )
        result = decide_action(state)
        assert result["decision"] == "OPTIMIZE"

    def test_remind_high_urgency(self):
        state = make_state(urgency_level="high", due_in_days=2)
        result = decide_action(state)
        assert result["decision"] == "REMIND"

    def test_remind_medium_urgency(self):
        state = make_state(urgency_level="medium", due_in_days=5)
        result = decide_action(state)
        assert result["decision"] == "REMIND"

    def test_optimize_low_urgency_overpriced(self):
        state = make_state(urgency_level="low", pricing_verdict="overpriced", due_in_days=20)
        result = decide_action(state)
        assert result["decision"] == "OPTIMIZE"

    def test_ignore_no_amount_no_due_date(self):
        state = make_state(urgency_level="none", amount=None)
        result = decide_action(state)
        assert result["decision"] == "IGNORE"
        assert result["action_type"] is None
