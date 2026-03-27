"""
Life Admin API service — FastAPI application entry point.
"""
import os
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.telemetry.setup import setup_telemetry
from shared.db.session import init_db

from services.api.middleware.rls_middleware import RLSContextMiddleware
from services.api.routers import health, auth, bills, ingestion, statements, transactions

log = structlog.get_logger()

setup_telemetry("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("API service starting")
    await init_db()
    yield
    log.info("API service shutting down")


app = FastAPI(
    title="Life Admin API",
    description="Autonomous bill management system",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Custom middleware ─────────────────────────────────────────────────────────
app.add_middleware(RLSContextMiddleware)

# ─── Routers ──────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(health.router)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(auth.legacy_router, prefix="/api")
app.include_router(bills.router, prefix=API_PREFIX)
app.include_router(ingestion.router, prefix=API_PREFIX)
app.include_router(transactions.router, prefix=API_PREFIX)
app.include_router(statements.router, prefix=API_PREFIX)
