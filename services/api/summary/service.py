"""Dashboard summary and source analytics service for ThermalIntel Phase 4 & V2.

Responsible for:
- Serving GET /api/summary responses with consistent KPIs
- Serving GET /api/sources responses with source breakdowns
- Supporting high-performance targeted SQL aggregations without full table scans
- Supporting decoupled in-memory datasets for testing and simulation
"""

from datetime import datetime, timezone
from typing import List, Optional, Callable, Dict, Any, Tuple
import sqlite3

from services.api.schemas.summary import SummaryResponse, SourcesResponse, SourceBreakdown
from services.api.schemas.common import DataMode, RiskLevel, SourceType
from services.api.schemas.hotspot import Hotspot
from services.api.summary.analytics import SummaryAnalytics, SOURCE_METADATA
from services.api.schemas.v2.converters import row_to_hotspot_canonical


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
    ) -> None:
        """Set in-memory data for standalone testing."""
        self._in_memory_hotspots = hotspots
        self._in_memory_alerts_count = active_alerts_count
        self._last_sync_time = last_sync_time

    def get_summary(
        self,
        hotspots: Optional[List[Hotspot]] = None,
        active_alerts_count: Optional[int] = None,
    ) -> SummaryResponse:
        """Compute and return operational dashboard KPIs compliant with SummaryResponse.
        
        When backed by SQLite, uses targeted aggregate queries instead of full-table scans.
        """
        # If explicit in-memory hotspots passed or no DB connection, use analytical in-memory calculation
        if hotspots is not None or not self.connection_factory:
            data = hotspots if hotspots is not None else self._in_memory_hotspots
            alerts_cnt = (
                active_alerts_count
                if active_alerts_count is not None
                else self._in_memory_alerts_count
            )
            mode = self.default_data_mode
            last_sync = self._last_sync_time or datetime.now(timezone.utc).isoformat()

            kpis = SummaryAnalytics.compute_kpis(data, alerts_cnt)
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

        # High-performance targeted SQL aggregation execution
        return self._compute_summary_from_db(active_alerts_count=active_alerts_count)

    def get_sources(
        self, hotspots: Optional[List[Hotspot]] = None
    ) -> SourcesResponse:
        """Compute and return source risk profiles compliant with SourcesResponse.
        
        When backed by SQLite, executes a single GROUP BY aggregate query instead of
        loading all individual hotspot records.
        """
        if hotspots is not None or not self.connection_factory:
            data = hotspots if hotspots is not None else self._in_memory_hotspots
            mode = self.default_data_mode
            breakdowns, total_eval, dominant = SummaryAnalytics.compute_source_breakdown(data)
            return SourcesResponse(
                sources=breakdowns,
                total_evaluated=total_eval,
                dominant_source=dominant,
                data_mode=mode,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        return self._compute_sources_from_db()

    def get_summary_and_sources(
        self, hotspots: Optional[List[Hotspot]] = None
    ) -> Tuple[SummaryResponse, SourcesResponse]:
        """Convenience method returning both summary KPIs and source breakdowns."""
        summary = self.get_summary(hotspots=hotspots)
        sources = self.get_sources(hotspots=hotspots)
        return summary, sources

    # =========================================================================
    # High-Performance SQL Aggregations
    # =========================================================================

    def _compute_summary_from_db(
        self, active_alerts_count: Optional[int] = None
    ) -> SummaryResponse:
        """Compute summary KPIs directly using SQLite aggregate functions."""
        mode = self.default_data_mode
        last_sync = self._last_sync_time or datetime.now(timezone.utc).isoformat()
        unread_count = 0

        with self.connection_factory() as conn:
            cursor = conn.cursor()

            # 1. Targeted aggregate stats for counts, FRP, and risk score
            cursor.execute("""
                SELECT
                    COUNT(*) as total_count,
                    COALESCE(SUM(CASE WHEN risk_level = 'critical' OR risk_score >= 75.0 THEN 1 ELSE 0 END), 0) as crit_cnt,
                    COALESCE(SUM(CASE WHEN (risk_level = 'high' OR risk_score >= 50.0) AND NOT (risk_level = 'critical' OR risk_score >= 75.0) THEN 1 ELSE 0 END), 0) as high_cnt,
                    COALESCE(SUM(CASE WHEN (risk_level = 'medium' OR risk_score >= 25.0) AND NOT (risk_level IN ('critical', 'high') OR risk_score >= 50.0) THEN 1 ELSE 0 END), 0) as med_cnt,
                    COALESCE(SUM(CASE WHEN NOT (risk_level IN ('critical', 'high', 'medium') OR risk_score >= 25.0) THEN 1 ELSE 0 END), 0) as low_cnt,
                    COALESCE(AVG(frp), 0.0) as avg_frp,
                    COALESCE(MAX(frp), 0.0) as max_frp,
                    COALESCE(AVG(risk_score), 0.0) as avg_risk
                FROM hotspots
            """)
            agg = cursor.fetchone()

            total = agg["total_count"] if agg else 0
            if total == 0:
                return SummaryResponse(
                    total_active_hotspots=0,
                    critical_risk_count=0,
                    high_risk_count=0,
                    medium_risk_count=0,
                    low_risk_count=0,
                    active_alerts_count=0,
                    average_frp=0.0,
                    max_frp=0.0,
                    average_risk_score=0.0,
                    data_mode=mode,
                    last_sync_time=last_sync,
                    dominant_source=SourceType.UNKNOWN,
                    source_counts={},
                    recent_critical_hotspots=[],
                )

            crit_cnt = int(agg["crit_cnt"])
            high_cnt = int(agg["high_cnt"])
            med_cnt = int(agg["med_cnt"])
            low_cnt = int(agg["low_cnt"])
            avg_frp = round(float(agg["avg_frp"]), 2)
            max_frp = round(float(agg["max_frp"]), 2)
            avg_risk = round(float(agg["avg_risk"]), 1)

            # 2. Source distribution counts via GROUP BY
            cursor.execute("""
                SELECT source_type, COUNT(*) as cnt
                FROM hotspots
                GROUP BY source_type
                ORDER BY cnt DESC, source_type ASC
            """)
            source_rows = cursor.fetchall()
            source_counts: Dict[str, int] = {}
            for sr in source_rows:
                source_counts[sr["source_type"]] = int(sr["cnt"])

            dominant_str = source_rows[0]["source_type"] if source_rows else "unknown"
            try:
                dominant_source = SourceType(dominant_str)
            except ValueError:
                dominant_source = SourceType.UNKNOWN

            # 3. Top 5 critical / high hotspots (ordered by risk score, frp desc)
            cursor.execute("""
                SELECT * FROM hotspots
                WHERE (risk_level IN ('critical', 'high') OR risk_score >= 50.0)
                ORDER BY risk_score DESC, frp DESC, id ASC
                LIMIT 5
            """)
            recent_rows = cursor.fetchall()
            recent_critical = [row_to_hotspot_canonical(r) for r in recent_rows]

            # 4. Active alerts tally
            if active_alerts_count is not None:
                unread_count = active_alerts_count
            else:
                # Check alerts_v2 first
                try:
                    cursor.execute("SELECT COUNT(*) as unread FROM alerts_v2 WHERE state = 'active'")
                    row = cursor.fetchone()
                    if row and row["unread"] > 0:
                        unread_count = int(row["unread"])
                    else:
                        cursor.execute("SELECT COUNT(*) as unread FROM alerts WHERE is_acknowledged = 0")
                        legacy_row = cursor.fetchone()
                        if legacy_row:
                            unread_count = int(legacy_row["unread"])
                except Exception:
                    pass

            # 5. Metadata
            try:
                cursor.execute("SELECT key, value FROM system_meta WHERE key IN ('data_mode', 'last_sync')")
                for m in cursor.fetchall():
                    if m["key"] == "data_mode" and m["value"] == "live":
                        mode = DataMode.LIVE
                    elif m["key"] == "last_sync" and m["value"]:
                        last_sync = m["value"]
            except Exception:
                pass

        return SummaryResponse(
            total_active_hotspots=total,
            critical_risk_count=crit_cnt,
            high_risk_count=high_cnt,
            medium_risk_count=med_cnt,
            low_risk_count=low_cnt,
            active_alerts_count=unread_count,
            average_frp=avg_frp,
            max_frp=max_frp,
            average_risk_score=avg_risk,
            data_mode=mode,
            last_sync_time=last_sync,
            dominant_source=dominant_source,
            source_counts=source_counts,
            recent_critical_hotspots=recent_critical,
        )

    def _compute_sources_from_db(self) -> SourcesResponse:
        """Compute source risk breakdown directly using SQLite GROUP BY aggregate."""
        mode = self.default_data_mode
        breakdowns: List[SourceBreakdown] = []

        with self.connection_factory() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    source_type,
                    COUNT(*) as count,
                    COALESCE(AVG(frp), 0.0) as avg_frp,
                    COALESCE(AVG(risk_score), 0.0) as avg_risk
                FROM hotspots
                GROUP BY source_type
                ORDER BY count DESC, avg_risk DESC, source_type ASC
            """)
            rows = cursor.fetchall()

            total_evaluated = sum(r["count"] for r in rows)
            if total_evaluated == 0:
                return SourcesResponse(
                    sources=[],
                    total_evaluated=0,
                    dominant_source=SourceType.UNKNOWN,
                    data_mode=mode,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                )

            for r in rows:
                st_val = r["source_type"]
                try:
                    source_type = SourceType(st_val)
                except ValueError:
                    source_type = SourceType.UNKNOWN

                cnt = int(r["count"])
                pct = round((cnt / total_evaluated) * 100.0, 1)
                avg_frp = round(float(r["avg_frp"]), 2)
                avg_risk = round(float(r["avg_risk"]), 1)

                display_name, driver = SOURCE_METADATA.get(
                    source_type, (source_type.value.title(), "Thermal radiance signature")
                )

                breakdowns.append(
                    SourceBreakdown(
                        source_type=source_type,
                        display_name=display_name,
                        count=cnt,
                        percentage=pct,
                        average_frp=avg_frp,
                        average_risk=avg_risk,
                        primary_driver=driver,
                    )
                )

            # Dominant source
            dominant = breakdowns[0].source_type if breakdowns else SourceType.UNKNOWN

            # Metadata
            try:
                cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
                m = cursor.fetchone()
                if m and m["value"] == "live":
                    mode = DataMode.LIVE
            except Exception:
                pass

        return SourcesResponse(
            sources=breakdowns,
            total_evaluated=total_evaluated,
            dominant_source=dominant,
            data_mode=mode,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
