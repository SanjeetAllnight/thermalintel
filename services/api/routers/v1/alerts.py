"""V1 Alerts router for ThermalIntel API."""

from typing import Optional
from fastapi import APIRouter, Query, Response

from services.api.database import seed_if_empty
from services.api.alerts.service import AlertService
from services.api.alerts.health import AlertHealthMetrics
from services.api.routers.errors import NotFoundError, APIErrorResponse
from services.api.routers.pagination import validate_pagination_params, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.api.schemas import AlertsResponse, AlertSeverity

router = APIRouter(tags=["V1 - Alerts"])


def _get_connection_factory():
    import sqlite3
    from services.api.database import DB_PATH
    def factory():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    return factory


def _make_alert_service() -> AlertService:
    return AlertService(connection_factory=_get_connection_factory())


@router.get(
    "/alerts/health",
    response_model=AlertHealthMetrics,
    summary="Retrieve alert system health and noise suppression metrics",
)
def get_alerts_health(
    window_seconds: int = Query(86400, ge=60, description="Evaluation window in seconds"),
    as_of_utc: Optional[str] = Query(None, description="Snapshot reference timestamp in UTC ISO"),
    chatter_threshold: int = Query(3, ge=1, description="Threshold for chattering incident detection"),
):
    """Retrieve operational alert health metrics, noise suppression, and priority mix."""
    seed_if_empty()
    alert_service = _make_alert_service()
    return alert_service.get_alert_health(
        window_seconds=window_seconds,
        as_of_utc=as_of_utc,
        chatter_threshold=chatter_threshold,
    )


@router.get(
    "/alerts",
    response_model=AlertsResponse,
    summary="Retrieve operational risk alerts",
    responses={
        400: {"model": APIErrorResponse, "description": "Invalid query parameters"},
    },
)
def get_alerts(
    response: Response,
    severity: Optional[AlertSeverity] = Query(None, description="Filter by alert severity (info, warning, critical)"),
    unread_only: bool = Query(False, description="Filter unacknowledged alerts only"),
    page: int = Query(1, ge=1, description="1-based page index"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
):
    """Retrieve operational risk alerts and urgent notifications with deterministic pagination."""
    seed_if_empty()
    valid_page, valid_limit = validate_pagination_params(page=page, limit=limit)

    alert_service = _make_alert_service()
    raw_response = alert_service.get_alerts(severity=severity, unread_only=unread_only)

    all_items = raw_response.items
    total_count = len(all_items)
    start_idx = (valid_page - 1) * valid_limit
    end_idx = start_idx + valid_limit
    sliced_items = all_items[start_idx:end_idx]

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(valid_page)
    response.headers["X-Limit"] = str(valid_limit)

    return AlertsResponse(
        items=sliced_items,
        total=total_count,
        unread_count=raw_response.unread_count,
        generated_at=raw_response.generated_at,
    )


@router.get(
    "/alerts/{id}",
    summary="Retrieve alert by ID",
    responses={
        404: {"model": APIErrorResponse, "description": "Alert not found"},
    },
)
def get_alert_by_id(id: str):
    """Retrieve an alert by its ID (evaluates canonical alerts_v2 first, then legacy alerts)."""
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


@router.post(
    "/alerts/{id}/acknowledge",
    summary="Mark alert as acknowledged",
    responses={
        404: {"model": APIErrorResponse, "description": "Alert not found or already acknowledged"},
    },
)
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
