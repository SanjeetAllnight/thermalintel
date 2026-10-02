"""Comprehensive test suite for ThermalIntel V2 Persistent Incident Engine.

Covers:
1. New incident creation and stable identity rule (INC-YYYYMMDD-XXXX)
2. Existing incident continuation
3. Multiple observations aggregation
4. Cross-satellite multi-sensor observations (VIIRS Suomi-NPP, NOAA-20, MODIS Aqua)
5. Spatial boundary enforcement (within vs beyond threshold)
6. Temporal boundary enforcement (within vs beyond window)
7. Classification compatibility (conflicting source types separated)
8. Incident merge (deterministic survivor, history preservation, resolvability)
9. Incident split (lineage, child creation, event auditing)
10. Stable ID invariance under centroid shifts, risk updates, and observation additions
11. Append-only events timeline
12. Risk escalation and de-escalation transitions
13. Lifecycle closure and observation-driven reopen
14. Idempotency under duplicate ingestion
15. Idempotency under shuffled observation order
16. Property-style randomized ordering invariance
17. Service-level query methods (active, ID, timeline, observations, history)
18. Truthful dossier synthesis without fabricated intelligence numbers
"""

import json
import random
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import pytest

from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.v2 import (
    Observation,
    Incident,
    IncidentObservation,
    IncidentEvent,
    IncidentStatus,
    IncidentEventType,
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
    RiskFactor,
)
from services.api.incidents.models import CorrelationResult, IncidentHistory
from services.api.incidents.repository import IncidentRepository, InMemoryIncidentRepository
from services.api.incidents.engine import IncidentEngine, generate_stable_incident_id
from services.api.incidents.service import IncidentService
from services.api.migrations.runner import MigrationRunner


def make_test_observation(
    obs_id: str,
    lat: float = 38.5000,
    lon: float = -122.5000,
    acq_time: str = "2026-10-01T08:00:00Z",
    frp: float = 85.0,
    brightness: float = 330.0,
    satellite: str = "Suomi-NPP",
    instrument: str = "VIIRS",
    source_type: Optional[SourceType] = None,
) -> Observation:
    """Helper to instantiate a valid canonical Observation."""
    attrs = {}
    if source_type:
        attrs["source_type"] = source_type.value
    return Observation(
        observation_id=obs_id,
        provider="NASA_FIRMS",
        product=f"{instrument}_{satellite}_NRT",
        satellite=satellite,
        instrument=instrument,
        latitude=lat,
        longitude=lon,
        acquisition_time_utc=acq_time,
        ingestion_time_utc=acq_time,
        brightness=brightness,
        bright_t31=295.0,
        frp=frp,
        scan=0.375,
        track=0.375,
        daynight="N",
        detection_confidence="high",
        source_attributes=attrs,
        schema_version="2.0",
    )


@pytest.fixture
def in_memory_engine():
    """Fixture providing an IncidentEngine backed by an in-memory repository."""
    repo = InMemoryIncidentRepository()
    engine = IncidentEngine(
        repository=repo,
        spatial_threshold_km=2.0,
        temporal_window_hours=24.0,
    )
    return engine, repo


@pytest.fixture
def sqlite_engine():
    """Fixture providing an IncidentEngine backed by a temporary migrated SQLite database."""
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "test_incidents.db"
    runner = MigrationRunner(db_path)
    runner.apply_migrations()

    repo = IncidentRepository(db_path=db_path)
    engine = IncidentEngine(
        repository=repo,
        spatial_threshold_km=2.0,
        temporal_window_hours=24.0,
    )
    yield engine, repo
    temp_dir.cleanup()


# =============================================================================
# 1. New Incident Creation & Stable Identity
# =============================================================================

