"""Evaluation Report formatting and generation for ThermalIntel V2.

Produces machine-readable JSON reports and structured GitHub Markdown summaries.
Every metric strictly includes:
- metric name
- value
- n/sample size when applicable
- label type
- methodology/version

Implements Requirement 13:
'Evaluation should be able to produce structured machine-readable output.
 For example:
 evaluation report → JSON and optionally a simple Markdown summary.
 Every metric must include:
 - metric name
 - value
 - n/sample size when applicable
 - label type
 - methodology/version
 No fake precision.'
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field

from evaluation.labels import LabelType
from evaluation.metrics import MetricResult
from services.api.schemas.v2.common import now_utc_iso


class EvaluationReport(BaseModel):
    """Canonical machine-readable evaluation report model."""
    scenario_id: str
    scenario_name: Optional[str] = None
    evaluation_timestamp_utc: str = Field(default_factory=now_utc_iso)
    overall_label_type: LabelType = Field(default=LabelType.UNLABELLED)
    methodology_version: str = "v2.0-eval"
    metrics: List[MetricResult] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    sensitivity_summary: Optional[Dict[str, Any]] = None

    def get_metric(self, name: str) -> Optional[MetricResult]:
        """Find metric result by name."""
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to formatted machine-readable JSON string."""
        return self.model_dump_json(indent=indent)

    def to_markdown(self) -> str:
        """Render report as clean GitHub-style Markdown document with formatted tables."""
        lines = [
            f"# ThermalIntel V2 Evaluation Report: {self.scenario_id}",
            "",
            f"**Scenario Title:** {self.scenario_name or self.scenario_id}  ",
            f"**Evaluation Timestamp (UTC):** `{self.evaluation_timestamp_utc}`  ",
            f"**Ground-Truth Label Type:** `{self.overall_label_type.value}`  ",
            f"**Evaluation Methodology Version:** `{self.methodology_version}`  ",
            "",
            "## 1. Executive Summary",
            "",
        ]

        if self.summary:
            for k, v in self.summary.items():
                human_k = k.replace("_", " ").title()
                lines.append(f"- **{human_k}:** `{v}`")
            lines.append("")

        lines.extend([
            "## 2. Canonical Metrics Table",
            "",
            "| Metric Name | Value | Sample Size (n) | Label Type | Methodology / Version |",
            "| :--- | :--- | :---: | :--- | :--- |",
        ])

        for m in self.metrics:
            val_str = str(m.value) if m.value is not None else "*omitted (unlabelled)*"
            # Format dicts compactly
            if isinstance(m.value, dict):
                val_str = ", ".join(f"{k}: {v}" for k, v in m.value.items())
            n_str = str(m.sample_size) if m.sample_size is not None else "-"
            lbl_str = m.label_type.value
            ver_str = m.methodology_version

            lines.append(f"| `{m.name}` | {val_str} | {n_str} | `{lbl_str}` | `{ver_str}` |")

        lines.append("")

        # Sensitivity section if available
        if self.sensitivity_summary:
            lines.extend([
                "## 3. Risk Model Weight Sensitivity Analysis",
                "",
                f"- **Rank Stability Rating:** `{self.sensitivity_summary.get('rank_stability_rating', 'N/A')}`",
                f"- **Mean Rank Correlation ($\rho$):** `{self.sensitivity_summary.get('mean_rank_correlation', 'N/A')}`",
                f"- **Min Rank Correlation ($\rho$):** `{self.sensitivity_summary.get('min_rank_correlation', 'N/A')}`",
                f"- **Perturbation Delta:** `±{int(float(self.sensitivity_summary.get('perturbation_percentage', 0.15)) * 100)}%`",
                "",
            ])

        lines.append("---")
        lines.append("*Generated deterministically by ThermalIntel V2 Evaluation Harness.*")
        return "\n".join(lines)

    def save_json(self, path: Union[str, Path]) -> None:
        """Save JSON report to file."""
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(self.to_json(), encoding="utf-8")

    def save_markdown(self, path: Union[str, Path]) -> None:
        """Save Markdown summary to file."""
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(self.to_markdown(), encoding="utf-8")
