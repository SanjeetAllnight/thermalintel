"""Unit tests for historical backtest engine and source interface."""

import unittest
from evaluation.backtest import (
    BacktestEngine,
    FixtureBacktestSource,
    KnownEvent,
    BacktestResult,
)
from services.api.schemas.v2.observation import Observation


def make_obs(obs_id: str, acq_time: str, lat: float, lon: float, frp: float) -> Observation:
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
        brightness=330.0,
        frp=frp,
        daynight="D",
        detection_confidence="high",
        source_attributes={"nearest_place": "Historical Valley"},
    )


class TestBacktestEngine(unittest.TestCase):
    """Test historical backtest engine replay and ground truth matching."""

    def test_backtest_matches_known_event(self):
        observations = [
            make_obs("OBS-H1", "2023-08-15T12:00:00Z", 38.50, -120.50, 45.0),
            make_obs("OBS-H2", "2023-08-15T14:30:00Z", 38.51, -120.49, 95.0),
        ]
        known_events = [
            KnownEvent(
                event_id="HIST-CAL-2023-01",
                name="El Dorado Fire",
                event_type="wildfire",
                start_time_utc="2023-08-15T10:00:00Z",
                end_time_utc="2023-08-16T18:00:00Z",
                latitude=38.50,
                longitude=-120.50,
                radius_km=10.0,
            )
        ]

        source = FixtureBacktestSource(
            dataset_name="2023_sierra_benchmark",
            observations=observations,
            known_events=known_events,
        )

        engine = BacktestEngine()
        result = engine.run_backtest(source)

        self.assertEqual(result.dataset_name, "2023_sierra_benchmark")
        self.assertEqual(result.total_observations_replayed, 2)
        self.assertEqual(result.total_known_events, 1)
        self.assertEqual(result.detected_known_events, 1)
        self.assertEqual(result.detection_rate, 1.0)
        self.assertEqual(len(result.matched_pairs), 1)
        self.assertEqual(result.matched_pairs[0]["known_event_id"], "HIST-CAL-2023-01")


if __name__ == "__main__":
    unittest.main()
