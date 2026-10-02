"""Unit tests for scenario loading, schema validation, metadata, and ordering."""

import unittest
from pathlib import Path
from pydantic import ValidationError

from scenarios.schema import (
    Scenario,
    ScenarioObservation,
    ScenarioMode,
    ScenarioMetadata,
    ProviderControlEvent,
)
from scenarios.loader import (
    load_scenario_from_dict,
    load_scenario_from_file,
    list_available_scenarios,
)
from evaluation.labels import LabelType


class TestScenarioSchemaAndLoader(unittest.TestCase):
    """Test scenario schema constraints, loader validation, and ordering."""

    def test_scenario_valid_schema(self):
        data = {
            "id": "SCN-TEST-001",
            "name": "Validation Test Scenario",
            "description": "Testing scenario schema validation",
            "mode": "synthetic",
            "start_time_utc": "2026-10-01T10:00:00Z",
            "metadata": {
                "version": "1.0.0",
                "author": "Tester",
                "tags": ["unit_test"],
                "seed": 99,
            },
            "observations": [
                {
                    "observation_id": "OBS-001",
                    "acquisition_time_utc": "2026-10-01T10:15:00Z",
                    "latitude": 37.5,
                    "longitude": -122.2,
                    "brightness": 330.0,
                    "frp": 25.0,
                    "detection_confidence": "nominal",
                    "daynight": "D",
                    "label_type": "SYNTHETIC_EXPECTATION",
                }
            ],
            "provider_events": [
                {
                    "timestamp_utc": "2026-10-01T10:00:00Z",
                    "provider": "NASA_FIRMS",
                    "status": "success",
                }
            ],
        }
        scn = load_scenario_from_dict(data)
        self.assertEqual(scn.id, "SCN-TEST-001")
        self.assertEqual(scn.mode, ScenarioMode.SYNTHETIC)
        self.assertEqual(len(scn.observations), 1)
        self.assertEqual(len(scn.provider_events), 1)

    def test_invalid_coordinates_rejected(self):
        data = {
            "id": "SCN-INVALID-COORDS",
            "name": "Invalid Coords",
            "description": "Out of range latitude",
            "start_time_utc": "2026-10-01T10:00:00Z",
            "observations": [
                {
                    "observation_id": "OBS-BAD",
                    "acquisition_time_utc": "2026-10-01T10:15:00Z",
                    "latitude": 95.0,  # Invalid: > 90
                    "longitude": -122.2,
                    "brightness": 330.0,
                    "frp": 25.0,
                    "daynight": "D",
                }
            ],
        }
        with self.assertRaises(ValidationError):
            load_scenario_from_dict(data)

    def test_invalid_timestamp_rejected(self):
        data = {
            "id": "SCN-INVALID-TIME",
            "name": "Invalid Time",
            "description": "Malformed timestamp",
            "start_time_utc": "not-a-timestamp",
            "observations": [],
        }
        with self.assertRaises(ValueError):
            load_scenario_from_dict(data)

    def test_chronological_ordering_helpers(self):
        scn = Scenario(
            id="SCN-ORDER-TEST",
            name="Ordering Test",
            description="Testing chronological sorting helpers",
            start_time_utc="2026-10-01T08:00:00Z",
            observations=[
                ScenarioObservation(
                    observation_id="OBS-LATER",
                    acquisition_time_utc="2026-10-01T11:00:00Z",
                    latitude=30.0,
                    longitude=-90.0,
                    brightness=320.0,
                    frp=10.0,
                    daynight="D",
                ),
                ScenarioObservation(
                    observation_id="OBS-EARLIER",
                    acquisition_time_utc="2026-10-01T09:00:00Z",
                    latitude=30.0,
                    longitude=-90.0,
                    brightness=320.0,
                    frp=10.0,
                    daynight="D",
                ),
            ],
        )

        sorted_obs = scn.sorted_observations()
        self.assertEqual(sorted_obs[0].observation_id, "OBS-EARLIER")
        self.assertEqual(sorted_obs[1].observation_id, "OBS-LATER")

        # observations_up_to cutoff
        obs_at_10 = scn.observations_up_to("2026-10-01T10:00:00Z")
        self.assertEqual(len(obs_at_10), 1)
        self.assertEqual(obs_at_10[0].observation_id, "OBS-EARLIER")

    def test_list_available_scenarios_loads_all_packs(self):
        scenarios = list_available_scenarios()
        self.assertGreaterEqual(len(scenarios), 4)

        scenario_ids = [s.id for s in scenarios]
        self.assertIn("SCN-001-INDUSTRIAL-SPIKE", scenario_ids)
        self.assertIn("SCN-002-VEGETATION-EXPOSURE", scenario_ids)
        self.assertIn("SCN-003-WEAK-DETECTION", scenario_ids)
        self.assertIn("SCN-004-PROVIDER-DEGRADATION", scenario_ids)


if __name__ == "__main__":
    unittest.main()
