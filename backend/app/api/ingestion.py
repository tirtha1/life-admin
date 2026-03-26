"""
Ingestion API — Gmail sync, OAuth flow, manual bill submission.
"""
import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.models.bill import Bill, BillStatus
from app.schemas.bill import SyncResult
from app.services import gmail_service
from app.services.bill_extractor import (
    extract_bill_from_email,
    parse_due_date,
    normalize_bill_type,
)
from app.services.agent.bill_agent import run_bill_agent

log = structlog.get_logger()
router = APIRouter()
settings = get_settings()


# ─── Gmail OAuth2 ─────────────────────────────────────────────────────────────

@router.get("/oauth/start")
async def oauth_start():
    """Redirect user to Google OAuth consent screen."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    url = gmail_service.get_oauth_url()
    return RedirectResponse(url=url)


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str = ""):
    """
    Handle OAuth callback. Exchanges code for refresh token.
    In production, store this token securely (DB / secrets manager).
    """
    try:
        refresh_token = gmail_service.exchange_oauth_code(code)
        return {
            "message": "OAuth successful! Copy this refresh token to your .env file.",
            "refresh_token": refresh_token,
            "instruction": "Set GOOGLE_REFRESH_TOKEN=<token_above> in your .env file and restart.",
        }
    except Exception as e:
        log.error("OAuth callback failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")


# ─── Gmail Sync ───────────────────────────────────────────────────────────────

async def _process_emails(db: AsyncSession) -> SyncResult:
    """
    Full pipeline: Gmail → bill filter → Claude extraction → DB + agent.
    """
    emails = await gmail_service.fetch_bill_emails(max_results=50, days_back=30)

    result = SyncResult(emails_scanned=len(emails), bills_detected=0, bills_new=0, bills_skipped=0)

    for email in emails:
        try:
            # Check for duplicate
            existing = await db.execute(
                select(Bill).where(Bill.email_id == email.message_id)
            )
            if existing.scalar_one_or_none():
                result.bills_skipped += 1
                continue

            # Claude extraction
            extraction = await extract_bill_from_email(email.text_for_extraction())

            if not extraction.is_bill:
                log.debug("Email not a bill, skipping", subject=email.subject)
                continue

            result.bills_detected += 1

            # Create DB record
            bill = Bill(
                email_id=email.message_id,
                email_subject=email.subject,
                email_sender=email.sender,
                raw_email_body=email.body[:5000],
                provider=extraction.provider,
                bill_type=normalize_bill_type(extraction.bill_type),
                amount=extraction.amount,
                currency=extraction.currency,
                due_date=parse_due_date(extraction.due_date),
                billing_period=extraction.billing_period,
                status=BillStatus.PENDING,
                extraction_confidence=extraction.confidence,
                processed_at=datetime.utcnow(),
            )
            db.add(bill)
            await db.flush()
            await db.refresh(bill)

            result.bills_new += 1
            log.info(
                "Bill created",
                bill_id=bill.id,
                provider=bill.provider,
                amount=bill.amount,
                due_date=bill.due_date,
            )

            # Run agent immediately for newly detected bills
            try:
                await run_bill_agent(bill)
            except Exception as agent_err:
                log.error("Agent failed for new bill", bill_id=bill.id, error=str(agent_err))
                result.errors.append(f"Agent error for bill {bill.id}: {str(agent_err)[:80]}")

        except Exception as e:
            log.error("Error processing email", subject=email.subject, error=str(e))
            result.errors.append(f"Email '{email.subject[:50]}': {str(e)[:80]}")
            continue

    await db.commit()
    return result


@router.post("/sync", response_model=SyncResult)
async def sync_gmail(db: AsyncSession = Depends(get_db)):
    """
    Trigger Gmail sync: fetch → detect bills → extract → run agent.
    Runs synchronously and returns results.
    """
    log.info("Starting Gmail sync")
    try:
        result = await _process_emails(db)
        log.info(
            "Gmail sync complete",
            scanned=result.emails_scanned,
            new=result.bills_new,
            skipped=result.bills_skipped,
        )
        return result
    except Exception as e:
        log.error("Gmail sync failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/background")
async def sync_gmail_background(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Kick off Gmail sync as a background task (non-blocking)."""

    async def _bg_sync():
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await _process_emails(session)

    background_tasks.add_task(_bg_sync)
    return {"message": "Gmail sync started in background"}


# ─── Manual bill submission (no Gmail) ────────────────────────────────────────

class ManualBillInput:
    """For direct bill submission via API (no email)."""
    pass


@router.post("/manual", response_model=dict)
async def submit_manual_bill(
    provider: str,
    amount: float,
    due_date: str,
    bill_type: str = "other",
    currency: str = "INR",
    db: AsyncSession = Depends(get_db),
):
    """
    Manually add a bill without Gmail.
    Useful for SMS alerts or manual entry from dashboard.
    """
    from app.services.bill_extractor import parse_due_date, normalize_bill_type

    bill = Bill(
        provider=provider,
        bill_type=normalize_bill_type(bill_type),
        amount=amount,
        currency=currency,
        due_date=parse_due_date(due_date),
        status=BillStatus.PENDING,
        processed_at=datetime.utcnow(),
        extraction_confidence=1.0,
    )
    db.add(bill)
    await db.flush()
    await db.refresh(bill)

    # Run agent
    try:
        final_state = await run_bill_agent(bill)
        action = final_state["action"]
    except Exception as e:
        action = "error"
        log.error("Agent failed for manual bill", error=str(e))

    await db.commit()
    return {
        "bill_id": bill.id,
        "status": "created",
        "agent_action": action,
    }
