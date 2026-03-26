"""
Transactions API — list, spend stats, AI insights, delete.
"""
import structlog
from datetime import date, datetime, timedelta
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, extract, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.models.transaction import Transaction, TransactionType, TransactionCategory
from app.schemas.transaction import (
    TransactionRead, SpendStats, DailySpend,
    CategoryBreakdown, InsightsResponse,
)

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


# ─── List transactions ────────────────────────────────────────────────────────

@router.get("/", response_model=list[TransactionRead])
async def list_transactions(
    type: Optional[TransactionType] = Query(None),
    category: Optional[TransactionCategory] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Transaction).order_by(Transaction.date.desc(), Transaction.created_at.desc())

    if type:
        stmt = stmt.where(Transaction.type == type)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ─── Spend stats ──────────────────────────────────────────────────────────────

@router.get("/stats", response_model=SpendStats)
async def get_spend_stats(
    days: int = Query(30, le=365, description="Look-back window in days"),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    week_start = today - timedelta(days=7)
    month_start = today.replace(day=1)
    window_start = today - timedelta(days=days)

    debit = TransactionType.DEBIT

    # Totals
    async def _sum(from_date: date) -> float:
        r = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0))
            .where(Transaction.type == debit, Transaction.date >= from_date)
        )
        return float(r.scalar())

    async def _count(from_date: date) -> int:
        r = await db.execute(
            select(func.count(Transaction.id))
            .where(Transaction.type == debit, Transaction.date >= from_date)
        )
        return int(r.scalar())

    total_month = await _sum(month_start)
    total_today = await _sum(today)
    total_week = await _sum(week_start)
    count = await _count(window_start)

    # Daily spend (last `days` days)
    daily_result = await db.execute(
        select(Transaction.date, func.sum(Transaction.amount), func.count(Transaction.id))
        .where(Transaction.type == debit, Transaction.date >= window_start)
        .group_by(Transaction.date)
        .order_by(Transaction.date.desc())
    )
    daily_rows = daily_result.all()
    daily_spend = [
        DailySpend(date=row[0], total=float(row[1]), count=int(row[2]))
        for row in daily_rows
    ]

    # Category breakdown
    cat_result = await db.execute(
        select(Transaction.category, func.sum(Transaction.amount), func.count(Transaction.id))
        .where(Transaction.type == debit, Transaction.date >= window_start)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    )
    cat_rows = cat_result.all()
    window_total = sum(float(r[1]) for r in cat_rows) or 1.0
    category_breakdown = [
        CategoryBreakdown(
            category=row[0].value if hasattr(row[0], 'value') else str(row[0]),
            total=float(row[1]),
            count=int(row[2]),
            percentage=round(float(row[1]) / window_total * 100, 1),
        )
        for row in cat_rows
    ]

    # Top merchant
    top_merchant_result = await db.execute(
        select(Transaction.merchant, func.sum(Transaction.amount))
        .where(Transaction.type == debit, Transaction.date >= window_start, Transaction.merchant.isnot(None))
        .group_by(Transaction.merchant)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(1)
    )
    top_row = top_merchant_result.first()
    top_merchant = top_row[0] if top_row else None

    return SpendStats(
        total_this_month=total_month,
        total_today=total_today,
        total_this_week=total_week,
        transaction_count=count,
        daily_spend=daily_spend,
        category_breakdown=category_breakdown,
        top_merchant=top_merchant,
    )


# ─── AI Insights ──────────────────────────────────────────────────────────────

@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    days: int = Query(30, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Generate natural language spending insights using Claude."""
    window_start = date.today() - timedelta(days=days)

    result = await db.execute(
        select(Transaction)
        .where(Transaction.type == TransactionType.DEBIT, Transaction.date >= window_start)
        .order_by(Transaction.date.desc())
        .limit(200)
    )
    transactions = result.scalars().all()

    if not transactions:
        return InsightsResponse(
            insights=["No transactions found in the selected period. Sync your Gmail to get started."],
            generated_at=datetime.utcnow().isoformat(),
        )

    # Build a compact summary for Claude
    total = sum(t.amount for t in transactions)
    by_category: dict[str, float] = {}
    by_merchant: dict[str, float] = {}
    for t in transactions:
        cat = t.category.value if hasattr(t.category, 'value') else str(t.category)
        by_category[cat] = by_category.get(cat, 0) + t.amount
        if t.merchant:
            by_merchant[t.merchant] = by_merchant.get(t.merchant, 0) + t.amount

    top_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]
    top_merchants = sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)[:5]

    summary = (
        f"Period: last {days} days\n"
        f"Total spent: ₹{total:,.0f}\n"
        f"Transactions: {len(transactions)}\n"
        f"Top categories: {', '.join(f'{c} ₹{a:,.0f}' for c, a in top_cats)}\n"
        f"Top merchants: {', '.join(f'{m} ₹{a:,.0f}' for m, a in top_merchants)}\n"
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            system=(
                "You are a personal finance advisor for an Indian user. "
                "Given spending data, produce 3–5 short, actionable insights. "
                "Use ₹ for amounts. Be specific and friendly. "
                "Return only a JSON array of strings, each insight as one string. "
                "Example: [\"You spent ₹3,200 on food this month — 40% of your total budget.\"]"
            ),
            messages=[{"role": "user", "content": summary}],
        )
        import json
        text = resp.content[0].text.strip()
        # Extract JSON array
        start = text.find('[')
        end = text.rfind(']') + 1
        insights = json.loads(text[start:end]) if start != -1 else [text]
    except Exception as e:
        log.warning("insights generation failed", error=str(e))
        insights = [
            f"Total spent in last {days} days: ₹{total:,.0f}",
            f"Top category: {top_cats[0][0]} (₹{top_cats[0][1]:,.0f})" if top_cats else "No category data",
            f"Most visited merchant: {top_merchants[0][0]} (₹{top_merchants[0][1]:,.0f})" if top_merchants else "No merchant data",
        ]

    return InsightsResponse(
        insights=insights,
        generated_at=datetime.utcnow().isoformat(),
    )


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.delete(txn)
