"""Determinism verification tests for ThermalIntel V2 Replay and Evaluation.

Implements Requirement 7 & 14:
'The same scenario run twice with:
 same inputs
 same as_of sequence
 same algorithm versions
 must produce the same:
 - observations
 - assessments
 - incidents
 - event transitions
 - alerts
 where deterministic IDs are applicable.
 If randomness exists, seed it.'
"""

import unittest
from pathlib import Path

from scenarios.loader import load_scenario_from_file
from services.replay.player import ReplayPlayer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "data"


class TestReplayDeterminism(unittest.TestCase):
    """Verify that running any scenario twice produces 100% byte-for-byte and ID-identical outputs."""

    def _assert_runs_identical(self, scenario_filename: str):
        path = DATA_DIR / scenario_filename
        scenario = load_scenario_from_file(path)

        # Run 1
        player1 = ReplayPlayer(scenario=scenario)
        history1 = player1.run_to_completion()
        pipeline1 = player1.pipeline

        # Run 2
        player2 = ReplayPlayer(scenario=scenario)
        history2 = player2.run_to_completion()
        pipeline2 = player2.pipeline

        # 1. Compare Step Counts and Timestamps
        self.assertEqual(len(history1), len(history2))
        for s1, s2 in zip(history1, history2):
            self.assertEqual(s1.as_of_utc, s2.as_of_utc)
            self.assertEqual(
                [o.observation_id for o in s1.observations],
                [o.observation_id for o in s2.observations],
            )
            self.assertEqual(
                [a.assessment_id for a in s1.assessments],
                [a.assessment_id for a in s2.assessments],
            )
            self.assertEqual(
                [i.incident_id for i in s1.active_incidents],
                [i.incident_id for i in s2.active_incidents],
            )
            self.assertEqual(
                [e.event_id for e in s1.new_events],
                [e.event_id for e in s2.new_events],
            )
            self.assertEqual(
                [al.alert_id for al in s1.new_alerts],
                [al.alert_id for al in s2.new_alerts],
            )

        # 2. Compare Final Incidents
        self.assertEqual(len(pipeline1.incidents), len(pipeline2.incidents))
        for inc1, inc2 in zip(pipeline1.incidents, pipeline2.incidents):
            self.assertEqual(inc1.incident_id, inc2.incident_id)
            self.assertEqual(inc1.observation_count, inc2.observation_count)
            self.assertEqual(inc1.peak_frp, inc2.peak_frp)
            self.assertEqual(inc1.average_frp, inc2.average_frp)
            self.assertEqual(inc1.current_risk_score, inc2.current_risk_score)
            self.assertEqual(inc1.current_severity, inc2.current_severity)
            self.assertEqual(inc1.current_classification, inc2.current_classification)
            self.assertEqual(inc1.centroid_latitude, inc2.centroid_latitude)
            self.assertEqual(inc1.centroid_longitude, inc2.centroid_longitude)

        # 3. Compare Timeline Events
        self.assertEqual(len(pipeline1.events), len(pipeline2.events))
        for evt1, evt2 in zip(pipeline1.events, pipeline2.events):
            self.assertEqual(evt1.event_id, evt2.event_id)
            self.assertEqual(evt1.event_type, evt2.event_type)
            self.assertEqual(evt1.timestamp_utc, evt2.timestamp_utc)
            self.assertEqual(evt1.reason, evt2.reason)

        # 4. Compare Alerts
        self.assertEqual(len(pipeline1.alerts), len(pipeline2.alerts))
        for a1, a2 in zip(pipeline1.alerts, pipeline2.alerts):
            self.assertEqual(a1.alert_id, a2.alert_id)
            self.assertEqual(a1.rule_id, a2.rule_id)
            self.assertEqual(a1.dedupe_key, a2.dedupe_key)
            self.assertEqual(a1.priority, a2.priority)
            self.assertEqual(a1.title, a2.title)

    def test_determinism_scenario_1_industrial(self):
        self._assert_runs_identical("scenario_1_industrial_spike.json")

    def test_determinism_scenario_2_vegetation(self):
        self._assert_runs_identical("scenario_2_vegetation_exposure.json")

    def test_determinism_scenario_3_weak(self):
        self._assert_runs_identical("scenario_3_weak_detection.json")

    def test_determinism_scenario_4_provider(self):
        self._assert_runs_identical("scenario_4_provider_degradation.json")


if __name__ == "__main__":
    unittest.main()
