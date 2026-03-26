"""
SQLAlchemy ORM models matching the production schema.
All user-data tables support Row-Level Security.
"""
import enum
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String, Text, Boolean, Numeric, Date, DateTime,
    Enum as SAEnum, ARRAY, LargeBinary, ForeignKey, JSON,
    UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


def new_uuid() -> str:
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────────

class BillStatus(str, enum.Enum):
    DETECTED = "detected"
    EXTRACTED = "extracted"
    REVIEW_REQUIRED = "review_required"
    CONFIRMED = "confirmed"
    REMINDED = "reminded"
    PAID = "paid"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ActionType(str, enum.Enum):
    REMINDER_EMAIL = "reminder_email"
    REMINDER_SMS = "reminder_sms"
    REMINDER_WHATSAPP = "reminder_whatsapp"
    CALENDAR_EVENT = "calendar_event"
    PAYMENT_INITIATED = "payment_initiated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    OPTIMIZE_SUGGESTION = "optimize_suggestion"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=new_uuid
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    raw_emails: Mapped[list["RawEmail"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    bills: Mapped[list["Bill"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    actions: Mapped[list["Action"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # 'google', 'microsoft'
    access_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)   # AES-256 encrypted
    refresh_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # AES-256 encrypted
    token_expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="oauth_tokens")

    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),)


class RawEmail(Base):
    __tablename__ = "raw_emails"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Gmail message ID
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)  # Raw email stored in S3
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="raw_emails")
    bills: Mapped[list["Bill"]] = relationship(back_populates="raw_email")

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_raw_email_user_message"),
        Index("idx_raw_emails_user_processed", "user_id", "processed"),
    )


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    raw_email_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("raw_emails.id"), nullable=True
    )

    # Extracted fields
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    bill_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    billing_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    billing_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # State machine
    status: Mapped[BillStatus] = mapped_column(SAEnum(BillStatus, name="bill_status", values_callable=lambda x: [e.value for e in x]), default=BillStatus.DETECTED)

    # LLM metadata
    extraction_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    extraction_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extraction_raw: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Flags
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="bills")
    raw_email: Mapped[Optional["RawEmail"]] = relationship(back_populates="bills")
    transitions: Mapped[list["BillTransition"]] = relationship(back_populates="bill", cascade="all, delete-orphan")
    actions: Mapped[list["Action"]] = relationship(back_populates="bill")

    __table_args__ = (
        Index("idx_bills_user_status", "user_id", "status"),
        Index("idx_bills_due_date", "due_date"),
    )


class BillTransition(Base):
    __tablename__ = "bill_transitions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    bill_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[Optional[BillStatus]] = mapped_column(SAEnum(BillStatus, name="bill_status", values_callable=lambda x: [e.value for e in x]), nullable=True)
    to_status: Mapped[BillStatus] = mapped_column(SAEnum(BillStatus, name="bill_status", values_callable=lambda x: [e.value for e in x]), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50), default="system")  # 'system', 'agent', 'user'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bill: Mapped["Bill"] = relationship(back_populates="transitions")


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    bill_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bills.id"), nullable=True
    )
    action_type: Mapped[ActionType] = mapped_column(SAEnum(ActionType, name="action_type", values_callable=lambda x: [e.value for e in x]), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(SAEnum(ActionStatus, name="action_status", values_callable=lambda x: [e.value for e in x]), default=ActionStatus.PENDING)
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="actions")
    bill: Mapped[Optional["Bill"]] = relationship(back_populates="actions")

    __table_args__ = (
        Index("idx_actions_idempotency", "idempotency_key"),
        Index("idx_actions_bill", "bill_id"),
    )


# ─── State machine guard ──────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[BillStatus, set[BillStatus]] = {
    BillStatus.DETECTED:        {BillStatus.EXTRACTED, BillStatus.REVIEW_REQUIRED, BillStatus.FAILED},
    BillStatus.EXTRACTED:       {BillStatus.CONFIRMED, BillStatus.REVIEW_REQUIRED},
    BillStatus.REVIEW_REQUIRED: {BillStatus.CONFIRMED, BillStatus.CANCELLED},
    BillStatus.CONFIRMED:       {BillStatus.REMINDED, BillStatus.PAID, BillStatus.CANCELLED},
    BillStatus.REMINDED:        {BillStatus.PAID, BillStatus.CANCELLED},
    BillStatus.PAID:            set(),
    BillStatus.CANCELLED:       set(),
    BillStatus.FAILED:          set(),
}


def validate_transition(from_status: BillStatus, to_status: BillStatus) -> None:
    allowed = VALID_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise ValueError(
            f"Invalid bill state transition: {from_status.value} → {to_status.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )
