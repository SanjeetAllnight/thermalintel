"""Anomaly Detection Subsystem.

Redesigned for truthful, reproducible, evidence-based operational intelligence.

Hierarchy:
1. PRIMARY ANOMALY DEFINITION: Historical and Site Baseline (BaselineEvaluator).
   Answers: "How unusual is this activity for this location?"
2. SECONDARY UNSUPERVISED SIGNAL: Scikit-learn IsolationForest for multi-variate
   population analysis when an explicit population of >= 5 observations is provided.

Guarantees:
- Deterministic behavior with fixed random_state (42).
- Zero-variance division-by-zero protection.
- Documented contamination semantics (0.10: assumed 10% outlier rate in satellite overpasses).
- Clean degradation on small populations or missing telemetry.
- Method and version provenance identification.
"""

import math
from typing import List, Optional
import numpy as np
from sklearn.ensemble import IsolationForest

from services.api.schemas.intelligence import AnomalyResult
from services.api.schemas.v2.assessment import AnomalyAssessment
from services.intelligence.config import (
    DEFAULT_BASELINE_FRP_MEAN,
    DEFAULT_BASELINE_FRP_STD,
    ANOMALY_SIGMA_THRESHOLD,
    ISOLATION_FOREST_ESTIMATORS,
    ISOLATION_FOREST_CONTAMINATION,
    RANDOM_STATE_PINNED,
    METHODOLOGY_BASELINE_STATISTICAL,
    METHODOLOGY_ISOLATION_FOREST,
    ALGORITHM_VERSION,
)
from services.intelligence.baseline import BaselineEvaluator, BaselineEvaluation, BaselineStatus
from services.intelligence.features import FeatureVector
from services.intelligence.thresholds import ISOLATION_FOREST_MIN_POPULATION


