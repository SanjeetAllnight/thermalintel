"""ThermalIntel V1 Baseline Regression Snapshot Test Suite.

Ensures that V2 enhancements do not regress or silently alter verified V1 behavior,
API contract schemas, or demo dataset responses.
"""

import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.schemas import (
    HealthResponse,
    HotspotsResponse,
    IncidentDetail,
    SummaryResponse,
    AlertsResponse,
    SourcesResponse,
    RefreshResponse,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "v1_baseline"


class TestV1BaselineSnapshot(unittest.TestCase):
    """Regression suite comparing live API responses against frozen V1 baseline snapshots."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Ensure database is freshly seeded with demo dataset
        cls.client.post("/api/refresh", json={"force_sample": True})

        # Load golden fixtures
        with open(FIXTURES_DIR / "health_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_health = json.load(f)
        with open(FIXTURES_DIR / "hotspots_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_hotspots = json.load(f)
        with open(FIXTURES_DIR / "hotspot_detail_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_detail = json.load(f)
        with open(FIXTURES_DIR / "summary_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_summary = json.load(f)
        with open(FIXTURES_DIR / "alerts_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_alerts = json.load(f)
        with open(FIXTURES_DIR / "sources_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_sources = json.load(f)
        with open(FIXTURES_DIR / "refresh_baseline.json", "r", encoding="utf-8") as f:
            cls.fixture_refresh = json.load(f)

    def test_health_baseline(self):
        """Verify GET /api/health against V1 schema and baseline fixture."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = HealthResponse(**data)
        self.assertEqual(validated.status, "ok")
        self.assertEqual(validated.data_mode.value, "demo")

        # Key structure matches baseline
        self.assertEqual(set(data.keys()), set(self.fixture_health.keys()))
        self.assertEqual(set(data["services"].keys()), set(self.fixture_health["services"].keys()))

    def test_hotspots_baseline(self):
        """Verify GET /api/hotspots against V1 schema and baseline fixture."""
        resp = self.client.get("/api/hotspots")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = HotspotsResponse(**data)
        self.assertEqual(validated.data_mode.value, "demo")
        self.assertGreaterEqual(validated.total, len(self.fixture_hotspots["items"]))

        # Structure matches baseline
        self.assertEqual(set(data.keys()), set(self.fixture_hotspots.keys()))
        self.assertGreater(len(data["items"]), 0)

        # First item attributes
        first_item = data["items"][0]
        expected_keys = {
            "id", "latitude", "longitude", "brightness", "scan", "track",
            "acq_date", "acq_time", "satellite", "instrument", "confidence",
            "version", "bright_t31", "frp", "daynight", "source_type",
            "risk_score", "risk_level", "is_anomaly", "cluster_id",
            "cluster_size", "nearest_place", "last_updated",
        }
        self.assertTrue(expected_keys.issubset(set(first_item.keys())))

    def test_hotspot_detail_baseline(self):
        """Verify GET /api/hotspots/:id against V1 schema and baseline fixture."""
        first_id = self.fixture_detail["hotspot"]["id"]
        resp = self.client.get(f"/api/hotspots/{first_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = IncidentDetail(**data)
        self.assertEqual(validated.hotspot.id, first_id)
        self.assertEqual(validated.data_mode.value, "demo")

        # Structure matches baseline
        self.assertEqual(set(data.keys()), set(self.fixture_detail.keys()))
        self.assertIn("geospatial", data)
        self.assertIn("weather", data)
        self.assertIn("historical", data)
        self.assertIn("intelligence", data)
        self.assertIn("timeline", data)

    def test_hotspot_detail_not_found(self):
        """Verify GET /api/hotspots/:id returns 404 for invalid ID."""
        resp = self.client.get("/api/hotspots/NON_EXISTENT_ID_99999")
        self.assertEqual(resp.status_code, 404)

    def test_summary_baseline(self):
        """Verify GET /api/summary against V1 schema and baseline fixture."""
        resp = self.client.get("/api/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = SummaryResponse(**data)
        self.assertEqual(validated.data_mode.value, "demo")

        # Top-level KPI keys match baseline
        self.assertEqual(set(data.keys()), set(self.fixture_summary.keys()))
        self.assertGreaterEqual(validated.total_active_hotspots, 10)
        self.assertIn(validated.dominant_source.value, ["wildfire", "prescribed_burn", "industrial", "agricultural", "urban"])

    def test_alerts_baseline(self):
        """Verify GET /api/alerts against V1 schema and baseline fixture."""
        resp = self.client.get("/api/alerts")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = AlertsResponse(**data)
        self.assertEqual(set(data.keys()), set(self.fixture_alerts.keys()))
        self.assertGreaterEqual(validated.total, 1)

        # Check alert item structure
        first_alert = data["items"][0]
        alert_keys = {
            "id", "hotspot_id", "severity", "title", "message",
            "risk_score", "location_name", "latitude", "longitude",
            "timestamp", "is_acknowledged", "recommended_action", "tags"
        }
        self.assertTrue(alert_keys.issubset(set(first_alert.keys())))

    def test_sources_baseline(self):
        """Verify GET /api/sources against V1 schema and baseline fixture."""
        resp = self.client.get("/api/sources")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = SourcesResponse(**data)
        self.assertEqual(validated.data_mode.value, "demo")
        self.assertEqual(set(data.keys()), set(self.fixture_sources.keys()))
        self.assertGreater(len(validated.sources), 0)

    def test_refresh_baseline(self):
        """Verify POST /api/refresh against V1 schema and baseline fixture."""
        resp = self.client.post("/api/refresh", json={"force_sample": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Schema validation
        validated = RefreshResponse(**data)
        self.assertIn(validated.status, ["success", "fallback_sample"])
        self.assertEqual(validated.data_mode.value, "demo")
        self.assertEqual(set(data.keys()), set(self.fixture_refresh.keys()))
        self.assertGreaterEqual(validated.ingested_count, 10)


if __name__ == "__main__":
    unittest.main()
