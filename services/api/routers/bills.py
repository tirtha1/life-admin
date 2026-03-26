"""
Bills router - CRUD + agent trigger endpoints.
All routes are RLS-protected via get_current_user dependency.
"""
import asyncio
import structlog
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Bill, BillStatus, BillTransition, validate_transition
from shared.db.session import get_db_session
from services.agent.graph import run_agent
from services.api.security import CurrentUser, get_current_user

log = structlog.get_logger()

router = APIRouter(prefix="/bills", tags=["bills"])


class BillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    bill_type: str
    amount: Optional[float]
    currency: str
    due_date: Optional[date]
    status: str
    extraction_confidence: Optional[float]
    is_overdue: bool
    is_recurring: bool
    needs_review: bool

    @classmethod
    def from_orm_bill(cls, bill: Bill) -> "BillRead":
        return cls(
            id=bill.id,
            provider=bill.provider,
            bill_type=bill.bill_type,
            amount=float(bill.amount) if bill.amount else None,
            currency=bill.currency,
            due_date=bill.due_date,
            status=bill.status.value.lower(),
            extraction_confidence=float(bill.extraction_confidence)
            if bill.extraction_confidence
            else None,
            is_overdue=bill.is_overdue,
            is_recurring=bill.is_recurring,
            needs_review=bill.needs_review,
        )


class BillStats(BaseModel):
    total: int
    pending: int
    overdue: int
    paid: int
    total_due_amount: float
    needs_review: int


class BillStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class AgentRunResult(BaseModel):
    bill_id: UUID
    action: str
    notes: str


async def _load_bill_for_user(session: AsyncSession, user_id: str, bill_id: UUID) -> Bill:
    result = await session.execute(
        select(Bill).where(
            Bill.id == bill_id,
            Bill.user_id == user_id,
        )
    )
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


