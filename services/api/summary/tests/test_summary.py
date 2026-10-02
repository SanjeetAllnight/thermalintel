"""Tests for Phase 4 Summary and Sources Analytics Subsystem.

Covers:
15. total active counts
16. severity counts (critical, high, medium, low)
17. internally consistent totals (critical + high + medium + low == total)
18. empty summary dataset handling
19. demo dataset summary verification
20. dominant source calculation
21. source counts
22. source percentages (summing to 100%)
23. source risk & FRP distribution
24. empty sources dataset handling
"""

import json
from pathlib import Path
import pytest

from services.api.schemas.common import RiskLevel, SourceType, DataMode
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.summary import SummaryResponse, SourcesResponse
from services.api.summary.analytics import SummaryAnalytics
from services.api.summary.service import SummaryService


def make_hotspot(
    hid: str,
    risk_score: float,
    risk_level: RiskLevel,
    frp: float,
    source_type: SourceType,
) -> Hotspot:
    return Hotspot(
        id=hid,
        latitude=38.0,
        longitude=-122.0,
        brightness=320.0,
        scan=0.38,
        track=0.36,
        acq_date="2026-10-01",
        acq_time="1000",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=290.0,
        frp=frp,
        daynight="D",
        source_type=source_type,
        risk_score=risk_score,
        risk_level=risk_level,
        is_anomaly=False,
        cluster_id="CL-TEST",
        cluster_size=1,
        nearest_place="Test Valley",
        last_updated="2026-10-01T10:05:00Z",
    )


def test_summary_counts_and_consistency():
    """Requirements 15, 16, 17: Total counts, severity counts, and internal consistency."""
    h1 = make_hotspot("H-CRIT", 85.0, RiskLevel.CRITICAL, 120.0, SourceType.WILDFIRE)
    h2 = make_hotspot("H-HIGH-1", 65.0, RiskLevel.HIGH, 60.0, SourceType.WILDFIRE)
    h3 = make_hotspot("H-HIGH-2", 55.0, RiskLevel.HIGH, 40.0, SourceType.INDUSTRIAL)
    h4 = make_hotspot("H-MED-1", 35.0, RiskLevel.MEDIUM, 20.0, SourceType.AGRICULTURAL)
    h5 = make_hotspot("H-LOW-1", 15.0, RiskLevel.LOW, 10.0, SourceType.PRESCRIBED_BURN)

    hotspots = [h1, h2, h3, h4, h5]
    service = SummaryService()
    summary = service.get_summary(hotspots=hotspots, active_alerts_count=2)

    assert isinstance(summary, SummaryResponse)
    assert summary.total_active_hotspots == 5
    assert summary.critical_risk_count == 1
    assert summary.high_risk_count == 2
    assert summary.medium_risk_count == 1
    assert summary.low_risk_count == 1

    # Internal consistency check:
    sum_severities = (
        summary.critical_risk_count
        + summary.high_risk_count
        + summary.medium_risk_count
        + summary.low_risk_count
    )
    assert sum_severities == summary.total_active_hotspots

    # Averages check
    # FRPs: 120 + 60 + 40 + 20 + 10 = 250 / 5 = 50.0
    assert summary.average_frp == 50.0
    assert summary.max_frp == 120.0
    # Risk: 85 + 65 + 55 + 35 + 15 = 255 / 5 = 51.0
    assert summary.average_risk_score == 51.0
    assert summary.active_alerts_count == 2


def test_empty_summary_dataset():
    """Requirement 18: Empty dataset returns zeroed metrics and does not crash."""
    service = SummaryService()
    summary = service.get_summary(hotspots=[], active_alerts_count=0)

    assert summary.total_active_hotspots == 0
    assert summary.critical_risk_count == 0
    assert summary.high_risk_count == 0
    assert summary.medium_risk_count == 0
    assert summary.low_risk_count == 0
    assert summary.average_frp == 0.0
    assert summary.max_frp == 0.0
    assert summary.average_risk_score == 0.0
    assert summary.dominant_source == SourceType.UNKNOWN
    assert summary.source_counts == {}
    assert summary.recent_critical_hotspots == []


def test_demo_dataset_summary():
    """Requirement 19: Verify summary calculations against bundled sample_hotspots.json."""
    sample_path = Path("data/sample/sample_hotspots.json")
    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        hotspots = [Hotspot(**item) for item in raw_data]

        service = SummaryService()
        summary = service.get_summary(hotspots=hotspots, active_alerts_count=3)

        assert summary.total_active_hotspots == len(hotspots)
        assert summary.total_active_hotspots > 0
        assert summary.average_frp > 0.0
        assert summary.max_frp > 0.0
        assert summary.dominant_source in SourceType
        # Total consistency
        assert (
            summary.critical_risk_count
            + summary.high_risk_count
            + summary.medium_risk_count
            + summary.low_risk_count
        ) == summary.total_active_hotspots


def test_dominant_source_calculation():
    """Requirement 20: Dominant source calculation picks most frequent source type."""
    hotspots = [
        make_hotspot("H-1", 70.0, RiskLevel.HIGH, 50.0, SourceType.WILDFIRE),
        make_hotspot("H-2", 60.0, RiskLevel.HIGH, 40.0, SourceType.WILDFIRE),
        make_hotspot("H-3", 80.0, RiskLevel.CRITICAL, 90.0, SourceType.INDUSTRIAL),
    ]
    service = SummaryService()
    summary = service.get_summary(hotspots=hotspots)

    assert summary.dominant_source == SourceType.WILDFIRE
    assert summary.source_counts["wildfire"] == 2
    assert summary.source_counts["industrial"] == 1


