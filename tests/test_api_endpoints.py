"""Integration test verifying frozen FastAPI endpoints with the data engine."""

import unittest
from starlette.testclient import TestClient

from services.api.main import app
from services.api.data.service import data_service
from services.api.schemas import DataMode, RiskLevel, SourceType


class TestApiFrozenContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure database has seeded data
        data_service.sync(force_sample=True)
        cls.client = TestClient(app)

    def test_get_health(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("data_mode", data)
        self.assertIn("services", data)

    def test_get_hotspots(self):
        resp = self.client.get("/api/hotspots?page=1&page_size=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 10)
        self.assertEqual(len(data["items"]), 10)
        self.assertGreaterEqual(data["total"], 10)

    def test_get_hotspots_filtering(self):
        resp = self.client.get("/api/hotspots?risk_level=critical")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["items"]:
            self.assertEqual(item["risk_level"], "critical")

    def test_get_hotspot_by_id_found(self):
        resp = self.client.get("/api/hotspots/VIIRS-SNPP-20261001-001")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("hotspot", data)
        self.assertEqual(data["hotspot"]["id"], "VIIRS-SNPP-20261001-001")
        self.assertIn("geospatial", data)
        self.assertIn("weather", data)

    def test_get_hotspot_by_id_not_found(self):
        resp = self.client.get("/api/hotspots/NONEXISTENT-HOTSPOT-ID")
        self.assertEqual(resp.status_code, 404)

    def test_get_summary(self):
        resp = self.client.get("/api/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["total_active_hotspots"], 10)
        self.assertIn("dominant_source", data)

    def test_get_alerts(self):
        resp = self.client.get("/api/alerts")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)

    def test_get_sources(self):
        resp = self.client.get("/api/sources")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("sources", data)

    def test_post_refresh(self):
        resp = self.client.post("/api/refresh", json={"force_sample": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["ingested_count"], 10)


if __name__ == "__main__":
    unittest.main()
