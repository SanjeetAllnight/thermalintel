"""Integration and verification tests for EnrichmentService."""

from pathlib import Path
from unittest.mock import MagicMock
import httpx
import pytest

from services.api.enrichment.cache import EnrichmentCache
from services.api.enrichment.models import EnrichmentResult, EnrichmentStatus
from services.api.enrichment.service import EnrichmentService
from services.api.geospatial.overpass import OSMFeature, OverpassClient
from services.api.history.recurrence import HistoricalRecurrenceAnalyzer
from services.api.schemas.hotspot import Hotspot
from services.api.weather.open_meteo import OpenMeteoClient


@pytest.fixture
def sample_realistic_hotspot() -> Hotspot:
    """Realistic Hotspot matching sample data from Phase 0."""
    return Hotspot(
        id="VIIRS-SNPP-20261001-001",
        latitude=38.7421,
        longitude=-122.8105,
        brightness=352.4,
        scan=0.38,
        track=0.36,
        acq_date="2026-10-01",
        acq_time="0845",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=298.4,
        frp=142.8,
        daynight="N",
        source_type="wildfire",
        risk_score=92.5,
        risk_level="critical",
        is_anomaly=True,
        cluster_id="CL-SONOMA-01",
        cluster_size=5,
        nearest_place="Geysers Basin, Sonoma County, CA",
        last_updated="2026-10-01T08:50:00Z"
    )


@pytest.fixture
def mock_overpass_features():
    """Mock pre-normalized OSM features."""
    return [
        OSMFeature(
            id="node/101",
            name="Geysers Geothermal Complex",
            category="industrial",
            feature_type="power_plant",
            latitude=38.7430,
            longitude=-122.8100,
            tags={"power": "plant"}
        ),
        OSMFeature(
            id="way/202",
            name="State Route 175",
            category="infrastructure",
            feature_type="highway_primary",
            latitude=38.7450,
            longitude=-122.8080,
            tags={"highway": "primary"}
        ),
        OSMFeature(
            id="node/303",
            name="Cobb Village",
            category="settlement",
            feature_type="village",
            latitude=38.7520,
            longitude=-122.8000,
            tags={"place": "village"}
        ),
    ]


@pytest.fixture
def mock_weather_response():
    """Mock Open-Meteo JSON payload."""
    return {
        "current": {
            "temperature_2m": 29.4,
            "relative_humidity_2m": 14.0,
            "wind_speed_10m": 38.5,
            "wind_gusts_10m": 58.0,
            "wind_direction_10m": 42.0,
            "precipitation": 0.0,
            "weather_code": 1
        }
    }


def test_complete_enrichment_realistic_hotspot(
    tmp_path: Path,
    sample_realistic_hotspot: Hotspot,
    mock_overpass_features,
    mock_weather_response
):
    """Verify complete end-to-end enrichment with all subsystems available."""
    cache = EnrichmentCache(cache_dir=tmp_path)

    # Mock Overpass Client
    mock_overpass = MagicMock(spec=OverpassClient)
    mock_overpass.fetch_features_radius.return_value = mock_overpass_features

    # Mock Weather HTTP
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_weather_response
    mock_resp.url = "https://api.open-meteo.com/v1/forecast"
    mock_http.get.return_value = mock_resp
    weather_client = OpenMeteoClient(cache=cache, http_client=mock_http)

    service = EnrichmentService(
        overpass_client=mock_overpass,
        weather_client=weather_client,
        cache=cache
    )

    prior_hotspots = [
        {
            "id": "PREV-01",
            "latitude": 38.7420,
            "longitude": -122.8104,
            "acq_date": "2026-09-30",
            "acq_time": "0845",
            "frp": 120.0
        }
    ]

    result: EnrichmentResult = service.enrich_hotspot(
        sample_realistic_hotspot,
        prior_hotspots=prior_hotspots
    )

    # Status checks
    assert result.status == EnrichmentStatus.COMPLETE
    assert result.hotspot_id == sample_realistic_hotspot.id
    assert result.latitude == sample_realistic_hotspot.latitude
    assert result.longitude == sample_realistic_hotspot.longitude

    # Geospatial checks
    assert result.geospatial.nearest_infrastructure == "State Route 175"
    assert result.geospatial.distance_to_infrastructure_meters is not None
    assert result.nearest_industrial_facility == "Geysers Geothermal Complex"
    assert result.distance_to_industrial_meters is not None
    assert result.distance_to_industrial_meters < 200.0

    # Weather checks
    assert result.weather.temperature_celsius == 29.4
    assert result.weather.relative_humidity_percent == 14.0
    assert result.weather.wind_speed_kmh == 38.5
    assert result.weather.wind_direction_cardinal == "NE"
    assert result.weather.fire_weather_index is not None
    assert result.weather.fire_weather_index >= 70.0

    # Historical checks
    assert result.historical.prior_detections_30d == 1
    assert result.historical.first_detected_date == "2026-09-30"
    assert result.repeated_activity is True

    # Interface checks for Phase 3 and Phase 4
    intel_kwargs = result.to_intelligence_kwargs(
        frp=sample_realistic_hotspot.frp,
        brightness=sample_realistic_hotspot.brightness
    )
    assert intel_kwargs["hotspot_id"] == sample_realistic_hotspot.id
    assert intel_kwargs["frp"] == 142.8
    assert intel_kwargs["wind_speed_kmh"] == 38.5
    assert intel_kwargs["relative_humidity_percent"] == 14.0
    assert intel_kwargs["temperature_celsius"] == 29.4

    incident_dict = result.to_incident_dict()
    assert "geospatial" in incident_dict
    assert "weather" in incident_dict
    assert "historical" in incident_dict


