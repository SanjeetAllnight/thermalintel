"""Unit tests for risk model weight sensitivity analysis."""

import unittest
from evaluation.sensitivity import (
    WeightSensitivityEvaluator,
    _compute_spearman_rank_correlation,
    _get_ranks,
)
from services.api.schemas.hotspot import Hotspot
from services.intelligence.context import HotspotContext
from services.api.schemas.common import RiskLevel, SourceType


def make_hotspot(hid: str, frp: float, bright: float = 330.0) -> Hotspot:
    return Hotspot(
        id=hid,
        latitude=34.0,
        longitude=-118.0,
        brightness=bright,
        scan=0.375,
        track=0.375,
        acq_date="2026-10-01",
        acq_time="1200",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="nominal",
        version="2.0",
        frp=frp,
        daynight="D",
        source_type=SourceType.UNKNOWN,
        risk_score=50.0,
        risk_level=RiskLevel.MEDIUM,
        is_anomaly=False,
        last_updated="2026-10-01T12:00:00Z",
    )


class TestWeightSensitivity(unittest.TestCase):
    """Test weight sensitivity evaluation, Spearman correlation, and rank consistency."""

    def test_spearman_rank_correlation(self):
        # Perfect correlation
        ranks_a = [1, 2, 3, 4, 5]
        ranks_b = [1, 2, 3, 4, 5]
        self.assertEqual(_compute_spearman_rank_correlation(ranks_a, ranks_b), 1.0)

        # Inverted correlation
        ranks_c = [5, 4, 3, 2, 1]
        self.assertEqual(_compute_spearman_rank_correlation(ranks_a, ranks_c), -1.0)

    def test_get_ranks(self):
        values = [10.0, 50.0, 25.0]
        # In descending order: 50.0 is rank 1, 25.0 is rank 2, 10.0 is rank 3
        ranks = _get_ranks(values, reverse=True)
        self.assertEqual(ranks, [3, 1, 2])

    def test_sensitivity_evaluator_runs_deterministically(self):
        hotspots = [
            make_hotspot("H1", frp=15.0),
            make_hotspot("H2", frp=80.0),
            make_hotspot("H3", frp=150.0),
        ]
        contexts = [
            HotspotContext(distance_to_settlement_m=5000.0, fire_weather_index=20.0),
            HotspotContext(distance_to_settlement_m=1200.0, fire_weather_index=55.0),
            HotspotContext(distance_to_settlement_m=400.0, fire_weather_index=80.0),
        ]

        evaluator = WeightSensitivityEvaluator(default_delta_pct=0.15)
        report1 = evaluator.evaluate(hotspots, contexts)
        report2 = evaluator.evaluate(hotspots, contexts)

        self.assertEqual(report1.sample_size, 3)
        self.assertEqual(report1.rank_stability_rating, "HIGH")
        self.assertGreaterEqual(report1.mean_rank_correlation, 0.90)

        # Determinism check
        self.assertEqual(report1.mean_rank_correlation, report2.mean_rank_correlation)
        self.assertEqual(len(report1.configurations), len(report2.configurations))
        for c1, c2 in zip(report1.configurations, report2.configurations):
            self.assertEqual(c1.configuration_name, c2.configuration_name)
            self.assertEqual(c1.spearman_rank_correlation, c2.spearman_rank_correlation)


if __name__ == "__main__":
    unittest.main()
