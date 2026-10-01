"""ThermalIntel API Backend Service.

Main FastAPI application entrypoint.
Exposes frozen REST API contracts on port 8000 with permissive CORS for local UI development.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from services.api.routers import api_router
from services.api.database import seed_if_empty

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and populate with fallback data if empty
    seed_if_empty()
    yield


app = FastAPI(
    title="ThermalIntel API",
    description="Geospatial AI system for satellite thermal anomaly detection, classification, and explainable risk scoring.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for local Next.js frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the frozen API router
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "service": "ThermalIntel API",
        "status": "online",
        "docs": "/docs",
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