def test_batch_enrichment_bbox_optimization(
    tmp_path: Path,
    mock_overpass_features,
    mock_weather_response
):
    """Test batch enrichment verifying single bbox query for multiple clustered hotspots."""
    cache = EnrichmentCache(cache_dir=tmp_path)

    mock_overpass = MagicMock(spec=OverpassClient)
    mock_overpass.fetch_features_bbox.return_value = mock_overpass_features

    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_weather_response
    mock_resp.url = "https://api.open-meteo.com/v1/forecast"
    mock_http.get.return_value = mock_resp
    weather_client = OpenMeteoClient(cache=cache, http_client=mock_http)

    service = EnrichmentService(
        overpass_client=mock_overpass,
        weather_client=weather_client,
        cache=cache
    )

    hotspots = [
        {"id": "H1", "latitude": 38.7421, "longitude": -122.8105, "acq_date": "2026-10-01", "frp": 100.0},
        {"id": "H2", "latitude": 38.7468, "longitude": -122.8052, "acq_date": "2026-10-01", "frp": 118.0},
        {"id": "H3", "latitude": 38.7510, "longitude": -122.8010, "acq_date": "2026-10-01", "frp": 90.0},
    ]

    results = service.enrich_hotspots(hotspots, prior_hotspots=[])
    assert len(results) == 3
    assert [r.hotspot_id for r in results] == ["H1", "H2", "H3"]

    # Verify fetch_features_bbox was called ONCE for the whole batch
    assert mock_overpass.fetch_features_bbox.call_count == 1


def test_enrichment_resilience_external_api_failure(tmp_path: Path):
    """When external APIs fail, service returns PARTIAL or structured UNAVAILABLE without crashing."""
    cache = EnrichmentCache(cache_dir=tmp_path)

    # Overpass failing
    mock_overpass = MagicMock(spec=OverpassClient)
    mock_overpass.fetch_features_radius.side_effect = httpx.ConnectTimeout("Overpass timeout")

    # Weather failing
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.side_effect = httpx.HTTPError("Open-Meteo 503")
    weather_client = OpenMeteoClient(cache=cache, http_client=mock_http)

    service = EnrichmentService(
        overpass_client=mock_overpass,
        weather_client=weather_client,
        cache=cache
    )

    hotspot = {
        "id": "FAIL-HOTSPOT",
        "latitude": 38.7421,
        "longitude": -122.8105,
        "acq_date": "2026-10-01",
        "frp": 60.0
    }

    # Should not raise exception
    result = service.enrich_hotspot(hotspot, prior_hotspots=[])
    assert result.status in (EnrichmentStatus.PARTIAL, EnrichmentStatus.UNAVAILABLE)
    assert result.sources_status["osm"] == "unavailable"
    assert result.sources_status["weather"] == "unavailable"
    assert result.geospatial.land_cover == "unknown"
    assert result.weather.forecast_summary == "Weather service unreachable"


def test_enrichment_invalid_coordinates(tmp_path: Path):
    """Invalid coordinates return controlled UNAVAILABLE result without raising."""
    service = EnrichmentService(cache=EnrichmentCache(cache_dir=tmp_path))
    invalid_hotspot = {
        "id": "INVALID-COORD",
        "latitude": 999.0,
        "longitude": -122.8105,
        "acq_date": "2026-10-01"
    }

    result = service.enrich_hotspot(invalid_hotspot)
    assert result.status == EnrichmentStatus.UNAVAILABLE
    assert result.hotspot_id == "INVALID-COORD"
    assert result.sources_status["osm"] == "unavailable"
    assert result.sources_status["weather"] == "unavailable"
