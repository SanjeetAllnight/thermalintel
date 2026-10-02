"""Historical and Site Baseline Evaluation Layer.

Answers the fundamental operational question:
"How unusual is this activity for this location?"

Clearly distinguishes:
- NO_BASELINE: Insufficient historical satellite overpass history to determine site norms.
- NORMAL: Activity conforms to established spatial/temporal operational patterns.
- ABNORMAL: Activity represents a statistically significant deviation or unexpected surge.

Guarantees:
- Deterministic behavior for single samples, identical populations, and zero-variance data.
- Strict division-by-zero protection.
- Principled degradation when site context is incomplete.
"""

import math
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Final

from services.intelligence.config import (
    DEFAULT_BASELINE_FRP_MEAN,
    DEFAULT_BASELINE_FRP_STD,
    ANOMALY_SIGMA_THRESHOLD,
    ANOMALY_HISTORICAL_SUPPRESSION_COUNT,
    METHODOLOGY_BASELINE_STATISTICAL,
)
from services.intelligence.features import FeatureVector
from services.intelligence.thresholds import (
    MIN_BASELINE_STD_EPSILON,
    ANOMALY_SIGMA_FLARE_SURGE,
    RECURRENT_MIN_PASSES_30D,
)


class BaselineStatus(str, Enum):
    """Operational status of site baseline comparison."""
    NO_BASELINE = "NO_BASELINE"
    NORMAL = "NORMAL"
    ABNORMAL = "ABNORMAL"


@dataclass
class BaselineEvaluation:
    """Structured result of evaluating an observation against local/regional baselines."""
    status: BaselineStatus
    baseline_mean_frp: float
    baseline_std_frp: float
    deviation_sigma: float
    is_anomaly: bool
    anomaly_score: float  # 0.0 to 1.0
    detection_frequency_per_day: Optional[float]
    frp_percentile: Optional[float]
    persistence_score: float
    has_sufficient_history: bool
    rationale: str
    methodology: str = METHODOLOGY_BASELINE_STATISTICAL


