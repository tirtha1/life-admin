import enum
from datetime import datetime, date
from sqlalchemy import String, Float, Date, DateTime, Text, Enum as SAEnum, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class BillStatus(str, enum.Enum):
    PENDING = "pending"       # Detected, not yet acted on
    REMINDED = "reminded"     # Reminder sent
    PAID = "paid"             # Marked as paid
    OVERDUE = "overdue"       # Past due date, unpaid
    IGNORED = "ignored"       # User dismissed
    OPTIMIZING = "optimizing" # Flagged for cost optimization


class BillType(str, enum.Enum):
    ELECTRICITY = "electricity"
    WATER = "water"
    GAS = "gas"
    INTERNET = "internet"
    PHONE = "phone"
    CREDIT_CARD = "credit_card"
    INSURANCE = "insurance"
    SUBSCRIPTION = "subscription"
    RENT = "rent"
    OTHER = "other"


class AgentAction(str, enum.Enum):
    PAY_NOW = "pay_now"
    REMIND = "remind"
    OPTIMIZE = "optimize"
    IGNORE = "ignore"
    NONE = "none"


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Source
    email_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_email_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extracted bill info
    provider: Mapped[str] = mapped_column(String(255), default="Unknown")
    bill_type: Mapped[BillType] = mapped_column(SAEnum(BillType), default=BillType.OTHER)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    billing_period: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status & agent
    status: Mapped[BillStatus] = mapped_column(SAEnum(BillStatus), default=BillStatus.PENDING)
    agent_action: Mapped[AgentAction] = mapped_column(SAEnum(AgentAction), default=AgentAction.NONE)
    is_overpriced: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extraction confidence
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Bill id={self.id} provider={self.provider} amount={self.amount} due={self.due_date}>"
