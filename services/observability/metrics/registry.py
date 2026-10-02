"""Central registry for operational metrics."""

from __future__ import annotations

import threading
from typing import Any, Mapping, Optional, Sequence

from services.observability.metrics.types import Counter, Gauge, Histogram, Metric


class MetricsRegistry:
    """Thread-safe registry for application operational metrics."""

    def __init__(self) -> None:
        self._metrics: dict[str, Metric] = {}
        self._lock = threading.Lock()

    def register(self, metric: Metric) -> Metric:
        with self._lock:
            if metric.name in self._metrics:
                # Return existing if already registered with same type
                existing = self._metrics[metric.name]
                if type(existing) is not type(metric):
                    raise ValueError(
                        f"Metric {metric.name} already registered with different type {type(existing).__name__}"
                    )
                return existing
            self._metrics[metric.name] = metric
            return metric

    def counter(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
    ) -> Counter:
        metric = Counter(name, description, label_names)
        return self.register(metric)  # type: ignore

    def gauge(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
    ) -> Gauge:
        metric = Gauge(name, description, label_names)
        return self.register(metric)  # type: ignore

    def histogram(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
        buckets: Optional[Sequence[float]] = None,
    ) -> Histogram:
        if buckets:
            metric = Histogram(name, description, label_names, buckets=buckets)
        else:
            metric = Histogram(name, description, label_names)
        return self.register(metric)  # type: ignore

    def get(self, name: str) -> Optional[Metric]:
        with self._lock:
            return self._metrics.get(name)

    def all_metrics(self) -> list[Metric]:
        with self._lock:
            return list(self._metrics.values())

    def reset(self) -> None:
        """Clear values of all registered metrics (primarily for test isolation)."""
        with self._lock:
            for metric in self._metrics.values():
                if isinstance(metric, (Counter, Gauge)):
                    with metric._lock:
                        metric._values.clear()
                elif isinstance(metric, Histogram):
                    with metric._lock:
                        metric._data.clear()


_DEFAULT_REGISTRY: Optional[MetricsRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_metrics_registry() -> MetricsRegistry:
    """Return the global default metrics registry singleton."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _REGISTRY_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = MetricsRegistry()
    return _DEFAULT_REGISTRY
