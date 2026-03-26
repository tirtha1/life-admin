"""
Two-layer idempotency guard for action execution.
Layer 1: Redis SET NX (fast, distributed)
Layer 2: DB action.status check (durable backstop)
"""
import os
import structlog
import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Action, ActionStatus

log = structlog.get_logger()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
ACTION_TTL = 60 * 60 * 24 * 3  # 3 days — action execution window

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _redis_key(idempotency_key: str) -> str:
    return f"action:lock:{idempotency_key}"


async def claim_action(
    session: AsyncSession,
    idempotency_key: str,
) -> tuple[bool, Action | None]:
    """
    Attempt to claim an action for execution.

    Returns:
        (True, action) if this worker claimed the action
        (False, action) if already claimed or completed
        (False, None) if action not found in DB
    """
    # Layer 2 check: DB status
    result = await session.execute(
        select(Action).where(Action.idempotency_key == idempotency_key)
    )
    action = result.scalar_one_or_none()

    if not action:
        log.warning("Action not found in DB", idempotency_key=idempotency_key)
        return False, None

    if action.status in (ActionStatus.SUCCESS, ActionStatus.SKIPPED):
        log.debug(
            "Action already completed",
            idempotency_key=idempotency_key,
            status=action.status.value,
        )
        return False, action

    # Layer 1: Redis SET NX (distributed lock)
    r = _get_redis()
    redis_key = _redis_key(idempotency_key)
    claimed = await r.set(redis_key, "1", nx=True, ex=ACTION_TTL)

    if not claimed:
        log.debug(
            "Action already locked by another worker",
            idempotency_key=idempotency_key,
        )
        return False, action

    # Mark action as in-progress in DB
    from datetime import datetime, timezone
    await session.execute(
        update(Action)
        .where(Action.idempotency_key == idempotency_key)
        .values(
            status=ActionStatus.PENDING,
            attempted_at=datetime.now(timezone.utc),
        )
    )
    log.info("Action claimed", idempotency_key=idempotency_key, action_id=str(action.id))
    return True, action


async def complete_action(
    session: AsyncSession,
    action: Action,
    success: bool,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Mark action as success or failed in DB."""
    from datetime import datetime, timezone

    new_status = ActionStatus.SUCCESS if success else ActionStatus.FAILED
    await session.execute(
        update(Action)
        .where(Action.id == action.id)
        .values(
            status=new_status,
            result=result,
            error_message=error,
            completed_at=datetime.now(timezone.utc),
        )
    )
    log.info(
        "Action completed",
        action_id=str(action.id),
        status=new_status.value,
        idempotency_key=action.idempotency_key,
    )