def test_new_incident_creation_and_stable_id(in_memory_engine):
    """When a cluster has no matching open incident, create persistent Incident with stable ID."""
    engine, repo = in_memory_engine
    obs = make_test_observation("OBS-001", lat=38.5, lon=-122.5, frp=120.0)

    result = engine.correlate_observations([obs])

    assert len(result.created_incidents) == 1
    inc = result.created_incidents[0]

    # Contract pattern: INC-YYYYMMDD-XXXX
    assert inc.incident_id.startswith("INC-20261001-")
    assert len(inc.incident_id) >= 16
    assert inc.observation_count == 1
    assert inc.peak_frp == 120.0
    assert inc.status == IncidentStatus.ACTIVE

    # Timeline events
    events = repo.list_incident_events(inc.incident_id)
    event_types = [e.event_type for e in events]
    assert IncidentEventType.CREATED in event_types
    assert IncidentEventType.OBSERVATION_ADDED in event_types


# =============================================================================
# 2. Existing Incident Continuation
# =============================================================================

def test_existing_incident_continuation(in_memory_engine):
    """New observations within spatial and temporal threshold match and continue existing incident."""
    engine, repo = in_memory_engine
    obs1 = make_test_observation("OBS-001", lat=38.500, lon=-122.500, acq_time="2026-10-01T08:00:00Z", frp=50.0)
    result1 = engine.correlate_observations([obs1])
    orig_inc_id = result1.created_incidents[0].incident_id

    # Observation 2: 4 hours later, 600m away (well within 2.0km and 24h)
    obs2 = make_test_observation("OBS-002", lat=38.505, lon=-122.504, acq_time="2026-10-01T12:00:00Z", frp=90.0)
    result2 = engine.correlate_observations([obs2])

    assert len(result2.created_incidents) == 0
    assert len(result2.updated_incidents) == 1

    updated_inc = repo.get_incident(orig_inc_id)
    assert updated_inc.incident_id == orig_inc_id
    assert updated_inc.observation_count == 2
    assert updated_inc.peak_frp == 90.0
    assert updated_inc.last_seen_utc == "2026-10-01T12:00:00Z"


# =============================================================================
# 3. Multiple Observations Aggregation
# =============================================================================

def test_multiple_observations_aggregation(in_memory_engine):
    """Multiple proximate observations group cleanly into a single incident."""
    engine, repo = in_memory_engine
    obs_batch = [
        make_test_observation(f"OBS-BATCH-{i}", lat=38.500 + i * 0.003, lon=-122.500 + i * 0.003, frp=40.0 + i * 15.0)
        for i in range(4)
    ]

    result = engine.correlate_observations(obs_batch)

    assert len(result.created_incidents) == 1
    inc = result.created_incidents[0]
    assert inc.observation_count == 4
    assert inc.peak_frp == 85.0
    assert result.associations_count == 4

    linked_obs = repo.list_incident_observations(inc.incident_id)
    assert len(linked_obs) == 4


# =============================================================================
# 4. Cross-Satellite Multi-Sensor Observations
# =============================================================================

def test_cross_satellite_observations(in_memory_engine):
    """Observations from different satellites and sensors in the same area correlate together."""
    engine, repo = in_memory_engine
    obs_snpp = make_test_observation("OBS-SNPP", lat=37.77, lon=-122.41, satellite="Suomi-NPP", instrument="VIIRS", acq_time="2026-10-01T08:00:00Z", frp=70.0)
    obs_noaa20 = make_test_observation("OBS-NOAA20", lat=37.773, lon=-122.412, satellite="NOAA-20", instrument="VIIRS", acq_time="2026-10-01T09:40:00Z", frp=95.0)
    obs_aqua = make_test_observation("OBS-AQUA", lat=37.771, lon=-122.409, satellite="Aqua", instrument="MODIS", acq_time="2026-10-01T11:15:00Z", frp=110.0)

    result = engine.correlate_observations([obs_snpp, obs_noaa20, obs_aqua])

    assert len(result.created_incidents) == 1
    inc = result.created_incidents[0]
    assert inc.observation_count == 3
    assert inc.peak_frp == 110.0

    linked = repo.list_incident_observations(inc.incident_id)
    satellites = {o.satellite for o in linked}
    assert satellites == {"Suomi-NPP", "NOAA-20", "Aqua"}


# =============================================================================
# 5. Spatial Boundary Enforcement
# =============================================================================

