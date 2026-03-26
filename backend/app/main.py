import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import create_tables
from app.core.config import get_settings
from app.api import bills, ingestion, health

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Life Admin API", env=settings.environment)
    await create_tables()
    log.info("Database tables ready")
    yield
    log.info("Shutting down Life Admin API")


app = FastAPI(
    title="Life Admin Autonomous System",
    description="AI-powered bill detection, tracking, and action engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(bills.router, prefix="/api/bills", tags=["bills"])
app.include_router(ingestion.router, prefix="/api/ingestion", tags=["ingestion"])


@app.get("/")
async def root():
    return {
        "name": "Life Admin Autonomous System",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }
