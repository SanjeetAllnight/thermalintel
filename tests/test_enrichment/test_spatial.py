"""Tests for geospatial mathematics and spatial utility functions."""

import math
import pytest

from services.api.geospatial.spatial import (
    calculate_bounding_box,
    degrees_to_cardinal,
    filter_features_in_radius,
    find_nearest_feature,
    haversine_distance_km,
    haversine_distance_meters,
    validate_coordinates,
)


def test_haversine_identical_points():
    """Distance between identical coordinates must be exactly 0.0 meters."""
    dist = haversine_distance_meters(38.7421, -122.8105, 38.7421, -122.8105)
    assert dist == 0.0
    assert haversine_distance_km(38.7421, -122.8105, 38.7421, -122.8105) == 0.0


def test_haversine_known_benchmark_distances():
    """Verify distance against known geographic benchmarks."""
    # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ~ 343 km
    dist_km = haversine_distance_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 340.0 < dist_km < 348.0

    # San Francisco (37.7749, -122.4194) to Los Angeles (34.0522, -118.2437) ~ 559 km
    sf_la_dist = haversine_distance_km(37.7749, -122.4194, 34.0522, -118.2437)
    assert 550.0 < sf_la_dist < 570.0


def test_coordinate_validation():
    """Ensure invalid latitude or longitude raises ValueError."""
    with pytest.raises(ValueError, match="Latitude"):
        validate_coordinates(91.0, 0.0)

    with pytest.raises(ValueError, match="Latitude"):
        validate_coordinates(-90.1, 0.0)

    with pytest.raises(ValueError, match="Longitude"):
        validate_coordinates(0.0, 180.1)

    with pytest.raises(ValueError, match="Longitude"):
        validate_coordinates(0.0, -180.1)

    with pytest.raises(ValueError, match="finite"):
        validate_coordinates(float("nan"), 0.0)


def test_calculate_bounding_box():
    """Verify bounding box calculation with buffer."""
    lats = [38.7421, 38.7468]
    lons = [-122.8105, -122.8052]
    south, west, north, east = calculate_bounding_box(lats, lons, buffer_km=5.0)

    assert south < min(lats)
    assert north > max(lats)
    assert west < min(lons)
    assert east > max(lons)

    # South and North must remain valid degrees
    assert -90.0 <= south <= 90.0
    assert -90.0 <= north <= 90.0
    assert -180.0 <= west <= 180.0
    assert -180.0 <= east <= 180.0


def test_calculate_bounding_box_invalid():
    """Empty or mismatched coordinates must raise ValueError."""
    with pytest.raises(ValueError):
        calculate_bounding_box([], [])

    with pytest.raises(ValueError):
        calculate_bounding_box([38.0], [120.0, 121.0])


def test_degrees_to_cardinal():
    """Test 16-point cardinal compass headings."""
    assert degrees_to_cardinal(0.0) == "N"
    assert degrees_to_cardinal(360.0) == "N"
    assert degrees_to_cardinal(42.0) == "NE"
    assert degrees_to_cardinal(90.0) == "E"
    assert degrees_to_cardinal(160.0) == "SSE"
    assert degrees_to_cardinal(180.0) == "S"
    assert degrees_to_cardinal(225.0) == "SW"
    assert degrees_to_cardinal(270.0) == "W"
    assert degrees_to_cardinal(315.0) == "NW"
    assert degrees_to_cardinal(float("nan")) == "N/A"


def test_find_nearest_feature():
    """Test nearest feature selection and search radius cap."""
    target_lat = 38.7421
    target_lon = -122.8105

    features = [
        {"id": "feat_far", "name": "Distant Substation", "lat": 38.8000, "lon": -122.8105},
        {"id": "feat_near", "name": "Nearby Plant", "lat": 38.7430, "lon": -122.8100},
        {"id": "feat_mid", "name": "Midway Highway", "lat": 38.7500, "lon": -122.8105},
    ]

    nearest = find_nearest_feature(target_lat, target_lon, features)
    assert nearest is not None
    feat, dist = nearest
    assert feat["id"] == "feat_near"
    assert dist < 200.0  # Approx 100-110m

    # Test max distance filter: when max distance is smaller than closest feature
    capped = find_nearest_feature(target_lat, target_lon, features, max_distance_meters=50.0)
    assert capped is None


def test_filter_features_in_radius():
    """Test radius filtering and ascending distance ordering."""
    target_lat = 38.7421
    target_lon = -122.8105

    features = [
        {"id": "feat_far", "lat": 39.5000, "lon": -122.8105},  # > 80 km
        {"id": "feat_1km", "lat": 38.7500, "lon": -122.8105},  # ~ 880m
        {"id": "feat_200m", "lat": 38.7435, "lon": -122.8105}, # ~ 155m
    ]

    in_radius = filter_features_in_radius(target_lat, target_lon, features, radius_meters=1000.0)
    assert len(in_radius) == 2
    # Must be ordered by distance ascending
    assert in_radius[0][0]["id"] == "feat_200m"
    assert in_radius[1][0]["id"] == "feat_1km"
    assert in_radius[0][1] < in_radius[1][1]
