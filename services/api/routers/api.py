"""ThermalIntel Frozen API Router — Modernized and Hardened.

CONTRACT ENDPOINTS:
- GET /api/health
- GET /api/hotspots
- GET /api/hotspots/{id}
- GET /api/summary
- GET /api/alerts/health
- GET /api/alerts
- GET /api/alerts/{id}
- POST /api/alerts/{id}/acknowledge
- GET /api/incidents
- GET /api/incidents/{id}
- GET /api/incidents/{id}/timeline
- GET /api/incidents/{id}/observations
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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.api.security import verify_admin_key, verify_refresh_rate_limit
from services.api.scheduler.orchestrator import get_refresh_orchestrator
from services.api.routers.errors import NotFoundError, APIErrorResponse
from services.api.routers.pagination import (
    validate_pagination_params,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
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
from services.api.alerts.health import AlertHealthMetrics
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.observation import Observation
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
        version="2.0.0",
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
    response: Response,
    risk_level: Optional[RiskLevel] = Query(None, description="Filter by risk category"),
    source_type: Optional[SourceType] = Query(None, description="Filter by thermal source type"),
    min_frp: Optional[float] = Query(None, ge=0.0, description="Minimum Fire Radiative Power (MW)"),
    min_confidence: Optional[str] = Query(None, description="Filter by minimum confidence (nominal, high)"),
    is_anomaly: Optional[bool] = Query(None, description="Filter by anomaly status"),
    cluster_id: Optional[str] = Query(None, description="Filter by specific cluster ID"),
    page: int = Query(1, ge=1, description="Page index"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    limit: Optional[int] = Query(None, ge=1, le=MAX_PAGE_SIZE, description="Items per page (alias for page_size)"),
):
    """Retrieve filtered and paginated thermal anomaly hotspots with deterministic ordering."""
    seed_if_empty()
    valid_page, valid_limit = validate_pagination_params(page=page, page_size=page_size, limit=limit)

    data_service = _make_data_service()
    res = data_service.get_hotspots(
        risk_level=risk_level,
        source_type=source_type,
        min_frp=min_frp,
        min_confidence=min_confidence,
        is_anomaly=is_anomaly,
        cluster_id=cluster_id,
        page=valid_page,
        page_size=valid_limit,
    )

    response.headers["X-Total-Count"] = str(res.total)
    response.headers["X-Page"] = str(valid_page)
    response.headers["X-Page-Size"] = str(valid_limit)
    return res


@router.get("/hotspots/{id}", response_model=IncidentDetail)
def get_hotspot_detail(id: str):
    """Retrieve full incident dossier including geospatial, weather, historical, and AI risk breakdown."""
    seed_if_empty()
    incident_service = _make_incident_service()
    detail = incident_service.get_incident_detail_by_id(id)
    if not detail:
        raise NotFoundError(
            message=f"Hotspot with ID '{id}' not found",
            details={"hotspot_id": id},
        )
    return detail


@router.get("/summary", response_model=SummaryResponse)
def get_summary():
    """Retrieve operational dashboard KPIs: counts, averages, critical hotspots, and system telemetry."""
    seed_if_empty()
    summary_service = _make_summary_service()
    return summary_service.get_summary()


# ── Alerts Routes (health must precede parameterized /{id}) ──────────────────

@router.get("/alerts/health", response_model=AlertHealthMetrics)
def get_alerts_health(
    window_seconds: int = Query(86400, ge=60, description="Evaluation window in seconds"),
    as_of_utc: Optional[str] = Query(None, description="Snapshot reference timestamp in UTC ISO"),
    chatter_threshold: int = Query(3, ge=1, description="Threshold for chattering incident detection"),
):
    """Retrieve operational alert health metrics and noise suppression telemetry."""
    seed_if_empty()
    alert_service = _make_alert_service()
    return alert_service.get_alert_health(
        window_seconds=window_seconds,
        as_of_utc=as_of_utc,
        chatter_threshold=chatter_threshold,
    )


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    response: Response,
    severity: Optional[AlertSeverity] = Query(None, description="Filter by alert severity"),
    unread_only: bool = Query(False, description="Filter unacknowledged alerts only"),
    page: int = Query(1, ge=1, description="1-based page index"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
):
    """Retrieve operational risk alerts and urgent notifications with deterministic pagination."""
    seed_if_empty()
    valid_page, valid_limit = validate_pagination_params(page=page, limit=limit)

    alert_service = _make_alert_service()
    raw = alert_service.get_alerts(severity=severity, unread_only=unread_only)

    all_items = raw.items
    total_count = len(all_items)
    start_idx = (valid_page - 1) * valid_limit
    end_idx = start_idx + valid_limit
    sliced = all_items[start_idx:end_idx]

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(valid_page)
    response.headers["X-Limit"] = str(valid_limit)

    return AlertsResponse(
        items=sliced,
        total=total_count,
        unread_count=raw.unread_count,
        generated_at=raw.generated_at,
    )


@router.get("/alerts/{id}")
def get_alert_by_id(id: str):
    """Retrieve an alert by its ID (checks canonical alerts_v2 first, then legacy alerts)."""
    seed_if_empty()
    alert_service = _make_alert_service()
    v2_alert = alert_service.get_alert_v2_by_id(id)
    if v2_alert:
        return v2_alert
    alerts_resp = alert_service.get_alerts()
    for item in alerts_resp.items:
        if item.id == id:
            return item
    raise NotFoundError(
        message=f"Alert with ID '{id}' not found",
        details={"alert_id": id},
    )


@router.post("/alerts/{id}/acknowledge")
def acknowledge_alert(id: str):
    """Mark an alert as acknowledged persistently in SQLite."""
    seed_if_empty()
    alert_service = _make_alert_service()
    updated = alert_service.acknowledge_alert_v2(id)
    if not updated:
        updated = alert_service.acknowledge_alert(id)
    if not updated:
        raise NotFoundError(
            message=f"Alert with ID '{id}' not found or already acknowledged",
            details={"alert_id": id},
        )
    return {"status": "ok", "alert_id": id, "acknowledged": True}


# ── Canonical Persistent Incidents Routes ────────────────────────────────────

@router.get("/incidents", response_model=List[Incident])
def get_incidents(
    response: Response,
    status: Optional[str] = Query(None, description="Comma-separated incident status filter"),
    min_risk: Optional[float] = Query(None, ge=0.0, le=100.0, description="Minimum risk score"),
    page: int = Query(1, ge=1, description="1-based page index"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
):
    """Retrieve persistent incidents matching lifecycle status and risk criteria."""
    seed_if_empty()
    valid_page, valid_limit = validate_pagination_params(page=page, limit=limit)

    incident_service = _make_incident_service()
    status_list = [s.strip() for s in status.split(",")] if status else None
    all_incidents = incident_service.get_active_incidents(status=status_list, min_risk=min_risk)

    total_count = len(all_incidents)
    start_idx = (valid_page - 1) * valid_limit
    end_idx = start_idx + valid_limit
    paged = all_incidents[start_idx:end_idx]

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(valid_page)
    response.headers["X-Limit"] = str(valid_limit)
    return paged


@router.get("/incidents/{id}", response_model=Incident)
def get_incident_by_id(id: str):
    """Retrieve persistent incident by permanent identifier."""
    seed_if_empty()
    incident_service = _make_incident_service()
    inc = incident_service.get_incident_by_id(id)
    if not inc:
        raise NotFoundError(
            message=f"Incident with ID '{id}' not found",
            details={"incident_id": id},
        )
    return inc


@router.get("/incidents/{id}/timeline", response_model=List[IncidentEvent])
def get_incident_timeline(id: str):
    """Retrieve chronological immutable lifecycle events for an incident."""
    seed_if_empty()
    incident_service = _make_incident_service()
    inc = incident_service.get_incident_by_id(id)
    if not inc:
        raise NotFoundError(
            message=f"Incident with ID '{id}' not found",
            details={"incident_id": id},
        )
    return incident_service.get_incident_timeline(id)


@router.get("/incidents/{id}/observations", response_model=List[Observation])
def get_incident_observations(id: str):
    """Retrieve satellite observations correlated to an incident."""
    seed_if_empty()
    incident_service = _make_incident_service()
    inc = incident_service.get_incident_by_id(id)
    if not inc:
        raise NotFoundError(
            message=f"Incident with ID '{id}' not found",
            details={"incident_id": id},
        )
    return incident_service.get_incident_observations(id)


# ── Analytics & Refresh Routes ───────────────────────────────────────────────

@router.get("/sources", response_model=SourcesResponse)
def get_sources():
    """Retrieve thermal anomaly breakdown and intelligence distribution by source type."""
    seed_if_empty()
    summary_service = _make_summary_service()
    return summary_service.get_sources()


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    dependencies=[Depends(verify_admin_key), Depends(verify_refresh_rate_limit)],
)
async def trigger_refresh(req: Optional[RefreshRequest] = None):
    """Trigger data synchronization from NASA FIRMS or reload sample dataset.
    
    Protected mutation endpoint:
    - requires X-API-Key header when ADMIN_API_KEY is configured
    - protected by in-process rate limiting
    - single-flight execution sharing across concurrent callers and scheduler
    """
    seed_if_empty()
    force = req.force_sample if req else False
    orchestrator = get_refresh_orchestrator()
    return await orchestrator.execute_refresh(
        force_sample=force,
        trigger="manual",
        wait_if_in_flight=True,
    )
