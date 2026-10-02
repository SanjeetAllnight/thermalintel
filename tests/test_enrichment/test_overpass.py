"""Tests for OpenStreetMap Overpass client, parser, and geospatial context derivation."""

from pathlib import Path
from unittest.mock import MagicMock
import httpx
import pytest

from services.api.enrichment.cache import EnrichmentCache
from services.api.geospatial.overpass import (
    FeatureCategory,
    OSMFeature,
    OverpassClient,
    build_overpass_bbox_query,
    build_overpass_radius_query,
    categorize_osm_tags,
    derive_geospatial_context,
    parse_overpass_response,
)


@pytest.fixture
def mock_overpass_response():
    """Realistic Overpass JSON fixture containing industrial, infrastructure, settlement, and park elements."""
    return {
        "version": 0.6,
        "elements": [
            {
                "type": "node",
                "id": 101,
                "lat": 38.7430,
                "lon": -122.8100,
                "tags": {
                    "name": "Geysers Geothermal Power Plant",
                    "power": "plant",
                    "plant:source": "geothermal"
                }
            },
            {
                "type": "way",
                "id": 202,
                "center": {"lat": 38.7450, "lon": -122.8080},
                "tags": {
                    "name": "PG&E 230kV Transmission Line",
                    "power": "line"
                }
            },
            {
                "type": "node",
                "id": 303,
                "lat": 38.7520,
                "lon": -122.8000,
                "tags": {
                    "name": "Cobb Mountain Community",
                    "place": "village"
                }
            },
            {
                "type": "relation",
                "id": 404,
                "center": {"lat": 38.7400, "lon": -122.8150},
                "tags": {
                    "name": "Boggs Mountain Demonstration State Forest",
                    "boundary": "protected_area",
                    "leisure": "nature_reserve"
                }
            }
        ]
    }


def test_build_overpass_queries():
    """Verify Overpass QL query string synthesis."""
    bbox_q = build_overpass_bbox_query(38.0, -123.0, 39.0, -122.0, timeout_sec=15)
    assert "[out:json][timeout:15];" in bbox_q
    assert "38.000000,-123.000000,39.000000,-122.000000" in bbox_q
    assert 'nwr["power"="plant"]' in bbox_q

    radius_q = build_overpass_radius_query(38.7421, -122.8105, radius_meters=3000.0)
    assert "(around:3000,38.742100,-122.810500)" in radius_q


def test_categorize_osm_tags():
    """Verify semantic tagging parser."""
    cat, ftype, name = categorize_osm_tags({"power": "plant", "plant:source": "gas", "name": "CoGen Plant"})
    assert cat == FeatureCategory.INDUSTRIAL
    assert "power_gas" in ftype
    assert name == "CoGen Plant"

    cat, ftype, name = categorize_osm_tags({"highway": "primary", "ref": "SR 175"})
    assert cat == FeatureCategory.INFRASTRUCTURE
    assert "highway_primary" in ftype
    assert "SR 175" in name

    cat, ftype, name = categorize_osm_tags({"place": "town", "name": "Healdsburg"})
    assert cat == FeatureCategory.SETTLEMENT
    assert ftype == "town"
    assert name == "Healdsburg"

    cat, ftype, name = categorize_osm_tags({"boundary": "national_park", "name": "Yosemite"})
    assert cat == FeatureCategory.PROTECTED_AREA
    assert name == "Yosemite"


def test_parse_overpass_response(mock_overpass_response):
    """Test normalizing raw Overpass JSON elements into typed OSMFeatures."""
    features = parse_overpass_response(mock_overpass_response)
    assert len(features) == 4

    categories = {f.category for f in features}
    assert FeatureCategory.INDUSTRIAL in categories
    assert FeatureCategory.INFRASTRUCTURE in categories
    assert FeatureCategory.SETTLEMENT in categories
    assert FeatureCategory.PROTECTED_AREA in categories

    # Verify coordinate extraction from way center
    way_feat = next(f for f in features if f.id == "way/202")
    assert way_feat.latitude == 38.7450
    assert way_feat.longitude == -122.8080


