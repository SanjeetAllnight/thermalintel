"""Low-cardinality thread-safe operational metrics primitives."""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Mapping, Optional, Sequence, Tuple

# Metric name must be Prometheus-compatible: [a-zA-Z_:][a-zA-Z0-9_:]*
METRIC_NAME_REGEX = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
# Label name must be: [a-zA-Z_][a-zA-Z0-9_]*
LABEL_NAME_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _sanitize_label_value(val: Any, max_len: int = 64) -> str:
    """Normalize label values and truncate to prevent memory exhaustion / cardinality explosions."""
    if val is None:
        return "none"
    s = str(val).strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s


def _canonical_labels(
    declared_names: Sequence[str],
    labels: Mapping[str, Any],
) -> Tuple[Tuple[str, str], ...]:
    """Validate and sort labels into an immutable tuple key."""
    result = []
    for name in declared_names:
        val = labels.get(name, "unknown")
        result.append((name, _sanitize_label_value(val)))
    return tuple(result)


class Metric:
    """Base class for all operational metrics."""

    def __init__(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
    ) -> None:
        if not METRIC_NAME_REGEX.match(name):
            raise ValueError(f"Invalid metric name: {name}")
        self.name = name
        self.description = description
        self.label_names = tuple(label_names or ())
        for lname in self.label_names:
            if not LABEL_NAME_REGEX.match(lname):
                raise ValueError(f"Invalid label name: {lname}")
        self._lock = threading.Lock()

    def _labels_to_key(self, **labels: Any) -> Tuple[Tuple[str, str], ...]:
        return _canonical_labels(self.label_names, labels)


class Counter(Metric):
    """Monotonically increasing counter."""

    def __init__(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__(name, description, label_names)
        self._values: dict[Tuple[Tuple[str, str], ...], float] = {}

    def inc(self, value: float = 1.0, **labels: Any) -> None:
        if value < 0:
            raise ValueError("Counters can only be incremented by non-negative amounts.")
        key = self._labels_to_key(**labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + value

    def get(self, **labels: Any) -> float:
        key = self._labels_to_key(**labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def collect(self) -> dict[Tuple[Tuple[str, str], ...], float]:
        with self._lock:
            return dict(self._values)


class Gauge(Metric):
    """Metric that represents a single numerical value that can arbitrarily go up and down."""

    def __init__(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__(name, description, label_names)
        self._values: dict[Tuple[Tuple[str, str], ...], float] = {}

    def set(self, value: float, **labels: Any) -> None:
        key = self._labels_to_key(**labels)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, value: float = 1.0, **labels: Any) -> None:
        key = self._labels_to_key(**labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + value

    def dec(self, value: float = 1.0, **labels: Any) -> None:
        key = self._labels_to_key(**labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) - value

    def get(self, **labels: Any) -> float:
        key = self._labels_to_key(**labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def collect(self) -> dict[Tuple[Tuple[str, str], ...], float]:
        with self._lock:
            return dict(self._values)


class Histogram(Metric):
    """Samples observations (usually durations or sizes) into configurable buckets."""

    def __init__(
        self,
        name: str,
        description: str,
        label_names: Optional[Sequence[str]] = None,
        buckets: Sequence[float] = DEFAULT_BUCKETS,
    ) -> None:
        super().__init__(name, description, label_names)
        self.buckets = tuple(sorted(buckets))
        # Structure: key -> {"count": int, "sum": float, "buckets": {bucket_le: count}}
        self._data: dict[Tuple[Tuple[str, str], ...], dict[str, Any]] = {}

    def observe(self, value: float, **labels: Any) -> None:
        key = self._labels_to_key(**labels)
        with self._lock:
            if key not in self._data:
                self._data[key] = {
                    "count": 0,
                    "sum": 0.0,
                    "bucket_counts": {b: 0 for b in self.buckets},
                }
            entry = self._data[key]
            entry["count"] += 1
            entry["sum"] += float(value)
            for b in self.buckets:
                if value <= b:
                    entry["bucket_counts"][b] += 1

    def timer(self, **labels: Any) -> Timer:
        return Timer(self, **labels)

    def collect(self) -> dict[Tuple[Tuple[str, str], ...], dict[str, Any]]:
        with self._lock:
            # Deep copy
            result = {}
            for k, v in self._data.items():
                result[k] = {
                    "count": v["count"],
                    "sum": v["sum"],
                    "bucket_counts": dict(v["bucket_counts"]),
                }
            return result


class Timer:
    """Context manager for measuring execution time and recording to a Histogram or Gauge."""

    def __init__(self, target: Histogram | Gauge, **labels: Any) -> None:
        self.target = target
        self.labels = labels
        self.start_time: float = 0.0
        self.duration_seconds: float = 0.0

    def __enter__(self) -> Timer:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.duration_seconds = time.perf_counter() - self.start_time
        if isinstance(self.target, Histogram):
            self.target.observe(self.duration_seconds, **self.labels)
        elif isinstance(self.target, Gauge):
            self.target.set(self.duration_seconds, **self.labels)
