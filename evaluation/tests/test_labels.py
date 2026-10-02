"""Unit tests for evaluation label semantics and ground truth distinctions."""

import unittest
from evaluation.labels import LabelType
from evaluation.metrics import compute_classification_metrics
from services.api.schemas.v2.assessment import (
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
)
from services.api.schemas.v2.common import SourceType, RiskLevel


def make_dummy_assessment(pred_source: SourceType) -> Assessment:
    return Assessment(
        assessment_id="ASM-TEST",
        target_id="OBS-TEST",
        target_type="observation",
        classification=ClassificationAssessment(
            predicted_source=pred_source,
            classification_confidence=0.85,
            probabilities={pred_source.value: 0.85},
        ),
        anomaly=AnomalyAssessment(
            is_anomaly=False,
            anomaly_score=0.1,
            baseline_deviation_sigma=0.5,
            anomaly_rationale="Normal",
        ),
        risk=RiskAssessmentResult(
            risk_score=35.0,
            severity=RiskLevel.MEDIUM,
            frp_component=30.0,
            weather_component=25.0,
            proximity_component=20.0,
            historical_component=15.0,
            factors=[],
            recommended_action="Monitor",
        ),
        data_quality=DataQualityAssessment(completeness_score=0.8, uncertainty_score=0.2),
        methodology=AssessmentMethodology(
            method="Test",
            algorithm_version="v2",
            input_hash="hash",
            as_of_utc="2026-10-01T12:00:00Z",
        ),
    )


class TestLabelSemantics(unittest.TestCase):
    """Test label semantics and ground truth separation."""

    def test_label_types_exist(self):
        self.assertEqual(LabelType.GROUND_TRUTH.value, "GROUND_TRUTH")
        self.assertEqual(LabelType.WEAK_LABEL.value, "WEAK_LABEL")
        self.assertEqual(LabelType.SYNTHETIC_EXPECTATION.value, "SYNTHETIC_EXPECTATION")
        self.assertEqual(LabelType.UNLABELLED.value, "UNLABELLED")

    def test_is_ground_truth_strictly_isolated(self):
        self.assertTrue(LabelType.GROUND_TRUTH.is_ground_truth)
        self.assertFalse(LabelType.WEAK_LABEL.is_ground_truth)
        self.assertFalse(LabelType.SYNTHETIC_EXPECTATION.is_ground_truth)
        self.assertFalse(LabelType.UNLABELLED.is_ground_truth)

    def test_allows_accuracy_metric(self):
        self.assertTrue(LabelType.GROUND_TRUTH.allows_accuracy_metric)
        self.assertTrue(LabelType.WEAK_LABEL.allows_accuracy_metric)
        self.assertTrue(LabelType.SYNTHETIC_EXPECTATION.allows_accuracy_metric)
        self.assertFalse(LabelType.UNLABELLED.allows_accuracy_metric)

    def test_unlabelled_data_omits_accuracy_metric(self):
        """Verify Requirement 10: Prevents presenting synthetic or unlabelled data as accuracy."""
        asms = [make_dummy_assessment(SourceType.WILDFIRE)]
        # Evaluated as UNLABELLED
        metrics = compute_classification_metrics(asms, label_type=LabelType.UNLABELLED)

        acc_metric = next((m for m in metrics if m.name == "classification_accuracy"), None)
        self.assertIsNotNone(acc_metric)
        self.assertIsNone(acc_metric.value, "Accuracy must be None for unlabelled data")
        self.assertEqual(acc_metric.label_type, LabelType.UNLABELLED)


if __name__ == "__main__":
    unittest.main()
