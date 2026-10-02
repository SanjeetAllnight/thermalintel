"""Tests for TerrainProvider, elevation retrieval, slope calculation, and V2 terrain contracts."""

from pathlib import Path
from unittest.mock import MagicMock
import httpx
import pytest

from services.api.enrichment.cache import EnrichmentCache
from services.api.geospatial.terrain import TerrainProvider, TerrainResult
from services.api.schemas.v2.common import FreshnessState


def test_terrain_elevation_from_forecast_telemetry():
    """When elevation is already known from forecast telemetry, provider uses it directly."""
    provider = TerrainProvider()
    result = provider.fetch_terrain(38.7421, -122.8105, known_elevation=750.5, compute_slope=False)

    assert result.status == "available"
    assert result.elevation_meters == 750.5
    assert result.slope_degrees is None
    assert result.provenance is not None
    assert result.provenance.provider == "Open-Meteo"
    assert result.provenance.product == "Forecast_Telemetry_Elevation"


def test_terrain_elevation_api_live_success(tmp_path: Path):
    """When querying Open-Meteo Elevation API, returns parsed elevation and caches it."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"elevation": [680.2]}
    mock_http.get.return_value = mock_resp

    provider = TerrainProvider(cache=cache, http_client=mock_http)
    result = provider.fetch_terrain(38.7421, -122.8105)

    assert result.status == "available"
    assert result.elevation_meters == 680.2
    assert mock_http.get.called

    # Subsequent call hits disk cache
    mock_http.get.reset_mock()
    cached = provider.fetch_terrain(38.7421, -122.8105)
    assert cached.status == "available"
    assert cached.elevation_meters == 680.2
    assert not mock_http.get.called


def test_terrain_unavailable_no_phantom_values(tmp_path: Path):
    """When elevation API is unreachable and no cache exists, explicitly returns None, no fabricated 0.0."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.side_effect = httpx.ConnectTimeout("Elevation service down")

    provider = TerrainProvider(cache=cache, http_client=mock_http)
    result = provider.fetch_terrain(38.7421, -122.8105)

    assert result.status == "unavailable"
    assert result.elevation_meters is None
    assert result.slope_degrees is None
    assert result.is_available is False

    # Convert to V2 canonical contract
    v2_terrain = result.to_v2_enrichment()
    assert v2_terrain.elevation_meters.status == "unavailable"
    assert v2_terrain.elevation_meters.value is None  # NO PHANTOM ZERO
    assert v2_terrain.slope_degrees.status == "unavailable"
    assert v2_terrain.slope_degrees.value is None


def test_terrain_v2_conversion_available():
    """Verify TerrainResult conversion to V2 TerrainEnrichment with audit provenance."""
    result = TerrainResult(
        elevation_meters=850.0,
        slope_degrees=14.5,
        aspect_degrees=180.0,
        fuel_load_estimate="dense_coniferous",
        status="available"
    )

    v2_terrain = result.to_v2_enrichment()
    assert v2_terrain.elevation_meters.value == 850.0
    assert v2_terrain.elevation_meters.status == "available"
    assert v2_terrain.slope_degrees.value == 14.5
    assert v2_terrain.aspect_degrees is not None
    assert v2_terrain.aspect_degrees.value == 180.0
    assert v2_terrain.fuel_load_estimate.value == "dense_coniferous"

    prov = v2_terrain.elevation_meters.provenance
    assert prov.provider == "Open-Meteo_Terrain"
    assert prov.freshness_state == FreshnessState.FRESH


def test_terrain_invalid_coordinates():
    """Invalid coordinates return structured unavailable TerrainResult."""
    provider = TerrainProvider()
    result = provider.fetch_terrain(999.0, 999.0)
    assert result.status == "unavailable"
    assert result.elevation_meters is None
    assert "Invalid coordinates" in (result.error_message or "")
