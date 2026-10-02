"""ThermalIntel V2 Evaluation Subsystem.

Provides metric computation, confusion matrices, risk sensitivity analysis,
label semantics, historical backtesting, and machine-readable evaluation report generation.
"""

from .labels import LabelType
from .metrics import (
    MetricResult,
    compute_classification_metrics,
    compute_risk_stability_metrics,
    compute_incident_metrics,
    compute_alert_metrics,
    compute_event_transition_metrics,
)
from .sensitivity import (
    WeightSensitivityEvaluator,
    SensitivityReport,
    PerturbationResult,
)
from .backtest import (
    BacktestEngine,
    BacktestSource,
    FixtureBacktestSource,
    BacktestResult,
    KnownEvent,
)
from .report import EvaluationReport
from .harness import EvaluationHarness

__all__ = [
    "LabelType",
    "MetricResult",
    "compute_classification_metrics",
    "compute_risk_stability_metrics",
    "compute_incident_metrics",
    "compute_alert_metrics",
    "compute_event_transition_metrics",
    "WeightSensitivityEvaluator",
    "SensitivityReport",
    "PerturbationResult",
    "BacktestEngine",
    "BacktestSource",
    "FixtureBacktestSource",
    "BacktestResult",
    "KnownEvent",
    "EvaluationReport",
    "EvaluationHarness",
]
