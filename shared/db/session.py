"""
Async SQLAlchemy session factory.
Supports Row-Level Security via SET LOCAL app.current_user_id.

Two session types:
  get_db_session(user_id)   — RLS-enforced, for user-facing API routes
  get_db_session_system()   — No RLS, for internal services

Both are async generators compatible with FastAPI Depends AND direct async for loops.
"""
import os
import structlog
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

log = structlog.get_logger()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://lifeadmin:lifeadmin123@localhost:5432/lifeadmin",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("ENVIRONMENT", "development") == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Test DB connectivity on startup. Raises if DB is unreachable."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    log.info("Database connection verified")


async def get_db_session(user_id: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator yielding a DB session with RLS context set for user_id.
    Compatible with both FastAPI Depends and direct `async for` iteration.
    Enforces row-level security via SET LOCAL app.current_user_id.
    """
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": user_id},
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session_system() -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator yielding a DB session WITHOUT RLS.
    Use only in internal services — never in user-facing API routes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
