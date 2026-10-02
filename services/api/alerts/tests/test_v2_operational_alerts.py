"""Comprehensive tests for V2 persistent, transition-driven operational alert layer.

Covers:
1. Transition-driven alert generation:
   - New incident (critical, warning, low/filtered)
   - Escalation (risk & severity elevation with forensic evidence)
   - De-escalation (advisory alert with reduced threat context)
   - Reopen (rekindled flare up)
   - Closure (resolution alert & active alert auto-resolution)
2. Deterministic deduplication:
   - Repeated same transition event produces 0 duplicates
   - Repeated refresh / sync
   - Multiple detections on same incident do not flood alerts
3. Cooldown and flood protection:
   - Per-rule cooldown
   - Per-incident pacing cooldown
   - Bounded window alert generation / rate limiting
   - Chattering incident suppression
   - Critical escalation override
4. Lifecycle states:
   - Active -> Acknowledged -> Resolved -> Suppressed
5. Restart semantics & SQLite persistence:
   - Database source of truth
   - Acknowledgement persistence across service re-instantiation
   - Unread count consistency before and after service reconstruction
6. Alert Health telemetry:
   - Window filtering
   - Priority mix
   - Suppression counts
   - Alert rate per hour
   - Chattering incident identification
"""

import os
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta

from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import (
    AlertSeverity,
    AlertState,
    IncidentEventType,
    IncidentStatus,
    RiskLevel,
    SourceType,
    now_utc_iso,
)
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.incident import Incident
from services.api.alerts.service import AlertService
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.deduplication import AlertDeduplicator
from services.api.alerts.cooldown import FloodProtectionEngine, FloodProtectionConfig
from services.api.alerts.health import compute_health_from_alerts
from services.api.migrations import run_migrations


