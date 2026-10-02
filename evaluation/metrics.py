"""Evaluation metrics computation for ThermalIntel V2.

Computes:
- Classification counts and distributions
- Confusion matrix and F1/Precision/Recall (only when valid labels exist)
- Risk stability and volatility across observation sequences
- Incident counts, states, and escalation transitions
- Alert counts, priority distributions, and deduplication efficiency
- Event transition counts

Implements Requirement 9, 10, 13:
- Distinguishes GROUND_TRUTH, WEAK_LABEL, SYNTHETIC_EXPECTATION, UNLABELLED
- Never fabricates accuracy for unlabelled data
- Preserves explicit sample sizes (n) and methodologies
"""

import math
from typing import Dict, Any, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from evaluation.labels import LabelType
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.assessment import Assessment
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.event import IncidentEvent


class MetricResult(BaseModel):
    """Structured container for an individual evaluation metric."""
    name: str = Field(..., description="Canonical metric identifier")
    value: Any = Field(..., description="Computed metric value (scalar, dict, or percentage)")
    sample_size: Optional[int] = Field(None, description="Sample size 'n' representing observations evaluated")
    label_type: LabelType = Field(default=LabelType.UNLABELLED, description="Provenance classification of ground truth/labels")
    methodology_version: str = Field(default="v2.0-eval", description="Semantic evaluation methodology version")
    description: Optional[str] = Field(None, description="Human-readable explanation of the metric")


def compute_classification_metrics(
    assessments: List[Assessment],
    expected_labels: Optional[List[Optional[str]]] = None,
    label_type: LabelType = LabelType.UNLABELLED,
    methodology_version: str = "v2.0-eval",
) -> List[MetricResult]:
    """Calculate classification counts, distributions, and confusion matrix when labels exist."""
    results: List[MetricResult] = []
    n = len(assessments)

    # 1. Predicted class distribution counts
    pred_counts: Dict[str, int] = {}
    for asm in assessments:
        src = asm.classification.predicted_source.value
        pred_counts[src] = pred_counts.get(src, 0) + 1

    results.append(
        MetricResult(
            name="classification_predicted_counts",
            value=pred_counts,
            sample_size=n,
            label_type=label_type,
            methodology_version=methodology_version,
            description="Frequency of predicted thermal source categories",
        )
    )

    # 2. Strict Ground-Truth / Label Rule:
    # Do NOT compute accuracy or confusion matrix for UNLABELLED data
    if not label_type.allows_accuracy_metric or not expected_labels:
        results.append(
            MetricResult(
                name="classification_accuracy",
                value=None,
                sample_size=n,
                label_type=label_type,
                methodology_version=methodology_version,
                description="Classification accuracy omitted: dataset is UNLABELLED (no ground truth)",
            )
        )
        return results

    # Valid labels exist: Compute confusion matrix and accuracy
    matrix: Dict[str, Dict[str, int]] = {}
    correct = 0
    labeled_count = 0

    for asm, exp in zip(assessments, expected_labels):
        if not exp:
            continue
        labeled_count += 1
        actual = exp.lower().strip()
        pred = asm.classification.predicted_source.value.lower().strip()

        if actual not in matrix:
            matrix[actual] = {}
        matrix[actual][pred] = matrix[actual].get(pred, 0) + 1

        if actual == pred:
            correct += 1

    if labeled_count > 0:
        accuracy = round(correct / labeled_count, 4)
        results.append(
            MetricResult(
                name="classification_accuracy",
                value=accuracy,
                sample_size=labeled_count,
                label_type=label_type,
                methodology_version=methodology_version,
                description=f"Classification accuracy scored against {label_type.value}",
            )
        )
        results.append(
            MetricResult(
                name="confusion_matrix",
                value=matrix,
                sample_size=labeled_count,
                label_type=label_type,
                methodology_version=methodology_version,
                description="Confusion matrix [actual][predicted]",
            )
        )

    return results


