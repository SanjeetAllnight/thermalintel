"""Unit tests for evaluation metrics computation."""

import unittest
from evaluation.labels import LabelType
from evaluation.metrics import (
    compute_classification_metrics,
    compute_risk_stability_metrics,
    compute_incident_metrics,
    compute_alert_metrics,
    compute_event_transition_metrics,
)
from services.api.schemas.v2.assessment import (
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
)
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.common import (
    SourceType,
    RiskLevel,
    IncidentStatus,
    AlertSeverity,
    AlertState,
    IncidentEventType,
)


def make_assessment(pred: SourceType, risk: float, sev: RiskLevel) -> Assessment:
    return Assessment(
        assessment_id=f"ASM-{pred.value}-{risk}",
        target_id="OBS-1",
        target_type="observation",
        classification=ClassificationAssessment(
            predicted_source=pred,
            classification_confidence=0.88,
            probabilities={pred.value: 0.88},
        ),
        anomaly=AnomalyAssessment(
            is_anomaly=risk > 60.0,
            anomaly_score=risk / 100.0,
            baseline_deviation_sigma=1.2,
            anomaly_rationale="Evaluated",
        ),
        risk=RiskAssessmentResult(
            risk_score=risk,
            severity=sev,
            frp_component=risk * 0.4,
            weather_component=risk * 0.3,
            proximity_component=risk * 0.2,
            historical_component=risk * 0.1,
            factors=[],
            recommended_action="Dispatch",
        ),
        data_quality=DataQualityAssessment(completeness_score=1.0, uncertainty_score=0.1),
        methodology=AssessmentMethodology(
            method="Test",
            algorithm_version="v2.0",
            input_hash="hash",
            as_of_utc="2026-10-01T12:00:00Z",
        ),
    )


class TestMetricsComputation(unittest.TestCase):
    """Test metric computation functions for classification, risk, incidents, alerts, events."""

    def test_classification_with_labels_computes_confusion_matrix(self):
        asms = [
            make_assessment(SourceType.WILDFIRE, 50.0, RiskLevel.MEDIUM),
            make_assessment(SourceType.INDUSTRIAL, 20.0, RiskLevel.LOW),
            make_assessment(SourceType.WILDFIRE, 80.0, RiskLevel.CRITICAL),
        ]
        expected = ["wildfire", "industrial", "wildfire"]

        metrics = compute_classification_metrics(
            assessments=asms,
            expected_labels=expected,
            label_type=LabelType.SYNTHETIC_EXPECTATION,
        )

        acc = next(m for m in metrics if m.name == "classification_accuracy")
        self.assertEqual(acc.value, 1.0)
        self.assertEqual(acc.sample_size, 3)

        cm = next(m for m in metrics if m.name == "confusion_matrix")
        self.assertEqual(cm.value["wildfire"]["wildfire"], 2)
        self.assertEqual(cm.value["industrial"]["industrial"], 1)

    def test_risk_stability_metrics(self):
        asms = [
            make_assessment(SourceType.WILDFIRE, 30.0, RiskLevel.MEDIUM),
            make_assessment(SourceType.WILDFIRE, 45.0, RiskLevel.MEDIUM),
            make_assessment(SourceType.WILDFIRE, 85.0, RiskLevel.CRITICAL),
        ]
        metrics = compute_risk_stability_metrics(asms)

        mean_metric = next(m for m in metrics if m.name == "risk_mean_score")
        self.assertAlmostEqual(mean_metric.value, 53.33, places=1)

        flips_metric = next(m for m in metrics if m.name == "risk_severity_flips")
        self.assertEqual(flips_metric.value, 1)  # MEDIUM -> CRITICAL = 1 flip

        max_delta = next(m for m in metrics if m.name == "risk_max_step_delta")
        self.assertEqual(max_delta.value, 40.0)  # 85 - 45 = 40

    def test_incident_metrics(self):
        incidents = [
            Incident(
                incident_id="INC-1",
                status=IncidentStatus.ACTIVE,
                first_seen_utc="2026-10-01T12:00:00Z",
                last_seen_utc="2026-10-01T14:00:00Z",
                centroid_latitude=34.0,
                centroid_longitude=-118.0,
                peak_frp=150.0,
                average_frp=80.0,
                observation_count=2,
                current_risk_score=75.0,
                current_severity=RiskLevel.CRITICAL,
            )
        ]
        metrics = compute_incident_metrics(incidents)

        count = next(m for m in metrics if m.name == "incident_count")
        self.assertEqual(count.value, 1)

        peak = next(m for m in metrics if m.name == "incident_max_peak_frp")
        self.assertEqual(peak.value, 150.0)

    def test_alert_metrics(self):
        alerts = [
            AlertV2(
                alert_id="ALT-1",
                rule_id="RULE_1",
                dedupe_key="DED-1",
                priority=AlertSeverity.CRITICAL,
                title="Critical Fire",
                message="Situation critical",
            ),
            AlertV2(
                alert_id="ALT-2",
                rule_id="RULE_2",
                dedupe_key="DED-2",
                priority=AlertSeverity.WARNING,
                title="Warning Fire",
                message="Situation warning",
            ),
        ]
        metrics = compute_alert_metrics(alerts)
        count = next(m for m in metrics if m.name == "alert_count")
        self.assertEqual(count.value, 2)

        p_dist = next(m for m in metrics if m.name == "alert_priority_distribution")
        self.assertEqual(p_dist.value["critical"], 1)
        self.assertEqual(p_dist.value["warning"], 1)

    def test_event_transition_metrics(self):
        events = [
            IncidentEvent(
                event_id="EVT-1",
                incident_id="INC-1",
                event_type=IncidentEventType.CREATED,
                reason="Created",
            ),
            IncidentEvent(
                event_id="EVT-2",
                incident_id="INC-1",
                event_type=IncidentEventType.ESCALATED,
                reason="Escalated",
            ),
        ]
        metrics = compute_event_transition_metrics(events)
        count = next(m for m in metrics if m.name == "incident_event_count")
        self.assertEqual(count.value, 2)
        dist = next(m for m in metrics if m.name == "incident_event_type_distribution")
        self.assertEqual(dist.value["created"], 1)
        self.assertEqual(dist.value["escalated"], 1)


if __name__ == "__main__":
    unittest.main()
