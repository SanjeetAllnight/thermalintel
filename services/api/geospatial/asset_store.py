"""Local static asset store for OpenStreetMap and GIS context.

Provides an in-process, file-backed GeoJSON asset representation for relatively static
OSM context (industrial sites, infrastructure, settlements, protected conservation areas).
Decouples thermal anomaly enrichment from live Overpass network queries, enabling:
- Sub-millisecond local spatial lookups via scipy.spatial.cKDTree
- Offline and demo operation
- Real polygon containment checks for conservation reserves
- Replaceable service interface for future database/GIS backends
"""

from abc import ABC, abstractmethod
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    from scipy.spatial import cKDTree
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from services.api.geospatial.overpass import FeatureCategory, OSMFeature
from services.api.geospatial.spatial import (
    haversine_distance_meters,
    latlon_to_cartesian_meters,
    point_in_geojson_geometry,
    validate_coordinates,
)

logger = logging.getLogger(__name__)

DEFAULT_ASSET_STORE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "geospatial"
    / "static_assets.geojson"
)

# Reference static assets for key operational demonstration regions
# 1. Sonoma County / The Geysers (Wildfire & Geothermal complex)
# 2. Houston Ship Channel (Industrial refining complex)
# 3. Central Valley / Fresno (Agricultural & interface zones)
DEFAULT_STATIC_ASSETS_GEOJSON: Dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        # Sonoma County / The Geysers
        {
            "type": "Feature",
            "id": "node/sonoma-ind-01",
            "properties": {
                "name": "Geysers Geothermal Power Plant",
                "category": "industrial",
                "feature_type": "power_plant",
                "tags": {"power": "plant", "plant:source": "geothermal", "operator": "Calpine"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-122.8100, 38.7430]
            }
        },
        {
            "type": "Feature",
            "id": "way/sonoma-infra-01",
            "properties": {
                "name": "PG&E 230kV Transmission Corridor",
                "category": "infrastructure",
                "feature_type": "power_line",
                "tags": {"power": "line", "voltage": "230000"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-122.8080, 38.7450]
            }
        },
        {
            "type": "Feature",
            "id": "way/sonoma-infra-02",
            "properties": {
                "name": "State Route 175",
                "category": "infrastructure",
                "feature_type": "highway_primary",
                "tags": {"highway": "primary", "ref": "SR 175"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-122.7950, 38.7550]
            }
        },
        {
            "type": "Feature",
            "id": "node/sonoma-set-01",
            "properties": {
                "name": "Cobb Mountain Community",
                "category": "settlement",
                "feature_type": "village",
                "tags": {"place": "village", "population": "1800"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-122.8000, 38.7520]
            }
        },
        {
            "type": "Feature",
            "id": "node/sonoma-set-02",
            "properties": {
                "name": "Middletown",
                "category": "settlement",
                "feature_type": "town",
                "tags": {"place": "town", "population": "1300"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-122.6150, 38.7520]
            }
        },
        # Boggs Mountain State Forest with actual polygon boundary coordinates
        {
            "type": "Feature",
            "id": "relation/sonoma-prot-01",
            "properties": {
                "name": "Boggs Mountain Demonstration State Forest",
                "category": "protected_area",
                "feature_type": "nature_reserve",
                "tags": {
                    "boundary": "protected_area",
                    "leisure": "nature_reserve",
                    "ownership": "state"
                }
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-122.8300, 38.7300],
                    [-122.8000, 38.7300],
                    [-122.8000, 38.7500],
                    [-122.8300, 38.7500],
                    [-122.8300, 38.7300]
                ]]
            }
        },
        # Houston Ship Channel
        {
            "type": "Feature",
            "id": "node/houston-ind-01",
            "properties": {
                "name": "Baytown Petrochemical Complex & Refinery",
                "category": "industrial",
                "feature_type": "refinery",
                "tags": {"man_made": "works", "industrial": "refinery"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-95.0120, 29.7450]
            }
        },
        {
            "type": "Feature",
            "id": "node/houston-ind-02",
            "properties": {
                "name": "Houston Ship Channel Flare Stack Cluster",
                "category": "industrial",
                "feature_type": "flare_stack",
                "tags": {"industrial": "flare_stack", "man_made": "works"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-95.1248, 29.7154]
            }
        },
        {
            "type": "Feature",
            "id": "node/houston-set-01",
            "properties": {
                "name": "Pasadena",
                "category": "settlement",
                "feature_type": "city",
                "tags": {"place": "city", "population": "150000"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-95.2091, 29.6911]
            }
        },
        # Central Valley / Fresno
        {
            "type": "Feature",
            "id": "node/fresno-set-01",
            "properties": {
                "name": "Fresno Agricultural Basin",
                "category": "settlement",
                "feature_type": "town",
                "tags": {"place": "town", "population": "25000"}
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-119.8214, 36.8122]
            }
        },
        {
            "type": "Feature",
            "id": "relation/sierra-nat-01",
            "properties": {
                "name": "Sierra National Forest Boundary",
                "category": "protected_area",
                "feature_type": "nature_reserve",
                "tags": {"boundary": "national_park", "natural": "wood"}
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-119.5000, 36.9000],
                    [-119.2000, 36.9000],
                    [-119.2000, 37.2000],
                    [-119.5000, 37.2000],
                    [-119.5000, 36.9000]
                ]]
            }
        }
    ]
}


