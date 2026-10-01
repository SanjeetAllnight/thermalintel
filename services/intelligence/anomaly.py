"""Anomaly Detection Subsystem.

Provides:
1. Sklearn IsolationForest for population-level multi-variate anomaly detection.
2. Deterministic statistical baseline fallback for single hotspots or small datasets (< 5 items).
3. Radiometric surge identification while suppressing routine industrial operational flares.
"""

import math
from typing import List, Optional, Tuple
import numpy as np
from sklearn.ensemble import IsolationForest

from services.api.schemas.intelligence import AnomalyResult
from services.intelligence.config import (
    DEFAULT_BASELINE_FRP_MEAN,
    DEFAULT_BASELINE_FRP_STD,
    ANOMALY_SIGMA_THRESHOLD,
    ANOMALY_HISTORICAL_SUPPRESSION_COUNT,
    ISOLATION_FOREST_ESTIMATORS,
    ISOLATION_FOREST_CONTAMINATION,
    RANDOM_STATE,
)
from services.intelligence.features import FeatureVector


class AnomalyDetector:
    """Statistical and machine learning anomaly detector for thermal observations."""

    def __init__(
        self,
        baseline_frp_mean: float = DEFAULT_BASELINE_FRP_MEAN,
        baseline_frp_std: float = DEFAULT_BASELINE_FRP_STD,
        sigma_threshold: float = ANOMALY_SIGMA_THRESHOLD,
        random_state: int = RANDOM_STATE,
    ):
        self.baseline_frp_mean = baseline_frp_mean
        self.baseline_frp_std = max(1.0, baseline_frp_std)
        self.sigma_threshold = sigma_threshold
        self.random_state = random_state

    def detect(
        self,
        features: FeatureVector,
        population_features: Optional[List[FeatureVector]] = None,
    ) -> AnomalyResult:
        """Evaluate whether a thermal observation is an anomaly.

        If a sufficient population is provided (>= 5 items), fits IsolationForest.
        Otherwise, falls back to deterministic statistical z-score baseline.
        """
        # Batch / population ML path
        if population_features and len(population_features) >= 5:
            return self._detect_population_isolation_forest(features, population_features)

        # Fallback single / small-data statistical baseline path
        return self._detect_statistical_fallback(features)

    def _detect_statistical_fallback(self, f: FeatureVector) -> AnomalyResult:
        """Deterministic statistical z-score evaluation against regional and historical baselines."""
        frp = f.frp
        deviation = (frp - self.baseline_frp_mean) / self.baseline_frp_std

        # Check for historical recurrence suppression
        # Known industrial / recurrent sites with multiple passes match operational expectations
        prior_passes = f.prior_detections_30d or 0
        if prior_passes >= ANOMALY_HISTORICAL_SUPPRESSION_COUNT or f.is_recurrent_site:
            if deviation < 3.0:
                is_anomaly = False
                anomaly_score = max(0.05, min(0.25, 0.10 + (deviation * 0.04)))
                rationale = (
                    f"Recurring site ({prior_passes} passes in 30d). "
                    f"Radiant heat of {frp:.1f} MW aligns with continuous operational baseline."
                )
            else:
                # Sudden massive spike even at an industrial site is an anomaly
                is_anomaly = True
                anomaly_score = min(0.95, max(0.65, 0.50 + (deviation * 0.08)))
                rationale = (
                    f"Unprecedented radiance spike at recurring site ({prior_passes} passes). "
                    f"Output exceeds operational baseline by {deviation:.1f} standard deviations."
                )
        elif deviation >= self.sigma_threshold:
            is_anomaly = True
            # Normalized score from 0.65 to 0.99 for significant deviations
            anomaly_score = min(0.99, max(0.65, 0.50 + (deviation * 0.10)))
            rationale = (
                f"Thermal radiance ({frp:.1f} MW) is {deviation:.1f} standard deviations "
                f"above regional baseline ({self.baseline_frp_mean:.1f} MW)."
            )
        else:
            is_anomaly = False
            # Normalized score from 0.0 to 0.55 for normal variation
            normalized_score = max(0.0, (deviation + 1.0) / 5.0)
            anomaly_score = min(0.55, normalized_score)
            rationale = (
                f"Radiant energy output ({frp:.1f} MW) within normal expected variation bounds "
                f"({deviation:.1f} sigma deviation)."
            )

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=round(float(anomaly_score), 3),
            baseline_deviation=round(float(deviation), 2),
            anomaly_rationale=rationale,
        )

    def _detect_population_isolation_forest(
        self,
        target: FeatureVector,
        population: List[FeatureVector],
    ) -> AnomalyResult:
        """Multi-variate anomaly detection using IsolationForest on an observed population."""
        # Build numerical feature matrix: [FRP, Brightness, Persistence]
        X = np.array([
            [fv.frp, fv.brightness, fv.persistence_score]
            for fv in population
        ], dtype=np.float64)

        target_vec = np.array([[target.frp, target.brightness, target.persistence_score]], dtype=np.float64)

        try:
            iso = IsolationForest(
                n_estimators=ISOLATION_FOREST_ESTIMATORS,
                contamination=ISOLATION_FOREST_CONTAMINATION,
                random_state=self.random_state,
            )
            iso.fit(X)

            # Decision function: lower values mean more anomalous (typically in [-0.5, 0.5])
            raw_score = float(iso.decision_function(target_vec)[0])
            pred_label = int(iso.predict(target_vec)[0])  # -1 for anomaly, 1 for normal

            # Map raw score (-0.4 to +0.4) smoothly to [0.0, 1.0] where 1.0 = highly anomalous
            # Using sigmoid: 1 / (1 + exp(score * 6.0))
            anomaly_score = 1.0 / (1.0 + math.exp(raw_score * 6.0))

            # Calculate target FRP z-score against this population
            pop_frps = [fv.frp for fv in population]
            pop_mean = float(np.mean(pop_frps))
            pop_std = max(1.0, float(np.std(pop_frps)))
            deviation = (target.frp - pop_mean) / pop_std

            is_anomaly = pred_label == -1 or anomaly_score >= 0.65 or deviation >= self.sigma_threshold

            if is_anomaly:
                rationale = (
                    f"IsolationForest identified observation as multivariate outlier "
                    f"(score: {anomaly_score:.2f}, {deviation:.1f} sigma above population mean)."
                )
            else:
                rationale = (
                    f"Observation clusters consistently with the population distribution "
                    f"(score: {anomaly_score:.2f}, within expected bounds)."
                )

            return AnomalyResult(
                is_anomaly=is_anomaly,
                anomaly_score=round(float(max(0.0, min(1.0, anomaly_score))), 3),
                baseline_deviation=round(float(deviation), 2),
                anomaly_rationale=rationale,
            )
        except Exception:
            # Resilient fallback if scikit-learn fitting fails on degenerate data
            return self._detect_statistical_fallback(target)
