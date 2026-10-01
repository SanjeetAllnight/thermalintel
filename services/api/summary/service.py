"""Dashboard summary and source analytics service for ThermalIntel Phase 4.

Responsible for:
- Serving GET /api/summary responses with consistent KPIs
- Serving GET /api/sources responses with source breakdowns
- Supporting both SQLite persistence and decoupled in-memory datasets
"""

from datetime import datetime, timezone
from typing import List, Optional, Callable, Dict, Any
import sqlite3

from services.api.schemas.summary import SummaryResponse, SourcesResponse
from services.api.schemas.common import DataMode, RiskLevel, SourceType
from services.api.schemas.hotspot import Hotspot
from services.api.summary.analytics import SummaryAnalytics


class SummaryService:
    """Core service providing dashboard summary metrics and source risk analytics."""

    def __init__(
        self,
        connection_factory: Optional[Callable[[], sqlite3.Connection]] = None,
        data_mode: DataMode = DataMode.DEMO,
    ):
        """Initialize SummaryService.
        
        Args:
            connection_factory: Optional SQLite connection provider.
            data_mode: Default data mode when not queried from database.
        """
        self.connection_factory = connection_factory
        self.default_data_mode = data_mode
        self._in_memory_hotspots: List[Hotspot] = []
        self._in_memory_alerts_count: int = 0
        self._last_sync_time: Optional[str] = None

    def set_in_memory_data(
        self,
        hotspots: List[Hotspot],
        active_alerts_count: int = 0,
        last_sync_time: Optional[str] = None,
    ):
        """Set in-memory data for standalone testing."""
        self._in_memory_hotspots = hotspots
        self._in_memory_alerts_count = active_alerts_count
        self._last_sync_time = last_sync_time

    def get_summary(
        self,
        hotspots: Optional[List[Hotspot]] = None,
        active_alerts_count: Optional[int] = None,
    ) -> SummaryResponse:
        """Compute and return operational dashboard KPIs compliant with SummaryResponse."""
        mode = self.default_data_mode
        last_sync = self._last_sync_time or datetime.now(timezone.utc).isoformat()

        if hotspots is None:
            if self.connection_factory:
                hotspots, active_alerts_count, mode, last_sync = self._load_data_from_db()
            else:
                hotspots = self._in_memory_hotspots
                active_alerts_count = (
                    self._in_memory_alerts_count
                    if active_alerts_count is None
                    else active_alerts_count
                )
        else:
            if active_alerts_count is None:
                active_alerts_count = self._in_memory_alerts_count

        kpis = SummaryAnalytics.compute_kpis(hotspots, active_alerts_count or 0)

        return SummaryResponse(
            total_active_hotspots=kpis["total_active_hotspots"],
            critical_risk_count=kpis["critical_risk_count"],
            high_risk_count=kpis["high_risk_count"],
            medium_risk_count=kpis["medium_risk_count"],
            low_risk_count=kpis["low_risk_count"],
            active_alerts_count=kpis["active_alerts_count"],
            average_frp=kpis["average_frp"],
            max_frp=kpis["max_frp"],
            average_risk_score=kpis["average_risk_score"],
            data_mode=mode,
            last_sync_time=last_sync,
            dominant_source=kpis["dominant_source"],
            source_counts=kpis["source_counts"],
            recent_critical_hotspots=kpis["recent_critical_hotspots"],
        )

    def get_sources(
        self, hotspots: Optional[List[Hotspot]] = None
    ) -> SourcesResponse:
        """Compute and return source risk profiles compliant with SourcesResponse."""
        mode = self.default_data_mode

        if hotspots is None:
            if self.connection_factory:
                hotspots, _, mode, _ = self._load_data_from_db()
            else:
                hotspots = self._in_memory_hotspots

        breakdowns, total_eval, dominant = SummaryAnalytics.compute_source_breakdown(
            hotspots
        )

        return SourcesResponse(
            sources=breakdowns,
            total_evaluated=total_eval,
            dominant_source=dominant,
            data_mode=mode,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _load_data_from_db(
        self,
    ) -> tuple[List[Hotspot], int, DataMode, str]:
        """Fetch active hotspots and metadata from SQLite database."""
        hotspots: List[Hotspot] = []
        unread_count = 0
        mode = self.default_data_mode
        last_sync = datetime.now(timezone.utc).isoformat()

        if not self.connection_factory:
            return hotspots, unread_count, mode, last_sync

        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM hotspots")
                rows = cursor.fetchall()
                for r in rows:
                    hotspots.append(
                        Hotspot(
                            id=r["id"],
                            latitude=r["latitude"],
                            longitude=r["longitude"],
                            brightness=r["brightness"],
                            scan=r["scan"] if "scan" in r.keys() and r["scan"] is not None else 0.375,
                            track=r["track"] if "track" in r.keys() and r["track"] is not None else 0.375,
                            acq_date=r["acq_date"],
                            acq_time=r["acq_time"],
                            satellite=r["satellite"],
                            instrument=r["instrument"] if "instrument" in r.keys() and r["instrument"] else "VIIRS",
                            confidence=r["confidence"],
                            version=r["version"] if "version" in r.keys() and r["version"] else "2.0NRT",
                            bright_t31=r["bright_t31"] if "bright_t31" in r.keys() else None,
                            frp=r["frp"],
                            daynight=r["daynight"],
                            source_type=SourceType(r["source_type"]),
                            risk_score=r["risk_score"],
                            risk_level=RiskLevel(r["risk_level"]),
                            is_anomaly=bool(r["is_anomaly"]),
                            cluster_id=r["cluster_id"] if "cluster_id" in r.keys() else None,
                            cluster_size=r["cluster_size"] if "cluster_size" in r.keys() and r["cluster_size"] else 1,
                            nearest_place=r["nearest_place"] if "nearest_place" in r.keys() else None,
                            last_updated=r["last_updated"],
                        )
                    )

                cursor.execute("SELECT COUNT(*) as unread FROM alerts WHERE is_acknowledged = 0")
                unread_row = cursor.fetchone()
                if unread_row:
                    unread_count = unread_row["unread"]

                cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
                mode_row = cursor.fetchone()
                if mode_row and mode_row["value"] == "live":
                    mode = DataMode.LIVE

                cursor.execute("SELECT value FROM system_meta WHERE key = 'last_sync'")
                sync_row = cursor.fetchone()
                if sync_row and sync_row["value"]:
                    last_sync = sync_row["value"]
        except Exception:
            pass

        return hotspots, unread_count, mode, last_sync