class AssetStoreInterface(ABC):
    """Abstract interface defining operations for local static asset querying."""

    @abstractmethod
    def query_radius(
        self,
        lat: float,
        lon: float,
        radius_meters: float = 5000.0,
        categories: Optional[Sequence[str]] = None
    ) -> List[OSMFeature]:
        """Return all features within radius."""
        pass

    @abstractmethod
    def query_bbox(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        categories: Optional[Sequence[str]] = None
    ) -> List[OSMFeature]:
        """Return all features within bounding box."""
        pass

    @abstractmethod
    def find_nearest(
        self,
        lat: float,
        lon: float,
        category: Optional[str] = None,
        max_distance_meters: Optional[float] = None
    ) -> Optional[Tuple[OSMFeature, float]]:
        """Return nearest feature and distance in meters."""
        pass

    @abstractmethod
    def check_protected_area(
        self,
        lat: float,
        lon: float
    ) -> Tuple[bool, Optional[str], str]:
        """Check if coordinates intersect a protected conservation area.
        
        Returns:
            Tuple of (is_inside, area_name, geometry_status)
            where geometry_status is one of:
            - 'verified_polygon': real polygon containment test executed
            - 'degraded_centroid': centroid proximity only, exact boundary unavailable
            - 'none': no protected area nearby
        """
        pass


