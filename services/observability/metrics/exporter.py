"""Prometheus exposition and JSON snapshot exporters for ThermalIntel metrics."""

from __future__ import annotations

import math
from typing import Any, Optional

from services.observability.metrics.registry import MetricsRegistry, get_metrics_registry
from services.observability.metrics.types import Counter, Gauge, Histogram


def _format_labels(labels: tuple[tuple[str, str], ...], extra: Optional[dict[str, str]] = None) -> str:
    """Format labels into Prometheus syntax: {key="value",...}."""
    items = list(labels)
    if extra:
        for k, v in extra.items():
            items.append((k, v))
    if not items:
        return ""
    # Sort for deterministic output
    sorted_items = sorted(items, key=lambda x: x[0])
    parts = [f'{k}="{v}"' for k, v in sorted_items]
    return "{" + ",".join(parts) + "}"


def export_prometheus(registry: Optional[MetricsRegistry] = None) -> str:
    """Render all registered metrics in standard Prometheus text exposition format."""
    reg = registry or get_metrics_registry()
    lines: list[str] = []

    for metric in sorted(reg.all_metrics(), key=lambda m: m.name):
        if isinstance(metric, Counter):
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} counter")
            data = metric.collect()
            if not data:
                # Default 0 representation if never incremented without labels
                if not metric.label_names:
                    lines.append(f"{metric.name} 0")
            else:
                for labels, val in sorted(data.items(), key=lambda x: x[0]):
                    lbl_str = _format_labels(labels)
                    lines.append(f"{metric.name}{lbl_str} {val:g}")

        elif isinstance(metric, Gauge):
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} gauge")
            data = metric.collect()
            if not data:
                if not metric.label_names:
                    lines.append(f"{metric.name} 0")
            else:
                for labels, val in sorted(data.items(), key=lambda x: x[0]):
                    lbl_str = _format_labels(labels)
                    lines.append(f"{metric.name}{lbl_str} {val:g}")

        elif isinstance(metric, Histogram):
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} histogram")
            data = metric.collect()
            for labels, hdata in sorted(data.items(), key=lambda x: x[0]):
                count = hdata["count"]
                total_sum = hdata["sum"]
                bucket_counts = hdata["bucket_counts"]

                for b in metric.buckets:
                    b_count = bucket_counts.get(b, 0)
                    lbl_str = _format_labels(labels, extra={"le": f"{b:g}"})
                    lines.append(f"{metric.name}_bucket{lbl_str} {b_count}")

                # +Inf bucket equals total count
                inf_lbl_str = _format_labels(labels, extra={"le": "+Inf"})
                lines.append(f"{metric.name}_bucket{inf_lbl_str} {count}")
                lbl_str = _format_labels(labels)
                lines.append(f"{metric.name}_sum{lbl_str} {total_sum:g}")
                lines.append(f"{metric.name}_count{lbl_str} {count}")

    # Prometheus specification requires trailing newline
    return "\n".join(lines) + "\n"


def export_json(registry: Optional[MetricsRegistry] = None) -> dict[str, Any]:
    """Render all registered metrics as a structured JSON-serializable dictionary."""
    reg = registry or get_metrics_registry()
    output: dict[str, Any] = {}

    for metric in reg.all_metrics():
        if isinstance(metric, (Counter, Gauge)):
            mtype = "counter" if isinstance(metric, Counter) else "gauge"
            samples = []
            for labels, val in metric.collect().items():
                samples.append({
                    "labels": dict(labels),
                    "value": val,
                })
            output[metric.name] = {
                "type": mtype,
                "description": metric.description,
                "samples": samples,
            }
        elif isinstance(metric, Histogram):
            samples = []
            for labels, hdata in metric.collect().items():
                samples.append({
                    "labels": dict(labels),
                    "count": hdata["count"],
                    "sum": hdata["sum"],
                    "buckets": hdata["bucket_counts"],
                })
            output[metric.name] = {
                "type": "histogram",
                "description": metric.description,
                "buckets": list(metric.buckets),
                "samples": samples,
            }

    return output
