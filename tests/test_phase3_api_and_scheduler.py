"""Comprehensive integration and unit tests for Phase 3 API, Security, Refresh Orchestration, and Scheduler."""

import asyncio
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient

from services.api.main import app
from services.api.config import (
    ApiConfig,
    SchedulerConfig,
    SecurityConfig,
    get_api_config,
    reload_api_config,
    DEFAULT_INGESTION_INTERVAL_SECONDS,
)
from services.api.database import seed_if_empty
from services.api.security import (
    get_refresh_rate_limiter,
    sanitize_or_generate_request_id,
    verify_admin_key,
)
from services.api.scheduler.orchestrator import RefreshOrchestrator, get_refresh_orchestrator
from services.api.scheduler.scheduler import IngestionScheduler, get_scheduler
from services.api.routers.operational import register_metrics_collector
from services.api.schemas import RefreshResponse, DataMode


class TestPhase3ApiV1Routing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_if_empty(force=True)
        cls.client = TestClient(app)

    def test_root_info_contains_v1_and_probes(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["version"], "2.0.0")
        self.assertIn("GET /healthz", data["operational_probes"])
        self.assertIn("GET /readyz", data["operational_probes"])
        self.assertIn("GET /metrics", data["operational_probes"])
        self.assertEqual(data["v1_surface_prefix"], "/api/v1")
        self.assertIn("scheduler", data)

    def test_v1_health(self):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], "2.0.0")
        self.assertIn("data_mode", data)
        self.assertIn("services", data)

    def test_v1_hotspots_list(self):
        resp = self.client.get("/api/v1/hotspots?page=1&limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 10)
        self.assertEqual(len(data["items"]), 10)
        self.assertEqual(resp.headers.get("X-Total-Count"), str(data["total"]))
        self.assertEqual(resp.headers.get("X-Page"), "1")
        self.assertEqual(resp.headers.get("X-Page-Size"), "10")

    def test_v1_hotspot_detail_found(self):
        resp = self.client.get("/api/v1/hotspots/VIIRS-SNPP-20261001-001")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("hotspot", data)
        self.assertEqual(data["hotspot"]["id"], "VIIRS-SNPP-20261001-001")

    def test_v1_hotspot_detail_not_found(self):
        resp = self.client.get("/api/v1/hotspots/NON_EXISTENT_HOTSPOT_99999")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "not_found")
        self.assertIn("request_id", data["error"])

    def test_v1_incidents_list(self):
        resp = self.client.get("/api/v1/incidents?page=1&limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertIn("X-Total-Count", resp.headers)
        self.assertIn("X-Page", resp.headers)

    def test_v1_incident_detail_not_found(self):
        resp = self.client.get("/api/v1/incidents/INC-NOT-FOUND-999")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertEqual(data["error"]["code"], "not_found")

    def test_v1_alerts_health(self):
        resp = self.client.get("/api/v1/alerts/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("window_seconds", data)
        self.assertIn("alert_rate_per_hour", data)

    def test_v1_alerts_list(self):
        resp = self.client.get("/api/v1/alerts?page=1&limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("X-Total-Count", resp.headers)

    def test_v1_summary(self):
        resp = self.client.get("/api/v1/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_active_hotspots", data)

    def test_v1_sources(self):
        resp = self.client.get("/api/v1/sources")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("sources", data)

    def test_v1_scheduler_status(self):
        resp = self.client.get("/api/v1/scheduler/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("enabled", data)
        self.assertIn("running", data)
        self.assertIn("interval_seconds", data)


class TestOperationalProbes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_if_empty(force=True)
        cls.client = TestClient(app)

    def test_healthz_liveness(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "ThermalIntel API")
        self.assertGreaterEqual(data["uptime_seconds"], 0.0)
        self.assertIn("timestamp", data)

    def test_readyz_readiness(self):
        resp = self.client.get("/readyz")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["checks"]["database"], "ok")
        self.assertEqual(data["checks"]["schema"], "ok")

    def test_metrics_json(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["service"], "thermalintel")
        self.assertIn("uptime_seconds", data)
        self.assertIn("counts", data)
        self.assertIn("scheduler", data)

    def test_metrics_prometheus(self):
        resp = self.client.get("/metrics", headers={"Accept": "text/plain"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp.headers["content-type"])
        text = resp.text
        self.assertIn("# HELP thermalintel_uptime_seconds", text)
        self.assertIn("# TYPE thermalintel_uptime_seconds gauge", text)
        self.assertIn("thermalintel_hotspots_total", text)

    def test_metrics_custom_collector_hook(self):
        def sample_collector():
            return {"custom_metric_pipeline": 100.0}

        register_metrics_collector(sample_collector)
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("observability", data)
        self.assertEqual(data["observability"]["custom_metric_pipeline"], 100.0)


class TestRequestIdsAndStructuredErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_if_empty(force=True)
        cls.client = TestClient(app)

    def test_request_id_generated_when_missing(self):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        req_id = resp.headers.get("X-Request-ID")
        self.assertTrue(req_id and req_id.startswith("req-"))
        self.assertEqual(resp.headers.get("X-Correlation-ID"), req_id)

    def test_request_id_preserved_when_valid(self):
        custom_id = "trusted-audit-trace-uuid-12345"
        resp = self.client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Request-ID"), custom_id)
        self.assertEqual(resp.headers.get("X-Correlation-ID"), custom_id)

    def test_request_id_sanitized_when_malformed(self):
        malformed = "../../../etc/passwd; DROP TABLE"
        resp = self.client.get("/api/v1/health", headers={"X-Request-ID": malformed})
        self.assertEqual(resp.status_code, 200)
        req_id = resp.headers.get("X-Request-ID")
        self.assertNotEqual(req_id, malformed)
        self.assertTrue(req_id.startswith("req-"))

    def test_structured_error_shape_on_404(self):
        resp = self.client.get("/api/v1/hotspots/UNKNOWN-HOTSPOT-XYZ")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        # Verify backward compatibility
        self.assertIn("detail", data)
        # Verify structured error
        self.assertIn("error", data)
        err = data["error"]
        self.assertEqual(err["code"], "not_found")
        self.assertIn("UNKNOWN-HOTSPOT-XYZ", err["message"])
        self.assertIn("request_id", err)
        self.assertEqual(err["request_id"], resp.headers.get("X-Request-ID"))
        self.assertIn("timestamp", err)

    def test_structured_error_on_validation_failure(self):
        # min_frp must be >= 0.0
        resp = self.client.get("/api/v1/hotspots?min_frp=-10.5")
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "invalid_request")
        self.assertIn("validation_errors", data["error"]["details"])

    def test_no_secrets_leaked_in_errors(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "super_secret_production_key_xyz"}):
            resp = self.client.post("/api/v1/refresh", headers={"X-API-Key": "wrong_key"})
            self.assertEqual(resp.status_code, 403)
            self.assertNotIn("super_secret_production_key_xyz", resp.text)


class TestPaginationHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_if_empty(force=True)
        cls.client = TestClient(app)

    def test_hotspots_pagination_defaults(self):
        resp = self.client.get("/api/v1/hotspots")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 50)

    def test_hotspots_pagination_custom(self):
        resp = self.client.get("/api/v1/hotspots?page=2&limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 5)
        self.assertEqual(len(data["items"]), 5)

    def test_hotspots_invalid_page_negative(self):
        resp = self.client.get("/api/v1/hotspots?page=0")
        self.assertIn(resp.status_code, [400, 422])
        data = resp.json()
        self.assertEqual(data["error"]["code"], "invalid_request")

    def test_hotspots_invalid_limit_too_large(self):
        resp = self.client.get("/api/v1/hotspots?page=1&page_size=9999")
        self.assertIn(resp.status_code, [400, 422])
        data = resp.json()
        self.assertEqual(data["error"]["code"], "invalid_request")

    def test_incidents_pagination_slicing(self):
        resp = self.client.get("/api/v1/incidents?page=1&limit=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertLessEqual(len(data), 2)
        self.assertEqual(resp.headers.get("X-Page"), "1")
        self.assertEqual(resp.headers.get("X-Limit"), "2")


class TestRefreshHardeningAndSingleFlight(unittest.TestCase):
    def setUp(self):
        seed_if_empty(force=True)
        self.client = TestClient(app)
        get_refresh_rate_limiter().reset()

    def tearDown(self):
        limiter = get_refresh_rate_limiter()
        limiter.max_requests = 1000
        limiter.reset()

    def test_refresh_authenticated_success(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "secret-key-123"}):
            resp = self.client.post(
                "/api/v1/refresh",
                json={"force_sample": True},
                headers={"X-API-Key": "secret-key-123"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn(data["status"], ["success", "fallback_sample"])
            self.assertGreaterEqual(data["ingested_count"], 1)

    def test_refresh_missing_key_401(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "secret-key-123"}):
            resp = self.client.post("/api/v1/refresh", json={"force_sample": True})
            self.assertEqual(resp.status_code, 401)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "authentication_failure")

    def test_refresh_invalid_key_403(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "secret-key-123"}):
            resp = self.client.post(
                "/api/v1/refresh",
                json={"force_sample": True},
                headers={"X-API-Key": "wrong-key"},
            )
            self.assertEqual(resp.status_code, 403)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "authorization_failure")

    def test_refresh_fail_closed_in_production(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "ADMIN_API_KEY": ""}):
            resp = self.client.post("/api/v1/refresh", json={"force_sample": True})
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "internal_failure")

    def test_refresh_rate_limiting_429(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": ""}):
            # Set rate limit to 2 calls
            limiter = get_refresh_rate_limiter()
            limiter.max_requests = 2
            limiter.window_seconds = 60

            # 1st call: OK
            resp1 = self.client.post("/api/v1/refresh", json={"force_sample": True})
            self.assertEqual(resp1.status_code, 200)

            # 2nd call: OK
            resp2 = self.client.post("/api/v1/refresh", json={"force_sample": True})
            self.assertEqual(resp2.status_code, 200)

            # 3rd call: Rate limited (429)
            resp3 = self.client.post("/api/v1/refresh", json={"force_sample": True})
            self.assertEqual(resp3.status_code, 429)
            data = resp3.json()
            self.assertEqual(data["error"]["code"], "rate_limited")
            self.assertIn("Retry-After", resp3.headers)

    def test_refresh_single_flight_execution(self):
        """Simulate concurrent calls to execute_refresh and ensure single underlying invocation."""
        orchestrator = RefreshOrchestrator()
        sync_mock = MagicMock()
        sync_mock.return_value = RefreshResponse(
            status="success",
            message="Single flight test sync",
            ingested_count=10,
            data_mode=DataMode.DEMO,
            timestamp="2026-10-03T00:00:00Z",
            execution_time_seconds=0.05,
        )
        orchestrator._data_service.sync = sync_mock

        async def run_concurrent():
            # Launch 4 concurrent refresh calls
            results = await asyncio.gather(
                orchestrator.execute_refresh(force_sample=True, trigger="test1"),
                orchestrator.execute_refresh(force_sample=True, trigger="test2"),
                orchestrator.execute_refresh(force_sample=True, trigger="test3"),
                orchestrator.execute_refresh(force_sample=True, trigger="test4"),
            )
            return results

        results = asyncio.run(run_concurrent())
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertEqual(r.status, "success")
            self.assertEqual(r.ingested_count, 10)
        # Ensure underlying sync was called only ONCE!
        self.assertEqual(sync_mock.call_count, 1)

    def test_refresh_failure_safety_no_crash(self):
        """Simulate an unexpected sync error and verify safe recovery response."""
        orchestrator = RefreshOrchestrator()
        sync_mock = MagicMock(side_effect=RuntimeError("Simulated FIRMS network partition"))
        orchestrator._data_service.sync = sync_mock

        async def run():
            return await orchestrator.execute_refresh(force_sample=True, trigger="failure_test")

        res = asyncio.run(run())
        self.assertEqual(res.status, "fallback_sample")
        self.assertIn("fallback active", res.message)


class TestSchedulerBehaviorAndLifecycle(unittest.TestCase):
    def test_scheduler_disabled_by_default(self):
        cfg = SchedulerConfig(enabled=False, interval_seconds=300.0)
        scheduler = IngestionScheduler(config=cfg)
        started = asyncio.run(scheduler.start())
        self.assertFalse(started)
        self.assertFalse(scheduler.is_running)

    def test_scheduler_interval_validation_clamp_non_positive(self):
        # Non-positive interval must be clamped or safely defaulted
        with patch.dict(os.environ, {"INGESTION_ENABLED": "true", "INGESTION_INTERVAL_SECONDS": "-10"}):
            cfg = SchedulerConfig.from_env()
            self.assertEqual(cfg.interval_seconds, DEFAULT_INGESTION_INTERVAL_SECONDS)

        with patch.dict(os.environ, {"INGESTION_ENABLED": "true", "INGESTION_INTERVAL_SECONDS": "2"}):
            cfg = SchedulerConfig.from_env()
            self.assertGreaterEqual(cfg.interval_seconds, 5.0)

    def test_scheduler_startup_and_graceful_shutdown(self):
        cfg = SchedulerConfig(enabled=True, interval_seconds=10.0)
        scheduler = IngestionScheduler(config=cfg)

        async def run_lifecycle():
            started = await scheduler.start()
            self.assertTrue(started)
            self.assertTrue(scheduler.is_running)

            # Duplicate start must be rejected
            dup = await scheduler.start()
            self.assertFalse(dup)

            # Graceful shutdown
            await scheduler.stop(timeout=1.0)
            self.assertFalse(scheduler.is_running)

        asyncio.run(run_lifecycle())

    def test_scheduler_exception_resilience(self):
        """Ensure exceptions inside the scheduler worker loop do not kill the loop or crash the process."""
        cfg = SchedulerConfig(enabled=True, interval_seconds=0.05)
        orchestrator_mock = MagicMock()
        orchestrator_mock.execute_refresh = AsyncMock(side_effect=Exception("Transient satellite outage"))
        scheduler = IngestionScheduler(config=cfg, orchestrator=orchestrator_mock)

        async def test_resilience():
            await scheduler.start()
            # Let loop trigger at least 2 iterations
            await asyncio.sleep(0.15)
            status = scheduler.get_status()
            self.assertGreaterEqual(status["run_count"], 1)
            self.assertGreaterEqual(status["failure_count"], 1)
            self.assertEqual(status["last_status"], "error")
            self.assertTrue(scheduler.is_running)
            await scheduler.stop()

        asyncio.run(test_resilience())

    def test_scheduler_and_manual_refresh_collision(self):
        """Ensure that when a scheduled run and a manual refresh trigger concurrently, single-flight shares the run."""
        orchestrator = RefreshOrchestrator()
        sync_mock = MagicMock()
        sync_mock.return_value = RefreshResponse(
            status="success",
            message="Collision test sync",
            ingested_count=5,
            data_mode=DataMode.DEMO,
            timestamp="2026-10-03T00:00:00Z",
            execution_time_seconds=0.02,
        )
        orchestrator._data_service.sync = sync_mock

        async def test_collision():
            # Trigger manual and scheduler concurrently
            manual_task = orchestrator.execute_refresh(trigger="manual")
            scheduler_task = orchestrator.execute_refresh(trigger="scheduler")
            res_manual, res_scheduler = await asyncio.gather(manual_task, scheduler_task)
            self.assertEqual(res_manual.status, "success")
            self.assertEqual(res_scheduler.status, "success")
            # Ingestion only executed once
            self.assertEqual(sync_mock.call_count, 1)

        asyncio.run(test_collision())


if __name__ == "__main__":
    unittest.main()
