from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from app.models.bill import BillStatus, BillType, AgentAction


# ─── Extraction schema (Claude output) ────────────────────────────────────────

class BillExtraction(BaseModel):
    """Structured output from Claude bill extraction."""
    is_bill: bool = Field(description="True if this email contains a bill/invoice/payment request")
    provider: str = Field(default="Unknown", description="Service provider name, e.g. 'Airtel', 'BSES'")
    bill_type: str = Field(default="other", description="Type: electricity, water, gas, internet, phone, credit_card, insurance, subscription, rent, other")
    amount: Optional[float] = Field(default=None, description="Total amount due in numeric form")
    currency: str = Field(default="INR", description="Currency code e.g. INR, USD")
    due_date: Optional[str] = Field(default=None, description="Due date in YYYY-MM-DD format")
    billing_period: Optional[str] = Field(default=None, description="e.g. 'October 2024'")
    confidence: float = Field(default=0.5, description="Extraction confidence 0.0-1.0")


# ─── API schemas ──────────────────────────────────────────────────────────────

class BillBase(BaseModel):
    provider: str
    bill_type: BillType
    amount: Optional[float]
    currency: str = "INR"
    due_date: Optional[date]
    billing_period: Optional[str]
    status: BillStatus


class BillRead(BillBase):
    id: int
    email_id: Optional[str]
    email_subject: Optional[str]
    email_sender: Optional[str]
    agent_action: AgentAction
    is_overpriced: bool
    notification_sent: bool
    agent_notes: Optional[str]
    extraction_confidence: Optional[float]
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BillUpdate(BaseModel):
    status: Optional[BillStatus] = None
    amount: Optional[float] = None
    due_date: Optional[date] = None
    agent_notes: Optional[str] = None


class BillStats(BaseModel):
    total: int
    pending: int
    reminded: int
    paid: int
    overdue: int
    total_amount_due: float
    overpriced_count: int


class SyncResult(BaseModel):
    emails_scanned: int
    bills_detected: int
    bills_new: int
    bills_skipped: int
    errors: list[str] = []


class AgentRunResult(BaseModel):
    bill_id: int
    action: AgentAction
    notes: str
    notification_sent: bool
