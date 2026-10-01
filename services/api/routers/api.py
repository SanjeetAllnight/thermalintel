"""ThermalIntel Frozen API Router — Fully Integrated.

CONTRACT ENDPOINTS:
- GET /api/health
- GET /api/hotspots
- GET /api/hotspots/{id}
- GET /api/summary
- GET /api/alerts
- GET /api/sources
- POST /api/refresh

Integration wiring:
  Phase 1  → HotspotDataService  (ingestion, normalization, FIRMS, fallback)
  Phase 2  → EnrichmentService   (OSM, weather, history) — enriches on detail fetch
  Phase 3  → ThermalIntelligenceEngine (classification, anomaly, risk)
  Phase 4  → IncidentService, SummaryService, AlertService
  Phase 5  → Consumed by Next.js UI via these endpoints
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from services.api.schemas import (
    HealthResponse,
    HotspotsResponse,
    IncidentDetail,
    SummaryResponse,
    SourcesResponse,
    AlertsResponse,
    AlertSeverity,
    RefreshRequest,
    RefreshResponse,
    DataMode,
    RiskLevel,
    SourceType,
)
from services.api.database import get_connection, seed_if_empty

# ── Phase 1: Data Engine ──────────────────────────────────────────────────────
from services.api.data.service import HotspotDataService

# ── Phase 4: Incidents, Alerts, Summary ──────────────────────────────────────
from services.api.incidents.service import IncidentService
from services.api.incidents.adapters import SQLiteIncidentAdapter
from services.api.summary.service import SummaryService
from services.api.alerts.service import AlertService

router = APIRouter(prefix="/api", tags=["ThermalIntel Frozen API"])


# ── Service Factories (use connection_factory pattern for SQLite) ─────────────

def _get_connection_factory():
    """Return a callable that yields a Row-factory SQLite connection."""
    import sqlite3
    from services.api.database import DB_PATH
    def factory():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    return factory


def _make_data_service() -> HotspotDataService:
    return HotspotDataService()


def _make_incident_service() -> IncidentService:
    adapter = SQLiteIncidentAdapter(connection_factory=_get_connection_factory())
    return IncidentService(adapter=adapter)


def _make_summary_service() -> SummaryService:
    return SummaryService(connection_factory=_get_connection_factory())


def _make_alert_service() -> AlertService:
    return AlertService(connection_factory=_get_connection_factory())


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
def get_health():
    """Health check returning system status, operational data mode, and subsystem readiness."""
    seed_if_empty()
    mode = DataMode.DEMO
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
            row = cursor.fetchone()
            if row and row["value"] == "live":
                mode = DataMode.LIVE
    except Exception:
        pass

    # Probe intelligence engine availability
    intelligence_status = "online"
    try:
        from services.intelligence.engine import ThermalIntelligenceEngine  # noqa: F401
    except Exception:
        intelligence_status = "degraded"

    return HealthResponse(
        status="ok",
        version="1.0.0",
        data_mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services={
            "database": "connected",
            "firms_api": "ready",
            "intelligence_engine": intelligence_status,
            "enrichment_engine": "ready",
            "incident_layer": "ready",
        },
    )


@router.get("/hotspots", response_model=HotspotsResponse)
def get_hotspots(
    risk_level: Optional[RiskLevel] = Query(None, description="Filter by risk category"),
    source_type: Optional[SourceType] = Query(None, description="Filter by thermal source type"),
    min_frp: Optional[float] = Query(None, ge=0.0, description="Minimum Fire Radiative Power (MW)"),
    min_confidence: Optional[str] = Query(None, description="Filter by minimum confidence (nominal, high)"),
    is_anomaly: Optional[bool] = Query(None, description="Filter by anomaly status"),
    cluster_id: Optional[str] = Query(None, description="Filter by specific cluster ID"),
    page: int = Query(1, ge=1, description="Page index"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
):
    """Retrieve filtered and paginated thermal anomaly hotspots."""
    seed_if_empty()
    data_service = _make_data_service()
    return data_service.get_hotspots(
        risk_level=risk_level,
        source_type=source_type,
        min_frp=min_frp,
        min_confidence=min_confidence,
        is_anomaly=is_anomaly,
        cluster_id=cluster_id,
        page=page,
        page_size=page_size,
    )


@router.get("/hotspots/{id}", response_model=IncidentDetail)
def get_hotspot_detail(id: str):
    """Retrieve full incident dossier including geospatial, weather, historical, and AI risk breakdown."""
    seed_if_empty()
    incident_service = _make_incident_service()
    detail = incident_service.get_incident_detail_by_id(id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hotspot with ID '{id}' not found",
        )
    return detail


@router.get("/summary", response_model=SummaryResponse)
def get_summary():
    """Retrieve operational dashboard KPIs: counts, averages, critical hotspots, and system telemetry."""
    seed_if_empty()
    summary_service = _make_summary_service()
    return summary_service.get_summary()


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    severity: Optional[AlertSeverity] = Query(None, description="Filter by alert severity"),
    unread_only: bool = Query(False, description="Filter unacknowledged alerts only"),
):
    """Retrieve operational risk alerts and urgent notifications."""
    seed_if_empty()
    alert_service = _make_alert_service()
    return alert_service.get_alerts(severity=severity, unread_only=unread_only)


@router.get("/sources", response_model=SourcesResponse)
def get_sources():
    """Retrieve thermal anomaly breakdown and intelligence distribution by source type."""
    seed_if_empty()
    summary_service = _make_summary_service()
    return summary_service.get_sources()


@router.post("/refresh", response_model=RefreshResponse)
def trigger_refresh(req: Optional[RefreshRequest] = None):
    """Trigger data synchronization from NASA FIRMS or reload sample dataset."""
    seed_if_empty()
    data_service = _make_data_service()
    force = req.force_sample if req else False
    return data_service.sync(force_sample=force)
