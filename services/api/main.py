"""ThermalIntel API Backend Service — Modernized & Hardened.

Main FastAPI application entrypoint.
Exposes modernized /api/v1 endpoints, frozen /api contracts, operational probes,
CORS protection, correlation tracking, and safe background ingestion scheduler.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from services.api.config import get_api_config
from services.api.routers import api_router, v1_router, operational_router
from services.api.routers.errors import register_error_handlers
from services.api.database import seed_if_empty
from services.api.security import get_cors_origins, RequestCorrelationMiddleware
from services.api.scheduler import get_scheduler

load_dotenv()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and populate with fallback data if empty
    seed_if_empty()

    # Phase 3: Start background ingestion scheduler if enabled
    scheduler = get_scheduler()
    if scheduler.config.enabled:
        logger.info("Initializing and starting background ingestion scheduler...")
        await scheduler.start()

    yield

    # Phase 3: Gracefully shut down background scheduler
    if scheduler.is_running:
        logger.info("Shutting down background ingestion scheduler...")
        await scheduler.stop()


cfg = get_api_config()

app = FastAPI(
    title=cfg.title,
    description=cfg.description,
    version=cfg.version,
    lifespan=lifespan,
    docs_url=cfg.docs_url,
    redoc_url=cfg.redoc_url,
)

# 1. Register structured API error handlers
register_error_handlers(app)

# 2. Add Request Correlation ID Middleware (outermost for all requests)
app.add_middleware(RequestCorrelationMiddleware)

# 3. Enable configuration-driven CORS without wildcards
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# 4. Include routers: Operational probes, Modernized V1, and Frozen Legacy Contract
app.include_router(operational_router)
app.include_router(v1_router)
app.include_router(api_router)


@app.get("/")
def root():
    scheduler = get_scheduler()
    return {
        "service": "ThermalIntel API",
        "version": cfg.version,
        "status": "online",
        "docs": "/docs",
        "redoc": "/redoc",
        "operational_probes": [
            "GET /healthz",
            "GET /readyz",
            "GET /metrics",
        ],
        "v1_surface_prefix": "/api/v1",
        "scheduler": {
            "enabled": scheduler.config.enabled,
            "running": scheduler.is_running,
            "interval_seconds": scheduler.interval_seconds,
        },
        "frozen_contract_endpoints": [
            "GET /api/health",
            "GET /api/hotspots",
            "GET /api/hotspots/{id}",
            "GET /api/summary",
            "GET /api/alerts",
            "GET /api/sources",
            "POST /api/refresh",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("services.api.main:app", host="0.0.0.0", port=port, reload=True)
