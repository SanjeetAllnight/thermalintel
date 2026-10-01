"""Tests for Phase 4 Alerts Subsystem.

Covers:
9. critical incident produces alert
10. high incident produces alert
11. low incident does not incorrectly become critical (or produce unwanted alerts)
12. alert priority ordering (CRITICAL > WARNING > INFO, then risk score descending)
13. duplicate alert prevention
14. deterministic alert IDs
Edge cases: empty alert list, acknowledgment status, severity filtering, unread filtering.
"""

import pytest
from datetime import datetime, timezone

from services.api.schemas.common import AlertSeverity, RiskLevel, SourceType
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.alert import Alert, AlertsResponse
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.deduplication import AlertDeduplicator
from services.api.alerts.priority import AlertPriorityComparator
from services.api.alerts.service import AlertService


def create_sample_hotspot(
    hid: str = "VIIRS-SNPP-001",
    risk_score: float = 85.0,
    risk_level: RiskLevel = RiskLevel.CRITICAL,
    frp: float = 110.0,
    source_type: SourceType = SourceType.WILDFIRE,
    nearest_place: str = "Sonoma Basin, CA",
) -> Hotspot:
    return Hotspot(
        id=hid,
        latitude=38.74,
        longitude=-122.81,
        brightness=340.0,
        scan=0.38,
        track=0.36,
        acq_date="2026-10-01",
        acq_time="0845",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=295.0,
        frp=frp,
        daynight="N",
        source_type=source_type,
        risk_score=risk_score,
        risk_level=risk_level,
        is_anomaly=True,
        cluster_id="CL-01",
        cluster_size=1,
        nearest_place=nearest_place,
        last_updated="2026-10-01T08:50:00Z",
    )


def test_critical_incident_produces_alert():
    """Requirement 9: Critical incident produces a CRITICAL alert."""
    hotspot = create_sample_hotspot(
        hid="VIIRS-CRIT-01",
        risk_score=92.5,
        risk_level=RiskLevel.CRITICAL,
        frp=145.0,
    )
    generator = AlertGenerator()
    alert = generator.generate_from_hotspot(hotspot)

    assert alert is not None
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.hotspot_id == "VIIRS-CRIT-01"
    assert alert.risk_score == 92.5
    assert "critical_frp" in alert.tags
    assert not alert.is_acknowledged
    assert len(alert.title) > 0
    assert len(alert.message) > 0


def test_high_incident_produces_alert():
    """Requirement 10: High incident produces a WARNING alert."""
    hotspot = create_sample_hotspot(
        hid="VIIRS-HIGH-01",
        risk_score=68.0,
        risk_level=RiskLevel.HIGH,
        frp=65.0,
    )
    generator = AlertGenerator()
    alert = generator.generate_from_hotspot(hotspot)

    assert alert is not None
    assert alert.severity == AlertSeverity.WARNING
    assert alert.hotspot_id == "VIIRS-HIGH-01"
    assert alert.risk_score == 68.0
    assert not alert.is_acknowledged


def test_low_incident_does_not_become_critical():
    """Requirement 11: Low incident must not become critical or produce alerts."""
    hotspot = create_sample_hotspot(
        hid="VIIRS-LOW-01",
        risk_score=15.0,
        risk_level=RiskLevel.LOW,
        frp=8.0,
    )
    generator = AlertGenerator(include_medium=False)
    alert = generator.generate_from_hotspot(hotspot)

    # Low incidents must not generate an alert by default
    assert alert is None

    # Even if include_medium is True, low risk must never produce a critical or warning alert
    gen_medium = AlertGenerator(include_medium=True)
    alert_opt = gen_medium.generate_from_hotspot(hotspot)
    assert alert_opt is None


def test_alert_priority_ordering():
    """Requirement 12: Alert priority ordering strictly respects severity and risk score."""
    a_crit_90 = Alert(
        id="ALT-CRIT-90",
        hotspot_id="H-1",
        severity=AlertSeverity.CRITICAL,
        title="Crit 90",
        message="Critical threat",
        risk_score=90.0,
        location_name="Zone A",
        latitude=38.0,
        longitude=-122.0,
        timestamp="2026-10-01T08:00:00Z",
        recommended_action="Act",
    )
    a_crit_95 = Alert(
        id="ALT-CRIT-95",
        hotspot_id="H-2",
        severity=AlertSeverity.CRITICAL,
        title="Crit 95",
        message="Critical threat high",
        risk_score=95.0,
        location_name="Zone B",
        latitude=38.1,
        longitude=-122.1,
        timestamp="2026-10-01T08:00:00Z",
        recommended_action="Act",
    )
    a_warn_70 = Alert(
        id="ALT-WARN-70",
        hotspot_id="H-3",
        severity=AlertSeverity.WARNING,
        title="Warn 70",
        message="Warning threat",
        risk_score=70.0,
        location_name="Zone C",
        latitude=38.2,
        longitude=-122.2,
        timestamp="2026-10-01T08:30:00Z",
        recommended_action="Monitor",
    )
    a_info_40 = Alert(
        id="ALT-INFO-40",
        hotspot_id="H-4",
        severity=AlertSeverity.INFO,
        title="Info 40",
        message="Informational",
        risk_score=40.0,
        location_name="Zone D",
        latitude=38.3,
        longitude=-122.3,
        timestamp="2026-10-01T09:00:00Z",
        recommended_action="Log",
    )

    alerts = [a_info_40, a_warn_70, a_crit_90, a_crit_95]
    sorted_alerts = AlertPriorityComparator.sort(alerts)

    # Order must be: a_crit_95, a_crit_90, a_warn_70, a_info_40
    assert sorted_alerts[0].id == "ALT-CRIT-95"
    assert sorted_alerts[1].id == "ALT-CRIT-90"
    assert sorted_alerts[2].id == "ALT-WARN-70"
    assert sorted_alerts[3].id == "ALT-INFO-40"