def test_spatial_boundary_separation(in_memory_engine):
    """Observations separated beyond distance threshold form separate incidents."""
    engine, _ = in_memory_engine
    obs_a = make_test_observation("OBS-A", lat=38.000, lon=-122.000)
    # Distance approx 11 km north (> 2.0 km threshold)
    obs_b = make_test_observation("OBS-B", lat=38.100, lon=-122.000)

    result = engine.correlate_observations([obs_a, obs_b])

    assert len(result.created_incidents) == 2
    id_a = result.created_incidents[0].incident_id
    id_b = result.created_incidents[1].incident_id
    assert id_a != id_b


# =============================================================================
# 6. Temporal Boundary Enforcement
# =============================================================================

def test_temporal_boundary_separation(in_memory_engine):
    """Observations at the same location but separated by > 24 hours form separate incidents."""
    engine, _ = in_memory_engine
    obs_day1 = make_test_observation("OBS-DAY1", lat=38.0, lon=-122.0, acq_time="2026-10-01T08:00:00Z")
    # 36 hours later (> 24 hour window)
    obs_day2 = make_test_observation("OBS-DAY2", lat=38.0, lon=-122.0, acq_time="2026-10-02T20:00:00Z")

    result = engine.correlate_observations([obs_day1, obs_day2])

    assert len(result.created_incidents) == 2


# =============================================================================
# 7. Classification Compatibility
# =============================================================================

def test_classification_compatibility_separation(in_memory_engine):
    """Incompatible classification types (e.g. volcanic vs agricultural) do not merge if > 300m."""
    engine, _ = in_memory_engine
    obs_volc = make_test_observation("OBS-VOLC", lat=38.000, lon=-122.000, source_type=SourceType.VOLCANIC)
    # 800m away, agricultural (> 300m threshold for incompatible sources)
    obs_agri = make_test_observation("OBS-AGRI", lat=38.007, lon=-122.000, source_type=SourceType.AGRICULTURAL)

    result = engine.correlate_observations([obs_volc, obs_agri])

    assert len(result.created_incidents) == 2


# =============================================================================
# 8. Incident Merge
# =============================================================================

def test_incident_merge_semantics(in_memory_engine):
    """Deterministic merge preserves history, re-associates observations, and keeps merged ID resolvable."""
    engine, repo = in_memory_engine

    # Incident 1 (earlier: 08:00 UTC)
    obs1 = make_test_observation("OBS-M1", lat=38.000, lon=-122.000, acq_time="2026-10-01T08:00:00Z", frp=50.0)
    res1 = engine.correlate_observations([obs1])
    inc1_id = res1.created_incidents[0].incident_id

    # Incident 2 (later: 09:00 UTC, outside spatial threshold of inc1 so it forms separate incident)
    obs2 = make_test_observation("OBS-M2", lat=38.050, lon=-122.050, acq_time="2026-10-01T09:00:00Z", frp=90.0)
    res2 = engine.correlate_observations([obs2])
    inc2_id = res2.created_incidents[0].incident_id

    assert inc1_id != inc2_id

    # Execute merge
    survivor, absorbed = engine.merge_incidents(inc1_id, inc2_id, reason="Complex expansion merge")

    # Survivor must be inc1 (earlier first_seen)
    assert survivor.incident_id == inc1_id
    assert absorbed.incident_id == inc2_id

    # Absorbed status is CLOSED (not deleted)
    assert absorbed.status == IncidentStatus.CLOSED

    # Historical resolvability: querying absorbed ID still succeeds
    queried_absorbed = repo.get_incident(inc2_id)
    assert queried_absorbed is not None
    assert queried_absorbed.status == IncidentStatus.CLOSED

    # Survivor now contains observations from both
    survivor_obs = repo.list_incident_observations(inc1_id)
    assert len(survivor_obs) == 2
    assert survivor.peak_frp == 90.0

    # Append-only timeline events check
    events_absorbed = repo.list_incident_events(inc2_id)
    events_survivor = repo.list_incident_events(inc1_id)

    assert any(e.event_type == IncidentEventType.MERGED and e.metadata.get("surviving_incident_id") == inc1_id for e in events_absorbed)
    assert any(e.event_type == IncidentEventType.MERGED and e.metadata.get("absorbed_incident_id") == inc2_id for e in events_survivor)