class AnomalyDetector:
    """Evaluates thermal observations using statistical site baselines and secondary IsolationForest."""

    def __init__(
        self,
        baseline_frp_mean: float = DEFAULT_BASELINE_FRP_MEAN,
        baseline_frp_std: float = DEFAULT_BASELINE_FRP_STD,
        sigma_threshold: float = ANOMALY_SIGMA_THRESHOLD,
        random_state: int = RANDOM_STATE_PINNED,
    ):
        self.baseline_frp_mean = baseline_frp_mean
        self.baseline_frp_std = max(1.0, baseline_frp_std)
        self.sigma_threshold = sigma_threshold
        self.random_state = random_state
        self.baseline_evaluator = BaselineEvaluator(
            baseline_frp_mean=baseline_frp_mean,
            baseline_frp_std=baseline_frp_std,
            sigma_threshold=sigma_threshold,
        )

    def detect(
        self,
        features: FeatureVector,
        population_features: Optional[List[FeatureVector]] = None,
    ) -> AnomalyResult:
        """Evaluate whether a thermal observation is an anomaly.

        If a valid, diverse population of >= 5 items is provided, uses IsolationForest.
        Otherwise, falls back to the deterministic statistical site baseline.
        """
        # Batch / population ML path (secondary signal)
        if population_features and len(population_features) >= ISOLATION_FOREST_MIN_POPULATION:
            return self._detect_population_isolation_forest(features, population_features)

        # Primary signal: Historical and site statistical baseline
        return self._detect_statistical_baseline(features)

    def detect_v2(
        self,
        features: FeatureVector,
        population_features: Optional[List[FeatureVector]] = None,
    ) -> AnomalyAssessment:
        """Evaluate and return canonical V2 AnomalyAssessment contract."""
        res = self.detect(features, population_features=population_features)
        return AnomalyAssessment(
            is_anomaly=res.is_anomaly,
            anomaly_score=res.anomaly_score,
            baseline_deviation_sigma=res.baseline_deviation,
            anomaly_rationale=res.anomaly_rationale,
        )

    def _detect_statistical_baseline(self, f: FeatureVector) -> AnomalyResult:
        """Primary baseline evaluation: compares against localized and regional empirical priors."""
        eval_res: BaselineEvaluation = self.baseline_evaluator.evaluate_site_baseline(f)

        return AnomalyResult(
            is_anomaly=eval_res.is_anomaly,
            anomaly_score=round(float(eval_res.anomaly_score), 3),
            baseline_deviation=round(float(eval_res.deviation_sigma), 2),
            anomaly_rationale=eval_res.rationale,
        )

    def _detect_population_isolation_forest(
        self,
        target: FeatureVector,
        population: List[FeatureVector],
    ) -> AnomalyResult:
        """Multi-variate anomaly detection using IsolationForest on an explicit population.
        
        Contamination semantics:
        - `contamination=0.10` specifies that approximately 10% of pixels in a regional overpass
          are expected to represent true anomalous combustion departures.
        - Fixed random_state guarantees bitwise determinism across executions.
        - Checks for degenerate zero-variance in the population before fitting.
        """
        # Handle missing target FRP
        if target.frp is None or math.isnan(target.frp):
            return self._detect_statistical_baseline(target)

        # Extract features for population: [FRP, Brightness, Persistence]
        frp_vals = [fv.frp for fv in population if fv.frp is not None and not math.isnan(fv.frp)]
        if not frp_vals:
            return self._detect_statistical_baseline(target)

        # Check for zero-variance population (all FRP identical)
        frp_std = float(np.std(frp_vals))
        if frp_std < 1e-6:
            # Clean degradation to baseline handling for zero-variance data
            pop_mean = float(np.mean(frp_vals))
            eval_res = self.baseline_evaluator.evaluate_site_baseline(
                target,
                custom_baseline_mean=pop_mean,
                custom_baseline_std=0.0,
            )
            return AnomalyResult(
                is_anomaly=eval_res.is_anomaly,
                anomaly_score=round(float(eval_res.anomaly_score), 3),
                baseline_deviation=round(float(eval_res.deviation_sigma), 2),
                anomaly_rationale=eval_res.rationale,
            )

        X = np.array([
            [
                max(0.0, float(fv.frp)),
                max(0.0, float(fv.brightness)),
                float(fv.persistence_score),
            ]
            for fv in population
        ], dtype=np.float64)

        target_vec = np.array([[
            max(0.0, float(target.frp)),
            max(0.0, float(target.brightness)),
            float(target.persistence_score),
        ]], dtype=np.float64)

        try:
            iso = IsolationForest(
                n_estimators=ISOLATION_FOREST_ESTIMATORS,
                contamination=ISOLATION_FOREST_CONTAMINATION,
                random_state=self.random_state,
            )
            iso.fit(X)

            raw_score = float(iso.decision_function(target_vec)[0])
            pred_label = int(iso.predict(target_vec)[0])  # -1 for outlier, 1 for inlier

            # Map raw score (-0.4 to +0.4) smoothly to [0.0, 1.0] where 1.0 = highly anomalous
            anomaly_score = 1.0 / (1.0 + math.exp(raw_score * 6.0))

            pop_mean = float(np.mean(frp_vals))
            pop_std_safe = max(1.0, frp_std)
            deviation = (target.frp - pop_mean) / pop_std_safe

            # Anomaly criterion combines tree outlier status, anomaly score, and sigma threshold
            is_anomaly = (pred_label == -1) or (anomaly_score >= 0.65) or (deviation >= self.sigma_threshold)

            # Recurrent site suppression check
            prior_passes = target.prior_detections_30d or 0
            if (prior_passes >= 15 or target.is_recurrent_site) and deviation < 3.0:
                is_anomaly = False
                anomaly_score = min(0.30, anomaly_score * 0.4)
                rationale = (
                    f"IsolationForest contextualized with recurring baseline ({prior_passes} passes in 30d). "
                    f"Operational emitter within regional population bounds."
                )
            elif is_anomaly:
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
            return self._detect_statistical_baseline(target)
