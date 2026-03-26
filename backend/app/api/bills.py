"""
Bills API — CRUD + agent trigger endpoints.
"""
import structlog
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.bill import Bill, BillStatus, AgentAction
from app.schemas.bill import BillRead, BillUpdate, BillStats, AgentRunResult
from app.services.agent.bill_agent import run_bill_agent

log = structlog.get_logger()
router = APIRouter()


# ─── List & filter ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[BillRead])
async def list_bills(
    status: Optional[BillStatus] = Query(None),
    bill_type: Optional[str] = Query(None),
    overpriced: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """List bills with optional filters."""
    stmt = select(Bill).order_by(Bill.due_date.asc().nullslast(), Bill.created_at.desc())

    if status:
        stmt = stmt.where(Bill.status == status)
    if bill_type:
        stmt = stmt.where(Bill.bill_type == bill_type)
    if overpriced is not None:
        stmt = stmt.where(Bill.is_overpriced == overpriced)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats", response_model=BillStats)
async def get_bill_stats(db: AsyncSession = Depends(get_db)):
    """Dashboard stats."""
    total_result = await db.execute(select(func.count(Bill.id)))
    total = total_result.scalar() or 0

    def count_by_status(s: BillStatus):
        return select(func.count(Bill.id)).where(Bill.status == s)

    pending = (await db.execute(count_by_status(BillStatus.PENDING))).scalar() or 0
    reminded = (await db.execute(count_by_status(BillStatus.REMINDED))).scalar() or 0
    paid = (await db.execute(count_by_status(BillStatus.PAID))).scalar() or 0
    overdue = (await db.execute(count_by_status(BillStatus.OVERDUE))).scalar() or 0

    amount_result = await db.execute(
        select(func.sum(Bill.amount)).where(
            Bill.status.in_([BillStatus.PENDING, BillStatus.REMINDED, BillStatus.OVERDUE])
        )
    )
    total_amount = amount_result.scalar() or 0.0

    overpriced_result = await db.execute(
        select(func.count(Bill.id)).where(Bill.is_overpriced == True)
    )
    overpriced_count = overpriced_result.scalar() or 0

    return BillStats(
        total=total,
        pending=pending,
        reminded=reminded,
        paid=paid,
        overdue=overdue,
        total_amount_due=float(total_amount),
        overpriced_count=overpriced_count,
    )


# ─── Single bill ──────────────────────────────────────────────────────────────

@router.get("/{bill_id}", response_model=BillRead)
async def get_bill(bill_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@router.patch("/{bill_id}", response_model=BillRead)
async def update_bill(
    bill_id: int,
    payload: BillUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update bill status, amount, due date, or notes."""
    result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bill, field, value)

    await db.flush()
    await db.refresh(bill)
    return bill


@router.delete("/{bill_id}", status_code=204)
async def delete_bill(bill_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    await db.delete(bill)


# ─── Actions ──────────────────────────────────────────────────────────────────

@router.post("/{bill_id}/mark-paid", response_model=BillRead)
async def mark_paid(bill_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a bill as paid."""
    result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    bill.status = BillStatus.PAID
    bill.agent_notes = (bill.agent_notes or "") + " | Manually marked as paid."
    await db.flush()
    await db.refresh(bill)
    log.info("Bill marked paid", bill_id=bill_id)
    return bill


@router.post("/run-all-pending", response_model=list[AgentRunResult])
async def run_agent_for_all_pending(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Run the agent on all pending bills.
    Processes synchronously and returns results.
    """
    result = await db.execute(
        select(Bill).where(Bill.status == BillStatus.PENDING)
    )
    pending_bills = result.scalars().all()

    log.info("Running agent for pending bills", count=len(pending_bills))

    results = []
    for bill in pending_bills:
        try:
            final_state = await run_bill_agent(bill)
            results.append(
                AgentRunResult(
                    bill_id=bill.id,
                    action=AgentAction(final_state["action"]),
                    notes=" | ".join(final_state["execution_notes"]),
                    notification_sent=final_state["notification_sent"],
                )
            )
        except Exception as e:
            log.error("Agent failed for bill", bill_id=bill.id, error=str(e))
            results.append(
                AgentRunResult(
                    bill_id=bill.id,
                    action=AgentAction.NONE,
                    notes=f"Error: {str(e)[:100]}",
                    notification_sent=False,
                )
            )

    return results


@router.post("/{bill_id}/run-agent", response_model=AgentRunResult)
async def run_agent_for_bill(bill_id: int, db: AsyncSession = Depends(get_db)):
    """
    Manually trigger the LangGraph agent for a specific bill.
    Useful for re-processing or testing.
    """
    result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    try:
        final_state = await run_bill_agent(bill)
        return AgentRunResult(
            bill_id=bill_id,
            action=AgentAction(final_state["action"]),
            notes=" | ".join(final_state["execution_notes"]),
            notification_sent=final_state["notification_sent"],
        )
    except Exception as e:
        log.error("Agent run failed", bill_id=bill_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