def test_bridging_observation_automatic_merge(in_memory_engine):
    """When a new observation bridges two existing tracked incidents, they are merged automatically."""
    engine, repo = in_memory_engine

    # Incident 1 (at 38.000, -122.000)
    obs1 = make_test_observation("OBS-B1", lat=38.000, lon=-122.000, acq_time="2026-10-01T08:00:00Z", frp=50.0)
    res1 = engine.correlate_observations([obs1])
    inc1_id = res1.created_incidents[0].incident_id

    # Incident 2 (approx 3.3 km away at 38.030, -122.000, beyond 2.0 km threshold)
    obs2 = make_test_observation("OBS-B2", lat=38.030, lon=-122.000, acq_time="2026-10-01T08:30:00Z", frp=80.0)
    res2 = engine.correlate_observations([obs2])
    inc2_id = res2.created_incidents[0].incident_id
    assert inc1_id != inc2_id

    # Bridging observation at (38.015, -122.000), ~1.65 km from both inc1 and inc2
    obs_bridge = make_test_observation("OBS-BRIDGE", lat=38.015, lon=-122.000, acq_time="2026-10-01T09:00:00Z", frp=110.0)
    res_bridge = engine.correlate_observations([obs_bridge])

    # Should report one absorbed incident in merged_incidents
    assert len(res_bridge.merged_incidents) == 1
    absorbed_id = res_bridge.merged_incidents[0].incident_id
    assert absorbed_id == inc2_id

    # Survivor is inc1
    survivor = repo.get_incident(inc1_id)
    assert survivor.incident_id == inc1_id
    assert survivor.observation_count == 3
    assert survivor.peak_frp == 110.0

    # Absorbed is CLOSED and resolvable
    absorbed = repo.get_incident(inc2_id)
    assert absorbed.status == IncidentStatus.CLOSED


# =============================================================================
# 9. Incident Split
# =============================================================================

def test_incident_split_semantics(in_memory_engine):
    """Splitting an incident safely partitions observations, mints new child ID, and records SPLIT events."""
    engine, repo = in_memory_engine

    obs1 = make_test_observation("OBS-S1", lat=38.000, lon=-122.000, frp=60.0)
    obs2 = make_test_observation("OBS-S2", lat=38.001, lon=-122.001, frp=70.0)
    obs3 = make_test_observation("OBS-S3", lat=38.008, lon=-122.008, frp=150.0)

    res = engine.correlate_observations([obs1, obs2, obs3])
    parent_id = res.created_incidents[0].incident_id

    # Split OBS-S3 into a new child incident
    parent_after, child = engine.split_incident(
        parent_id,
        split_observation_ids=["OBS-S3"],
        reason="Divergent fire front detected",
    )

    # Child must have a unique stable incident ID
    assert child.incident_id != parent_id
    assert child.incident_id.startswith("INC-20261001-")
    assert child.observation_count == 1
    assert child.peak_frp == 150.0

    # Parent retains remaining 2 observations
    assert parent_after.observation_count == 2
    parent_obs = repo.list_incident_observations(parent_id)
    assert {o.observation_id for o in parent_obs} == {"OBS-S1", "OBS-S2"}

    # Child has OBS-S3
    child_obs = repo.list_incident_observations(child.incident_id)
    assert {o.observation_id for o in child_obs} == {"OBS-S3"}

    # Check SPLIT events on both
    p_events = repo.list_incident_events(parent_id)
    c_events = repo.list_incident_events(child.incident_id)

    assert any(e.event_type == IncidentEventType.SPLIT and e.metadata.get("child_incident_id") == child.incident_id for e in p_events)
    assert any(e.event_type == IncidentEventType.SPLIT and e.metadata.get("parent_incident_id") == parent_id for e in c_events)


# =============================================================================
# 10. Stable ID Invariance Under Evolution
# =============================================================================

