"""
Unit tests for the Redis-based email deduplicator.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_is_duplicate_first_time():
    """First encounter → not a duplicate, Redis key set."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True  # SETNX succeeded

    with patch("services.ingestion.deduplicator._get_redis", return_value=mock_redis):
        from services.ingestion.deduplicator import is_duplicate
        result = await is_duplicate("user-1", "msg-001")

    assert result is False
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_is_duplicate_second_time():
    """Second encounter → duplicate, Redis key already exists."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = None  # SETNX failed — key already exists

    with patch("services.ingestion.deduplicator._get_redis", return_value=mock_redis):
        from services.ingestion.deduplicator import is_duplicate
        result = await is_duplicate("user-1", "msg-001")

    assert result is True


@pytest.mark.asyncio
async def test_mark_processed_extends_ttl():
    """mark_processed should call expire() with the correct TTL."""
    mock_redis = AsyncMock()

    with patch("services.ingestion.deduplicator._get_redis", return_value=mock_redis):
        from services.ingestion.deduplicator import mark_processed, DEDUP_TTL
        await mark_processed("user-1", "msg-001")

    mock_redis.expire.assert_called_once_with(
        "dedup:email:user-1:msg-001", DEDUP_TTL
    )
