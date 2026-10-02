"""Tests for ThermalIntel Phase 0 Security Lockdown (CORS and Mutation Endpoint Safety)."""

import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.security import (
    get_cors_origins,
    get_admin_api_key,
    DEFAULT_DEV_ORIGINS,
)


class TestCorsHardening(unittest.TestCase):
    """Verify CORS configuration behavior and wildcard elimination."""

    def test_default_cors_origins(self):
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": ""}):
            origins = get_cors_origins()
            self.assertEqual(origins, DEFAULT_DEV_ORIGINS)
            self.assertNotIn("*", origins)

    def test_custom_cors_origins_parsing(self):
        custom = "https://app.thermalintel.org, https://console.thermalintel.org"
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": custom}):
            origins = get_cors_origins()
            self.assertEqual(
                origins,
                ["https://app.thermalintel.org", "https://console.thermalintel.org"],
            )
            self.assertNotIn("*", origins)

    def test_wildcard_is_strictly_rejected(self):
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://example.com, *"}):
            origins = get_cors_origins()
            self.assertEqual(origins, ["https://example.com"])
            self.assertNotIn("*", origins)

    def test_cors_preflight_headers_allowed_origin(self):
        client = TestClient(app)
        # http://localhost:3000 is an allowed origin
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertNotEqual(resp.headers.get("access-control-allow-origin"), "*")

    def test_cors_preflight_headers_disallowed_origin(self):
        client = TestClient(app)
        # Unauthorized origin should NOT get access-control-allow-origin header
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "https://malicious-site.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)


class TestMutationEndpointSafety(unittest.TestCase):
    """Verify mutation endpoint (POST /api/refresh) security guard and API key verification."""

    def setUp(self):
        self.client = TestClient(app)

    def test_mutation_allowed_in_dev_mode_without_key_configured(self):
        """In development mode (ADMIN_API_KEY empty/unset), requests succeed without X-API-Key."""
        with patch.dict(os.environ, {"ADMIN_API_KEY": ""}):
            resp = self.client.post("/api/refresh", json={"force_sample": True})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn(data["status"], ["success", "fallback_sample"])

    def test_mutation_rejected_401_when_key_configured_but_header_missing(self):
        """When ADMIN_API_KEY is configured, missing X-API-Key must return 401."""
        with patch.dict(os.environ, {"ADMIN_API_KEY": "super-secret-admin-token-123"}):
            resp = self.client.post("/api/refresh", json={"force_sample": True})
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Missing required 'X-API-Key' header", resp.json()["detail"])
            # Ensure key is not leaked in response
            self.assertNotIn("super-secret-admin-token-123", resp.text)

    def test_mutation_rejected_403_when_key_invalid(self):
        """When ADMIN_API_KEY is configured, wrong X-API-Key must return 403."""
        with patch.dict(os.environ, {"ADMIN_API_KEY": "super-secret-admin-token-123"}):
            resp = self.client.post(
                "/api/refresh",
                json={"force_sample": True},
                headers={"X-API-Key": "wrong-key"},
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("Invalid 'X-API-Key'", resp.json()["detail"])
            # Ensure key is not leaked in response
            self.assertNotIn("super-secret-admin-token-123", resp.text)

    def test_mutation_accepted_200_when_key_valid(self):
        """When ADMIN_API_KEY is configured, matching X-API-Key succeeds."""
        with patch.dict(os.environ, {"ADMIN_API_KEY": "super-secret-admin-token-123"}):
            resp = self.client.post(
                "/api/refresh",
                json={"force_sample": True},
                headers={"X-API-Key": "super-secret-admin-token-123"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn(data["status"], ["success", "fallback_sample"])


if __name__ == "__main__":
    unittest.main()
