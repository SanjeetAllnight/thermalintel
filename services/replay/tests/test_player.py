"""Unit tests for ReplayPlayer engine controls and deterministic sequence execution."""

import unittest
from datetime import datetime, timezone, timedelta

from scenarios.schema import Scenario, ScenarioObservation, ScenarioMetadata
from services.replay.clock import SimulatedClock
from services.replay.player import ReplayPlayer, PlayerState


def create_test_scenario() -> Scenario:
    """Helper creating a 3-step deterministic test scenario."""
    return Scenario(
        id="SCN-TEST-PLAYER",
        name="Test Player Scenario",
        description="Scenario for verifying player controls",
        start_time_utc="2026-10-01T12:00:00Z",
        metadata=ScenarioMetadata(seed=42),
        observations=[
            ScenarioObservation(
                observation_id="OBS-T1",
                acquisition_time_utc="2026-10-01T12:30:00Z",
                latitude=34.0,
                longitude=-118.0,
                brightness=320.0,
                frp=15.0,
                detection_confidence="nominal",
                daynight="D",
            ),
            ScenarioObservation(
                observation_id="OBS-T2",
                acquisition_time_utc="2026-10-01T14:00:00Z",
                latitude=34.01,
                longitude=-118.01,
                brightness=340.0,
                frp=45.0,
                detection_confidence="nominal",
                daynight="D",
            ),
            ScenarioObservation(
                observation_id="OBS-T3",
                acquisition_time_utc="2026-10-01T16:00:00Z",
                latitude=34.02,
                longitude=-118.02,
                brightness=380.0,
                frp=120.0,
                detection_confidence="high",
                daynight="D",
            ),
        ],
    )


class TestReplayPlayer(unittest.TestCase):
    """Test ReplayPlayer controls: play, pause, step, reset, speed, jump."""

    def setUp(self):
        self.scenario = create_test_scenario()
        self.player = ReplayPlayer(scenario=self.scenario)

    def test_initial_state(self):
        self.assertEqual(self.player.state, PlayerState.READY)
        self.assertEqual(self.player.current_simulated_timestamp, "2026-10-01T12:00:00+00:00")
        self.assertEqual(len(self.player.history), 0)

    def test_play_and_pause(self):
        self.player.play()
        self.assertTrue(self.player.is_playing)
        self.assertFalse(self.player.is_paused)

        self.player.pause()
        self.assertFalse(self.player.is_playing)
        self.assertTrue(self.player.is_paused)

    def test_step_advances_clock_and_processes_events(self):
        self.player.play()

        # Step 1: should advance to 12:30:00 and process OBS-T1
        res1 = self.player.step()
        self.assertIsNotNone(res1)
        self.assertIn("12:30:00", self.player.current_simulated_timestamp)
        self.assertEqual(len(res1.observations), 1)
        self.assertEqual(res1.observations[0].observation_id, "OBS-T1")
        self.assertEqual(len(self.player.history), 1)

        # Step 2: should advance to 14:00:00 and process OBS-T2
        res2 = self.player.step()
        self.assertIsNotNone(res2)
        self.assertIn("14:00:00", self.player.current_simulated_timestamp)
        self.assertEqual(len(res2.observations), 1)
        self.assertEqual(res2.observations[0].observation_id, "OBS-T2")
        self.assertEqual(len(self.player.history), 2)

    def test_reset_restores_initial_state(self):
        self.player.play()
        self.player.step()
        self.player.step()
        self.assertGreater(len(self.player.history), 0)

        self.player.reset()
        self.assertEqual(self.player.state, PlayerState.READY)
        self.assertEqual(self.player.current_simulated_timestamp, "2026-10-01T12:00:00+00:00")
        self.assertEqual(len(self.player.history), 0)
        self.assertEqual(len(self.player.pipeline.incidents), 0)

    def test_speed_adjustment(self):
        self.assertEqual(self.player.speed, 1.0)
        self.player.set_speed(2.5)
        self.assertEqual(self.player.speed, 2.5)

        with self.assertRaises(ValueError):
            self.player.set_speed(0.0)
        with self.assertRaises(ValueError):
            self.player.set_speed(-1.0)

    def test_jump_to_future_timestamp(self):
        # Jump directly to 15:00:00 (which is after OBS-T1 and OBS-T2)
        res = self.player.jump_to("2026-10-01T15:00:00Z")
        self.assertIn("15:00:00", self.player.current_simulated_timestamp)

        # Should have stepped through OBS-T1 and OBS-T2
        all_obs_ids = [obs.observation_id for step in self.player.history for obs in step.observations]
        self.assertIn("OBS-T1", all_obs_ids)
        self.assertIn("OBS-T2", all_obs_ids)
        self.assertNotIn("OBS-T3", all_obs_ids)

    def test_jump_to_past_timestamp_rewinds_and_replays(self):
        # First advance to end
        self.player.jump_to("2026-10-01T16:00:00Z")
        self.assertEqual(len(self.player.history), 3)

        # Now jump back to 13:00:00 (only OBS-T1 should be ingested)
        self.player.jump_to("2026-10-01T13:00:00Z")
        self.assertIn("13:00:00", self.player.current_simulated_timestamp)
        all_obs_ids = [obs.observation_id for step in self.player.history for obs in step.observations]
        self.assertEqual(all_obs_ids, ["OBS-T1"])

    def test_run_to_completion(self):
        history = self.player.run_to_completion()
        self.assertTrue(self.player.is_finished)
        self.assertEqual(len(history), 3)
        self.assertIn("16:00:00", self.player.current_simulated_timestamp)

    def test_deterministic_sequence(self):
        """Verify identical sequential stepping produces identical history and IDs."""
        player1 = ReplayPlayer(scenario=self.scenario)
        history1 = player1.run_to_completion()

        player2 = ReplayPlayer(scenario=self.scenario)
        history2 = player2.run_to_completion()

        self.assertEqual(len(history1), len(history2))
        for h1, h2 in zip(history1, history2):
            self.assertEqual(h1.as_of_utc, h2.as_of_utc)
            self.assertEqual([o.observation_id for o in h1.observations], [o.observation_id for o in h2.observations])
            self.assertEqual([a.assessment_id for a in h1.assessments], [a.assessment_id for a in h2.assessments])
            self.assertEqual([i.incident_id for i in h1.active_incidents], [i.incident_id for i in h2.active_incidents])
            self.assertEqual([al.alert_id for al in h1.new_alerts], [al.alert_id for al in h2.new_alerts])


if __name__ == "__main__":
    unittest.main()