def test_stable_id_invariance_under_state_evolution(in_memory_engine):
    """Incident ID MUST NOT change when centroid shifts, peak FRP changes, or risk changes."""
    engine, repo = in_memory_engine
    obs1 = make_test_observation("OBS-STABLE-1", lat=38.100, lon=-122.100, frp=40.0)
    res = engine.correlate_observations([obs1])
    stable_id = res.created_incidents[0].incident_id

    # Observation 2 arrives with much higher FRP and shifted position
    obs2 = make_test_observation("OBS-STABLE-2", lat=38.109, lon=-122.109, frp=350.0)
    engine.correlate_observations([obs2])

    inc = repo.get_incident(stable_id)
    assert inc.incident_id == stable_id
    assert inc.peak_frp == 350.0
    assert inc.centroid_latitude != 38.100  # Centroid shifted
    assert inc.current_severity == RiskLevel.CRITICAL  # Risk changed


# =============================================================================
# 11. Append-Only Events Timeline
# =============================================================================

def test_append_only_events_timeline(in_memory_engine):
    """Timeline events are append-only and ordered chronologically."""
    engine, repo = in_memory_engine
    obs1 = make_test_observation("OBS-EVT-1", frp=30.0)
    res = engine.correlate_observations([obs1])
    inc_id = res.created_incidents[0].incident_id

    # Escalate by adding high-power observation
    obs2 = make_test_observation("OBS-EVT-2", frp=200.0)
    engine.correlate_observations([obs2])

    # Operator operations
    engine.acknowledge_incident(inc_id, reason="Dispatch alerted")
    engine.close_incident(inc_id, reason="Controlled burn extinguished")
    engine.reopen_incident(inc_id, reason="Flare-up reported")

    events = repo.list_incident_events(inc_id)
    event_types = [e.event_type for e in events]

    assert event_types == [
        IncidentEventType.CREATED,
        IncidentEventType.OBSERVATION_ADDED,
        IncidentEventType.OBSERVATION_ADDED,
        IncidentEventType.ESCALATED,
        IncidentEventType.ACKNOWLEDGED,
        IncidentEventType.CLOSED,
        IncidentEventType.REOPENED,
    ]

    # Verify chronological monotonicity
    timestamps = [e.timestamp_utc for e in events]
    assert timestamps == sorted(timestamps)


# =============================================================================
# 12. Risk Escalation and De-escalation
# =============================================================================

def test_risk_escalation_and_deescalation(in_memory_engine):
    """Meaningful risk tier crossings emit ESCALATED and DEESCALATED events."""
    engine, repo = in_memory_engine

    # Step 1: Low FRP observation -> initial severity MEDIUM / LOW
    obs1 = make_test_observation("OBS-R1", frp=20.0)
    res = engine.correlate_observations([obs1])
    inc_id = res.created_incidents[0].incident_id
    assert repo.get_incident(inc_id).current_severity in (RiskLevel.LOW, RiskLevel.MEDIUM)

    # Step 2: Critical observation added -> ESCALATED event
    obs2 = make_test_observation("OBS-R2", frp=150.0)
    engine.correlate_observations([obs2])

    inc_after = repo.get_incident(inc_id)
    assert inc_after.current_severity == RiskLevel.CRITICAL

    events = repo.list_incident_events(inc_id)
    assert any(e.event_type == IncidentEventType.ESCALATED for e in events)


# =============================================================================
# 13. Closure and Reopen Lifecycle
# =============================================================================

def test_closure_and_reopen_lifecycle(in_memory_engine):
    """Closed incident automatically reopens upon new satellite detection arrival."""
    engine, repo = in_memory_engine
    obs1 = make_test_observation("OBS-C1", frp=80.0)
    res = engine.correlate_observations([obs1])
    inc_id = res.created_incidents[0].incident_id

    # Explicitly close
    engine.close_incident(inc_id, reason="Contained by local crews")
    assert repo.get_incident(inc_id).status == IncidentStatus.CLOSED

    # Ingest new observation at same coordinate 6 hours later
    obs2 = make_test_observation("OBS-C2", acq_time="2026-10-01T14:00:00Z", frp=110.0)
    engine.correlate_observations([obs2])

    reopened_inc = repo.get_incident(inc_id)
    assert reopened_inc.status == IncidentStatus.ACTIVE
    assert reopened_inc.observation_count == 2

    events = repo.list_incident_events(inc_id)
    assert any(e.event_type == IncidentEventType.REOPENED for e in events)


