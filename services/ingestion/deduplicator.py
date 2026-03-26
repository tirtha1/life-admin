"""
Redis-based email deduplication guard.
Two layers: Redis (fast) + DB UNIQUE constraint (durable backstop).
"""
import os
import structlog
import redis.asyncio as aioredis

log = structlog.get_logger()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DEDUP_TTL = 60 * 60 * 24 * 7  # 7 days in seconds

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _dedup_key(user_id: str, message_id: str) -> str:
    return f"dedup:email:{user_id}:{message_id}"


async def is_duplicate(user_id: str, message_id: str) -> bool:
    """
    Returns True if this email has already been processed.
    Uses SETNX with 7-day TTL as a fast distributed check.
    """
    r = _get_redis()
    key = _dedup_key(user_id, message_id)

    # SETNX: only sets if key doesn't exist
    was_set = await r.set(key, "1", nx=True, ex=DEDUP_TTL)

    if was_set:
        log.debug("New email", user_id=user_id, message_id=message_id)
        return False  # Not a duplicate — we just claimed it
    else:
        log.debug("Duplicate email skipped", user_id=user_id, message_id=message_id)
        return True


async def mark_processed(user_id: str, message_id: str) -> None:
    """Extend TTL on successful processing."""
    r = _get_redis()
    key = _dedup_key(user_id, message_id)
    await r.expire(key, DEDUP_TTL)
