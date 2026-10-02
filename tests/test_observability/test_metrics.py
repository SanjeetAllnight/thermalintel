"""Tests for operational metrics primitives and exporters."""

from services.observability.metrics.exporter import export_json, export_prometheus
from services.observability.metrics.operational import OperationalMetrics
from services.observability.metrics.registry import MetricsRegistry
from services.observability.metrics.types import Counter, Gauge, Histogram


def test_counter_monotonic_increment():
    counter = Counter("test_counter_total", "Test counter", label_names=("method", "status"))
    counter.inc(method="GET", status="200")
    counter.inc(3.0, method="GET", status="200")
    counter.inc(1.0, method="POST", status="201")

    assert counter.get(method="GET", status="200") == 4.0
    assert counter.get(method="POST", status="201") == 1.0
    assert counter.get(method="DELETE", status="404") == 0.0


def test_gauge_values():
    gauge = Gauge("test_gauge", "Test gauge", label_names=("region",))
    gauge.set(42.5, region="us-west")
    assert gauge.get(region="us-west") == 42.5

    gauge.inc(2.5, region="us-west")
    assert gauge.get(region="us-west") == 45.0

    gauge.dec(10.0, region="us-west")
    assert gauge.get(region="us-west") == 35.0


def test_histogram_buckets_and_timer():
    hist = Histogram(
        "test_latency_seconds",
        "Test latency",
        label_names=("endpoint",),
        buckets=(0.01, 0.05, 0.1, 1.0),
    )
    hist.observe(0.005, endpoint="/api/health")
    hist.observe(0.02, endpoint="/api/health")
    hist.observe(0.5, endpoint="/api/health")

    data = hist.collect()
    key = (("endpoint", "/api/health"),)
    entry = data[key]
    assert entry["count"] == 3
    assert entry["bucket_counts"][0.01] == 1  # 0.005 <= 0.01
    assert entry["bucket_counts"][0.05] == 2  # 0.005, 0.02 <= 0.05
    assert entry["bucket_counts"][0.1] == 2
    assert entry["bucket_counts"][1.0] == 3


def test_label_cardinality_sanitization():
    counter = Counter("bounded_counter", "Test bounded", label_names=("query",))
    # Huge string should be truncated to prevent unbounded memory growth
    huge_str = "x" * 200
    counter.inc(query=huge_str)
    collected = counter.collect()
    assert len(list(collected.keys())[0][0][1]) <= 64


def test_prometheus_exposition_format():
    reg = MetricsRegistry()
    c = reg.counter("requests_total", "Total requests", label_names=("method",))
    c.inc(method="GET")

    g = reg.gauge("active_jobs", "Active jobs", label_names=())
    g.set(3)

    output = export_prometheus(reg)
    assert "# HELP requests_total Total requests\n" in output
    assert "# TYPE requests_total counter\n" in output
    assert 'requests_total{method="GET"} 1\n' in output
    assert "# HELP active_jobs Active jobs\n" in output
    assert "active_jobs 3\n" in output


def test_json_export():
    reg = MetricsRegistry()
    c = reg.counter("events_count", "Total events", label_names=("type",))
    c.inc(type="login")

    json_data = export_json(reg)
    assert "events_count" in json_data
    assert json_data["events_count"]["type"] == "counter"
    assert json_data["events_count"]["samples"][0]["labels"] == {"type": "login"}
    assert json_data["events_count"]["samples"][0]["value"] == 1.0


def test_operational_metrics_catalog():
    reg = MetricsRegistry()
    ops = OperationalMetrics(reg)

    assert ops.http_requests_total.name == "http_requests_total"
    assert ops.provider_runs_total.name == "provider_runs_total"
    assert ops.observations_quarantined_total.name == "observations_quarantined_total"
    assert ops.enrichment_operations_total.name == "enrichment_operations_total"
    assert ops.intelligence_assessments_total.name == "intelligence_assessments_total"
    assert ops.incidents_transitions_total.name == "incidents_transitions_total"
    assert ops.alerts_total.name == "alerts_total"
    assert ops.scheduler_runs_total.name == "scheduler_runs_total"
    assert ops.refresh_coalesced_total.name == "refresh_coalesced_total"
