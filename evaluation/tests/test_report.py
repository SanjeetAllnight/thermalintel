"""Unit tests for EvaluationReport generation and EvaluationHarness."""

import json
import unittest
from pathlib import Path
import tempfile

from evaluation.report import EvaluationReport
from evaluation.labels import LabelType
from evaluation.metrics import MetricResult
from evaluation.harness import EvaluationHarness
from scenarios.loader import load_scenario_from_file

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "data"


class TestEvaluationReportAndHarness(unittest.TestCase):
    """Test machine-readable JSON report and Markdown table generation."""

    def test_report_json_serialization(self):
        report = EvaluationReport(
            scenario_id="SCN-TEST",
            scenario_name="Test Scenario",
            overall_label_type=LabelType.SYNTHETIC_EXPECTATION,
            methodology_version="v2.0-eval",
            metrics=[
                MetricResult(
                    name="incident_count",
                    value=1,
                    sample_size=4,
                    label_type=LabelType.SYNTHETIC_EXPECTATION,
                    methodology_version="v2.0-eval",
                    description="Total incidents",
                ),
                MetricResult(
                    name="classification_accuracy",
                    value=1.0,
                    sample_size=4,
                    label_type=LabelType.SYNTHETIC_EXPECTATION,
                    methodology_version="v2.0-eval",
                ),
            ],
            summary={"incidents": 1, "alerts": 2},
        )

        json_str = report.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed["scenario_id"], "SCN-TEST")
        self.assertEqual(parsed["overall_label_type"], "SYNTHETIC_EXPECTATION")
        self.assertEqual(len(parsed["metrics"]), 2)
        # Every metric must include name, value, sample_size, label_type, methodology_version
        for m in parsed["metrics"]:
            self.assertIn("name", m)
            self.assertIn("value", m)
            self.assertIn("sample_size", m)
            self.assertIn("label_type", m)
            self.assertIn("methodology_version", m)

    def test_report_markdown_generation(self):
        report = EvaluationReport(
            scenario_id="SCN-TEST",
            scenario_name="Test Scenario",
            overall_label_type=LabelType.GROUND_TRUTH,
            methodology_version="v2.0-eval",
            metrics=[
                MetricResult(
                    name="incident_count",
                    value=1,
                    sample_size=3,
                    label_type=LabelType.GROUND_TRUTH,
                    methodology_version="v2.0-eval",
                )
            ],
            summary={"status": "passed"},
            sensitivity_summary={
                "rank_stability_rating": "HIGH",
                "mean_rank_correlation": 0.98,
                "min_rank_correlation": 0.94,
                "perturbation_percentage": 0.15,
            },
        )

        md = report.to_markdown()
        self.assertIn("# ThermalIntel V2 Evaluation Report: SCN-TEST", md)
        self.assertIn("| Metric Name | Value | Sample Size (n) | Label Type | Methodology / Version |", md)
        self.assertIn("`incident_count`", md)
        self.assertIn("GROUND_TRUTH", md)
        self.assertIn("Risk Model Weight Sensitivity Analysis", md)
        self.assertIn("HIGH", md)

    def test_harness_executes_scenario_and_produces_report(self):
        scenario = load_scenario_from_file(DATA_DIR / "scenario_1_industrial_spike.json")
        harness = EvaluationHarness()
        report = harness.evaluate_scenario(scenario, run_sensitivity=True)

        self.assertEqual(report.scenario_id, "SCN-001-INDUSTRIAL-SPIKE")
        self.assertEqual(report.overall_label_type, LabelType.SYNTHETIC_EXPECTATION)
        self.assertGreater(len(report.metrics), 5)
        self.assertIsNotNone(report.sensitivity_summary)

        # Test saving
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "report.json"
            md_path = Path(tmpdir) / "report.md"
            report.save_json(json_path)
            report.save_markdown(md_path)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())


if __name__ == "__main__":
    unittest.main()
