"""Hotspot Repository for SQLite persistence and query operations."""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union

from services.api.database import get_connection, init_db, invalidate_seed_cache
from services.api.schemas import Hotspot, RiskLevel, SourceType, DataMode

logger = logging.getLogger(__name__)


@contextmanager
def open_db():
    """Context manager ensuring connection is always closed cleanly."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def row_to_hotspot(r: sqlite3.Row) -> Hotspot:
    """Convert an SQLite Row object to a validated Hotspot Pydantic model."""
    st_val = r["source_type"]
    source_type = (
        SourceType(st_val)
        if st_val in SourceType._value2member_map_
        else SourceType.UNKNOWN
    )

    rl_val = r["risk_level"]
    risk_level = (
        RiskLevel(rl_val)
        if rl_val in RiskLevel._value2member_map_
        else RiskLevel.MEDIUM
    )

    return Hotspot(
        id=r["id"],
        latitude=r["latitude"],
        longitude=r["longitude"],
        brightness=r["brightness"],
        scan=r["scan"] if r["scan"] is not None else 0.375,
        track=r["track"] if r["track"] is not None else 0.375,
        acq_date=r["acq_date"],
        acq_time=r["acq_time"],
        satellite=r["satellite"],
        instrument=r["instrument"] or "VIIRS",
        confidence=r["confidence"],
        version=r["version"] or "2.0NRT",
        bright_t31=r["bright_t31"],
        frp=r["frp"],
        daynight=r["daynight"],
        source_type=source_type,
        risk_score=r["risk_score"],
        risk_level=risk_level,
        is_anomaly=bool(r["is_anomaly"]),
        cluster_id=r["cluster_id"],
        cluster_size=r["cluster_size"] if r["cluster_size"] is not None else 1,
        nearest_place=r["nearest_place"],
        last_updated=r["last_updated"],
    )


class HotspotRepository:
    """Repository managing persistence, retrieval, and filtering for Hotspot entities."""

    def __init__(self):
        init_db()

    def save_hotspot(self, hotspot: Hotspot, data_mode: str = "demo") -> Hotspot:
        """Insert or replace a single Hotspot in the database."""
        with open_db() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO hotspots (
                        id, latitude, longitude, brightness, scan, track,
                        acq_date, acq_time, satellite, instrument, confidence,
                        version, bright_t31, frp, daynight, source_type,
                        risk_score, risk_level, is_anomaly, cluster_id,
                        cluster_size, nearest_place, last_updated, data_mode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hotspot.id,
                        hotspot.latitude,
                        hotspot.longitude,
                        hotspot.brightness,
                        hotspot.scan,
                        hotspot.track,
                        hotspot.acq_date,
                        hotspot.acq_time,
                        hotspot.satellite,
                        hotspot.instrument,
                        hotspot.confidence,
                        hotspot.version,
                        hotspot.bright_t31,
                        hotspot.frp,
                        hotspot.daynight,
                        hotspot.source_type.value,
                        hotspot.risk_score,
                        hotspot.risk_level.value,
                        1 if hotspot.is_anomaly else 0,
                        hotspot.cluster_id,
                        hotspot.cluster_size or 1,
                        hotspot.nearest_place,
                        hotspot.last_updated,
                        data_mode,
                    ),
                )
        return hotspot

    def upsert_hotspots(self, hotspots: List[Hotspot], data_mode: str = "demo") -> int:
        """Batch insert or replace hotspots to avoid uncontrolled duplication."""
        if not hotspots:
            return 0

        params = [
            (
                h.id,
                h.latitude,
                h.longitude,
                h.brightness,
                h.scan,
                h.track,
                h.acq_date,
                h.acq_time,
                h.satellite,
                h.instrument,
                h.confidence,
                h.version,
                h.bright_t31,
                h.frp,
                h.daynight,
                h.source_type.value,
                h.risk_score,
                h.risk_level.value,
                1 if h.is_anomaly else 0,
                h.cluster_id,
                h.cluster_size or 1,
                h.nearest_place,
                h.last_updated,
                data_mode,
            )
            for h in hotspots
        ]

        with open_db() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO hotspots (
                        id, latitude, longitude, brightness, scan, track,
                        acq_date, acq_time, satellite, instrument, confidence,
                        version, bright_t31, frp, daynight, source_type,
                        risk_score, risk_level, is_anomaly, cluster_id,
                        cluster_size, nearest_place, last_updated, data_mode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                return cursor.rowcount if cursor.rowcount > 0 else len(hotspots)

    def get_by_id(self, hotspot_id: str) -> Optional[Hotspot]:
        """Fetch a single Hotspot by its unique identifier."""
        with open_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hotspots WHERE id = ?", (hotspot_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return row_to_hotspot(row)

    def get_hotspots(
        self,
        risk_level: Optional[Union[RiskLevel, str]] = None,
        source_type: Optional[Union[SourceType, str]] = None,
        min_frp: Optional[float] = None,
        min_confidence: Optional[str] = None,
        is_anomaly: Optional[bool] = None,
        cluster_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Hotspot], int]:
        """Query hotspots with multi-field filtering, pagination, and stable ordering."""
        query = "SELECT * FROM hotspots WHERE 1=1"
        params: List[Any] = []

        if risk_level is not None:
            rl_val = risk_level.value if isinstance(risk_level, RiskLevel) else str(risk_level)
            query += " AND risk_level = ?"
            params.append(rl_val)

        if source_type is not None:
            st_val = source_type.value if isinstance(source_type, SourceType) else str(source_type)
            query += " AND source_type = ?"
            params.append(st_val)

        if min_frp is not None:
            query += " AND frp >= ?"
            params.append(float(min_frp))

        if min_confidence is not None:
            query += " AND confidence = ?"
            params.append(str(min_confidence))

        if is_anomaly is not None:
            query += " AND is_anomaly = ?"
            params.append(1 if is_anomaly else 0)

        if cluster_id is not None:
            query += " AND cluster_id = ?"
            params.append(str(cluster_id))

        with open_db() as conn:
            cursor = conn.cursor()

            # Count matching
            count_sql = f"SELECT COUNT(*) as total FROM ({query})"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()["total"]

            # Paginate with stable ordering
            offset = max(0, (page - 1) * page_size)
            query += " ORDER BY frp DESC, acq_date DESC, acq_time DESC LIMIT ? OFFSET ?"
            query_params = list(params) + [page_size, offset]

            cursor.execute(query, query_params)
            rows = cursor.fetchall()
            items = [row_to_hotspot(r) for r in rows]

        return items, total

    def count_hotspots(self) -> int:
        """Return total number of hotspots stored in the database."""
        with open_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM hotspots")
            return cursor.fetchone()["total"]

    def clear_hotspots(self) -> int:
        """Remove all hotspots from the database. Returns count of removed items."""
        with open_db() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as total FROM hotspots")
                cnt = cursor.fetchone()["total"]
                cursor.execute("DELETE FROM hotspots")
                invalidate_seed_cache()
                return cnt

    # Metadata operations
    def set_system_meta(self, key: str, value: str) -> None:
        """Set a key-value record in the system_meta table."""
        with open_db() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO system_meta (key, value) VALUES (?, ?)",
                    (key, value),
                )

    def get_system_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a value by key from the system_meta table."""
        with open_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_meta WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default

    def set_data_mode(self, mode: Union[DataMode, str]) -> None:
        """Update system data mode ('live' or 'demo')."""
        val = mode.value if isinstance(mode, DataMode) else str(mode)
        self.set_system_meta("data_mode", val)

    def get_data_mode(self) -> DataMode:
        """Get the current system data mode."""
        mode_val = self.get_system_meta("data_mode", "demo")
        return DataMode.LIVE if mode_val == "live" else DataMode.DEMO

    def set_last_sync(self, timestamp_iso: str) -> None:
        """Update last sync timestamp."""
        self.set_system_meta("last_sync", timestamp_iso)

    def get_last_sync(self) -> Optional[str]:
        """Get the last sync timestamp."""
        return self.get_system_meta("last_sync")


# Default singleton instance
hotspot_repo = HotspotRepository()
