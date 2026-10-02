"""Risk model weight sensitivity analysis for ThermalIntel V2.

Evaluates how perturbations in composite risk criteria weights affect
risk scores and ranking stability across thermal anomaly observations.

Implements Requirement 11:
'Provide an evaluation hook for risk-model sensitivity.
 For example:
 baseline weights
 ± configurable perturbation
 rank stability
 Do not hardcode unsupported claims.
 A simple deterministic function/report is enough.'
"""

import math
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from services.intelligence.risk import RiskAssessor
from services.intelligence.features import FeatureExtractor, FeatureVector
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.anomaly import AnomalyDetector
from services.api.schemas.common import SourceType
from services.api.schemas.hotspot import Hotspot


class PerturbationResult(BaseModel):
    """Evaluation result for a single perturbed weight configuration."""
    configuration_name: str
    perturbed_weights: Dict[str, float]
    spearman_rank_correlation: float = Field(..., ge=-1.0, le=1.0)
    mean_absolute_error: float = Field(..., ge=0.0)
    max_rank_displacement: int = Field(..., ge=0)


class SensitivityReport(BaseModel):
    """Structured report documenting risk weight sensitivity findings."""
    baseline_weights: Dict[str, float]
    perturbation_percentage: float
    sample_size: int
    mean_rank_correlation: float
    min_rank_correlation: float
    rank_stability_rating: str  # HIGH, MODERATE, SENSITIVE
    configurations: List[PerturbationResult] = Field(default_factory=list)


def _compute_spearman_rank_correlation(ranks_a: List[int], ranks_b: List[int]) -> float:
    """Compute Spearman's rank correlation coefficient between two rankings."""
    n = len(ranks_a)
    if n <= 1:
        return 1.0

    d_squared_sum = sum((ra - rb) ** 2 for ra, rb in zip(ranks_a, ranks_b))
    rho = 1.0 - (6.0 * d_squared_sum) / (n * (n ** 2 - 1))
    return round(max(-1.0, min(1.0, rho)), 4)


def _get_ranks(values: List[float], reverse: bool = True) -> List[int]:
    """Assign 1-based ranks to values (highest value gets rank 1 by default)."""
    # Sort indices by value
    indexed = sorted(enumerate(values), key=lambda x: x[1], reverse=reverse)
    ranks = [0] * len(values)
    for rank, (orig_idx, _) in enumerate(indexed, start=1):
        ranks[orig_idx] = rank
    return ranks


class WeightSensitivityEvaluator:
    """Deterministic sensitivity evaluator for the ThermalIntel composite risk engine."""

    def __init__(
        self,
        baseline_weights: Optional[Dict[str, float]] = None,
        default_delta_pct: float = 0.15,
    ):
        self.baseline_weights = baseline_weights or {
            "frp": 0.35,
            "weather": 0.25,
            "proximity": 0.20,
            "anomaly": 0.15,
            "history": 0.05,
        }
        self.default_delta_pct = default_delta_pct

    def evaluate(
        self,
        hotspots: List[Hotspot],
        contexts: Optional[List[HotspotContext]] = None,
        delta_pct: Optional[float] = None,
    ) -> SensitivityReport:
        """Run weight sensitivity evaluation across a population of hotspots and contexts."""
        if not hotspots:
            return SensitivityReport(
                baseline_weights=self.baseline_weights,
                perturbation_percentage=0.0,
                sample_size=0,
                mean_rank_correlation=1.0,
                min_rank_correlation=1.0,
                rank_stability_rating="HIGH",
                configurations=[],
            )

        pct = delta_pct if delta_pct is not None else self.default_delta_pct
        ctx_list = contexts or [HotspotContext() for _ in hotspots]
        if len(ctx_list) < len(hotspots):
            ctx_list = ctx_list + [HotspotContext() for _ in range(len(hotspots) - len(ctx_list))]

        # Extract features and detect anomalies
        anomaly_detector = AnomalyDetector()
        feature_vectors: List[Tuple[FeatureVector, Any]] = []

        for h, c in zip(hotspots, ctx_list):
            fv = FeatureExtractor.extract(NormalizedHotspotInput.from_input(h), c)
            anom = anomaly_detector.detect(fv)
            feature_vectors.append((fv, anom))

        # 1. Baseline Scoring
        baseline_assessor = RiskAssessor(
            weight_frp=self.baseline_weights["frp"],
            weight_weather=self.baseline_weights["weather"],
            weight_proximity=self.baseline_weights["proximity"],
            weight_anomaly=self.baseline_weights["anomaly"],
            weight_history=self.baseline_weights["history"],
        )

        baseline_scores = [
            baseline_assessor.assess_risk(fv, SourceType.UNKNOWN, anom).risk_score
            for fv, anom in feature_vectors
        ]
        baseline_ranks = _get_ranks(baseline_scores)

        # 2. Generate Perturbed Configurations
        # Test each individual weight increased (+delta) and decreased (-delta)
        perturbations: List[PerturbationResult] = []

        for key in self.baseline_weights:
            for sign, direction in [(-1, "down"), (1, "up")]:
                perturbed = dict(self.baseline_weights)
                shift = self.baseline_weights[key] * pct * sign
                perturbed[key] = max(0.01, perturbed[key] + shift)

                # Re-normalize weights to sum to 1.0
                total = sum(perturbed.values())
                normalized_weights = {k: round(v / total, 4) for k, v in perturbed.items()}

                perturbed_assessor = RiskAssessor(
                    weight_frp=normalized_weights["frp"],
                    weight_weather=normalized_weights["weather"],
                    weight_proximity=normalized_weights["proximity"],
                    weight_anomaly=normalized_weights["anomaly"],
                    weight_history=normalized_weights["history"],
                )

                perturbed_scores = [
                    perturbed_assessor.assess_risk(fv, SourceType.UNKNOWN, anom).risk_score
                    for fv, anom in feature_vectors
                ]
                perturbed_ranks = _get_ranks(perturbed_scores)

                rho = _compute_spearman_rank_correlation(baseline_ranks, perturbed_ranks)
                mae = round(
                    sum(abs(b - p) for b, p in zip(baseline_scores, perturbed_scores)) / len(baseline_scores),
                    3
                )
                max_disp = max(abs(ra - rb) for ra, rb in zip(baseline_ranks, perturbed_ranks))

                perturbations.append(
                    PerturbationResult(
                        configuration_name=f"{key}_{direction}_{int(pct*100)}pct",
                        perturbed_weights=normalized_weights,
                        spearman_rank_correlation=rho,
                        mean_absolute_error=mae,
                        max_rank_displacement=max_disp,
                    )
                )

        correlations = [p.spearman_rank_correlation for p in perturbations]
        mean_rho = round(sum(correlations) / len(correlations), 4) if correlations else 1.0
        min_rho = min(correlations) if correlations else 1.0

        if min_rho >= 0.90:
            rating = "HIGH"
        elif min_rho >= 0.75:
            rating = "MODERATE"
        else:
            rating = "SENSITIVE"

        return SensitivityReport(
            baseline_weights=self.baseline_weights,
            perturbation_percentage=pct,
            sample_size=len(hotspots),
            mean_rank_correlation=mean_rho,
            min_rank_correlation=min_rho,
            rank_stability_rating=rating,
            configurations=perturbations,
        )