class BaselineEvaluator:
    """Evaluates thermal observations against empirical historical patterns and regional priors."""

    def __init__(
        self,
        baseline_frp_mean: float = DEFAULT_BASELINE_FRP_MEAN,
        baseline_frp_std: float = DEFAULT_BASELINE_FRP_STD,
        sigma_threshold: float = ANOMALY_SIGMA_THRESHOLD,
    ):
        self.baseline_frp_mean = float(baseline_frp_mean)
        self.baseline_frp_std = max(MIN_BASELINE_STD_EPSILON, float(baseline_frp_std))
        self.sigma_threshold = float(sigma_threshold)

    def evaluate_site_baseline(
        self,
        features: FeatureVector,
        custom_baseline_mean: Optional[float] = None,
        custom_baseline_std: Optional[float] = None,
    ) -> BaselineEvaluation:
        """Evaluate observation against historical baseline with zero-variance protection."""
        # 1. Check for missing or invalid FRP
        if features.frp is None or math.isnan(features.frp):
            return BaselineEvaluation(
                status=BaselineStatus.NO_BASELINE,
                baseline_mean_frp=self.baseline_frp_mean,
                baseline_std_frp=self.baseline_frp_std,
                deviation_sigma=0.0,
                is_anomaly=False,
                anomaly_score=0.0,
                detection_frequency_per_day=None,
                frp_percentile=None,
                persistence_score=0.0,
                has_sufficient_history=False,
                rationale="FRP measurement unavailable or unparseable; baseline deviation cannot be computed.",
            )

        frp = max(0.0, float(features.frp))
        mean = custom_baseline_mean if custom_baseline_mean is not None else self.baseline_frp_mean
        std = custom_baseline_std if custom_baseline_std is not None else self.baseline_frp_std

        # 2. Zero-variance protection: std <= 0 or identical samples
        if std <= 0.0 or abs(std) < 1e-9:
            return self._handle_zero_variance(frp, mean, features)

        # Calculate deviation in standard deviations
        deviation = (frp - mean) / std

        # 3. Assess History Completeness
        hist_30d = features.prior_detections_30d
        hist_90d = features.prior_detections_90d
        is_recurrent = features.is_recurrent_site
        has_sufficient_history = bool(
            (hist_30d is not None and hist_30d >= RECURRENT_MIN_PASSES_30D)
            or (hist_90d is not None and hist_90d >= 25)
            or is_recurrent
        )

        det_freq_per_day = (hist_30d / 30.0) if hist_30d is not None else None
        persistence = features.persistence_score

        # Approximate empirical FRP percentile using normal CDF approximation
        frp_percentile = self._approximate_percentile(deviation)

        # Case A: Known Recurrent Emitter (e.g. industrial flare stack, routine managed site)
        prior_passes = hist_30d or 0
        if prior_passes >= ANOMALY_HISTORICAL_SUPPRESSION_COUNT or is_recurrent:
            if deviation < ANOMALY_SIGMA_FLARE_SURGE:
                # Normal operational activity matching established baseline
                is_anomaly = False
                status = BaselineStatus.NORMAL
                anomaly_score = max(0.05, min(0.25, 0.10 + (deviation * 0.04)))
                rationale = (
                    f"Recurring site ({prior_passes} passes in 30d). "
                    f"Radiant heat of {frp:.1f} MW aligns with continuous operational baseline."
                )
            else:
                # Sudden massive spike even at an industrial site is an anomaly
                is_anomaly = True
                status = BaselineStatus.ABNORMAL
                anomaly_score = min(0.95, max(0.65, 0.50 + (deviation * 0.08)))
                rationale = (
                    f"Unprecedented radiance spike at recurring site ({prior_passes} passes). "
                    f"Output exceeds operational baseline by {deviation:.1f} standard deviations."
                )
            return BaselineEvaluation(
                status=status,
                baseline_mean_frp=round(mean, 2),
                baseline_std_frp=round(std, 2),
                deviation_sigma=round(deviation, 2),
                is_anomaly=is_anomaly,
                anomaly_score=round(anomaly_score, 3),
                detection_frequency_per_day=round(det_freq_per_day, 3) if det_freq_per_day is not None else None,
                frp_percentile=round(frp_percentile, 3),
                persistence_score=round(persistence, 3),
                has_sufficient_history=True,
                rationale=rationale,
            )

        # Case B: Insufficient Site History (New or unindexed site)
        if (hist_30d is None or hist_30d == 0) and (hist_90d is None or hist_90d == 0) and not is_recurrent:
            # NO_BASELINE status: we compare against regional default priors, but flag absence of site history
            if deviation >= self.sigma_threshold:
                is_anomaly = True
                status = BaselineStatus.NO_BASELINE
                anomaly_score = min(0.99, max(0.65, 0.50 + (deviation * 0.10)))
                rationale = (
                    f"No local site baseline available. "
                    f"Thermal radiance ({frp:.1f} MW) is {deviation:.1f} standard deviations "
                    f"above regional baseline ({mean:.1f} MW)."
                )
            else:
                is_anomaly = False
                status = BaselineStatus.NO_BASELINE
                normalized_score = max(0.0, (deviation + 1.0) / 5.0)
                anomaly_score = min(0.55, normalized_score)
                rationale = (
                    f"No local site baseline available. "
                    f"Radiant energy output ({frp:.1f} MW) within normal expected variation bounds "
                    f"evaluated against default regional prior ({mean:.1f} MW, deviation: {deviation:.1f} sigma)."
                )
            return BaselineEvaluation(
                status=status,
                baseline_mean_frp=round(mean, 2),
                baseline_std_frp=round(std, 2),
                deviation_sigma=round(deviation, 2),
                is_anomaly=is_anomaly,
                anomaly_score=round(anomaly_score, 3),
                detection_frequency_per_day=None,
                frp_percentile=round(frp_percentile, 3),
                persistence_score=round(persistence, 3),
                has_sufficient_history=False,
                rationale=rationale,
            )

        # Case C: Limited Historical History (1 to 9 passes)
        if deviation >= self.sigma_threshold:
            is_anomaly = True
            status = BaselineStatus.ABNORMAL
            anomaly_score = min(0.99, max(0.65, 0.50 + (deviation * 0.10)))
            rationale = (
                f"Thermal radiance ({frp:.1f} MW) is {deviation:.1f} standard deviations "
                f"above regional baseline ({mean:.1f} MW)."
            )
        else:
            is_anomaly = False
            status = BaselineStatus.NORMAL
            normalized_score = max(0.0, (deviation + 1.0) / 5.0)
            anomaly_score = min(0.55, normalized_score)
            rationale = (
                f"Radiant energy output ({frp:.1f} MW) within normal expected variation bounds "
                f"({deviation:.1f} sigma deviation)."
            )

        return BaselineEvaluation(
            status=status,
            baseline_mean_frp=round(mean, 2),
            baseline_std_frp=round(std, 2),
            deviation_sigma=round(deviation, 2),
            is_anomaly=is_anomaly,
            anomaly_score=round(anomaly_score, 3),
            detection_frequency_per_day=round(det_freq_per_day, 3) if det_freq_per_day is not None else None,
            frp_percentile=round(frp_percentile, 3),
            persistence_score=round(persistence, 3),
            has_sufficient_history=has_sufficient_history,
            rationale=rationale,
        )

    def _handle_zero_variance(
        self,
        frp: float,
        mean: float,
        features: FeatureVector,
    ) -> BaselineEvaluation:
        """Deterministic handling when standard deviation is zero (identical samples)."""
        if abs(frp - mean) < 1e-6:
            # Observation matches zero-variance mean exactly
            return BaselineEvaluation(
                status=BaselineStatus.NORMAL,
                baseline_mean_frp=round(mean, 2),
                baseline_std_frp=0.0,
                deviation_sigma=0.0,
                is_anomaly=False,
                anomaly_score=0.0,
                detection_frequency_per_day=None,
                frp_percentile=0.50,
                persistence_score=features.persistence_score,
                has_sufficient_history=features.has_history,
                rationale="Zero-variance population: observation exactly matches baseline mean.",
            )

        # Target differs from a zero-variance population
        # Use an empirical scale of 20% of mean or minimum 1.0 to prevent division by zero
        safe_scale = max(MIN_BASELINE_STD_EPSILON, abs(mean) * 0.20)
        deviation = (frp - mean) / safe_scale
        is_anomaly = abs(deviation) >= self.sigma_threshold
        status = BaselineStatus.ABNORMAL if is_anomaly else BaselineStatus.NORMAL
        anomaly_score = min(0.99, max(0.0, abs(deviation) / 5.0))

        return BaselineEvaluation(
            status=status,
            baseline_mean_frp=round(mean, 2),
            baseline_std_frp=0.0,
            deviation_sigma=round(deviation, 2),
            is_anomaly=is_anomaly,
            anomaly_score=round(anomaly_score, 3),
            detection_frequency_per_day=None,
            frp_percentile=self._approximate_percentile(deviation),
            persistence_score=features.persistence_score,
            has_sufficient_history=features.has_history,
            rationale=(
                f"Observation ({frp:.1f} MW) departs from zero-variance baseline ({mean:.1f} MW) "
                f"by {deviation:.1f} estimated scale units."
            ),
        )

    @staticmethod
    def _approximate_percentile(z: float) -> float:
        """Standard normal cumulative distribution function (CDF) approximation."""
        # Using error function approximation: 0.5 * (1 + erf(z / sqrt(2)))
        return min(1.0, max(0.0, 0.5 * (1.0 + math.erf(z / 1.41421356))))
