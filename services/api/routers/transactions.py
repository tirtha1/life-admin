"""
Transactions router — list, spend stats, AI insights, delete.
All routes are RLS-protected via get_current_user.
"""
import os
import json
import structlog
from datetime import date, datetime, timedelta
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Transaction, TransactionType, TransactionCategory
from shared.db.session import get_db_session
from services.api.security import CurrentUser, get_current_user

log = structlog.get_logger()
router = APIRouter(prefix="/transactions", tags=["transactions"])


# ─── Response schemas ─────────────────────────────────────────────────────────

class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email_id: Optional[str] = None
    amount: float
    type: str
    merchant: Optional[str] = None
    category: str
    date: date
    source: Optional[str] = None
    extraction_confidence: float

    @classmethod
    def from_orm(cls, t: Transaction) -> "TransactionRead":
        return cls(
            id=str(t.id),
            email_id=t.email_id,
            amount=float(t.amount),
            type=t.type.value,
            merchant=t.merchant,
            category=t.category.value,
            date=t.date,
            source=t.source,
            extraction_confidence=float(t.extraction_confidence or 0),
        )


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


class InsightsResponse(BaseModel):
    insights: list[str]
    generated_at: str


class TransactionSyncResult(BaseModel):
    emails_scanned: int
    transactions_found: int
    transactions_new: int
    transactions_skipped: int
    errors: int


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TransactionRead])
async def list_transactions(
    type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    async for session in get_db_session(current_user.user_id):
        stmt = select(Transaction).where(Transaction.user_id == current_user.user_id)

        if type:
            try:
                stmt = stmt.where(Transaction.type == TransactionType(type.lower()))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid type: {type}")
        if category:
            try:
                stmt = stmt.where(Transaction.category == TransactionCategory(category.lower()))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)

        stmt = stmt.order_by(Transaction.date.desc(), Transaction.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await session.execute(stmt)
        return [TransactionRead.from_orm(t) for t in result.scalars().all()]


# ─── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=SpendStats)
async def get_spend_stats(
    days: int = Query(30, le=365),
    current_user: CurrentUser = Depends(get_current_user),
):
    today = date.today()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=7)
    window_start = today - timedelta(days=days)
    uid = current_user.user_id
    debit = TransactionType.DEBIT

    async for session in get_db_session(uid):
        async def _sum(from_date: date) -> float:
            r = await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .where(and_(Transaction.user_id == uid, Transaction.type == debit, Transaction.date >= from_date))
            )
            return float(r or 0)

        total_month = await _sum(month_start)
        total_today = await _sum(today)
        total_week = await _sum(week_start)

        count = await session.scalar(
            select(func.count(Transaction.id))
            .where(and_(Transaction.user_id == uid, Transaction.type == debit, Transaction.date >= window_start))
        ) or 0

        # Daily spend
        daily_rows = (await session.execute(
            select(Transaction.date, func.sum(Transaction.amount), func.count(Transaction.id))
            .where(and_(Transaction.user_id == uid, Transaction.type == debit, Transaction.date >= window_start))
            .group_by(Transaction.date)
            .order_by(Transaction.date.desc())
        )).all()
        daily_spend = [DailySpend(date=r[0], total=float(r[1]), count=int(r[2])) for r in daily_rows]

        # Category breakdown
        cat_rows = (await session.execute(
            select(Transaction.category, func.sum(Transaction.amount), func.count(Transaction.id))
            .where(and_(Transaction.user_id == uid, Transaction.type == debit, Transaction.date >= window_start))
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
        )).all()
        window_total = sum(float(r[1]) for r in cat_rows) or 1.0
        category_breakdown = [
            CategoryBreakdown(
                category=r[0].value if hasattr(r[0], 'value') else str(r[0]),
                total=float(r[1]),
                count=int(r[2]),
                percentage=round(float(r[1]) / window_total * 100, 1),
            )
            for r in cat_rows
        ]

        # Top merchant
        top_row = (await session.execute(
            select(Transaction.merchant, func.sum(Transaction.amount))
            .where(and_(Transaction.user_id == uid, Transaction.type == debit,
                        Transaction.date >= window_start, Transaction.merchant.isnot(None)))
            .group_by(Transaction.merchant)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(1)
        )).first()

        return SpendStats(
            total_this_month=total_month,
            total_today=total_today,
            total_this_week=total_week,
            transaction_count=int(count),
            daily_spend=daily_spend,
            category_breakdown=category_breakdown,
            top_merchant=top_row[0] if top_row else None,
        )


# ─── AI Insights ──────────────────────────────────────────────────────────────

@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    days: int = Query(30, le=90),
    current_user: CurrentUser = Depends(get_current_user),
):
    window_start = date.today() - timedelta(days=days)
    uid = current_user.user_id

    async for session in get_db_session(uid):
        result = await session.execute(
            select(Transaction)
            .where(and_(
                Transaction.user_id == uid,
                Transaction.type == TransactionType.DEBIT,
                Transaction.date >= window_start,
            ))
            .order_by(Transaction.date.desc())
            .limit(200)
        )
        transactions = result.scalars().all()

    if not transactions:
        return InsightsResponse(
            insights=["No transactions found. Sync your Gmail to get started."],
            generated_at=datetime.utcnow().isoformat(),
        )

    total = sum(float(t.amount) for t in transactions)
    by_cat: dict[str, float] = {}
    by_merchant: dict[str, float] = {}
    for t in transactions:
        cat = t.category.value if hasattr(t.category, 'value') else str(t.category)
        by_cat[cat] = by_cat.get(cat, 0) + float(t.amount)
        if t.merchant:
            by_merchant[t.merchant] = by_merchant.get(t.merchant, 0) + float(t.amount)

    top_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:5]
    top_merchants = sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)[:5]

    summary = (
        f"Period: last {days} days | Total spent: ₹{total:,.0f} | Transactions: {len(transactions)}\n"
        f"Top categories: {', '.join(f'{c} ₹{a:,.0f}' for c, a in top_cats)}\n"
        f"Top merchants: {', '.join(f'{m} ₹{a:,.0f}' for m, a in top_merchants)}"
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            system=(
                "You are a personal finance advisor for an Indian user. "
                "Given spending data, produce 3–5 short actionable insights. "
                "Use ₹ for amounts. Be specific and friendly. "
                "Return ONLY a JSON array of strings, no other text. "
                'Example: ["You spent ₹3,200 on food this month — 40% of total."]'
            ),
            messages=[{"role": "user", "content": summary}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find('['), text.rfind(']') + 1
        insights = json.loads(text[start:end]) if start != -1 else [text]
    except Exception as e:
        log.warning("Insights generation failed", error=str(e))
        insights = [
            f"Total spent in last {days} days: ₹{total:,.0f}",
            f"Top category: {top_cats[0][0]} (₹{top_cats[0][1]:,.0f})" if top_cats else "No spend data yet",
            f"Most visited: {top_merchants[0][0]} (₹{top_merchants[0][1]:,.0f})" if top_merchants else "",
        ]
        insights = [i for i in insights if i]

    return InsightsResponse(insights=insights, generated_at=datetime.utcnow().isoformat())


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    async for session in get_db_session(current_user.user_id):
        result = await session.execute(
            select(Transaction).where(
                and_(Transaction.id == transaction_id, Transaction.user_id == current_user.user_id)
            )
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        await session.delete(txn)
