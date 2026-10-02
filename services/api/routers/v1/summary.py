"""V1 Summary and Sources router for ThermalIntel API."""

from fastapi import APIRouter

from services.api.database import seed_if_empty
from services.api.summary.service import SummaryService
from services.api.schemas import SummaryResponse, SourcesResponse

router = APIRouter(tags=["V1 - Analytics & Summary"])


def _get_connection_factory():
    import sqlite3
    from services.api.database import DB_PATH
    def factory():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    return factory


def _make_summary_service() -> SummaryService:
    return SummaryService(connection_factory=_get_connection_factory())


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="Retrieve operational dashboard KPIs",
)
def get_summary():
    """Retrieve operational dashboard KPIs: counts, averages, critical hotspots, and dominant source."""
    seed_if_empty()
    summary_service = _make_summary_service()
    return summary_service.get_summary()


@router.get(
    "/sources",
    response_model=SourcesResponse,
    summary="Retrieve categorical thermal source breakdown",
)
def get_sources():
    """Retrieve thermal anomaly breakdown and intelligence distribution by source type."""
    seed_if_empty()
    summary_service = _make_summary_service()
    return summary_service.get_sources()
