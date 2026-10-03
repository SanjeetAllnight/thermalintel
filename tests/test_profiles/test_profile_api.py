"""Tests for read-only profile discovery API endpoints."""

import pytest
from starlette.testclient import TestClient

from services.api.main import app
from profiles.loader import set_active_profile, reset_active_profile


@pytest.fixture
def client():
    reset_active_profile()
    with TestClient(app) as test_client:
        yield test_client
    reset_active_profile()


class TestProfileApiEndpoints:
    """Verifies that profile discovery endpoints function correctly and read-only."""

    def test_get_current_profile_default(self, client):
        """GET /api/v1/profile returns the active wildfire profile metadata."""
        response = client.get("/api/v1/profile")
        assert response.status_code == 200
        data = response.json()

        assert "active_profile" in data
        assert "available_profiles" in data

        active = data["active_profile"]
        assert active["id"] == "wildfire"
        assert "Wildfire" in active["display_name"]
        assert active["version"] == "2.0.0"
        assert "NASA_FIRMS" in active["enabled_providers"]
        assert "VEGETATION_FIRE" in active["supported_classes"]

        available = data["available_profiles"]
        assert "wildfire" in available
        assert "industrial-safety" in available

    def test_list_all_profiles(self, client):
        """GET /api/v1/profiles lists metadata for all registered profiles."""
        response = client.get("/api/v1/profiles")
        assert response.status_code == 200
        data = response.json()

        assert data["active_profile_id"] == "wildfire"
        assert data["count"] >= 2
        
        ids = [p["id"] for p in data["profiles"]]
        assert "wildfire" in ids
        assert "industrial-safety" in ids

    def test_root_endpoint_reflects_active_profile(self, client):
        """GET / includes the active profile identifier."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()

        assert "active_profile" in data
        assert data["active_profile"] == "wildfire"

    def test_api_reflects_runtime_profile_switch(self, client):
        """Verify API output updates dynamically when active profile changes."""
        set_active_profile("industrial-safety")

        response = client.get("/api/v1/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["active_profile"]["id"] == "industrial-safety"
        assert "Industrial" in data["active_profile"]["display_name"]

        root_res = client.get("/")
        assert root_res.status_code == 200
        assert root_res.json()["active_profile"] == "industrial-safety"
