"""
Ingestion router — trigger Gmail sync for the authenticated user.
"""
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from services.api.security import CurrentUser, get_current_user

log = structlog.get_logger()

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class SyncResponse(BaseModel):
    message: str
    user_id: str


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Trigger an immediate Gmail poll for the authenticated user.
    Dispatches a Celery task asynchronously.
    """
    try:
        from services.ingestion.tasks import poll_inbox
        poll_inbox.delay(current_user.user_id)
        log.info("Sync triggered", user_id=current_user.user_id)
    except Exception as exc:
        log.error("Failed to dispatch sync task", error=str(exc))
        raise HTTPException(status_code=503, detail="Ingestion service unavailable")

    return SyncResponse(
        message="Sync triggered — processing in background",
        user_id=current_user.user_id,
    )