def test_overpass_client_mock_http_success(tmp_path: Path, mock_overpass_response):
    """Client queries Overpass via HTTP and writes response to cache."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_overpass_response
    mock_http.post.return_value = mock_resp

    client = OverpassClient(cache=cache, http_client=mock_http)
    features = client.fetch_features_radius(38.7421, -122.8105, radius_meters=5000.0)

    assert len(features) == 4
    assert mock_http.post.called

    # Subsequent call must hit cache without invoking mock_http again
    mock_http.post.reset_mock()
    cached_features = client.fetch_features_radius(38.7421, -122.8105, radius_meters=5000.0)
    assert len(cached_features) == 4
    assert not mock_http.post.called


def test_overpass_client_failure_fallback(tmp_path: Path, mock_overpass_response):
    """When live network fails, client recovers via stale cache or empty list without throwing."""
    cache = EnrichmentCache(cache_dir=tmp_path)

    # Pre-populate cache
    from services.api.enrichment.cache import generate_cache_key
    k = generate_cache_key("radius", lat=38.7421, lon=-122.8105, radius=5000.0)
    features_data = [f.model_dump() for f in parse_overpass_response(mock_overpass_response)]
    cache.set("osm", k, features_data, ttl_seconds=-10)  # Expired entry

    # Setup failing HTTP client
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.side_effect = httpx.ConnectTimeout("Network unreachable")

    client = OverpassClient(cache=cache, http_client=mock_http)
    features = client.fetch_features_radius(38.7421, -122.8105, radius_meters=5000.0)

    # Must recover from stale cache
    assert len(features) == 4


def test_overpass_client_complete_failure_returns_empty(tmp_path: Path):
    """When network fails and no cache exists, return empty list gracefully."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.side_effect = httpx.HTTPError("Server error 500")

    client = OverpassClient(cache=cache, http_client=mock_http)
    features = client.fetch_features_radius(38.7421, -122.8105)
    assert features == []


def test_derive_geospatial_context(mock_overpass_response):
    """Test full synthesis of GeospatialContext and industrial distance calculations."""
    features = parse_overpass_response(mock_overpass_response)
    target_lat = 38.7421
    target_lon = -122.8105

    context, metadata = derive_geospatial_context(target_lat, target_lon, features)

    # Nearest industrial plant was at (38.7430, -122.8100) ~ 109 meters
    assert metadata["nearest_industrial_facility"] == "Geysers Geothermal Power Plant"
    assert metadata["distance_to_industrial_meters"] is not None
    assert metadata["distance_to_industrial_meters"] < 200.0

    # Nearest infrastructure (transmission line)
    assert context.nearest_infrastructure == "PG&E 230kV Transmission Line"
    assert context.distance_to_infrastructure_meters is not None
    assert context.distance_to_infrastructure_meters < 600.0

    # Nearest settlement (Cobb village)
    assert context.nearest_settlement == "Cobb Mountain Community"
    assert context.distance_to_settlement_meters is not None
    assert 1000.0 < context.distance_to_settlement_meters < 1500.0

    # Protected area (Boggs Mountain ~ 460m away)
    assert context.is_protected_area is True
    assert context.protected_area_name == "Boggs Mountain Demonstration State Forest"


def test_derive_geospatial_context_invalid_coordinates():
    """Invalid coordinates return controlled fallback GeospatialContext without raising."""
    context, metadata = derive_geospatial_context(100.0, 200.0, [])
    assert context.land_cover == "unknown"
    assert context.nearest_infrastructure is None
    assert metadata["status"] == "unavailable"