def test_duplicate_alert_prevention():
    """Requirement 13: Duplicate alerts for the same condition are suppressed."""
    a1 = Alert(
        id="ALT-001",
        hotspot_id="HOTSPOT-X",
        severity=AlertSeverity.CRITICAL,
        title="Fire Alert",
        message="Message 1",
        risk_score=85.0,
        location_name="Zone X",
        latitude=38.0,
        longitude=-122.0,
        timestamp="2026-10-01T08:00:00Z",
        is_acknowledged=False,
        recommended_action="Act",
    )
    # Same hotspot and severity, updated with higher risk
    a2 = Alert(
        id="ALT-001",
        hotspot_id="HOTSPOT-X",
        severity=AlertSeverity.CRITICAL,
        title="Fire Alert Updated",
        message="Message 2",
        risk_score=92.0,
        location_name="Zone X",
        latitude=38.0,
        longitude=-122.0,
        timestamp="2026-10-01T08:15:00Z",
        is_acknowledged=False,
        recommended_action="Act now",
    )

    dedup = AlertDeduplicator()
    deduped = dedup.deduplicate([a1, a2])

    assert len(deduped) == 1
    # Preserves higher risk score
    assert deduped[0].risk_score == 92.0


def test_deterministic_alert_ids():
    """Requirement 14: Deterministic Alert IDs derived from underlying entity."""
    dedup = AlertDeduplicator()

    id1 = dedup.generate_alert_id("VIIRS-SNPP-20261001-001")
    id2 = dedup.generate_alert_id("VIIRS-SNPP-20261001-001")
    assert id1 == id2
    assert id1 == "ALT-VIIRS-SNPP-20261001-001"

    # Preserves existing ALT- prefix
    id3 = dedup.generate_alert_id("ALT-20261001-001")
    assert id3 == "ALT-20261001-001"


def test_alert_service_filtering_and_acknowledgment():
    """Test AlertService querying, severity filter, unread filter, and acknowledgment."""
    service = AlertService()

    a1 = Alert(
        id="ALT-1",
        hotspot_id="H-1",
        severity=AlertSeverity.CRITICAL,
        title="Crit 1",
        message="msg",
        risk_score=90.0,
        location_name="Loc",
        latitude=38.0,
        longitude=-122.0,
        timestamp="2026-10-01T08:00:00Z",
        is_acknowledged=False,
        recommended_action="act",
    )
    a2 = Alert(
        id="ALT-2",
        hotspot_id="H-2",
        severity=AlertSeverity.WARNING,
        title="Warn 1",
        message="msg",
        risk_score=60.0,
        location_name="Loc",
        latitude=38.1,
        longitude=-122.1,
        timestamp="2026-10-01T08:00:00Z",
        is_acknowledged=False,
        recommended_action="act",
    )

    service.add_alert(a1)
    service.add_alert(a2)

    # 1. Total response
    res = service.get_alerts()
    assert isinstance(res, AlertsResponse)
    assert res.total == 2
    assert res.unread_count == 2

    # 2. Filter by severity
    crit_res = service.get_alerts(severity=AlertSeverity.CRITICAL)
    assert crit_res.total == 1
    assert crit_res.items[0].id == "ALT-1"

    # 3. Acknowledge ALT-1
    ack_res = service.acknowledge_alert("ALT-1")
    assert ack_res is True

    # 4. Filter by unread_only
    unread_res = service.get_alerts(unread_only=True)
    assert unread_res.total == 1
    assert unread_res.items[0].id == "ALT-2"
    assert unread_res.unread_count == 1


def test_sqlite_alert_service_integration():
    """Test AlertService querying seeded SQLite database."""
    from services.api.database import get_connection, seed_if_empty
    seed_if_empty()

    service = AlertService(connection_factory=get_connection)
    alerts_resp = service.get_alerts()
    assert alerts_resp.total > 0
    assert alerts_resp.unread_count >= 0
    # Alerts must be prioritized
    assert alerts_resp.items[0].severity in (AlertSeverity.CRITICAL, AlertSeverity.WARNING)

