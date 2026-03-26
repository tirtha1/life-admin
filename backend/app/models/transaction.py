"""
Transaction model — UPI / bank / payment alert transactions extracted from Gmail.
"""
import enum
from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, Float, String, Text, Date,
    DateTime, Enum as SAEnum, func,
)
from app.core.database import Base


class TransactionType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionCategory(str, enum.Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    UTILITIES = "utilities"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    TRAVEL = "travel"
    SUBSCRIPTIONS = "subscriptions"
    OTHER = "other"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(String(255), unique=True, nullable=True)  # for deduplication

    # Core extracted fields
    amount = Column(Float, nullable=False)
    type = Column(SAEnum(TransactionType), nullable=False, default=TransactionType.DEBIT)
    merchant = Column(String(255), nullable=True)
    category = Column(SAEnum(TransactionCategory), default=TransactionCategory.OTHER, nullable=False)
    date = Column(Date, nullable=False)
    source = Column(String(100), nullable=True)  # e.g. "HDFC Bank", "GPay", "Paytm"

    # Raw data
    raw_text = Column(Text, nullable=True)
    extraction_confidence = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
