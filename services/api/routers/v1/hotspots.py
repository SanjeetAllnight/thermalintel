"""V1 Hotspots router for ThermalIntel API."""

from typing import Optional
from fastapi import APIRouter, Query, Response

from services.api.database import seed_if_empty
from services.api.data.service import HotspotDataService
from services.api.incidents.service import IncidentService
from services.api.incidents.adapters import SQLiteIncidentAdapter
from services.api.routers.errors import NotFoundError, APIErrorResponse
from services.api.routers.pagination import validate_pagination_params, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.api.schemas import (
    HotspotsResponse,
    IncidentDetail,
    RiskLevel,
    SourceType,
)

router = APIRouter(tags=["V1 - Hotspots"])


def _get_connection_factory():
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


@router.get(
    "/hotspots",
    response_model=HotspotsResponse,
    summary="Retrieve filtered and paginated thermal hotspots",
    responses={
        400: {"model": APIErrorResponse, "description": "Invalid filter or pagination parameters"},
        422: {"model": APIErrorResponse, "description": "Validation error"},
    },
)
def get_hotspots(
    response: Response,
    risk_level: Optional[RiskLevel] = Query(None, description="Filter by risk category"),
    source_type: Optional[SourceType] = Query(None, description="Filter by thermal source type"),
    min_frp: Optional[float] = Query(None, ge=0.0, description="Minimum Fire Radiative Power (MW)"),
    min_confidence: Optional[str] = Query(None, description="Filter by minimum confidence (nominal, high)"),
    is_anomaly: Optional[bool] = Query(None, description="Filter by anomaly status"),
    cluster_id: Optional[str] = Query(None, description="Filter by specific cluster ID"),
    page: int = Query(1, ge=1, description="1-based page index"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    limit: Optional[int] = Query(None, ge=1, le=MAX_PAGE_SIZE, description="Items per page (alias for page_size)"),
):
    """Retrieve paginated and filtered thermal anomaly hotspots with deterministic ordering."""
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


@router.get(
    "/hotspots/{id}",
    response_model=IncidentDetail,
    summary="Retrieve full incident dossier by hotspot ID",
    responses={
        404: {"model": APIErrorResponse, "description": "Hotspot with specified ID not found"},
    },
)
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
