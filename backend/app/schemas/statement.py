"""
Pydantic schemas for bank statement upload analysis.
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.transaction import TransactionCategory


class StatementTransaction(BaseModel):
    date: date
    description: str
    amount: float
    signed_amount: float
    type: Literal["debit", "credit"]
    merchant: Optional[str] = None
    category: TransactionCategory


class StatementRecurringPayment(BaseModel):
    merchant: str
    category: TransactionCategory
    monthly_estimate: float
    occurrences: int
    cadence: str
    confidence: float
    last_seen: date
    reason: str


class StatementLeakInsight(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    amount: float
    merchant: Optional[str] = None
    category: Optional[TransactionCategory] = None
    rationale: str
    suggested_action: str


class StatementAction(BaseModel):
    title: str
    priority: Literal["low", "medium", "high"]
    action_type: Literal["cancel_subscription", "set_budget", "review_spike", "monitor"]
    description: str
    estimated_monthly_savings: float = 0.0
    merchant: Optional[str] = None
    category: Optional[TransactionCategory] = None


class StatementSummary(BaseModel):
    period_start: date
    period_end: date
    transaction_count: int
    total_spent: float
    total_income: float
    net_cashflow: float
    recurring_spend: float
    potential_monthly_savings: float
    top_category: Optional[TransactionCategory] = None


class StatementAnalysisResponse(BaseModel):
    file_name: str
    file_type: Literal["csv", "pdf"]
    parser_used: str
    llm_enhanced: bool
    assistant_summary: str
    warnings: list[str]
    summary: StatementSummary
    recurring_payments: list[StatementRecurringPayment]
    leak_insights: list[StatementLeakInsight]
    suggested_actions: list[StatementAction]
    transactions: list[StatementTransaction]
