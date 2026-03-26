"""
Unit tests for the bill extraction validator.
"""
import pytest
from datetime import date, timedelta

from services.processor.extractor import BillExtraction
from services.processor.validator import validate, ValidationOutcome


def make_extraction(**overrides) -> BillExtraction:
    defaults = dict(
        provider="Airtel",
        bill_type="mobile",
        amount=599.0,
        currency="INR",
        due_date=(date.today() + timedelta(days=10)).isoformat(),
        billing_period_start=None,
        billing_period_end=None,
        account_number="9876543210",
        is_overdue=False,
        is_recurring=True,
        confidence=0.92,
        extraction_notes=None,
    )
    defaults.update(overrides)
    return BillExtraction(**defaults)


class TestValidate:
    def test_accept_high_confidence(self):
        result = validate(make_extraction(), "msg-001")
        assert result.outcome == ValidationOutcome.ACCEPT
        assert not result.needs_review

    def test_reject_very_low_confidence(self):
        result = validate(make_extraction(confidence=0.3), "msg-002")
        assert result.outcome == ValidationOutcome.REJECT

    def test_review_low_confidence(self):
        result = validate(make_extraction(confidence=0.6), "msg-003")
        assert result.outcome == ValidationOutcome.REVIEW
        assert result.needs_review

    def test_review_high_value(self):
        result = validate(make_extraction(amount=75_000.0), "msg-004")
        assert result.outcome == ValidationOutcome.REVIEW

    def test_review_missing_provider(self):
        result = validate(make_extraction(provider=""), "msg-005")
        assert result.outcome == ValidationOutcome.REVIEW

    def test_review_overdue_due_date(self):
        old_date = (date.today() - timedelta(days=40)).isoformat()
        result = validate(make_extraction(due_date=old_date), "msg-006")
        assert result.outcome == ValidationOutcome.REVIEW

    def test_due_date_parsed_correctly(self):
        future = date.today() + timedelta(days=5)
        result = validate(make_extraction(due_date=future.isoformat()), "msg-007")
        assert result.due_date == future

    def test_invalid_date_returns_none(self):
        result = validate(make_extraction(due_date="not-a-date"), "msg-008")
        assert result.due_date is None

    def test_billing_period_coherence(self):
        result = validate(
            make_extraction(
                billing_period_start="2025-06-01",
                billing_period_end="2025-05-01",  # end before start
            ),
            "msg-009",
        )
        assert result.outcome == ValidationOutcome.REVIEW
