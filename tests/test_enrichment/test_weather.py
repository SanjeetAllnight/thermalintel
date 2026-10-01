"""Tests for Open-Meteo weather client, Fire Weather Index, and telemetry normalization."""

from pathlib import Path
from unittest.mock import MagicMock
import httpx
import pytest

from services.api.enrichment.cache import EnrichmentCache
from services.api.weather.open_meteo import (
    OpenMeteoClient,
    WeatherResult,
    WeatherStatus,
    compute_fire_weather_index,
    create_unavailable_weather_context,
    generate_forecast_summary,
)


@pytest.fixture
def mock_open_meteo_response():
    """Realistic Open-Meteo API JSON response."""
    return {
        "latitude": 38.75,
        "longitude": -122.8125,
        "generationtime_ms": 0.045,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "elevation": 880.0,
        "current": {
            "time": "2026-10-01T08:45",
            "interval": 900,
            "temperature_2m": 29.4,
            "relative_humidity_2m": 14.0,
            "wind_speed_10m": 38.5,
            "wind_gusts_10m": 58.0,
            "wind_direction_10m": 42.0,
            "precipitation": 0.0,
            "weather_code": 1
        }
    }


def test_compute_fire_weather_index():
    """Test FWI danger proxy under critical and moderate conditions."""
    # Critical fire weather: hot, critically dry, gale gusts
    critical_fwi = compute_fire_weather_index(
        temperature_c=32.0,
        humidity_percent=12.0,
        wind_speed_kmh=40.0,
        wind_gust_kmh=60.0,
        precipitation_mm=0.0
    )
    assert critical_fwi >= 80.0

    # Low risk weather: cool, humid, calm, recent rain
    low_fwi = compute_fire_weather_index(
        temperature_c=14.0,
        humidity_percent=85.0,
        wind_speed_kmh=8.0,
        wind_gust_kmh=12.0,
        precipitation_mm=5.0
    )
    assert low_fwi <= 20.0


def test_forecast_summary_generation():
    """Test human-readable operational forecast summary formatting."""
    summary = generate_forecast_summary(
        temp_c=29.4,
        humidity=14.0,
        wind_kmh=38.5,
        wind_cardinal="NE",
        fwi=88.5
    )
    assert "Critical Fire Weather" in summary
    assert "29.4°C" in summary
    assert "NE" in summary


def test_open_meteo_client_mock_success(tmp_path: Path, mock_open_meteo_response):
    """Test successful Open-Meteo query, normalization, and caching."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_open_meteo_response
    mock_resp.url = "https://api.open-meteo.com/v1/forecast?..."
    mock_http.get.return_value = mock_resp

    client = OpenMeteoClient(cache=cache, http_client=mock_http)
    result = client.fetch_weather(38.7421, -122.8105)

    assert result.status == WeatherStatus.AVAILABLE
    ctx = result.context
    assert ctx.temperature_celsius == 29.4
    assert ctx.relative_humidity_percent == 14.0
    assert ctx.wind_speed_kmh == 38.5
    assert ctx.wind_gust_kmh == 58.0
    assert ctx.wind_direction_degrees == 42.0
    assert ctx.wind_direction_cardinal == "NE"
    assert ctx.fire_weather_index is not None
    assert ctx.fire_weather_index >= 70.0

    # Verify second query for nearby point in same ~1.1km grid uses cached value
    mock_http.get.reset_mock()
    # (38.7421 rounds to 38.74, -122.8105 rounds to -122.81)
    cached_result = client.fetch_weather(38.7424, -122.8103)
    assert cached_result.status == WeatherStatus.CACHED
    assert not mock_http.get.called


def test_open_meteo_client_failure_fallback(tmp_path: Path):
    """When network fails and no cache exists, return structured unavailable context without crashing."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.side_effect = httpx.ConnectTimeout("Open-Meteo down")

    client = OpenMeteoClient(cache=cache, http_client=mock_http)
    result = client.fetch_weather(38.7421, -122.8105)

    assert result.status == WeatherStatus.UNAVAILABLE
    assert result.context.forecast_summary == "Weather service unreachable"
    assert result.context.temperature_celsius == 0.0


def test_open_meteo_client_invalid_coordinates(tmp_path: Path):
    """Invalid coordinates return controlled unavailable status."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    client = OpenMeteoClient(cache=cache)

    result = client.fetch_weather(999.0, -122.8105)
    assert result.status == WeatherStatus.UNAVAILABLE
    assert "Invalid coordinates" in result.context.forecast_summary
