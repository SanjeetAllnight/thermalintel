"""Observation Repository for SQLite persistence and query operations.

Manages pure remote sensing observations (sensor evidence) conforming to the
frozen V2 canonical Observation contract.
CRITICAL: Limited strictly to persistence; contains no ML or incident classification logic.
"""

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from services.api.database import get_connection, init_db
from services.api.schemas.v2.observation import Observation

logger = logging.getLogger(__name__)


def row_to_observation(r: sqlite3.Row) -> Observation:
    """Convert an SQLite Row to a validated V2 Observation model."""
    keys = r.keys()
    source_attrs = {}
    if "source_attributes_json" in keys and r["source_attributes_json"]:
        try:
            source_attrs = json.loads(r["source_attributes_json"])
        except Exception:
            source_attrs = {}

    return Observation(
        observation_id=r["observation_id"],
        provider=r["provider"],
        product=r["product"],
        satellite=r["satellite"],
        instrument=r["instrument"],
        latitude=float(r["latitude"]),
        longitude=float(r["longitude"]),
        acquisition_time_utc=r["acquisition_time_utc"],
        ingestion_time_utc=r["ingestion_time_utc"],
        brightness=float(r["brightness"]),
        bright_t31=float(r["bright_t31"]) if r["bright_t31"] is not None else None,
        frp=float(r["frp"]),
        scan=float(r["scan"]) if r["scan"] is not None else None,
        track=float(r["track"]) if r["track"] is not None else None,
        daynight=r["daynight"],
        detection_confidence=r["detection_confidence"],
        source_attributes=source_attrs,
        raw_payload_id=r["raw_payload_id"] if "raw_payload_id" in keys else None,
        schema_version=r["schema_version"] if "schema_version" in keys and r["schema_version"] else "2.0",
    )


class ObservationRepository:
    """Repository managing persistence and retrieval for V2 Observation entities."""

    def __init__(self):
        init_db()

    def save_observation(self, obs: Observation) -> Observation:
        """Insert or replace a single Observation."""
        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO observations (
                        observation_id, provider, product, satellite, instrument,
                        latitude, longitude, acquisition_time_utc, ingestion_time_utc,
                        brightness, bright_t31, frp, scan, track,
                        daynight, detection_confidence, source_attributes_json,
                        raw_payload_id, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        obs.observation_id,
                        obs.provider,
                        obs.product,
                        obs.satellite,
                        obs.instrument,
                        obs.latitude,
                        obs.longitude,
                        obs.acquisition_time_utc,
                        obs.ingestion_time_utc,
                        obs.brightness,
                        obs.bright_t31,
                        obs.frp,
                        obs.scan,
                        obs.track,
                        obs.daynight,
                        obs.detection_confidence,
                        json.dumps(obs.source_attributes),
                        obs.raw_payload_id,
                        obs.schema_version,
                    ),
                )
        return obs

    def save_observations(self, observations: List[Observation]) -> int:
        """Batch insert or replace observations idempotently."""
        if not observations:
            return 0

        params = [
            (
                obs.observation_id,
                obs.provider,
                obs.product,
                obs.satellite,
                obs.instrument,
                obs.latitude,
                obs.longitude,
                obs.acquisition_time_utc,
                obs.ingestion_time_utc,
                obs.brightness,
                obs.bright_t31,
                obs.frp,
                obs.scan,
                obs.track,
                obs.daynight,
                obs.detection_confidence,
                json.dumps(obs.source_attributes),
                obs.raw_payload_id,
                obs.schema_version,
            )
            for obs in observations
        ]

        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO observations (
                        observation_id, provider, product, satellite, instrument,
                        latitude, longitude, acquisition_time_utc, ingestion_time_utc,
                        brightness, bright_t31, frp, scan, track,
                        daynight, detection_confidence, source_attributes_json,
                        raw_payload_id, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                return cursor.rowcount if cursor.rowcount > 0 else len(observations)

    def get_by_id(self, observation_id: str) -> Optional[Observation]:
        """Fetch an Observation by its deterministic ID."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM observations WHERE observation_id = ?", (observation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return row_to_observation(row)

    def get_observations(
        self,
        provider: Optional[str] = None,
        product: Optional[str] = None,
        min_frp: Optional[float] = None,
        start_time_utc: Optional[str] = None,
        end_time_utc: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Observation], int]:
        """Query observations with supported filtering, pagination, and deterministic ordering."""
        query = "SELECT * FROM observations WHERE 1=1"
        params: List[Any] = []

        if provider is not None:
            query += " AND provider = ?"
            params.append(provider)

        if product is not None:
            query += " AND product = ?"
            params.append(product)

        if min_frp is not None:
            query += " AND frp >= ?"
            params.append(float(min_frp))

        if start_time_utc is not None:
            query += " AND acquisition_time_utc >= ?"
            params.append(start_time_utc)

        if end_time_utc is not None:
            query += " AND acquisition_time_utc <= ?"
            params.append(end_time_utc)

        with get_connection() as conn:
            cursor = conn.cursor()

            count_sql = f"SELECT COUNT(*) as total FROM ({query})"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()["total"]

            query += " ORDER BY acquisition_time_utc DESC, frp DESC LIMIT ? OFFSET ?"
            query_params = list(params) + [limit, offset]

            cursor.execute(query, query_params)
            rows = cursor.fetchall()
            items = [row_to_observation(r) for r in rows]

        return items, total

    def count(self) -> int:
        """Count total observations stored."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM observations")
            return cursor.fetchone()["cnt"]

    def clear(self) -> int:
        """Delete all observations from database."""
        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as cnt FROM observations")
                cnt = cursor.fetchone()["cnt"]
                cursor.execute("DELETE FROM observations")
                return cnt


# Singleton instance
observation_repo = ObservationRepository()