@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary SQLite database initialized with canonical V2 schema."""
    db_file = str(tmp_path / "test_alerts_v2.db")
    run_migrations(db_file)

    def connection_factory():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        return conn

    return connection_factory


def make_incident(
    iid: str = "INC-20261001-0001",
    severity: RiskLevel = RiskLevel.CRITICAL,
    risk_score: float = None,
    peak_frp: float = None,
    status: IncidentStatus = IncidentStatus.ACTIVE,
    nearest_place: str = "Sonoma Basin, CA",
    obs_count: int = 3,
) -> Incident:
    if risk_score is None:
        if severity == RiskLevel.CRITICAL:
            risk_score = 85.0
        elif severity == RiskLevel.HIGH:
            risk_score = 60.0
        elif severity == RiskLevel.MEDIUM:
            risk_score = 35.0
        else:
            risk_score = 15.0

    if peak_frp is None:
        if severity == RiskLevel.CRITICAL:
            peak_frp = 120.0
        elif severity == RiskLevel.HIGH:
            peak_frp = 50.0
        elif severity == RiskLevel.MEDIUM:
            peak_frp = 25.0
        else:
            peak_frp = 8.0
    return Incident(
        incident_id=iid,
        status=status,
        first_seen_utc="2026-10-01T08:00:00Z",
        last_seen_utc="2026-10-01T08:30:00Z",
        centroid_latitude=38.74,
        centroid_longitude=-122.81,
        nearest_place=nearest_place,
        peak_frp=peak_frp,
        average_frp=peak_frp * 0.8,
        observation_count=obs_count,
        current_risk_score=risk_score,
        current_severity=severity,
        current_classification=SourceType.WILDFIRE,
        created_at_utc="2026-10-01T08:00:00Z",
        updated_at_utc="2026-10-01T08:30:00Z",
    )


def make_event(
    event_id: str,
    incident_id: str,
    event_type: IncidentEventType,
    reason: str,
    metadata: dict = None,
    timestamp_utc: str = "2026-10-01T08:30:00Z",
) -> IncidentEvent:
    return IncidentEvent(
        event_id=event_id,
        incident_id=incident_id,
        event_type=event_type,
        timestamp_utc=timestamp_utc,
        actor="system_correlator",
        reason=reason,
        metadata=metadata or {},
    )


# =============================================================================
# 1. Transition-Driven Alert Generation Tests
# =============================================================================

def test_transition_new_critical_incident_produces_alert():
    """NEW INCIDENT with critical severity triggers a CRITICAL AlertV2 with evidence."""
    service = AlertService()
    inc = make_incident(severity=RiskLevel.CRITICAL, risk_score=88.0, peak_frp=115.0)
    evt = make_event("EVT-01", inc.incident_id, IncidentEventType.CREATED, "New wildfire cluster identified")

    alert = service.process_incident_transition(inc, evt)

    assert alert is not None
    assert alert.priority == AlertSeverity.CRITICAL
    assert alert.state == AlertState.ACTIVE
    assert alert.rule_id == "RULE_NEW_INCIDENT"
    assert alert.incident_id == inc.incident_id
    assert "critical_frp" in alert.metadata["tags"]
    # Forensic evidence verification
    assert alert.evidence["current_risk_score"] == 88.0
    assert alert.evidence["peak_frp"] == 115.0
    assert alert.evidence["event_reason"] == "New wildfire cluster identified"


def test_transition_new_high_incident_produces_warning_alert():
    """NEW INCIDENT with high severity triggers a WARNING AlertV2."""
    service = AlertService()
    inc = make_incident(severity=RiskLevel.HIGH, risk_score=62.0, peak_frp=55.0)
    evt = make_event("EVT-02", inc.incident_id, IncidentEventType.CREATED, "Elevated heat signature")

    alert = service.process_incident_transition(inc, evt)

    assert alert is not None
    assert alert.priority == AlertSeverity.WARNING
    assert alert.rule_id == "RULE_NEW_INCIDENT"


def test_transition_new_low_incident_does_not_produce_alert():
    """NEW INCIDENT with low severity is filtered out and does NOT become an alert."""
    service = AlertService()
    inc = make_incident(severity=RiskLevel.LOW, risk_score=15.0, peak_frp=8.0)
    evt = make_event("EVT-03", inc.incident_id, IncidentEventType.CREATED, "Low thermal noise")

    alert = service.process_incident_transition(inc, evt)
    assert alert is None


def test_transition_escalation_produces_evidence_rich_alert():
    """ESCALATED transition generates alert with old/new risk deltas in evidence."""
    service = AlertService()
    inc = make_incident(severity=RiskLevel.CRITICAL, risk_score=91.0, peak_frp=140.0)
    evt = make_event(
        "EVT-ESC-01",
        inc.incident_id,
        IncidentEventType.ESCALATED,
        reason="FRP surged above 100MW; flame front expanding towards settlement",
        metadata={
            "old_severity": "high",
            "new_severity": "critical",
            "old_risk": 65.0,
            "new_risk": 91.0,
        },
    )

    alert = service.process_incident_transition(inc, evt)

    assert alert is not None
    assert alert.priority == AlertSeverity.CRITICAL
    assert alert.rule_id in ("RULE_INCIDENT_ESCALATED", "RULE_EXTREME_FRP")
    assert alert.evidence["current_risk_score"] == 91.0
    assert alert.evidence["previous_risk_score"] == 65.0
    assert alert.evidence["current_severity"] == "critical"
    assert alert.evidence["previous_severity"] == "high"


def test_transition_deescalation_produces_advisory_alert():
    """DEESCALATED transition produces an advisory notification (not critical alarm)."""
    service = AlertService()
    inc = make_incident(severity=RiskLevel.MEDIUM, risk_score=40.0, peak_frp=20.0)
    evt = make_event(
        "EVT-DEESC-01",
        inc.incident_id,
        IncidentEventType.DEESCALATED,
        reason="Rainfall reduced active perimeter; thermal output dampened",
        metadata={"old_severity": "critical", "new_severity": "medium", "old_risk": 85.0, "new_risk": 40.0},
    )

    alert = service.process_incident_transition(inc, evt)

    assert alert is not None
    assert alert.priority == AlertSeverity.INFO
    assert alert.rule_id == "RULE_INCIDENT_DEESCALATED"
    assert alert.evidence["transition"] == "deescalated"


def test_transition_reopen_produces_urgent_alert():
    """REOPENED transition warns of rekindled activity."""
    service = AlertService()
    inc = make_incident(severity=RiskLevel.HIGH, risk_score=70.0, peak_frp=80.0)
    evt = make_event(
        "EVT-REOPEN-01",
        inc.incident_id,
        IncidentEventType.REOPENED,
        reason="Thermal recurrence detected in previously contained zone",
    )

    alert = service.process_incident_transition(inc, evt)

    assert alert is not None
    assert alert.priority == AlertSeverity.WARNING
    assert alert.rule_id == "RULE_INCIDENT_REOPENED"
    assert "reopened" in alert.metadata["tags"]


def test_transition_closure_auto_resolves_active_alerts():
    """CLOSED transition marks existing active alerts on the incident as RESOLVED."""
    service = AlertService()
    inc = make_incident(iid="INC-CLOSE-TEST", severity=RiskLevel.CRITICAL)

    # 1. Create active alert
    evt_create = make_event("EVT-C1", inc.incident_id, IncidentEventType.CREATED, "Initial flare")
    active_alert = service.process_incident_transition(inc, evt_create)
    assert active_alert is not None
    assert active_alert.state == AlertState.ACTIVE

    # 2. Close incident
    evt_close = make_event("EVT-C2", inc.incident_id, IncidentEventType.CLOSED, "Fire extinguished")
    closed_inc = make_incident(iid="INC-CLOSE-TEST", status=IncidentStatus.CLOSED, severity=RiskLevel.LOW, risk_score=10.0)
    close_alert = service.process_incident_transition(closed_inc, evt_close)

    assert close_alert is not None
    assert close_alert.state == AlertState.RESOLVED

    # 3. Verify original alert was transitioned to RESOLVED
    fetched_original = service.get_alert_v2_by_id(active_alert.alert_id)
    assert fetched_original.state == AlertState.RESOLVED


# =============================================================================
# 2. Deduplication Tests
# =============================================================================

def test_dedup_repeated_same_event():
    """Processing the exact same transition event multiple times produces only 1 alert."""
    service = AlertService()
    inc = make_incident(iid="INC-DEDUP-01", severity=RiskLevel.CRITICAL)
    evt = make_event("EVT-D1", inc.incident_id, IncidentEventType.CREATED, "Single event")

    alert1 = service.process_incident_transition(inc, evt)
    assert alert1 is not None

    # Repeat same event
    alert2 = service.process_incident_transition(inc, evt)
    assert alert2 is None  # Suppressed by deterministic dedupe

    alerts = service.get_alerts_v2(incident_id=inc.incident_id)
    assert len(alerts) == 1


def test_dedup_multiple_observations_on_same_incident_do_not_flood():
    """Multiple observation additions do not generate duplicate new incident alerts."""
    service = AlertService()
    inc = make_incident(iid="INC-MULTI-OBS", severity=RiskLevel.HIGH)

    # Observation 1 -> CREATED
    evt1 = make_event("EVT-M1", inc.incident_id, IncidentEventType.CREATED, "First detection")
    a1 = service.process_incident_transition(inc, evt1)
    assert a1 is not None

    # Observation 2 -> OBSERVATION_ADDED (minor change, no escalation)
    evt2 = make_event("EVT-M2", inc.incident_id, IncidentEventType.OBSERVATION_ADDED, "Second detection joined")
    inc.observation_count = 2
    a2 = service.process_incident_transition(inc, evt2)
    # OBSERVATION_ADDED without extreme FRP or escalation does not trigger spam alert
    assert a2 is None

    alerts = service.get_alerts_v2(incident_id=inc.incident_id)
    assert len(alerts) == 1


# =============================================================================
# 3. Cooldown and Flood Protection Tests
# =============================================================================

def test_per_rule_cooldown_suppression():
    """Same rule on the same incident within cooldown window is suppressed."""
    config = FloodProtectionConfig(per_rule_cooldown_seconds=600, per_incident_cooldown_seconds=10)
    service = AlertService(flood_engine=FloodProtectionEngine(config))

    inc = make_incident(iid="INC-COOL-01", severity=RiskLevel.HIGH, risk_score=60.0)

    # Event 1 at T=0
    evt1 = make_event("EVT-R1", inc.incident_id, IncidentEventType.ESCALATED, "Escalate 1", timestamp_utc="2026-10-01T08:00:00Z")
    a1 = service.process_incident_transition(inc, evt1)
    assert a1 is not None
    assert a1.state == AlertState.ACTIVE

    # Event 2 at T=60s (within 600s rule cooldown, same severity)
    evt2 = make_event("EVT-R2", inc.incident_id, IncidentEventType.ESCALATED, "Escalate 2", timestamp_utc="2026-10-01T08:01:00Z")
    a2 = service.process_incident_transition(inc, evt2)

    assert a2 is not None
    assert a2.state == AlertState.SUPPRESSED
    assert "RULE_COOLDOWN" in a2.evidence.get("suppression_type", "")


def test_per_incident_pacing_cooldown():
    """Rapid successive events on the same incident are paced."""
    config = FloodProtectionConfig(per_rule_cooldown_seconds=10, per_incident_cooldown_seconds=180)
    service = AlertService(flood_engine=FloodProtectionEngine(config))

    inc = make_incident(iid="INC-PACE-01", severity=RiskLevel.HIGH)

    # Alert 1
    evt1 = make_event("EVT-P1", inc.incident_id, IncidentEventType.CREATED, "Created", timestamp_utc="2026-10-01T08:00:00Z")
    a1 = service.process_incident_transition(inc, evt1)
    assert a1.state == AlertState.ACTIVE

    # Alert 2 from different rule at T=30s (< 180s pacing cooldown)
    evt2 = make_event("EVT-P2", inc.incident_id, IncidentEventType.REOPENED, "Reopened", timestamp_utc="2026-10-01T08:00:30Z")
    a2 = service.process_incident_transition(inc, evt2)
    assert a2.state == AlertState.SUPPRESSED
    assert "INCIDENT_COOLDOWN" in a2.evidence.get("suppression_type", "")


def test_chattering_incident_rate_limiting():
    """Incidents generating excessive alerts exceed window limit and are suppressed."""
    config = FloodProtectionConfig(
        per_rule_cooldown_seconds=0,
        per_incident_cooldown_seconds=0,
        max_alerts_per_window=3,
        window_seconds=3600,
    )
    service = AlertService(flood_engine=FloodProtectionEngine(config))
    inc = make_incident(iid="INC-CHATTER-01", severity=RiskLevel.HIGH)

    # Fire 3 allowed alerts
    for i in range(3):
        evt = make_event(f"EVT-CH-{i}", inc.incident_id, IncidentEventType.ESCALATED, f"Esc {i}", timestamp_utc=f"2026-10-01T08:0{i}:00Z")
        # Ensure distinct dedupe key
        inc.current_risk_score = 60.0 + i
        a = service.process_incident_transition(inc, evt)
        assert a.state == AlertState.ACTIVE

    # 4th alert must be suppressed due to rate limiting
    evt4 = make_event("EVT-CH-4", inc.incident_id, IncidentEventType.ESCALATED, "Esc 4", timestamp_utc="2026-10-01T08:10:00Z")
    a4 = service.process_incident_transition(inc, evt4)
    assert a4.state == AlertState.SUPPRESSED
    assert a4.evidence.get("suppression_type") == "RATE_LIMITED"


def test_critical_escalation_bypasses_pacing_cooldown():
    """A genuine CRITICAL escalation overrides minor pacing cooldown."""
    config = FloodProtectionConfig(per_rule_cooldown_seconds=900, per_incident_cooldown_seconds=180)
    service = AlertService(flood_engine=FloodProtectionEngine(config))

    inc = make_incident(iid="INC-CRIT-OVERRIDE", severity=RiskLevel.HIGH, risk_score=60.0, peak_frp=50.0)

    # 1. Warning alert at T=0
    evt1 = make_event("EVT-W1", inc.incident_id, IncidentEventType.CREATED, "Created", timestamp_utc="2026-10-01T08:00:00Z")
    a1 = service.process_incident_transition(inc, evt1)
    assert a1.priority == AlertSeverity.WARNING

    # 2. Critical surge at T=30s
    inc_crit = make_incident(iid="INC-CRIT-OVERRIDE", severity=RiskLevel.CRITICAL, risk_score=95.0, peak_frp=150.0)
    evt2 = make_event(
        "EVT-C2",
        inc.incident_id,
        IncidentEventType.ESCALATED,
        "Critical explosive canopy flare",
        timestamp_utc="2026-10-01T08:00:30Z",
    )
    a2 = service.process_incident_transition(inc_crit, evt2)

    # Must be allowed through despite 30s elapsed!
    assert a2.state == AlertState.ACTIVE
    assert a2.priority == AlertSeverity.CRITICAL


# =============================================================================
# 4. Lifecycle State Transitions Tests
# =============================================================================

def test_alert_lifecycle_states(temp_db):
    """Test full progression: active -> acknowledged -> resolved -> suppressed."""
    service = AlertService(connection_factory=temp_db)
    inc = make_incident(iid="INC-LIFE-01", severity=RiskLevel.CRITICAL)
    evt = make_event("EVT-L1", inc.incident_id, IncidentEventType.CREATED, "Initial fire")

    alert = service.process_incident_transition(inc, evt)
    assert alert.state == AlertState.ACTIVE

    # Acknowledge
    ack_ok = service.acknowledge_alert_v2(alert.alert_id)
    assert ack_ok is True
    fetched = service.get_alert_v2_by_id(alert.alert_id)
    assert fetched.state == AlertState.ACKNOWLEDGED
    assert fetched.acknowledged_at_utc is not None

    # Resolve
    res_ok = service.resolve_alert(alert.alert_id, reason="Contained by air tanker")
    assert res_ok is True
    fetched = service.get_alert_v2_by_id(alert.alert_id)
    assert fetched.state == AlertState.RESOLVED
    assert fetched.resolved_at_utc is not None

    # Suppress
    sup_ok = service.suppress_alert(alert.alert_id, reason="False alarm verification")
    assert sup_ok is True
    fetched = service.get_alert_v2_by_id(alert.alert_id)
    assert fetched.state == AlertState.SUPPRESSED


# =============================================================================
# 5. Restart Semantics & SQLite Persistence Tests
# =============================================================================

def test_acknowledgement_survives_service_restart(temp_db):
    """Acknowledgment state survives service re-instantiation and database is source of truth."""
    # 1. First service instance creates and acknowledges alert
    service_1 = AlertService(connection_factory=temp_db)
    inc = make_incident(iid="INC-PERSIST-01", severity=RiskLevel.CRITICAL)
    evt = make_event("EVT-P1", inc.incident_id, IncidentEventType.CREATED, "Initial alert")

    alert = service_1.process_incident_transition(inc, evt)
    assert alert is not None

    # Initial unread count should be 1
    resp_before = service_1.get_alerts()
    assert resp_before.unread_count == 1

    # Operator acknowledges alert
    ack_res = service_1.acknowledge_alert(alert.alert_id)
    assert ack_res is True

    # 2. Simulate process/service restart: instantiate a completely new service instance
    service_2 = AlertService(connection_factory=temp_db)

    # 3. Verify state remains acknowledged in new service
    fetched_v2 = service_2.get_alert_v2_by_id(alert.alert_id)
    assert fetched_v2 is not None
    assert fetched_v2.state == AlertState.ACKNOWLEDGED
    assert fetched_v2.acknowledged_at_utc is not None

    # 4. Verify unread_count is 0 in new service
    resp_after = service_2.get_alerts()
    assert resp_after.unread_count == 0
    assert resp_after.total == 1
    assert resp_after.items[0].is_acknowledged is True


# =============================================================================
# 6. Operational Alert Health Telemetry Tests
# =============================================================================

def test_alert_health_computation():
    """Verify alert health telemetry metrics, priority mix, and chatter identification."""
    alerts = [
        AlertV2(
            alert_id="A-1",
            incident_id="INC-NOISY",
            rule_id="RULE_NEW_INCIDENT",
            dedupe_key="K-1",
            priority=AlertSeverity.CRITICAL,
            state=AlertState.ACKNOWLEDGED,
            title="Crit 1",
            message="Msg",
            created_at_utc="2026-10-01T08:00:00Z",
            acknowledged_at_utc="2026-10-01T08:05:00Z",
        ),
        AlertV2(
            alert_id="A-2",
            incident_id="INC-NOISY",
            rule_id="RULE_INCIDENT_ESCALATED",
            dedupe_key="K-2",
            priority=AlertSeverity.CRITICAL,
            state=AlertState.ACTIVE,
            title="Crit 2",
            message="Msg",
            created_at_utc="2026-10-01T08:10:00Z",
        ),
        AlertV2(
            alert_id="A-3",
            incident_id="INC-NOISY",
            rule_id="RULE_EXTREME_FRP",
            dedupe_key="K-3",
            priority=AlertSeverity.WARNING,
            state=AlertState.SUPPRESSED,
            title="Warn 1",
            message="Msg",
            created_at_utc="2026-10-01T08:15:00Z",
        ),
        AlertV2(
            alert_id="A-4",
            incident_id="INC-QUIET",
            rule_id="RULE_NEW_INCIDENT",
            dedupe_key="K-4",
            priority=AlertSeverity.INFO,
            state=AlertState.RESOLVED,
            title="Info 1",
            message="Msg",
            created_at_utc="2026-10-01T08:20:00Z",
            resolved_at_utc="2026-10-01T08:30:00Z",
        ),
    ]

    metrics = compute_health_from_alerts(
        alerts=alerts,
        window_seconds=3600,
        as_of_utc="2026-10-01T08:30:00Z",
        chatter_threshold=3,
    )

    assert metrics.total_alerts == 4
    assert metrics.critical_count == 2
    assert metrics.warning_count == 1
    assert metrics.info_count == 1
    assert metrics.acknowledged_count == 1
    assert metrics.unresolved_count == 1
    assert metrics.resolved_count == 1
    assert metrics.suppressed_count == 1
    assert metrics.alert_rate_per_hour == 4.0

    # Priority mix: 2/4 = 50% critical, 1/4 = 25% warning, 1/4 = 25% info
    assert metrics.priority_mix["critical"] == 50.0
    assert metrics.priority_mix["warning"] == 25.0
    assert metrics.priority_mix["info"] == 25.0

    # Chattering incident detection
    assert len(metrics.chattering_incidents) == 1
    chatter = metrics.chattering_incidents[0]
    assert chatter.incident_id == "INC-NOISY"
    assert chatter.alert_count == 3
    assert chatter.critical_count == 2
    assert chatter.suppressed_count == 1


def test_dedup_repeated_refresh_cycles():
    """Repeated sync/refresh sweeps across multiple incidents produce zero duplicates."""
    service = AlertService()
    inc1 = make_incident(iid="INC-REFRESH-01", severity=RiskLevel.CRITICAL)
    inc2 = make_incident(iid="INC-REFRESH-02", severity=RiskLevel.HIGH)

    evt1 = make_event("EVT-R1", inc1.incident_id, IncidentEventType.CREATED, "Init 1")
    evt2 = make_event("EVT-R2", inc2.incident_id, IncidentEventType.CREATED, "Init 2")

    # Cycle 1: First sync
    a1 = service.process_incident_transition(inc1, evt1)
    a2 = service.process_incident_transition(inc2, evt2)
    assert a1 is not None
    assert a2 is not None

    all_alerts_cycle_1 = service.get_alerts_v2()
    assert len(all_alerts_cycle_1) == 2

    # Cycle 2: Second sync/refresh with identical event context
    a1_repeat = service.process_incident_transition(inc1, evt1)
    a2_repeat = service.process_incident_transition(inc2, evt2)
    assert a1_repeat is None
    assert a2_repeat is None

    # Total alerts in service remains strictly 2
    all_alerts_cycle_2 = service.get_alerts_v2()
    assert len(all_alerts_cycle_2) == 2

    # Cycle 3: Third sync/refresh
    a1_repeat_3 = service.process_incident_transition(inc1, evt1)
    assert a1_repeat_3 is None
    assert len(service.get_alerts_v2()) == 2


def test_resolution_and_suppression_survives_service_restart(temp_db):
    """Resolution and suppression state persists in SQLite and survives service reconstruction."""
    # Service 1: Create alerts and transition their states
    service_1 = AlertService(connection_factory=temp_db)

    inc1 = make_incident(iid="INC-PERSIST-RES", severity=RiskLevel.CRITICAL)
    inc2 = make_incident(iid="INC-PERSIST-SUP", severity=RiskLevel.HIGH)

    evt1 = make_event("EVT-PR-1", inc1.incident_id, IncidentEventType.CREATED, "To be resolved")
    evt2 = make_event("EVT-PS-1", inc2.incident_id, IncidentEventType.CREATED, "To be suppressed")

    a1 = service_1.process_incident_transition(inc1, evt1)
    a2 = service_1.process_incident_transition(inc2, evt2)

    assert a1.state == AlertState.ACTIVE
    assert a2.state == AlertState.ACTIVE

    # Resolve a1 and suppress a2
    service_1.resolve_alert(a1.alert_id, reason="Contained by crew")
    service_1.suppress_alert(a2.alert_id, reason="Controlled burn confirmed")

    # Service 2: Reconstruct service from same database
    service_2 = AlertService(connection_factory=temp_db)

    fetched_a1 = service_2.get_alert_v2_by_id(a1.alert_id)
    assert fetched_a1 is not None
    assert fetched_a1.state == AlertState.RESOLVED
    assert fetched_a1.resolved_at_utc is not None

    fetched_a2 = service_2.get_alert_v2_by_id(a2.alert_id)
    assert fetched_a2 is not None
    assert fetched_a2.state == AlertState.SUPPRESSED

    # Unread count must be 0 because none are active
    v1_alerts = service_2.get_alerts()
    assert v1_alerts.unread_count == 0


def test_alert_evidence_answering_why_created():
    """Verify Alert evidence answers 'WHY WAS THIS ALERT CREATED' comprehensively."""
    service = AlertService()
    inc = make_incident(
        iid="INC-EVIDENCE-TEST",
        severity=RiskLevel.CRITICAL,
        risk_score=92.5,
        peak_frp=165.0,
        nearest_place="Napa Foothills, CA",
    )
    evt = make_event(
        event_id="EVT-EV-01",
        incident_id=inc.incident_id,
        event_type=IncidentEventType.ESCALATED,
        reason="Radiance jumped 70MW; perimeter encroaching residential structures",
        metadata={"old_risk": 55.0, "new_risk": 92.5, "old_severity": "high", "new_severity": "critical"},
    )

    alert = service.process_incident_transition(inc, evt)
    assert alert is not None

    # Evidence inspection
    ev = alert.evidence
    assert ev["incident_id"] == "INC-EVIDENCE-TEST"
    assert ev["triggering_rule"] == "RULE_INCIDENT_ESCALATED"
    assert ev["transition"] == "escalated"
    assert ev["current_risk_score"] == 92.5
    assert ev["previous_risk_score"] == 55.0
    assert ev["current_severity"] == "critical"
    assert ev["previous_severity"] == "high"
    assert ev["peak_frp"] == 165.0
    assert ev["nearest_place"] == "Napa Foothills, CA"
    assert ev["event_reason"] == "Radiance jumped 70MW; perimeter encroaching residential structures"
    assert ev["event_id"] == "EVT-EV-01"
    assert ev["event_timestamp_utc"] == "2026-10-01T08:30:00Z"
    assert alert.created_at_utc == "2026-10-01T08:30:00Z"