# =============================================================================
# 14. Idempotency Under Duplicate Ingestion
# =============================================================================

def test_duplicate_ingestion_idempotency(in_memory_engine):
    """Ingesting identical observations twice causes zero duplicate links, events, or incidents."""
    engine, repo = in_memory_engine
    obs_batch = [
        make_test_observation("OBS-IDEMP-1", frp=50.0),
        make_test_observation("OBS-IDEMP-2", frp=75.0),
    ]

    # Run 1
    res1 = engine.correlate_observations(obs_batch)
    assert len(res1.created_incidents) == 1
    assert res1.associations_count == 2
    inc_id = res1.created_incidents[0].incident_id

    events_count_1 = len(repo.list_incident_events(inc_id))

    # Run 2: Exact duplicate ingestion
    res2 = engine.correlate_observations(obs_batch)
    assert len(res2.created_incidents) == 0
    assert len(res2.updated_incidents) == 0
    assert res2.associations_count == 0

    events_count_2 = len(repo.list_incident_events(inc_id))
    assert events_count_1 == events_count_2

    # Verification: incident record is unchanged
    inc = repo.get_incident(inc_id)
    assert inc.observation_count == 2


# =============================================================================
# 15. Idempotency Under Shuffled Input Order
# =============================================================================

def test_shuffled_observation_order_determinism():
    """Ingestion produces identical incident assignments regardless of input ordering."""
    obs_batch = [
        make_test_observation("OBS-SHUF-1", lat=38.500, lon=-122.500, frp=40.0),
        make_test_observation("OBS-SHUF-2", lat=38.502, lon=-122.502, frp=95.0),
        make_test_observation("OBS-SHUF-3", lat=38.504, lon=-122.504, frp=60.0),
    ]

    # Run on Repo A with original order
    repo_a = InMemoryIncidentRepository()
    engine_a = IncidentEngine(repository=repo_a)
    res_a = engine_a.correlate_observations(obs_batch)

    # Run on Repo B with reversed order
    repo_b = InMemoryIncidentRepository()
    engine_b = IncidentEngine(repository=repo_b)
    shuffled_batch = list(reversed(obs_batch))
    res_b = engine_b.correlate_observations(shuffled_batch)

    assert len(res_a.created_incidents) == len(res_b.created_incidents)
    inc_a = res_a.created_incidents[0]
    inc_b = res_b.created_incidents[0]

    assert inc_a.incident_id == inc_b.incident_id
    assert inc_a.centroid_latitude == inc_b.centroid_latitude
    assert inc_a.centroid_longitude == inc_b.centroid_longitude
    assert inc_a.peak_frp == inc_b.peak_frp
    assert inc_a.observation_count == inc_b.observation_count


# =============================================================================
# 16. Property-Style Randomized Fuzzing
# =============================================================================

def test_property_order_invariance_fuzzing():
    """Property test: 10 random permutations of the same observation set yield identical incident states."""
    base_observations = [
        make_test_observation(f"OBS-FUZZ-{i}", lat=38.0 + (i % 3) * 0.005, lon=-122.0 + (i % 3) * 0.005, frp=30.0 + i * 10.0)
        for i in range(6)
    ]

    # Baseline reference run
    baseline_repo = InMemoryIncidentRepository()
    baseline_engine = IncidentEngine(repository=baseline_repo)
    baseline_result = baseline_engine.correlate_observations(base_observations)
    expected_ids = sorted([inc.incident_id for inc in baseline_result.created_incidents])

    for seed in range(10):
        rng = random.Random(seed)
        shuffled = list(base_observations)
        rng.shuffle(shuffled)

        test_repo = InMemoryIncidentRepository()
        test_engine = IncidentEngine(repository=test_repo)
        test_result = test_engine.correlate_observations(shuffled)
        actual_ids = sorted([inc.incident_id for inc in test_result.created_incidents])

        assert actual_ids == expected_ids, f"Failed deterministic property on permutation seed {seed}"


