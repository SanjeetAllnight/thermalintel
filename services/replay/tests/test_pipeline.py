"""Integration tests for ReplayPipeline executing full ThermalIntel V2 stages."""

import unittest
from datetime import datetime, timezone

from services.replay.clock import SimulatedClock
from services.replay.pipeline import ReplayPipeline
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.common import RiskLevel, AlertSeverity, IncidentEventType


def make_obs(obs_id: str, acq_time: str, frp: float, lat: float = 34.0, lon: float = -118.0) -> Observation:
    """Helper creating test observation."""
    return Observation(
        observation_id=obs_id,
        provider="NASA_FIRMS",
        product="VIIRS_SNPP_NRT",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        latitude=lat,
        longitude=lon,
        acquisition_time_utc=acq_time,
        ingestion_time_utc=acq_time,
        brightness=320.0 + (frp * 0.4),
        bright_t31=295.0,
        frp=frp,
        daynight="D",
        detection_confidence="high",
        source_attributes={"nearest_place": "Foothill Valley"},
    )


class TestReplayPipeline(unittest.TestCase):
    """Test full pipeline execution in simulated time."""

    def setUp(self):
        self.clock = SimulatedClock("2026-10-01T12:00:00Z")
        self.pipeline = ReplayPipeline(clock=self.clock, seed=42)

    def test_pipeline_single_observation_flow(self):
        obs = make_obs("OBS-PIPE-1", "2026-10-01T12:00:00Z", frp=35.0)
        res = self.pipeline.process_observations([obs], as_of_utc="2026-10-01T12:00:00Z")

        # 1. Observation processed
        self.assertEqual(len(res.observations), 1)

        # 2. Assessment generated with methodology
        self.assertEqual(len(res.assessments), 1)
        asm = res.assessments[0]
        self.assertEqual(asm.target_id, "OBS-PIPE-1")
        self.assertEqual(asm.methodology.as_of_utc, "2026-10-01T12:00:00Z")
        self.assertIsNotNone(asm.methodology.input_hash)

        # 3. Incident created
        self.assertEqual(len(res.active_incidents), 1)
        inc = res.active_incidents[0]
        self.assertTrue(inc.incident_id.startswith("INC-"))
        self.assertEqual(inc.observation_count, 1)
        self.assertEqual(inc.peak_frp, 35.0)

        # 4. Lifecycle event created
        self.assertEqual(len(res.new_events), 1)
        self.assertEqual(res.new_events[0].event_type, IncidentEventType.CREATED)

    def test_pipeline_incident_stable_identity_and_escalation(self):
        # Step 1: Initial moderate detection (creates incident)
        obs1 = make_obs("OBS-INC-1", "2026-10-01T12:00:00Z", frp=20.0, lat=34.000, lon=-118.000)
        res1 = self.pipeline.process_observations([obs1], as_of_utc="2026-10-01T12:00:00Z")
        inc_id = res1.active_incidents[0].incident_id

        # Step 2: Nearby detection with extreme FRP (correlates to same incident and escalates)
        obs2 = make_obs("OBS-INC-2", "2026-10-01T14:00:00Z", frp=160.0, lat=34.005, lon=-118.004)
        res2 = self.pipeline.process_observations([obs2], as_of_utc="2026-10-01T14:00:00Z")

        # Verify stable incident identity
        self.assertEqual(len(self.pipeline.incidents), 1)
        inc = self.pipeline.incidents[0]
        self.assertEqual(inc.incident_id, inc_id)
        self.assertEqual(inc.observation_count, 2)
        self.assertEqual(inc.peak_frp, 160.0)

        # Verify lifecycle events include created, observation_added, and escalated
        event_types = [e.event_type for e in self.pipeline.events]
        self.assertIn(IncidentEventType.CREATED, event_types)
        self.assertIn(IncidentEventType.OBSERVATION_ADDED, event_types)
        self.assertIn(IncidentEventType.ESCALATED, event_types)

    def test_pipeline_as_of_semantics_vs_created_at(self):
        """Verify Requirement 2: as_of_utc represents simulated time, created_at represents DB time."""
        sim_time = "2021-06-15T08:30:00Z"
        obs = make_obs("OBS-TIME-1", sim_time, frp=40.0)
        res = self.pipeline.process_observations([obs], as_of_utc=sim_time)

        asm = res.assessments[0]
        self.assertEqual(asm.methodology.as_of_utc, sim_time)
        self.assertNotEqual(asm.created_at_utc, sim_time)

        inc = res.active_incidents[0]
        self.assertEqual(inc.first_seen_utc, sim_time)
        self.assertNotEqual(inc.created_at_utc, sim_time)

    def test_pipeline_alert_deduplication(self):
        # Processing identical risk condition twice should not generate duplicate alert
        obs1 = make_obs("OBS-DED-1", "2026-10-01T12:00:00Z", frp=90.0, lat=34.1, lon=-118.1)
        res1 = self.pipeline.process_observations([obs1], as_of_utc="2026-10-01T12:00:00Z")
        self.assertEqual(len(res1.new_alerts), 1)

        # Another observation for the same incident with same risk level
        obs2 = make_obs("OBS-DED-2", "2026-10-01T13:00:00Z", frp=92.0, lat=34.102, lon=-118.101)
        res2 = self.pipeline.process_observations([obs2], as_of_utc="2026-10-01T13:00:00Z")

        # Deduplicator should have suppressed duplicate alert for same condition
        self.assertEqual(len(res2.new_alerts), 0)
        self.assertEqual(len(self.pipeline.alerts), 1)


if __name__ == "__main__":
    unittest.main()