async def _update_bill_status_in_session(
    session: AsyncSession,
    bill: Bill,
    update: BillStatusUpdate,
    actor: str,
) -> Bill:
    try:
        new_status = BillStatus(update.status.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    old_status = bill.status

    try:
        validate_transition(old_status, new_status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    bill.status = new_status
    if new_status == BillStatus.PAID:
        bill.is_overdue = False

    transition = BillTransition(
        bill_id=bill.id,
        from_status=old_status,
        to_status=new_status,
        reason=update.reason or "Manual status update",
        actor=actor,
    )
    session.add(transition)
    await session.commit()
    await session.refresh(bill)
    return bill


async def _run_agent_for_bill_async(bill: Bill) -> AgentRunResult:
    final_state = await asyncio.to_thread(
        run_agent,
        bill_id=str(bill.id),
        user_id=str(bill.user_id),
        provider=bill.provider,
        bill_type=bill.bill_type,
        amount=float(bill.amount) if bill.amount is not None else None,
        currency=bill.currency,
        due_date=bill.due_date,
        is_overdue=bill.is_overdue,
        is_recurring=bill.is_recurring,
        needs_review=bill.needs_review,
        status=bill.status.value,
    )
    notes = final_state.get("execution_notes", []) + final_state.get("errors", [])
    return AgentRunResult(
        bill_id=bill.id,
        action=str(final_state.get("decision", "IGNORE")).lower(),
        notes=" | ".join(notes) if notes else "Agent completed",
    )


@router.get("", response_model=list[BillRead])
async def list_bills(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List bills for the authenticated user."""
    async for session in get_db_session(current_user.user_id):
        query = select(Bill).where(Bill.user_id == current_user.user_id)
        if status_filter:
            try:
                query = query.where(Bill.status == BillStatus(status_filter.lower()))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}",
                )
        query = query.order_by(Bill.due_date.asc().nullslast(), Bill.created_at.desc())
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        bills = result.scalars().all()
        return [BillRead.from_orm_bill(bill) for bill in bills]


@router.get("/stats", response_model=BillStats)
async def get_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return aggregate bill statistics for the user."""
    async for session in get_db_session(current_user.user_id):
        total = await session.scalar(
            select(func.count(Bill.id)).where(Bill.user_id == current_user.user_id)
        )
        pending = await session.scalar(
            select(func.count(Bill.id)).where(
                and_(
                    Bill.user_id == current_user.user_id,
                    Bill.status == BillStatus.CONFIRMED,
                )
            )
        )
        overdue = await session.scalar(
            select(func.count(Bill.id)).where(
                and_(Bill.user_id == current_user.user_id, Bill.is_overdue == True)
            )
        )
        paid = await session.scalar(
            select(func.count(Bill.id)).where(
                and_(Bill.user_id == current_user.user_id, Bill.status == BillStatus.PAID)
            )
        )
        needs_review = await session.scalar(
            select(func.count(Bill.id)).where(
                and_(Bill.user_id == current_user.user_id, Bill.needs_review == True)
            )
        )
        total_due = await session.scalar(
            select(func.coalesce(func.sum(Bill.amount), 0)).where(
                and_(
                    Bill.user_id == current_user.user_id,
                    Bill.status.in_([BillStatus.CONFIRMED, BillStatus.REVIEW_REQUIRED]),
                )
            )
        )
        return BillStats(
            total=total or 0,
            pending=pending or 0,
            overdue=overdue or 0,
            paid=paid or 0,
            total_due_amount=float(total_due or 0),
            needs_review=needs_review or 0,
        )


@router.post("/run-all-pending", response_model=list[AgentRunResult])
async def run_agent_for_all_pending(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Compatibility endpoint for the current frontend.
    Runs the agent for extracted/review-required bills awaiting follow-up.
    """
    async for session in get_db_session(current_user.user_id):
        result = await session.execute(
            select(Bill).where(
                Bill.user_id == current_user.user_id,
                Bill.status.in_([BillStatus.EXTRACTED, BillStatus.REVIEW_REQUIRED]),
            )
        )
        bills = result.scalars().all()

        log.info(
            "Running agent for actionable bills",
            user_id=current_user.user_id,
            count=len(bills),
        )

        results: list[AgentRunResult] = []
        for bill in bills:
            try:
                results.append(await _run_agent_for_bill_async(bill))
            except Exception as exc:
                log.error(
                    "Agent run failed",
                    user_id=current_user.user_id,
                    bill_id=str(bill.id),
                    error=str(exc),
                    exc_info=True,
                )
                results.append(
                    AgentRunResult(
                        bill_id=bill.id,
                        action="ignore",
                        notes=f"Agent error: {exc}",
                    )
                )

        return results


@router.get("/{bill_id}", response_model=BillRead)
async def get_bill(
    bill_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Fetch a single bill by ID."""
    async for session in get_db_session(current_user.user_id):
        bill = await _load_bill_for_user(session, current_user.user_id, bill_id)
        return BillRead.from_orm_bill(bill)


@router.patch("/{bill_id}/status", response_model=BillRead)
async def update_bill_status(
    bill_id: UUID,
    update: BillStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update bill status with state-machine validation."""
    async for session in get_db_session(current_user.user_id):
        bill = await _load_bill_for_user(session, current_user.user_id, bill_id)
        bill = await _update_bill_status_in_session(
            session=session,
            bill=bill,
            update=update,
            actor=f"user:{current_user.user_id}",
        )
        return BillRead.from_orm_bill(bill)


@router.post("/{bill_id}/mark-paid", response_model=BillRead)
async def mark_paid(
    bill_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Compatibility endpoint used by the frontend to mark a bill as paid."""
    return await update_bill_status(
        bill_id=bill_id,
        update=BillStatusUpdate(status="paid", reason="Marked paid from dashboard"),
        current_user=current_user,
    )


@router.post("/{bill_id}/run-agent", response_model=AgentRunResult)
async def run_agent_for_bill(
    bill_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Compatibility endpoint used by the frontend to run the decision agent for one bill."""
    async for session in get_db_session(current_user.user_id):
        bill = await _load_bill_for_user(session, current_user.user_id, bill_id)
        try:
            return await _run_agent_for_bill_async(bill)
        except Exception as exc:
            log.error(
                "Agent run failed",
                user_id=current_user.user_id,
                bill_id=str(bill.id),
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"Agent error: {exc}")


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a bill by transitioning it to cancelled."""
    async for session in get_db_session(current_user.user_id):
        bill = await _load_bill_for_user(session, current_user.user_id, bill_id)
        await _update_bill_status_in_session(
            session=session,
            bill=bill,
            update=BillStatusUpdate(status="cancelled", reason="Deleted by user"),
            actor=f"user:{current_user.user_id}",
        )
        return None
