"""
Shared pytest fixtures for Life Admin tests.
"""
import os
import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def sample_parsed_email():
    """A sample ParsedEmail for testing."""
    from services.ingestion.gmail_client import ParsedEmail
    return ParsedEmail(
        message_id="test-msg-001",
        thread_id="thread-001",
        subject="Airtel Postpaid Bill - June 2025",
        sender="noreply@airtel.com",
        received_at="Mon, 01 Jun 2025 10:00:00 +0530",
        body_text=(
            "Dear Customer,\n\nYour postpaid bill for June 2025 is ready.\n"
            "Amount Due: ₹599.00\nDue Date: 15 Jun 2025\n"
            "Account: 9876543210\n\nPay now to avoid late fees."
        ),
        snippet="Your postpaid bill for June 2025 is ready. Amount Due: ₹599.00",
    )


@pytest.fixture
def sample_bill_extraction():
    """A sample BillExtraction for testing."""
    from services.processor.extractor import BillExtraction
    return BillExtraction(
        provider="Airtel",
        bill_type="mobile",
        amount=599.0,
        currency="INR",
        due_date="2025-06-15",
        billing_period_start="2025-05-01",
        billing_period_end="2025-05-31",
        account_number="9876543210",
        is_overdue=False,
        is_recurring=True,
        confidence=0.93,
        extraction_notes=None,
    )


@pytest.fixture
def sample_agent_state():
    """A sample AgentState for testing."""
    return {
        "bill_id": "11111111-1111-1111-1111-111111111111",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "provider": "Airtel",
        "bill_type": "mobile",
        "amount": 599.0,
        "currency": "INR",
        "due_date": date(2025, 6, 15),
        "is_overdue": False,
        "is_recurring": True,
        "needs_review": False,
        "status": "extracted",
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