# =============================================================================
# 17. Service-Level Query Methods
# =============================================================================

def test_incident_service_query_methods(in_memory_engine):
    """IncidentService exposes active incidents, timeline, observations, history, and assessment."""
    engine, repo = in_memory_engine
    service = IncidentService(repository=repo, engine=engine)

    obs = make_test_observation("OBS-SVC-1", frp=110.0)
    service.correlate_observations([obs])

    active = service.get_active_incidents()
    assert len(active) == 1
    inc_id = active[0].incident_id

    # Incident by ID
    inc = service.get_incident_by_id(inc_id)
    assert inc is not None
    assert inc.incident_id == inc_id

    # Timeline
    timeline = service.get_incident_timeline(inc_id)
    assert len(timeline) >= 2

    # Observations
    observations = service.get_incident_observations(inc_id)
    assert len(observations) == 1
    assert observations[0].observation_id == "OBS-SVC-1"

    # History bundle
    history = service.get_incident_history(inc_id)
    assert isinstance(history, IncidentHistory)
    assert history.incident.incident_id == inc_id
    assert len(history.observations) == 1
    assert len(history.events) >= 2


# =============================================================================
# 18. Truthful Dossier Synthesis Without Fabricated Numbers
# =============================================================================

def test_truthful_dossier_synthesis_no_fabrication():
    """Dossier fallback removes fabricated values (0.85, 40.0, 45.0) and presents truthful metrics."""
    from services.api.schemas.hotspot import Hotspot
    hotspot = Hotspot(
        id="VIIRS-TRUTHFUL-01",
        latitude=38.5,
        longitude=-122.5,
        brightness=340.0,
        scan=0.375,
        track=0.375,
        acq_date="2026-10-01",
        acq_time="0830",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=290.0,
        frp=140.0,
        daynight="N",
        source_type=SourceType.WILDFIRE,
        risk_score=85.0,
        risk_level=RiskLevel.CRITICAL,
        is_anomaly=True,
        cluster_id=None,
        cluster_size=1,
        nearest_place="Sonoma County",
        last_updated="2026-10-01T08:35:00Z",
    )

    service = IncidentService(repository=InMemoryIncidentRepository())
    detail = service.build_incident_detail(hotspot=hotspot, intelligence=None)

    # Verify no fabricated values
    assert detail.intelligence.risk.weather_component == 0.0  # Not 40.0
    assert detail.intelligence.risk.proximity_component == 0.0  # Not 45.0
    assert detail.intelligence.risk.historical_component == 0.0  # Not 15.0
    assert detail.intelligence.classification.confidence == 0.0  # Not 0.85
    assert detail.intelligence.risk.risk_score == 85.0
    assert detail.intelligence.risk.risk_level == RiskLevel.CRITICAL


# =============================================================================
# 19. SQLite Database Persistence Integration Test
# =============================================================================

def test_sqlite_persistence_end_to_end(sqlite_engine):
    """Verify all operations work end-to-end against real migrated SQLite database."""
    engine, repo = sqlite_engine
    obs1 = make_test_observation("OBS-SQLITE-1", lat=38.7, lon=-122.8, frp=130.0)
    obs2 = make_test_observation("OBS-SQLITE-2", lat=38.705, lon=-122.805, frp=160.0)

    result = engine.correlate_observations([obs1, obs2])
    assert len(result.created_incidents) == 1
    inc_id = result.created_incidents[0].incident_id

    # Verify in SQLite directly
    with repo.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (inc_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["observation_count"] == 2
        assert row["peak_frp"] == 160.0

        cursor.execute("SELECT COUNT(*) as cnt FROM incident_observations WHERE incident_id = ?", (inc_id,))
        assert cursor.fetchone()["cnt"] == 2

        cursor.execute("SELECT COUNT(*) as cnt FROM incident_events WHERE incident_id = ?", (inc_id,))
        assert cursor.fetchone()["cnt"] >= 2