class GeoJSONAssetStore(AssetStoreInterface):
    """High-performance in-memory asset store indexed with scipy.spatial.cKDTree."""

    def __init__(
        self,
        file_path: Optional[Path] = None,
        auto_load: bool = True
    ):
        self.file_path = Path(file_path) if file_path else DEFAULT_ASSET_STORE_PATH
        self._raw_features: List[Dict[str, Any]] = []
        self._features: List[OSMFeature] = []
        self._geometries: List[Optional[Dict[str, Any]]] = []
        self._kd_tree: Optional[Any] = None
        self._cartesian_coords: Optional[np.ndarray] = None

        if auto_load:
            self.load()

    def load(self, source_path: Optional[Path] = None) -> int:
        """Load features from GeoJSON file or fall back to default reference collection."""
        path = Path(source_path) if source_path else self.file_path

        data: Optional[Dict[str, Any]] = None
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning("Failed to parse GeoJSON asset store from %s: %s", path, e)

        if data is None:
            data = DEFAULT_STATIC_ASSETS_GEOJSON

        return self.ingest_geojson(data)

    def save(self, target_path: Optional[Path] = None) -> bool:
        """Serialize current in-memory features to a GeoJSON file."""
        path = Path(target_path) if target_path else self.file_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            collection = {
                "type": "FeatureCollection",
                "features": self._raw_features
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(collection, f, indent=2)
            return True
        except Exception as e:
            logger.warning("Failed to save GeoJSON asset store to %s: %s", path, e)
            return False

    def ingest_geojson(self, data: Dict[str, Any]) -> int:
        """Ingest GeoJSON FeatureCollection into memory and rebuild spatial index."""
        if not isinstance(data, dict):
            return 0

        raw_list = data.get("features", [])
        if not isinstance(raw_list, list):
            return 0

        self._raw_features = []
        self._features = []
        self._geometries = []

        coords_3d: List[Tuple[float, float, float]] = []

        for item in raw_list:
            if not isinstance(item, dict):
                continue

            geom = item.get("geometry", {})
            props = item.get("properties", {})
            feat_id = str(item.get("id") or props.get("id", f"asset-{len(self._features)}"))

            # Extract representative lat/lon
            lat: Optional[float] = None
            lon: Optional[float] = None

            if geom.get("type") == "Point" and "coordinates" in geom:
                c = geom["coordinates"]
                lon, lat = float(c[0]), float(c[1])
            elif geom.get("type") in ("Polygon", "MultiPolygon") and "coordinates" in geom:
                # Use centroid / bbox mean for indexing
                try:
                    all_pts: List[Tuple[float, float]] = []
                    coords_structure = geom["coordinates"]
                    if geom["type"] == "Polygon":
                        all_pts = coords_structure[0]
                    else:
                        for poly in coords_structure:
                            all_pts.extend(poly[0])
                    lon = sum(p[0] for p in all_pts) / len(all_pts)
                    lat = sum(p[1] for p in all_pts) / len(all_pts)
                except Exception:
                    continue

            if lat is None or lon is None:
                continue

            try:
                validate_coordinates(lat, lon)
            except ValueError:
                continue

            cat_str = props.get("category", "other")
            try:
                category = FeatureCategory(cat_str)
            except ValueError:
                category = FeatureCategory.OTHER

            osm_feat = OSMFeature(
                id=feat_id,
                name=props.get("name", "Asset"),
                category=category,
                feature_type=props.get("feature_type", "asset"),
                latitude=lat,
                longitude=lon,
                tags=props.get("tags", {})
            )

            self._raw_features.append(item)
            self._features.append(osm_feat)
            self._geometries.append(geom if geom.get("type") in ("Polygon", "MultiPolygon") else None)
            coords_3d.append(latlon_to_cartesian_meters(lat, lon))

        # Build KD-tree index
        if HAS_SCIPY and coords_3d:
            self._cartesian_coords = np.array(coords_3d, dtype=np.float64)
            self._kd_tree = cKDTree(self._cartesian_coords)
        else:
            self._cartesian_coords = None
            self._kd_tree = None

        logger.debug("Ingested %d static geospatial assets into local store", len(self._features))
        return len(self._features)

    def query_radius(
        self,
        lat: float,
        lon: float,
        radius_meters: float = 5000.0,
        categories: Optional[Sequence[str]] = None
    ) -> List[OSMFeature]:
        """Query features within radius using KD-Tree or Haversine fallback."""
        validate_coordinates(lat, lon)
        if not self._features:
            return []

        cat_filter = set(categories) if categories else None
        results: List[OSMFeature] = []

        if self._kd_tree is not None:
            # Query KD-tree with Euclidean chord threshold
            # chord length for small angles: d_chord <= radius_meters
            target_pt = latlon_to_cartesian_meters(lat, lon)
            indices = self._kd_tree.query_ball_point(target_pt, r=radius_meters)
            for idx in indices:
                feat = self._features[idx]
                if cat_filter and feat.category.value not in cat_filter:
                    continue
                # Exact great-circle check to eliminate edge chord distortion
                dist = haversine_distance_meters(lat, lon, feat.latitude, feat.longitude)
                if dist <= radius_meters:
                    results.append(feat)
        else:
            for feat in self._features:
                if cat_filter and feat.category.value not in cat_filter:
                    continue
                dist = haversine_distance_meters(lat, lon, feat.latitude, feat.longitude)
                if dist <= radius_meters:
                    results.append(feat)

        return results

    def query_bbox(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        categories: Optional[Sequence[str]] = None
    ) -> List[OSMFeature]:
        """Query features within geographic bounding box."""
        validate_coordinates(south, west)
        validate_coordinates(north, east)

        cat_filter = set(categories) if categories else None
        results: List[OSMFeature] = []

        for feat in self._features:
            if cat_filter and feat.category.value not in cat_filter:
                continue
            if south <= feat.latitude <= north and west <= feat.longitude <= east:
                results.append(feat)

        return results

    def find_nearest(
        self,
        lat: float,
        lon: float,
        category: Optional[str] = None,
        max_distance_meters: Optional[float] = None
    ) -> Optional[Tuple[OSMFeature, float]]:
        """Locate closest feature, optionally constrained by category and max distance."""
        validate_coordinates(lat, lon)
        if not self._features:
            return None

        best_feat: Optional[OSMFeature] = None
        min_dist = float("inf")

        for feat in self._features:
            if category and feat.category.value != category:
                continue
            dist = haversine_distance_meters(lat, lon, feat.latitude, feat.longitude)
            if max_distance_meters is not None and dist > max_distance_meters:
                continue
            if dist < min_dist:
                min_dist = dist
                best_feat = feat

        if best_feat is None:
            return None
        return (best_feat, min_dist)

    def check_protected_area(
        self,
        lat: float,
        lon: float
    ) -> Tuple[bool, Optional[str], str]:
        """Determine if target coordinates lie inside a protected area or near one.
        
        Real polygon containment is used when polygon geometry is present.
        If only centroid data exists, returns explicit 'degraded_centroid'.
        """
        validate_coordinates(lat, lon)

        # 1. Search all protected area features
        protected_candidates: List[Tuple[int, OSMFeature]] = [
            (idx, f) for idx, f in enumerate(self._features)
            if f.category in (FeatureCategory.PROTECTED_AREA, FeatureCategory.NATURAL)
        ]

        if not protected_candidates:
            return (False, None, "none")

        # 2. Check polygon containment first
        for idx, feat in protected_candidates:
            geom = self._geometries[idx]
            if geom is not None:
                # Real polygon containment check
                if point_in_geojson_geometry(lat, lon, geom):
                    return (True, feat.name, "verified_polygon")

        # 3. If no polygon containment, inspect proximity to centroids
        # If within 1500m of a protected feature that lacks polygon geometry, report degraded
        for idx, feat in protected_candidates:
            geom = self._geometries[idx]
            dist = haversine_distance_meters(lat, lon, feat.latitude, feat.longitude)
            if dist <= 1500.0:
                if geom is None:
                    # Centroid proximity without polygon geometry -> explicitly degraded
                    return (False, feat.name, "degraded_centroid")

        return (False, None, "none")

    def count(self) -> int:
        """Total number of features in store."""
        return len(self._features)
