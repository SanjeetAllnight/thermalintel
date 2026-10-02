"""Unit tests for ScenarioProvider and provider degradation telemetry."""

import unittest
from datetime import datetime, timezone

from scenarios.schema import (
    Scenario,
    ScenarioObservation,
    ProviderControlEvent,
    ScenarioMetadata,
)
from services.replay.clock import SimulatedClock
from services.replay.provider import ScenarioProvider, scenario_obs_to_v2_observation
from services.api.schemas.v2.common import ProviderStatus


def create_degradation_scenario() -> Scenario:
    """Helper creating scenario with controlled provider degradation and recovery."""
    return Scenario(
        id="SCN-TEST-PROVIDER",
        name="Test Provider Scenario",
        description="Scenario for testing provider status transitions",
        start_time_utc="2026-10-01T08:00:00Z",
        metadata=ScenarioMetadata(seed=42),
        provider_events=[
            ProviderControlEvent(
                timestamp_utc="2026-10-01T08:00:00Z",
                provider="NASA_FIRMS",
                status="success",
            ),
            ProviderControlEvent(
                timestamp_utc="2026-10-01T09:00:00Z",
                provider="NASA_FIRMS",
                status="failed",
                error_type="Http503",
                error_message="NASA FIRMS API server error",
            ),
            ProviderControlEvent(
                timestamp_utc="2026-10-01T10:00:00Z",
                provider="NASA_FIRMS",
                status="success",
            ),
        ],
        observations=[
            ScenarioObservation(
                observation_id="OBS-P1",
                acquisition_time_utc="2026-10-01T08:30:00Z",
                latitude=35.0,
                longitude=-119.0,
                brightness=325.0,
                frp=20.0,
                detection_confidence="nominal",
                daynight="D",
            ),
            ScenarioObservation(
                observation_id="OBS-P2",
                acquisition_time_utc="2026-10-01T09:30:00Z",
                latitude=35.01,
                longitude=-119.01,
                brightness=330.0,
                frp=25.0,
                detection_confidence="nominal",
                daynight="D",
            ),
            ScenarioObservation(
                observation_id="OBS-P3",
                acquisition_time_utc="2026-10-01T10:30:00Z",
                latitude=35.02,
                longitude=-119.02,
                brightness=345.0,
                frp=50.0,
                detection_confidence="high",
                daynight="D",
            ),
        ],
    )


class TestScenarioProvider(unittest.TestCase):
    """Test ScenarioProvider observation yielding, status evaluation, and telemetry."""

    def setUp(self):
        self.scenario = create_degradation_scenario()
        self.clock = SimulatedClock("2026-10-01T08:00:00Z")
        self.provider = ScenarioProvider(scenario=self.scenario, clock=self.clock)

    def test_initial_status_is_success(self):
        status = self.provider.evaluate_provider_status()
        self.assertEqual(status, ProviderStatus.SUCCESS)
        self.assertFalse(self.provider.is_degraded)

    def test_fetch_observations_when_healthy(self):
        self.clock.set_time("2026-10-01T08:45:00Z")
        obs = self.provider.fetch_observations(consume=True)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0].observation_id, "OBS-P1")

        # Calling again with consume=True returns empty (already consumed)
        obs2 = self.provider.fetch_observations(consume=True)
        self.assertEqual(len(obs2), 0)

    def test_provider_degradation_state_change(self):
        # Advance into outage window (09:00:00 to 10:00:00)
        self.clock.set_time("2026-10-01T09:30:00Z")
        status = self.provider.evaluate_provider_status()
        self.assertEqual(status, ProviderStatus.FAILED)
        self.assertTrue(self.provider.is_degraded)

        # Observations during outage return empty
        obs = self.provider.fetch_observations(consume=True)
        self.assertEqual(len(obs), 0)

    def test_provider_recovery(self):
        # Advance past recovery (10:00:00)
        self.clock.set_time("2026-10-01T10:45:00Z")
        status = self.provider.evaluate_provider_status()
        self.assertEqual(status, ProviderStatus.SUCCESS)
        self.assertFalse(self.provider.is_degraded)

        # Pending observation OBS-P3 should now be fetched
        obs = self.provider.fetch_observations(consume=True)
        obs_ids = [o.observation_id for o in obs]
        self.assertIn("OBS-P3", obs_ids)

    def test_provider_runs_recording_without_secrets(self):
        self.clock.set_time("2026-10-01T08:30:00Z")
        self.provider.fetch_observations()
        runs = self.provider.get_provider_runs()
        self.assertEqual(len(runs), 1)
        run = runs[0]

        self.assertEqual(run.provider, "NASA_FIRMS")
        self.assertIn("scenario_id", run.request_metadata)

        # Verify strict security rule: no secret substrings in request_metadata keys
        for key in run.request_metadata:
            for forbidden in ("key", "secret", "token", "auth", "password"):
                self.assertNotIn(forbidden, key.lower())

    def test_hotspot_projection(self):
        self.clock.set_time("2026-10-01T08:30:00Z")
        hotspots = self.provider.fetch_hotspots(consume=True)
        self.assertEqual(len(hotspots), 1)
        h = hotspots[0]
        self.assertEqual(h.id, "P1")
        self.assertEqual(h.latitude, 35.0)
        self.assertEqual(h.frp, 20.0)


if __name__ == "__main__":
    unittest.main()
