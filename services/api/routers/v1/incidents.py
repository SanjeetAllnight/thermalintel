"""V1 Persistent Incidents router for ThermalIntel API."""

from typing import List, Optional
from fastapi import APIRouter, Query, Response

from services.api.database import seed_if_empty
from services.api.incidents.service import IncidentService
from services.api.incidents.adapters import SQLiteIncidentAdapter
from services.api.routers.errors import NotFoundError, APIErrorResponse
from services.api.routers.pagination import validate_pagination_params, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.observation import Observation

router = APIRouter(tags=["V1 - Incidents"])


def _get_connection_factory():
    import sqlite3
    from services.api.database import DB_PATH
    def factory():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    return factory


def _make_incident_service() -> IncidentService:
    adapter = SQLiteIncidentAdapter(connection_factory=_get_connection_factory())
    return IncidentService(adapter=adapter)


@router.get(
    "/incidents",
    response_model=List[Incident],
    summary="Retrieve persistent incidents with lifecycle and risk filters",
    responses={
        400: {"model": APIErrorResponse, "description": "Invalid status or risk filter"},
    },
)
def get_incidents(
    response: Response,
    status: Optional[str] = Query(None, description="Comma-separated incident status filter (e.g. active,monitoring)"),
    min_risk: Optional[float] = Query(None, ge=0.0, le=100.0, description="Minimum risk score threshold"),
    page: int = Query(1, ge=1, description="1-based page index"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
):
    """Retrieve persistent incidents matching lifecycle status and risk criteria with deterministic pagination."""
    seed_if_empty()
    valid_page, valid_limit = validate_pagination_params(page=page, limit=limit)

    incident_service = _make_incident_service()
    status_list = [s.strip() for s in status.split(",")] if status else None
    all_incidents = incident_service.get_active_incidents(status=status_list, min_risk=min_risk)

    total_count = len(all_incidents)
    start_idx = (valid_page - 1) * valid_limit
    end_idx = start_idx + valid_limit
    paged_incidents = all_incidents[start_idx:end_idx]

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(valid_page)
    response.headers["X-Limit"] = str(valid_limit)
    return paged_incidents


@router.get(
    "/incidents/{id}",
    response_model=Incident,
    summary="Retrieve persistent incident by ID",
    responses={
        404: {"model": APIErrorResponse, "description": "Incident not found"},
    },
)
def get_incident_by_id(id: str):
    """Retrieve persistent incident by permanent identifier (INC-YYYYMMDD-XXXX)."""
    seed_if_empty()
    incident_service = _make_incident_service()
    inc = incident_service.get_incident_by_id(id)
    if not inc:
        raise NotFoundError(
            message=f"Incident with ID '{id}' not found",
            details={"incident_id": id},
        )
    return inc


@router.get(
    "/incidents/{id}/timeline",
    response_model=List[IncidentEvent],
    summary="Retrieve chronological lifecycle events for an incident",
    responses={
        404: {"model": APIErrorResponse, "description": "Incident not found"},
    },
)
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


@router.get(
    "/incidents/{id}/observations",
    response_model=List[Observation],
    summary="Retrieve satellite observations correlated to an incident",
    responses={
        404: {"model": APIErrorResponse, "description": "Incident not found"},
    },
)
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
