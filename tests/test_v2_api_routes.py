"""Integration tests for V2 API routes: /api/alerts/health, /api/alerts/*, /api/incidents/*."""

import os
import unittest
from starlette.testclient import TestClient

from services.api.main import app
from services.api.database import seed_if_empty, get_connection


class TestV2ApiRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_if_empty(force=True)
        cls.client = TestClient(app)

    def test_get_alerts_health_default_window(self):
        """Verify GET /api/alerts/health returns valid AlertHealthMetrics."""
        resp = self.client.get("/api/alerts/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("window_seconds", data)
        self.assertIn("as_of_utc", data)
        self.assertIn("total_alerts", data)
        self.assertIn("critical_count", data)
        self.assertIn("alert_rate_per_hour", data)
        self.assertIn("priority_mix", data)
        self.assertIn("chattering_incidents", data)
        self.assertEqual(data["window_seconds"], 86400)

    def test_get_alerts_health_custom_params(self):
        """Verify GET /api/alerts/health respects query params."""
        resp = self.client.get("/api/alerts/health?window_seconds=3600&chatter_threshold=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["window_seconds"], 3600)

    def test_get_alert_by_id_and_acknowledge(self):
        """Verify retrieving an alert by ID and acknowledging it."""
        # First retrieve list of alerts to get a real ID
        list_resp = self.client.get("/api/alerts")
        self.assertEqual(list_resp.status_code, 200)
        items = list_resp.json()["items"]
        if items:
            alert_id = items[0]["id"]
            # Fetch by ID
            detail_resp = self.client.get(f"/api/alerts/{alert_id}")
            self.assertEqual(detail_resp.status_code, 200)

            # Acknowledge
            ack_resp = self.client.post(f"/api/alerts/{alert_id}/acknowledge")
            self.assertEqual(ack_resp.status_code, 200)
            self.assertTrue(ack_resp.json()["acknowledged"])

    def test_get_alert_not_found(self):
        """Verify non-existent alert returns 404."""
        resp = self.client.get("/api/alerts/NON_EXISTENT_ALERT_99999")
        self.assertEqual(resp.status_code, 404)

    def test_get_incidents_list(self):
        """Verify GET /api/incidents returns list."""
        resp = self.client.get("/api/incidents")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)

    def test_get_incident_not_found(self):
        """Verify non-existent incident returns 404."""
        resp = self.client.get("/api/incidents/INC-NOT-FOUND-999")
        self.assertEqual(resp.status_code, 404)