def test_sources_breakdown_counts_and_percentages():
    """Requirements 21, 22, 23: Source counts, percentages, and risk/FRP distributions."""
    # 4 Wildfires, 1 Industrial (Total 5)
    hotspots = [
        make_hotspot("W-1", 80.0, RiskLevel.CRITICAL, 100.0, SourceType.WILDFIRE),
        make_hotspot("W-2", 70.0, RiskLevel.HIGH, 80.0, SourceType.WILDFIRE),
        make_hotspot("W-3", 90.0, RiskLevel.CRITICAL, 120.0, SourceType.WILDFIRE),
        make_hotspot("W-4", 60.0, RiskLevel.HIGH, 60.0, SourceType.WILDFIRE),
        make_hotspot("I-1", 30.0, RiskLevel.MEDIUM, 25.0, SourceType.INDUSTRIAL),
    ]

    service = SummaryService()
    resp = service.get_sources(hotspots=hotspots)

    assert isinstance(resp, SourcesResponse)
    assert resp.total_evaluated == 5
    assert resp.dominant_source == SourceType.WILDFIRE
    assert len(resp.sources) == 2

    # Wildfire breakdown
    wf = resp.sources[0]
    assert wf.source_type == SourceType.WILDFIRE
    assert wf.count == 4
    assert wf.percentage == 80.0  # 4 / 5 * 100%
    assert wf.average_frp == 90.0  # (100 + 80 + 120 + 60) / 4 = 90.0
    assert wf.average_risk == 75.0  # (80 + 70 + 90 + 60) / 4 = 75.0
    assert len(wf.display_name) > 0
    assert len(wf.primary_driver) > 0

    # Industrial breakdown
    ind = resp.sources[1]
    assert ind.source_type == SourceType.INDUSTRIAL
    assert ind.count == 1
    assert ind.percentage == 20.0
    assert ind.average_frp == 25.0
    assert ind.average_risk == 30.0

    # Sum of percentages == 100.0%
    total_pct = sum(s.percentage for s in resp.sources)
    assert pytest.approx(total_pct, 0.1) == 100.0


def test_empty_sources_dataset():
    """Requirement 24: Empty source dataset handling."""
    service = SummaryService()
    resp = service.get_sources(hotspots=[])

    assert resp.total_evaluated == 0
    assert resp.dominant_source == SourceType.UNKNOWN
    assert resp.sources == []


def test_sqlite_summary_service_integration():
    """Test SummaryService querying seeded SQLite database."""
    from services.api.database import get_connection, seed_if_empty
    seed_if_empty()

    service = SummaryService(connection_factory=get_connection)
    summary = service.get_summary()
    assert summary.total_active_hotspots > 0
    assert (
        summary.critical_risk_count
        + summary.high_risk_count
        + summary.medium_risk_count
        + summary.low_risk_count
    ) == summary.total_active_hotspots

    sources_resp = service.get_sources()
    assert sources_resp.total_evaluated == summary.total_active_hotspots
    assert len(sources_resp.sources) > 0


def test_summary_targeted_sql_aggregate_efficiency():
    """Verify get_summary uses targeted aggregates rather than full-table SELECT * scans."""
    from services.api.database import get_connection, seed_if_empty
    seed_if_empty()

    executed_queries = []

    class QueryTrackingConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn

        def cursor(self):
            real_cur = self.real_conn.cursor()

            class QueryTrackingCursor:
                def __init__(self, cur):
                    self.cur = cur

                def execute(self, sql, params=()):
                    executed_queries.append(sql.strip())
                    return self.cur.execute(sql, params)

                def fetchone(self):
                    return self.cur.fetchone()

                def fetchall(self):
                    return self.cur.fetchall()

                def __getattr__(self, name):
                    return getattr(self.cur, name)

            return QueryTrackingCursor(real_cur)

        def commit(self):
            return self.real_conn.commit()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.real_conn.close()

    def tracking_factory():
        return QueryTrackingConnection(get_connection())

    service = SummaryService(connection_factory=tracking_factory)

    # 1. Summary
    executed_queries.clear()
    summary = service.get_summary()
    assert summary.total_active_hotspots > 0

    # Ensure NO unbounded full-table scans
    for q in executed_queries:
        normalized = " ".join(q.split()).upper()
        # "SELECT * FROM HOTSPOTS" without a LIMIT clause is forbidden
        if "SELECT * FROM HOTSPOTS" in normalized:
            assert "LIMIT" in normalized, f"Unbounded full-table scan detected: {q}"

    # Verify aggregation query was executed
    has_aggregate = any("COUNT(*)" in q.upper() and "AVG(" in q.upper() for q in executed_queries)
    assert has_aggregate, f"Expected aggregate query with COUNT and AVG, got: {executed_queries}"

    # 2. Sources
    executed_queries.clear()
    sources = service.get_sources()
    assert sources.total_evaluated > 0

    # Ensure NO SELECT * FROM hotspots at all in get_sources
    for q in executed_queries:
        normalized = " ".join(q.split()).upper()
        assert "SELECT * FROM HOTSPOTS" not in normalized, f"Full table scan in get_sources: {q}"

    # Verify GROUP BY was used
    has_group_by = any("GROUP BY" in q.upper() for q in executed_queries)
    assert has_group_by, f"Expected GROUP BY aggregate query in get_sources, got: {executed_queries}"