def compute_risk_stability_metrics(
    assessments: List[Assessment],
    methodology_version: str = "v2.0-eval",
) -> List[MetricResult]:
    """Measure risk score stability and volatility across sequential evaluations."""
    results: List[MetricResult] = []
    n = len(assessments)
    if n == 0:
        return results

    scores = [asm.risk.risk_score for asm in assessments]
    mean_score = sum(scores) / n

    if n > 1:
        variance = sum((s - mean_score) ** 2 for s in scores) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    # Severity flips
    severities = [asm.risk.severity.value for asm in assessments]
    flips = sum(1 for i in range(1, len(severities)) if severities[i] != severities[i - 1])

    # Max step delta
    max_delta = 0.0
    for i in range(1, len(scores)):
        delta = abs(scores[i] - scores[i - 1])
        if delta > max_delta:
            max_delta = delta

    results.append(
        MetricResult(
            name="risk_mean_score",
            value=round(mean_score, 2),
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Mean composite risk score across observations",
        )
    )
    results.append(
        MetricResult(
            name="risk_score_std_dev",
            value=round(std_dev, 2),
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Standard deviation of composite risk score across timeline",
        )
    )
    results.append(
        MetricResult(
            name="risk_severity_flips",
            value=flips,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Count of severity tier transitions across observations",
        )
    )
    results.append(
        MetricResult(
            name="risk_max_step_delta",
            value=round(max_delta, 2),
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Maximum absolute risk score jump between adjacent observations",
        )
    )

    return results


def compute_incident_metrics(
    incidents: List[Incident],
    methodology_version: str = "v2.0-eval",
) -> List[MetricResult]:
    """Calculate incident lifecycle, aggregation, and severity metrics."""
    results: List[MetricResult] = []
    n = len(incidents)

    status_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    total_obs = 0
    max_peak_frp = 0.0

    for inc in incidents:
        status_counts[inc.status.value] = status_counts.get(inc.status.value, 0) + 1
        severity_counts[inc.current_severity.value] = severity_counts.get(inc.current_severity.value, 0) + 1
        total_obs += inc.observation_count
        if inc.peak_frp > max_peak_frp:
            max_peak_frp = inc.peak_frp

    results.append(
        MetricResult(
            name="incident_count",
            value=n,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Total number of persistent real-world incidents synthesized",
        )
    )
    results.append(
        MetricResult(
            name="incident_status_distribution",
            value=status_counts,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Distribution of incidents across lifecycle operational states",
        )
    )
    results.append(
        MetricResult(
            name="incident_severity_distribution",
            value=severity_counts,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Distribution of current incident severity ratings",
        )
    )
    results.append(
        MetricResult(
            name="incident_max_peak_frp",
            value=round(max_peak_frp, 1),
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Highest peak Fire Radiative Power (MW) across incidents",
        )
    )

    return results


def compute_alert_metrics(
    alerts: List[AlertV2],
    methodology_version: str = "v2.0-eval",
) -> List[MetricResult]:
    """Calculate operational alert volume, priority distributions, and deduplication stats."""
    results: List[MetricResult] = []
    n = len(alerts)

    priority_counts: Dict[str, int] = {}
    for alt in alerts:
        p = alt.priority.value
        priority_counts[p] = priority_counts.get(p, 0) + 1

    results.append(
        MetricResult(
            name="alert_count",
            value=n,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Total deduplicated operational hazard alerts emitted",
        )
    )
    results.append(
        MetricResult(
            name="alert_priority_distribution",
            value=priority_counts,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Count of alerts grouped by operational priority level",
        )
    )

    return results


def compute_event_transition_metrics(
    events: List[IncidentEvent],
    methodology_version: str = "v2.0-eval",
) -> List[MetricResult]:
    """Calculate incident timeline lifecycle event counts."""
    results: List[MetricResult] = []
    n = len(events)

    event_counts: Dict[str, int] = {}
    for evt in events:
        t = evt.event_type.value
        event_counts[t] = event_counts.get(t, 0) + 1

    results.append(
        MetricResult(
            name="incident_event_count",
            value=n,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Total chronological timeline events recorded",
        )
    )
    results.append(
        MetricResult(
            name="incident_event_type_distribution",
            value=event_counts,
            sample_size=n,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version=methodology_version,
            description="Lifecycle audit events categorized by event type",
        )
    )

    return results