def test_overpass_client_empty_success(tmp_path: Path):
    """Successful Overpass query that returns empty elements returns SUCCESS_EMPTY status."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"version": 0.6, "elements": []}
    mock_resp.url = "https://overpass-api.de/api/interpreter"
    mock_http.post.return_value = mock_resp

    from services.api.geospatial.overpass import OSMStatus

    client = OverpassClient(cache=cache, http_client=mock_http)
    result = client.query_radius(38.7421, -122.8105)

    assert result.status == OSMStatus.SUCCESS_EMPTY
    assert result.features == []
    assert result.is_cached is False
    assert result.provenance is not None
    assert result.provenance.provider == "OpenStreetMap"
    assert result.provenance.freshness_state.value == "fresh"


def test_overpass_client_provider_failure_status(tmp_path: Path):
    """When Overpass HTTP query fails and no cache exists, status is PROVIDER_FAILURE, not empty."""
    cache = EnrichmentCache(cache_dir=tmp_path)
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 504
    mock_resp.text = "Gateway Timeout"
    mock_http.post.return_value = mock_resp

    from services.api.geospatial.overpass import OSMStatus
    from services.api.geospatial.rate_limiter import OverpassRateLimiter

    limiter = OverpassRateLimiter(max_retries=1, min_spacing_seconds=0.01)
    client = OverpassClient(cache=cache, http_client=mock_http, rate_limiter=limiter)
    result = client.query_radius(38.7421, -122.8105)

    assert result.status == OSMStatus.PROVIDER_FAILURE
    assert result.features == []
    assert "Server Error" in (result.error_message or "")
    assert result.provenance is not None
    assert result.provenance.freshness_state.value == "unavailable"


def test_overpass_rate_limiter_retry_and_cooldown():
    """OverpassRateLimiter performs bounded retry on 429 and enters temporary cooldown."""
    from services.api.geospatial.rate_limiter import OverpassRateLimiter

    limiter = OverpassRateLimiter(max_retries=2, min_spacing_seconds=0.01, backoff_factor=1.0)
    call_count = 0

    def _failing_call():
        nonlocal call_count
        call_count += 1
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        resp.headers = {"Retry-After": "0"}
        return resp

    resp, err = limiter.execute_with_retry(_failing_call)
    assert resp is None
    assert "Too Many Requests" in (err or "")
    assert limiter.is_in_cooldown is True

    # Immediate next query is blocked by cooldown without network attempt
    resp2, err2 = limiter.execute_with_retry(_failing_call)
    assert resp2 is None
    assert "cooldown" in (err2 or "")


def test_protected_area_polygon_vs_degraded_centroid():
    """Verify that verified polygon containment vs centroid distance produces proper status."""
    from services.api.geospatial.overpass import derive_geospatial_v2, OSMStatus
    from services.api.geospatial.asset_store import GeoJSONAssetStore

    store = GeoJSONAssetStore(auto_load=True)

    # 1. Point strictly inside Boggs Mountain State Forest polygon: (38.7400, -122.8150)
    context_in, meta_in = derive_geospatial_context(38.7400, -122.8150, [], asset_store=store)
    assert context_in.is_protected_area is True
    assert meta_in["protected_area_geometry_status"] == "verified_polygon"

    v2_in = derive_geospatial_v2(38.7400, -122.8150, [], status=OSMStatus.SUCCESS_NON_EMPTY, asset_store=store)
    assert v2_in.is_protected_area.value is True
    assert v2_in.is_protected_area.status == "available"

    # 2. Point 800m away from centroid of a protected feature that lacks polygon geometry
    from services.api.geospatial.overpass import OSMFeature, FeatureCategory
    point_only_feature = [
        OSMFeature(
            id="node/isolated-reserve",
            name="Point Only Nature Sanctuary",
            category=FeatureCategory.PROTECTED_AREA,
            feature_type="nature_reserve",
            latitude=35.0000,
            longitude=-120.0000,
            tags={"leisure": "nature_reserve"}
        )
    ]
    # Query ~800m north: (35.0072, -120.0000)
    context_pt, meta_pt = derive_geospatial_context(35.0072, -120.0000, point_only_feature, asset_store=None)
    assert context_pt.is_protected_area is False  # Not claimed as verified containment
    assert meta_pt["protected_area_geometry_status"] == "degraded_centroid"

    v2_pt = derive_geospatial_v2(35.0072, -120.0000, point_only_feature, status=OSMStatus.SUCCESS_NON_EMPTY, asset_store=None)
    assert v2_pt.is_protected_area.status == "degraded"
    assert v2_pt.is_protected_area.value is None  # No fabricated containment
    assert "Centroid proximity only" in (v2_pt.is_protected_area.error_message or "")
