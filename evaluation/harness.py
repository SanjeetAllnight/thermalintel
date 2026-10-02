"""Evaluation Harness for ThermalIntel V2.

Provides unified execution of simulation replay, metric computation,
label auditing, risk weight sensitivity analysis, and structured report synthesis.

Implements Requirement 9:
'Create a reusable evaluation layer that can accept:
 inputs → pipeline → outputs
 and produce structured results.
 Support metrics such as:
 classification counts
 confusion matrix when labels exist
 risk stability
 incident counts
 alert counts
 event transitions
 Do not invent accuracy.
 Do not automatically call heuristic-generated labels "ground truth."'
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from scenarios.schema import Scenario
from evaluation.labels import LabelType
from evaluation.metrics import (
    MetricResult,
    compute_classification_metrics,
    compute_risk_stability_metrics,
    compute_incident_metrics,
    compute_alert_metrics,
    compute_event_transition_metrics,
)
from evaluation.sensitivity import WeightSensitivityEvaluator
from evaluation.report import EvaluationReport
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.assessment import Assessment
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.converters import hotspot_from_v2
from services.intelligence.context import HotspotContext

logger = logging.getLogger(__name__)


class EvaluationHarness:
    """Reusable evaluation orchestrator for ThermalIntel V2."""

    def __init__(
        self,
        methodology_version: str = "v2.0-eval",
        sensitivity_evaluator: Optional[WeightSensitivityEvaluator] = None,
    ):
        self.methodology_version = methodology_version
        self.sensitivity_evaluator = sensitivity_evaluator or WeightSensitivityEvaluator()

    def evaluate_scenario(
        self,
        scenario: Scenario,
        run_sensitivity: bool = True,
    ) -> EvaluationReport:
        """Execute a scenario replay and evaluate complete pipeline behavior."""
        # Run scenario to completion using ReplayPlayer
        from services.replay.player import ReplayPlayer
        player = ReplayPlayer(scenario=scenario)
        player.run_to_completion()

        pipeline = player.pipeline
        observations = [
            # Extract collected observations from pipeline results
            obs
            for step in player.history
            for obs in step.observations
        ]

        # Extract annotations and determine dominant label type
        expected_labels: List[Optional[str]] = []
        label_types: List[LabelType] = []

        for so in scenario.sorted_observations():
            expected_labels.append(so.expected_source)
            label_types.append(so.label_type)

        overall_label_type = (
            label_types[0] if label_types else LabelType.SYNTHETIC_EXPECTATION
        )

        return self.evaluate_pipeline_outputs(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            observations=observations,
            assessments=pipeline.assessments,
            incidents=pipeline.incidents,
            alerts=pipeline.alerts,
            events=pipeline.events,
            expected_labels=expected_labels,
            label_type=overall_label_type,
            run_sensitivity=run_sensitivity,
        )

    def evaluate_pipeline_outputs(
        self,
        scenario_id: str,
        scenario_name: Optional[str] = None,
        observations: Optional[List[Observation]] = None,
        assessments: Optional[List[Assessment]] = None,
        incidents: Optional[List[Incident]] = None,
        alerts: Optional[List[AlertV2]] = None,
        events: Optional[List[IncidentEvent]] = None,
        expected_labels: Optional[List[Optional[str]]] = None,
        label_type: LabelType = LabelType.UNLABELLED,
        run_sensitivity: bool = True,
    ) -> EvaluationReport:
        """Evaluate raw output collections from a pipeline run."""
        obs_list = observations or []
        asm_list = assessments or []
        inc_list = incidents or []
        alt_list = alerts or []
        evt_list = events or []

        all_metrics: List[MetricResult] = []

        # 1. Classification Metrics (Strictly respects label semantics)
        cls_metrics = compute_classification_metrics(
            assessments=asm_list,
            expected_labels=expected_labels,
            label_type=label_type,
            methodology_version=self.methodology_version,
        )
        all_metrics.extend(cls_metrics)

        # 2. Risk Stability Metrics
        risk_metrics = compute_risk_stability_metrics(
            assessments=asm_list,
            methodology_version=self.methodology_version,
        )
        all_metrics.extend(risk_metrics)

        # 3. Incident Lifecycle Metrics
        inc_metrics = compute_incident_metrics(
            incidents=inc_list,
            methodology_version=self.methodology_version,
        )
        all_metrics.extend(inc_metrics)

        # 4. Operational Alert Metrics
        alt_metrics = compute_alert_metrics(
            alerts=alt_list,
            methodology_version=self.methodology_version,
        )
        all_metrics.extend(alt_metrics)

        # 5. Incident Timeline Event Metrics
        evt_metrics = compute_event_transition_metrics(
            events=evt_list,
            methodology_version=self.methodology_version,
        )
        all_metrics.extend(evt_metrics)

        # 6. Weight Sensitivity Analysis (optional)
        sensitivity_summary: Optional[Dict[str, Any]] = None
        if run_sensitivity and obs_list:
            hotspots = [hotspot_from_v2(o) for o in obs_list]
            contexts = [
                HotspotContext.from_dict(o.source_attributes.get("context") or {})
                for o in obs_list
            ]
            sens_report = self.sensitivity_evaluator.evaluate(hotspots, contexts)
            sensitivity_summary = {
                "rank_stability_rating": sens_report.rank_stability_rating,
                "mean_rank_correlation": sens_report.mean_rank_correlation,
                "min_rank_correlation": sens_report.min_rank_correlation,
                "perturbation_percentage": sens_report.perturbation_percentage,
                "sample_size": sens_report.sample_size,
            }

        # 7. Summary Synthesis
        summary: Dict[str, Any] = {
            "total_observations": len(obs_list),
            "total_assessments": len(asm_list),
            "total_incidents": len(inc_list),
            "total_alerts": len(alt_list),
            "total_timeline_events": len(evt_list),
            "label_provenance": label_type.value,
        }
        if inc_list:
            summary["primary_incident_id"] = inc_list[0].incident_id
            summary["final_severity"] = inc_list[0].current_severity.value
            summary["dominant_classification"] = inc_list[0].current_classification.value
            summary["peak_frp_mw"] = inc_list[0].peak_frp

        return EvaluationReport(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            overall_label_type=label_type,
            methodology_version=self.methodology_version,
            metrics=all_metrics,
            summary=summary,
            sensitivity_summary=sensitivity_summary,
        )
