"""Spatial and geographic utility calculations for ThermalIntel enrichment.

Provides deterministic, zero-dependency spatial mathematics:
- High-precision Haversine great-circle distance (meters & kilometers)
- Dynamic bounding-box calculation with buffer expansions
- 16-point cardinal compass heading conversion
- Proximity indexing and nearest-neighbor selection
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

EARTH_RADIUS_METERS: float = 6371000.0
EARTH_RADIUS_KM: float = 6371.0

CARDINAL_DIRECTIONS: List[str] = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW"
]


def validate_coordinates(lat: float, lon: float) -> None:
    """Validate that coordinates fall within standard geographic bounds.
    
    Raises:
        ValueError: If latitude or longitude are outside valid limits.
    """
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(f"Coordinates must be finite numbers: lat={lat}, lon={lon}")
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude must be between -90.0 and 90.0, got: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude must be between -180.0 and 180.0, got: {lon}")


def haversine_distance_meters(
    lat1: float, lon1: float,
    lat2: float, lon2: float
) -> float:
    """Compute the great-circle distance between two points in meters.
    
    Uses the Haversine formula with numerical stability clamping.
    
    Args:
        lat1: Latitude of point 1 in decimal degrees.
        lon1: Longitude of point 1 in decimal degrees.
        lat2: Latitude of point 2 in decimal degrees.
        lon2: Longitude of point 2 in decimal degrees.
        
    Returns:
        Distance in meters.
    """
    validate_coordinates(lat1, lon1)
    validate_coordinates(lat2, lon2)

    # Identical coordinates short-circuit
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    sin_half_phi = math.sin(delta_phi / 2.0)
    sin_half_lambda = math.sin(delta_lambda / 2.0)

    a = (sin_half_phi * sin_half_phi +
         math.cos(phi1) * math.cos(phi2) * sin_half_lambda * sin_half_lambda)

    # Numerical precision guard: clamp between 0.0 and 1.0
    a = max(0.0, min(1.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_METERS * c


def haversine_distance_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float
) -> float:
    """Compute the great-circle distance between two points in kilometers."""
    return haversine_distance_meters(lat1, lon1, lat2, lon2) / 1000.0


def calculate_bounding_box(
    latitudes: Sequence[float],
    longitudes: Sequence[float],
    buffer_km: float = 5.0
) -> Tuple[float, float, float, float]:
    """Calculate an expanded bounding box enclosing the provided coordinates.
    
    Args:
        latitudes: Sequence of latitude floats.
        longitudes: Sequence of longitude floats.
        buffer_km: Geographic buffer padding in kilometers.
        
    Returns:
        Tuple of (min_lat, min_lon, max_lat, max_lon) in decimal degrees.
        
    Raises:
        ValueError: If the sequences are empty or mismatched in length.
    """
    if not latitudes or not longitudes or len(latitudes) != len(longitudes):
        raise ValueError("Latitude and longitude sequences must be non-empty and equal length.")

    for lat, lon in zip(latitudes, longitudes):
        validate_coordinates(lat, lon)

    min_lat = min(latitudes)
    max_lat = max(latitudes)
    min_lon = min(longitudes)
    max_lon = max(longitudes)

    # Approximate degree conversions
    # 1 degree latitude ~ 111.0 km
    lat_buffer_deg = buffer_km / 111.0

    # Longitude degree depends on latitude: ~ 111.0 * cos(lat) km
    mean_lat = (min_lat + max_lat) / 2.0
    cos_lat = math.cos(math.radians(mean_lat))
    # Protect against high latitude singularity near poles
    lon_deg_km = 111.0 * max(0.01, abs(cos_lat))
    lon_buffer_deg = buffer_km / lon_deg_km

    south = max(-90.0, min_lat - lat_buffer_deg)
    north = min(90.0, max_lat + lat_buffer_deg)
    west = max(-180.0, min_lon - lon_buffer_deg)
    east = min(180.0, max_lon + lon_buffer_deg)

    return (south, west, north, east)


def degrees_to_cardinal(degrees: float) -> str:
    """Convert an azimuth bearing in degrees to a 16-point cardinal compass string.
    
    Args:
        degrees: Azimuth direction in degrees [0.0, 360.0].
        
    Returns:
        One of: N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW.
    """
    if not math.isfinite(degrees):
        return "N/A"

    normalized = degrees % 360.0
    sector_size = 22.5
    index = int((normalized + (sector_size / 2.0)) / sector_size) % 16
    return CARDINAL_DIRECTIONS[index]


def find_nearest_feature(
    target_lat: float,
    target_lon: float,
    features: Sequence[Dict[str, Any]],
    max_distance_meters: Optional[float] = None
) -> Optional[Tuple[Dict[str, Any], float]]:
    """Locate the nearest feature from a collection to the target coordinate.
    
    Features must contain 'latitude' (or 'lat') and 'longitude' (or 'lon').
    
    Args:
        target_lat: Target point latitude.
        target_lon: Target point longitude.
        features: Sequence of feature dictionaries.
        max_distance_meters: Optional search radius cap in meters.
        
    Returns:
        Tuple of (nearest_feature_dict, distance_in_meters), or None if no feature found.
    """
    validate_coordinates(target_lat, target_lon)

    nearest_feature: Optional[Dict[str, Any]] = None
    min_distance = float("inf")

    for f in features:
        f_lat = f.get("latitude") if "latitude" in f else f.get("lat")
        f_lon = f.get("longitude") if "longitude" in f else f.get("lon")
        if f_lat is None or f_lon is None:
            continue
        try:
            dist = haversine_distance_meters(target_lat, target_lon, float(f_lat), float(f_lon))
        except (ValueError, TypeError):
            continue

        if max_distance_meters is not None and dist > max_distance_meters:
            continue

        if dist < min_distance:
            min_distance = dist
            nearest_feature = f

    if nearest_feature is None:
        return None

    return (nearest_feature, min_distance)


def filter_features_in_radius(
    target_lat: float,
    target_lon: float,
    features: Sequence[Dict[str, Any]],
    radius_meters: float
) -> List[Tuple[Dict[str, Any], float]]:
    """Filter and rank features within a specified radius in ascending distance order.
    
    Args:
        target_lat: Center latitude.
        target_lon: Center longitude.
        features: Sequence of candidate feature dictionaries.
        radius_meters: Search radius in meters.
        
    Returns:
        List of (feature_dict, distance_in_meters) sorted by distance.
    """
    validate_coordinates(target_lat, target_lon)

    results: List[Tuple[Dict[str, Any], float]] = []
    for f in features:
        f_lat = f.get("latitude") if "latitude" in f else f.get("lat")
        f_lon = f.get("longitude") if "longitude" in f else f.get("lon")
        if f_lat is None or f_lon is None:
            continue
        try:
            dist = haversine_distance_meters(target_lat, target_lon, float(f_lat), float(f_lon))
        except (ValueError, TypeError):
            continue

        if dist <= radius_meters:
            results.append((f, dist))

    results.sort(key=lambda item: item[1])
    return results
