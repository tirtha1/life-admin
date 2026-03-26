"""
Bills router — CRUD + agent trigger endpoints.
All routes are RLS-protected via get_current_user dependency.
"""
import structlog
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.session import get_db_session
from shared.db.models import Bill, BillStatus, BillTransition, validate_transition

from services.api.security import CurrentUser, get_current_user

log = structlog.get_logger()

router = APIRouter(prefix="/bills", tags=["bills"])


# ─── Response schemas ─────────────────────────────────────────────────────────

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
    def from_orm_bill(cls, b: Bill) -> "BillRead":
        return cls(
            id=b.id,
            provider=b.provider,
            bill_type=b.bill_type,
            amount=float(b.amount) if b.amount else None,
            currency=b.currency,
            due_date=b.due_date,
            status=b.status.value.lower(),
            extraction_confidence=float(b.extraction_confidence) if b.extraction_confidence else None,
            is_overdue=b.is_overdue,
            is_recurring=b.is_recurring,
            needs_review=b.needs_review,
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


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("", response_model=list[BillRead])
async def list_bills(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List bills for the authenticated user."""
    async for session in get_db_session(current_user.user_id):
        q = select(Bill).where(Bill.user_id == current_user.user_id)
        if status_filter:
            try:
                q = q.where(Bill.status == BillStatus(status_filter.lower()))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}",
                )
        q = q.order_by(Bill.due_date.asc().nullslast(), Bill.created_at.desc())
        q = q.limit(limit).offset(offset)
        result = await session.execute(q)
        bills = result.scalars().all()
        return [BillRead.from_orm_bill(b) for b in bills]


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
                and_(Bill.user_id == current_user.user_id, Bill.status == BillStatus.CONFIRMED)
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


@router.get("/{bill_id}", response_model=BillRead)
async def get_bill(
    bill_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Fetch a single bill by ID."""
    async for session in get_db_session(current_user.user_id):
        result = await session.execute(
            select(Bill).where(
                Bill.id == bill_id, Bill.user_id == current_user.user_id
            )
        )
        bill = result.scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        return BillRead.from_orm_bill(bill)


@router.patch("/{bill_id}/status", response_model=BillRead)
async def update_bill_status(
    bill_id: UUID,
    update: BillStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update bill status (with state machine validation)."""
    async for session in get_db_session(current_user.user_id):
        result = await session.execute(
            select(Bill).where(
                Bill.id == bill_id, Bill.user_id == current_user.user_id
            )
        )
        bill = result.scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")

        try:
            new_status = BillStatus(update.status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

        old_status = bill.status

        # Validate transition via state machine guard
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
            actor=f"user:{current_user.user_id}",
        )
        session.add(transition)
        await session.commit()
        await session.refresh(bill)
        return BillRead.from_orm_bill(bill)


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a bill (sets status to cancelled)."""
    async for session in get_db_session(current_user.user_id):
        result = await session.execute(
            select(Bill).where(
                Bill.id == bill_id, Bill.user_id == current_user.user_id
            )
        )
        bill = result.scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")

        old_status = bill.status
        bill.status = BillStatus.CANCELLED
        transition = BillTransition(
            bill_id=bill.id,
            from_status=old_status,
            to_status=BillStatus.CANCELLED,
            reason="Deleted by user",
            actor=f"user:{current_user.user_id}",
        )
        session.add(transition)
        await session.commit()
