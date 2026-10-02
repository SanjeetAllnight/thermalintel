"""Provider Run Repository for SQLite persistence and observability telemetry.

Tracks execution outcomes, latency, throughput, and error classifications for
external provider runs (e.g. NASA FIRMS, Overpass, Open-Meteo).
CRITICAL: Never stores API keys, authentication credentials, or secrets.
"""

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from services.api.database import get_connection, init_db
from services.api.schemas.v2.common import ProviderStatus
from services.api.schemas.v2.provider import ProviderRun

logger = logging.getLogger(__name__)


def row_to_provider_run(r: sqlite3.Row) -> ProviderRun:
    """Convert an SQLite Row to a validated V2 ProviderRun model."""
    keys = r.keys()
    meta = {}
    if "request_metadata_json" in keys and r["request_metadata_json"]:
        try:
            meta = json.loads(r["request_metadata_json"])
        except Exception:
            meta = {}

    raw_status = r["status"]
    try:
        status_enum = ProviderStatus(raw_status)
    except ValueError:
        status_enum = ProviderStatus.FAILED

    return ProviderRun(
        run_id=r["run_id"],
        provider=r["provider"],
        product=r["product"],
        started_at_utc=r["started_at_utc"],
        finished_at_utc=r["finished_at_utc"],
        status=status_enum,
        rows_received=int(r["rows_received"]) if r["rows_received"] is not None else 0,
        duration_ms=int(r["duration_ms"]) if r["duration_ms"] is not None else None,
        error_type=r["error_type"],
        error_message=r["error_message"],
        request_metadata=meta,
        payload_id=r["payload_id"],
    )


class ProviderRunRepository:
    """Repository managing persistence and retrieval for ProviderRun telemetry."""

    def __init__(self):
        init_db()

    def save_run(self, run: ProviderRun) -> ProviderRun:
        """Insert or replace a ProviderRun execution record."""
        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO provider_runs (
                        run_id, provider, product, started_at_utc, finished_at_utc,
                        status, rows_received, duration_ms, error_type,
                        error_message, request_metadata_json, payload_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.provider,
                        run.product,
                        run.started_at_utc,
                        run.finished_at_utc,
                        run.status.value,
                        run.rows_received,
                        run.duration_ms,
                        run.error_type,
                        run.error_message,
                        json.dumps(run.request_metadata),
                        run.payload_id,
                    ),
                )
        return run

    def get_by_id(self, run_id: str) -> Optional[ProviderRun]:
        """Fetch a ProviderRun by ID."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM provider_runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return row_to_provider_run(row)

    def get_recent_runs(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ProviderRun]:
        """Fetch recent provider runs with optional filtering and reverse chronological ordering."""
        query = "SELECT * FROM provider_runs WHERE 1=1"
        params: List[Any] = []

        if provider is not None:
            query += " AND provider = ?"
            params.append(provider)

        if status is not None:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at_utc DESC LIMIT ?"
        params.append(limit)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [row_to_provider_run(r) for r in rows]

    def count(self) -> int:
        """Count total provider runs recorded."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM provider_runs")
            return cursor.fetchone()["cnt"]

    def clear(self) -> int:
        """Clear all provider runs from database."""
        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as cnt FROM provider_runs")
                cnt = cursor.fetchone()["cnt"]
                cursor.execute("DELETE FROM provider_runs")
                return cnt


# Singleton instance
provider_run_repo = ProviderRunRepository()
