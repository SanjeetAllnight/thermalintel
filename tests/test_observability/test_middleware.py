"""Tests for ObservabilityMiddleware and path normalization."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.observability.integration import setup_observability
from services.observability.metrics.operational import get_operational_metrics
from services.observability.middleware import ObservabilityMiddleware, normalize_path


def test_normalize_path():
    assert normalize_path("/api/hotspots/HS-12345") == "/api/hotspots/{id}"
    assert normalize_path("/api/incidents/INC-20261002-0001") == "/api/incidents/{id}"
    assert normalize_path("/api/incidents/INC-20261002-0001/timeline") == "/api/incidents/{id}/timeline"
    assert normalize_path("/api/incidents/INC-20261002-0001/observations") == "/api/incidents/{id}/observations"
    assert normalize_path("/api/alerts/ALT-001/acknowledge") == "/api/alerts/{id}/acknowledge"
    assert normalize_path("/api/alerts/ALT-001") == "/api/alerts/{id}"
    assert normalize_path("/api/health") == "/api/health"
    assert normalize_path("/api/health/") == "/api/health"


def test_observability_middleware_request_id_and_metrics():
    app = FastAPI()
    setup_observability(app, log_format="json", include_routes=True)

    @app.get("/test-endpoint")
    def sample_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    # 1. Custom request ID passed via header
    res = client.get("/test-endpoint", headers={"X-Request-ID": "custom-req-123"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == "custom-req-123"

    # 2. Generated request ID when not passed
    res2 = client.get("/test-endpoint")
    assert res2.status_code == 200
    assert "X-Request-ID" in res2.headers
    assert res2.headers["X-Request-ID"].startswith("req_")

    # 3. Verify operational metrics recorded
    metrics = get_operational_metrics()
    count = metrics.http_requests_total.get(method="GET", status_code="200", endpoint="/test-endpoint")
    assert count >= 2

    # 4. Verify /metrics route works
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    assert "http_requests_total" in metrics_res.text
