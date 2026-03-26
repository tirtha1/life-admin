"""
Pydantic schemas for transactions.
"""
from datetime import date
from typing import Optional
from pydantic import BaseModel
from app.models.transaction import TransactionType, TransactionCategory


# ─── Claude extraction output ─────────────────────────────────────────────────

class TransactionExtraction(BaseModel):
    is_transaction: bool
    amount: Optional[float] = None
    type: Optional[str] = None        # "debit" or "credit"
    merchant: Optional[str] = None
    category: Optional[str] = None
    date: Optional[str] = None        # YYYY-MM-DD
    source: Optional[str] = None      # bank or payment app
    confidence: float = 0.0


# ─── API response schemas ──────────────────────────────────────────────────────

class TransactionRead(BaseModel):
    id: int
    email_id: Optional[str] = None
    amount: float
    type: TransactionType
    merchant: Optional[str] = None
    category: TransactionCategory
    date: date
    source: Optional[str] = None
    extraction_confidence: float

    model_config = {"from_attributes": True}


# ─── Spend stats ──────────────────────────────────────────────────────────────

class DailySpend(BaseModel):
    date: date
    total: float
    count: int


class CategoryBreakdown(BaseModel):
    category: str
    total: float
    count: int
    percentage: float


class SpendStats(BaseModel):
    total_this_month: float
    total_today: float
    total_this_week: float
    transaction_count: int
    daily_spend: list[DailySpend]
    category_breakdown: list[CategoryBreakdown]
    top_merchant: Optional[str] = None


# ─── Insights ─────────────────────────────────────────────────────────────────

class InsightsResponse(BaseModel):
    insights: list[str]
    generated_at: str


# ─── Sync result ──────────────────────────────────────────────────────────────

class TransactionSyncResult(BaseModel):
    emails_scanned: int
    transactions_found: int
    transactions_new: int
    transactions_skipped: int
    errors: int
