"""Tests for HistoricalRecurrenceAnalyzer and persistence calculations."""

import sqlite3
import pytest

from services.api.history.recurrence import (
    HistoricalRecurrenceAnalyzer,
)
from services.api.schemas.hotspot import Hotspot


@pytest.fixture
def sample_prior_records():
    """Historical detection records in same geographic grid."""
    return [
        {
            "id": "VIIRS-SNPP-PREV-01",
            "latitude": 38.7422,
            "longitude": -122.8104,
            "acq_date": "2026-09-30",
            "acq_time": "0830",
            "frp": 110.0,
            "brightness": 345.0
        },
        {
            "id": "VIIRS-SNPP-PREV-02",
            "latitude": 38.7420,
            "longitude": -122.8106,
            "acq_date": "2026-09-29",
            "acq_time": "0840",
            "frp": 125.0,
            "brightness": 350.0
        },
        {
            "id": "VIIRS-SNPP-PREV-03",
            "latitude": 38.7423,
            "longitude": -122.8102,
            "acq_date": "2026-09-28",
            "acq_time": "0845",
            "frp": 95.0,
            "brightness": 340.0
        },
        {
            "id": "VIIRS-SNPP-DISTANT",
            "latitude": 39.5000,  # 80 km away
            "longitude": -122.8105,
            "acq_date": "2026-09-28",
            "acq_time": "0845",
            "frp": 50.0,
            "brightness": 320.0
        },
    ]


def test_recurrence_calculation_with_prior_detections(sample_prior_records):
    """Test 30d/90d count, recurrence index, and pattern detection."""
    analyzer = HistoricalRecurrenceAnalyzer(spatial_radius_meters=1000.0)

    target_hotspot = {
        "id": "VIIRS-SNPP-CURRENT",
        "latitude": 38.7421,
        "longitude": -122.8105,
        "acq_date": "2026-10-01",
        "acq_time": "0845",
        "frp": 140.0,
        "brightness": 352.0
    }

    result = analyzer.analyze(target_hotspot, candidate_history=sample_prior_records)

    assert result.status == "computed"
    ctx = result.context
    # Distant hotspot should be excluded, 3 nearby retained
    assert ctx.prior_detections_30d == 3
    assert ctx.prior_detections_90d == 3
    assert ctx.is_recurrent_site is True
    assert ctx.first_detected_date == "2026-09-28"
    assert ctx.detection_frequency_score > 0.1
    assert result.repeated_activity is True
    assert result.persistence_score > 0.0
    assert ctx.recurrent_pattern == "persistent_burn"


def test_industrial_flare_recurrence_pattern():
    """Persistent low-variance moderate radiance classified as known_industrial_stack."""
    analyzer = HistoricalRecurrenceAnalyzer(spatial_radius_meters=1000.0)

    # 12 prior detections across September with steady 20-30 MW FRP
    prior_flares = [
        {
            "id": f"FLARE-{i:02d}",
            "latitude": 29.7200,
            "longitude": -95.1200,
            "acq_date": f"2026-09-{10 + i:02d}",
            "acq_time": "0400",
            "frp": 25.0 + (i % 3),
            "brightness": 315.0
        }
        for i in range(12)
    ]

    target = {
        "id": "FLARE-CURRENT",
        "latitude": 29.7201,
        "longitude": -95.1202,
        "acq_date": "2026-09-25",
        "acq_time": "0410",
        "frp": 26.5,
        "brightness": 316.0
    }

    res = analyzer.analyze(target, candidate_history=prior_flares)
    assert res.context.prior_detections_30d >= 10
    assert res.context.recurrent_pattern == "known_industrial_stack"
    assert res.context.detection_frequency_score >= 0.5


def test_empty_historical_records():
    """Target with no prior detections returns zero recurrence and 'none' pattern."""
    analyzer = HistoricalRecurrenceAnalyzer()
    target = {
        "id": "NEW-FIRE-001",
        "latitude": 38.7421,
        "longitude": -122.8105,
        "acq_date": "2026-10-01",
        "acq_time": "0845",
        "frp": 80.0
    }

    res = analyzer.analyze(target, candidate_history=[])
    assert res.status == "empty"
    assert res.context.prior_detections_30d == 0
    assert res.context.prior_detections_90d == 0
    assert res.context.is_recurrent_site is False
    assert res.context.recurrent_pattern == "none"
    assert res.context.first_detected_date is None
    assert res.context.detection_frequency_score == 0.0


def test_database_backed_history_analysis():
    """Verify querying an active SQLite database when candidate_history is None."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE hotspots (
            id TEXT PRIMARY KEY,
            latitude REAL,
            longitude REAL,
            acq_date TEXT,
            acq_time TEXT,
            frp REAL,
            brightness REAL
        )
    """)
    cursor.execute("""
        INSERT INTO hotspots VALUES
        ('H1', 38.7420, -122.8104, '2026-09-25', '0800', 90.0, 340.0),
        ('H2', 38.7422, -122.8106, '2026-09-26', '0800', 95.0, 342.0)
    """)
    conn.commit()

    analyzer = HistoricalRecurrenceAnalyzer()
    target = {
        "id": "TARGET",
        "latitude": 38.7421,
        "longitude": -122.8105,
        "acq_date": "2026-09-28",
        "acq_time": "0800",
        "frp": 100.0,
        "brightness": 345.0
    }

    res = analyzer.analyze(target, candidate_history=None, db_connection=conn)
    assert res.context.prior_detections_30d == 2
    assert res.context.first_detected_date == "2026-09-25"
    conn.close()
