"""
Health check router.
"""
import os
import structlog
from fastapi import APIRouter
from pydantic import BaseModel

log = structlog.get_logger()
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="lifeadmin-api",
        version=os.environ.get("APP_VERSION", "0.1.0"),
    )
