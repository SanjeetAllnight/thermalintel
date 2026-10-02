"""Standard operational metrics catalog for ThermalIntel.

Provides strictly defined, low-cardinality metrics covering:
- HTTP API requests and latencies
- Telemetry ingestion and quarantine outcomes
- Contextual GIS/Weather enrichment
- Explainable intelligence assessments
- Incident lifecycle transitions and operational alerts
- Background scheduler and refresh single-flight coalescence
"""

from __future__ import annotations

from typing import Optional

from services.observability.metrics.registry import MetricsRegistry, get_metrics_registry
from services.observability.metrics.types import Counter, Gauge, Histogram

# Latency buckets tailored for web APIs and enrichment
HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
UPSTREAM_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)


class OperationalMetrics:
    """Encapsulates all standard ThermalIntel metrics."""

    def __init__(self, registry: Optional[MetricsRegistry] = None) -> None:
        reg = registry or get_metrics_registry()

        # =====================================================================
        # 1. HTTP API & Application Metrics
        # =====================================================================
        self.http_requests_total: Counter = reg.counter(
            "http_requests_total",
            "Total number of HTTP requests processed by endpoint and status.",
            label_names=("method", "status_code", "endpoint"),
        )
        self.http_requests_by_status_class: Counter = reg.counter(
            "http_requests_by_status_class",
            "HTTP request count categorized by status class (2xx, 4xx, 5xx).",
            label_names=("status_class",),
        )
        self.http_request_duration_seconds: Histogram = reg.histogram(
            "http_request_duration_seconds",
            "HTTP request latency distribution in seconds.",
            label_names=("method", "endpoint"),
            buckets=HTTP_DURATION_BUCKETS,
        )
        self.http_request_failures_total: Counter = reg.counter(
            "http_request_failures_total",
            "Total number of failed HTTP requests by error category.",
            label_names=("method", "endpoint", "error_type"),
        )
        self.http_active_requests: Gauge = reg.gauge(
            "http_active_requests",
            "Number of in-flight HTTP requests.",
            label_names=("method",),
        )

        # =====================================================================
        # 2. Ingestion & Provider Telemetry Metrics
        # =====================================================================
        self.provider_runs_total: Counter = reg.counter(
            "provider_runs_total",
            "Total number of provider ingestion runs.",
            label_names=("provider", "status"),
        )
        self.provider_fetch_duration_seconds: Histogram = reg.histogram(
            "provider_fetch_duration_seconds",
            "Latency of fetching remote telemetry from providers.",
            label_names=("provider",),
            buckets=UPSTREAM_DURATION_BUCKETS,
        )
        self.provider_errors_total: Counter = reg.counter(
            "provider_errors_total",
            "Total number of provider network, parsing, or auth errors.",
            label_names=("provider", "error_category"),
        )
        self.observations_received_total: Counter = reg.counter(
            "observations_received_total",
            "Total raw satellite thermal observations received.",
            label_names=("provider",),
        )
        self.observations_accepted_total: Counter = reg.counter(
            "observations_accepted_total",
            "Thermal observations successfully parsed and stored.",
            label_names=("provider",),
        )
        self.observations_quarantined_total: Counter = reg.counter(
            "observations_quarantined_total",
            "Thermal observations rejected and quarantined.",
            label_names=("provider", "reason"),
        )
        self.observations_duplicate_total: Counter = reg.counter(
            "observations_duplicate_total",
            "Thermal observations identified as duplicates (idempotent).",
            label_names=("provider",),
        )

        # =====================================================================
        # 3. Enrichment Metrics (GIS, Weather, Recurrence)
        # =====================================================================
        self.enrichment_operations_total: Counter = reg.counter(
            "enrichment_operations_total",
            "Total enrichment queries by enricher and outcome.",
            label_names=("enricher", "status"),
        )
        self.enrichment_duration_seconds: Histogram = reg.histogram(
            "enrichment_duration_seconds",
            "Duration of enrichment queries in seconds.",
            label_names=("enricher",),
            buckets=UPSTREAM_DURATION_BUCKETS,
        )
        self.enrichment_fallback_total: Counter = reg.counter(
            "enrichment_fallback_total",
            "Enrichment calls served via cached or fallback data.",
            label_names=("enricher", "reason"),
        )

        # =====================================================================
        # 4. Intelligence & Risk Scoring Metrics
        # =====================================================================
        self.intelligence_assessments_total: Counter = reg.counter(
            "intelligence_assessments_total",
            "Total anomaly risk assessments generated.",
            label_names=("classification", "risk_level"),
        )
        self.intelligence_duration_seconds: Histogram = reg.histogram(
            "intelligence_duration_seconds",
            "Time spent in AI anomaly detection, classification, and scoring.",
            label_names=("stage",),
            buckets=HTTP_DURATION_BUCKETS,
        )
        self.intelligence_failures_total: Counter = reg.counter(
            "intelligence_failures_total",
            "Failures encountered during intelligence evaluation.",
            label_names=("stage",),
        )

        # =====================================================================
        # 5. Incident Lifecycle & Operational Alert Metrics
        # =====================================================================
        self.incidents_created_total: Counter = reg.counter(
            "incidents_created_total",
            "Total new incidents created by initial risk category.",
            label_names=("risk_category",),
        )
        self.incidents_transitions_total: Counter = reg.counter(
            "incidents_transitions_total",
            "Incident state transitions (e.g. active -> closed).",
            label_names=("from_state", "to_state"),
        )
        self.active_incidents: Gauge = reg.gauge(
            "active_incidents",
            "Current count of active open incidents by status.",
            label_names=("status",),
        )
        self.alerts_total: Counter = reg.counter(
            "alerts_total",
            "Operational alerts generated or updated by priority and status.",
            label_names=("priority", "status"),
        )
        self.alerts_suppressed_total: Counter = reg.counter(
            "alerts_suppressed_total",
            "Alerts suppressed due to cooldown, deduplication, or chatter.",
            label_names=("reason",),
        )

        # =====================================================================
        # 6. Scheduler & Refresh Synchronization Metrics
        # =====================================================================
        self.scheduler_runs_total: Counter = reg.counter(
            "scheduler_runs_total",
            "Periodic background scheduler job runs.",
            label_names=("job_name", "status"),
        )
        self.scheduler_duration_seconds: Histogram = reg.histogram(
            "scheduler_duration_seconds",
            "Duration of background scheduled jobs in seconds.",
            label_names=("job_name",),
            buckets=UPSTREAM_DURATION_BUCKETS,
        )
        self.refresh_attempts_total: Counter = reg.counter(
            "refresh_attempts_total",
            "Refresh synchronization attempts by trigger type and status.",
            label_names=("trigger", "status"),
        )
        self.refresh_coalesced_total: Counter = reg.counter(
            "refresh_coalesced_total",
            "Refresh requests coalesced or rejected by single-flight execution lock.",
            label_names=(),
        )


_METRICS_INSTANCE: Optional[OperationalMetrics] = None


def get_operational_metrics() -> OperationalMetrics:
    """Return the global default operational metrics catalog."""
    global _METRICS_INSTANCE
    if _METRICS_INSTANCE is None:
        _METRICS_INSTANCE = OperationalMetrics()
    return _METRICS_INSTANCE
