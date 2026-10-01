"""Geospatial enrichment package for ThermalIntel.

Exports spatial mathematics utilities and Overpass OSM client.
"""

from .spatial import (
    haversine_distance_meters,
    haversine_distance_km,
    calculate_bounding_box,
    degrees_to_cardinal,
    find_nearest_feature,
    filter_features_in_radius,
    validate_coordinates,
)
from .overpass import (
    OverpassClient,
    OSMFeature,
    FeatureCategory,
    build_overpass_bbox_query,
    build_overpass_radius_query,
    parse_overpass_response,
    derive_geospatial_context,
)

__all__ = [
    "haversine_distance_meters",
    "haversine_distance_km",
    "calculate_bounding_box",
    "degrees_to_cardinal",
    "find_nearest_feature",
    "filter_features_in_radius",
    "validate_coordinates",
    "OverpassClient",
    "OSMFeature",
    "FeatureCategory",
    "build_overpass_bbox_query",
    "build_overpass_radius_query",
    "parse_overpass_response",
    "derive_geospatial_context",
]
