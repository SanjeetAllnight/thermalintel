"""OpenStreetMap / Overpass API client and geospatial feature extractor.

Features:
- Optimized regional bounding-box and radius queries
- Categorized parsing: industrial facilities, infrastructure, settlements, protected areas
- Local Haversine distance computations
- Resilient failure recovery: HTTP errors, timeouts, or malformed payloads return
  structured empty context rather than crashing
- File-backed caching integration via EnrichmentCache
"""

import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.api.enrichment.cache import EnrichmentCache
    from services.api.geospatial.asset_store import AssetStoreInterface
from services.api.geospatial.spatial import (
    degrees_to_cardinal,
    filter_features_in_radius,
    find_nearest_feature,
    haversine_distance_meters,
    point_in_geojson_geometry,
    validate_coordinates,
)
from services.api.schemas.incident import GeospatialContext
from services.api.schemas.v2.common import FreshnessState, Provenance, now_utc_iso
from services.api.schemas.v2.enrichment import EnrichmentDatum, GeospatialEnrichment

logger = logging.getLogger(__name__)

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_SEARCH_RADIUS_METERS = 5000.0
DEFAULT_TIMEOUT_SECONDS = 25.0


class OSMStatus(str, Enum):
    SUCCESS_NON_EMPTY = "successful_non_empty"
    SUCCESS_EMPTY = "successful_empty"
    STALE_CACHE = "stale_cache"
    UNAVAILABLE = "unavailable"
    PROVIDER_FAILURE = "provider_failure"


class OverpassResult(BaseModel):
    """Rich container for Overpass features, status semantics, and audit provenance."""
    features: List["OSMFeature"] = Field(default_factory=list)
    status: OSMStatus = Field(default=OSMStatus.SUCCESS_EMPTY)
    error_message: Optional[str] = None
    is_cached: bool = False
    is_stale: bool = False
    source_url: Optional[str] = None
    provenance: Optional[Provenance] = None


class FeatureCategory(str, Enum):
    INDUSTRIAL = "industrial"
    INFRASTRUCTURE = "infrastructure"
    SETTLEMENT = "settlement"
    PROTECTED_AREA = "protected_area"
    NATURAL = "natural"
    OTHER = "other"


class OSMFeature(BaseModel):
    """Normalized OpenStreetMap geospatial feature."""
    id: str
    name: str
    category: FeatureCategory
    feature_type: str
    latitude: float
    longitude: float
    tags: Dict[str, str] = Field(default_factory=dict)


def build_overpass_bbox_query(
    south: float,
    west: float,
    north: float,
    east: float,
    timeout_sec: int = 25
) -> str:
    """Build an Overpass QL query string for a geographic bounding box."""
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    return f"""
    [out:json][timeout:{timeout_sec}];
    (
      // Industrial Facilities
      nwr["landuse"="industrial"]({bbox});
      nwr["man_made"="works"]({bbox});
      nwr["industrial"]({bbox});
      nwr["power"="plant"]({bbox});
      nwr["power"="generator"]({bbox});

      // Critical Infrastructure
      nwr["power"="substation"]({bbox});
      nwr["power"="line"]({bbox});
      nwr["pipeline"]({bbox});
      way["highway"~"^(motorway|trunk|primary|secondary)$"]({bbox});

      // Settlements
      node["place"~"^(city|town|village|suburb|hamlet)$"]({bbox});

      // Protected Areas & Forests
      nwr["boundary"="national_park"]({bbox});
      nwr["boundary"="protected_area"]({bbox});
      nwr["leisure"="nature_reserve"]({bbox});
      nwr["landuse"="forest"]({bbox});
      nwr["natural"="wood"]({bbox});
    );
    out center tags;
    """


def build_overpass_radius_query(
    lat: float,
    lon: float,
    radius_meters: float = DEFAULT_SEARCH_RADIUS_METERS,
    timeout_sec: int = 25
) -> str:
    """Build an Overpass QL query string centered at a coordinate with search radius."""
    rad = int(radius_meters)
    around = f"(around:{rad},{lat:.6f},{lon:.6f})"
    return f"""
    [out:json][timeout:{timeout_sec}];
    (
      // Industrial
      nwr["landuse"="industrial"]{around};
      nwr["man_made"="works"]{around};
      nwr["industrial"]{around};
      nwr["power"="plant"]{around};
      nwr["power"="generator"]{around};

      // Infrastructure
      nwr["power"="substation"]{around};
      nwr["power"="line"]{around};
      nwr["pipeline"]{around};
      way["highway"~"^(motorway|trunk|primary|secondary)$"]{around};

      // Settlements
      node["place"~"^(city|town|village|suburb|hamlet)$"]{around};

      // Protected & Forest
      nwr["boundary"="national_park"]{around};
      nwr["boundary"="protected_area"]{around};
      nwr["leisure"="nature_reserve"]{around};
      nwr["landuse"="forest"]{around};
      nwr["natural"="wood"]{around};
    );
    out center tags;
    """


def categorize_osm_tags(tags: Dict[str, str]) -> Tuple[FeatureCategory, str, str]:
    """Inspect OSM element tags to derive category, feature type, and descriptive name.
    
    Returns:
        Tuple of (FeatureCategory, feature_type, display_name).
    """
    name = tags.get("name") or tags.get("description") or ""

    # 1. Industrial
    if tags.get("landuse") == "industrial":
        ind_type = tags.get("industrial") or "industrial_complex"
        return FeatureCategory.INDUSTRIAL, ind_type, name or f"Industrial Facility ({ind_type})"
    if tags.get("man_made") in ("works", "refinery", "gasometer"):
        return FeatureCategory.INDUSTRIAL, tags.get("man_made", "works"), name or "Industrial Works"
    if "industrial" in tags:
        return FeatureCategory.INDUSTRIAL, tags["industrial"], name or f"Industrial ({tags['industrial']})"
    if tags.get("power") in ("plant", "generator"):
        source = tags.get("generator:source") or tags.get("plant:source") or "energy"
        return FeatureCategory.INDUSTRIAL, f"power_{source}", name or f"Power Generation Plant ({source})"

    # 2. Critical Infrastructure
    if tags.get("power") in ("substation", "line", "minor_line", "switch"):
        ptype = tags["power"]
        return FeatureCategory.INFRASTRUCTURE, f"power_{ptype}", name or f"Power {ptype.title()}"
    if "highway" in tags:
        hw = tags["highway"]
        ref = tags.get("ref", "")
        disp = f"{ref} ({name})" if ref and name else (name or ref or f"Highway ({hw})")
        return FeatureCategory.INFRASTRUCTURE, f"highway_{hw}", disp
    if "pipeline" in tags:
        ptype = tags.get("substance", "pipeline")
        return FeatureCategory.INFRASTRUCTURE, "pipeline", name or f"Pipeline ({ptype})"

    # 3. Settlements
    if "place" in tags:
        place_type = tags["place"]
        return FeatureCategory.SETTLEMENT, place_type, name or f"Settlement ({place_type})"

    # 4. Protected Areas & Forest
    if tags.get("boundary") in ("national_park", "protected_area"):
        return FeatureCategory.PROTECTED_AREA, "protected_area", name or "Protected Conservation Area"
    if tags.get("leisure") == "nature_reserve":
        return FeatureCategory.PROTECTED_AREA, "nature_reserve", name or "Nature Reserve"
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return FeatureCategory.NATURAL, "forest", name or "Forest / Woodland Parcel"

    return FeatureCategory.OTHER, "unknown", name or "Geographic Feature"


def parse_overpass_response(data: Dict[str, Any]) -> List[OSMFeature]:
    """Parse raw Overpass JSON response into normalized OSMFeature objects.
    
    Handles nodes (lat/lon) and ways/relations (center.lat/center.lon).
    """
    if not isinstance(data, dict):
        return []

    elements = data.get("elements", [])
    if not isinstance(elements, list):
        return []

    features: List[OSMFeature] = []

    for el in elements:
        if not isinstance(el, dict):
            continue

        el_type = el.get("type", "node")
        el_id = str(el.get("id", ""))
        tags = el.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}

        # Resolve coordinate
        lat: Optional[float] = None
        lon: Optional[float] = None

        if el_type == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center")
            if isinstance(center, dict):
                lat = center.get("lat")
                lon = center.get("lon")
            elif "bounds" in el and isinstance(el["bounds"], dict):
                b = el["bounds"]
                lat = (b.get("minlat", 0.0) + b.get("maxlat", 0.0)) / 2.0
                lon = (b.get("minlon", 0.0) + b.get("maxlon", 0.0)) / 2.0

        if lat is None or lon is None:
            continue

        try:
            flat = float(lat)
            flon = float(lon)
            validate_coordinates(flat, flon)
        except (ValueError, TypeError):
            continue

        category, feature_type, display_name = categorize_osm_tags(tags)

        features.append(OSMFeature(
            id=f"{el_type}/{el_id}",
            name=display_name,
            category=category,
            feature_type=feature_type,
            latitude=flat,
            longitude=flon,
            tags={str(k): str(v) for k, v in tags.items()}
        ))

    return features


class OverpassClient:
    """HTTP client for querying OpenStreetMap Overpass with built-in cache, rate limiter, and fallbacks."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cache: Optional["EnrichmentCache"] = None,
        http_client: Optional[httpx.Client] = None,
        rate_limiter: Optional[Any] = None,
        asset_store: Optional["AssetStoreInterface"] = None
    ):
        self.api_url = api_url or os.getenv("OVERPASS_API_URL", DEFAULT_OVERPASS_URL)
        self.timeout = timeout
        if cache is None:
            from services.api.enrichment.cache import EnrichmentCache
            cache = EnrichmentCache()
        self.cache = cache
        self._external_client = http_client
        if rate_limiter is None:
            from services.api.geospatial.rate_limiter import OverpassRateLimiter
            rate_limiter = OverpassRateLimiter()
        self.rate_limiter = rate_limiter
        if asset_store is None:
            try:
                from services.api.geospatial.asset_store import GeoJSONAssetStore
                asset_store = GeoJSONAssetStore(auto_load=True)
            except Exception:
                asset_store = None
        self.asset_store = asset_store
        self._last_radius_result: Optional[OverpassResult] = None
        self._last_bbox_result: Optional[OverpassResult] = None

    def _execute_query_rich(
        self,
        query: str,
        cache_key: str,
        reference: str = ""
    ) -> OverpassResult:
        """Execute query with cache lookup, rate limiting, and resilient fallback handling."""
        fetch_time = now_utc_iso()

        # 1. Check valid cache BEFORE network or rate-limiting
        cached_data = self.cache.get("osm", cache_key, allow_stale=False)
        if cached_data is not None:
            features = [OSMFeature(**item) for item in cached_data]
            status = OSMStatus.SUCCESS_NON_EMPTY if features else OSMStatus.SUCCESS_EMPTY
            return OverpassResult(
                features=features,
                status=status,
                is_cached=True,
                is_stale=False,
                source_url=self.api_url,
                provenance=Provenance(
                    provider="OpenStreetMap",
                    product="Overpass_API",
                    observed_at_utc=fetch_time,
                    fetched_at_utc=fetch_time,
                    freshness_state=FreshnessState.CACHED,
                    ttl_seconds=86400,
                    reference=reference or cache_key
                )
            )

        # 2. Perform live network call protected by OverpassRateLimiter
        headers = {"User-Agent": "ThermalIntel/1.0 (geospatial-enrichment-prototype)"}
        network_error: Optional[str] = None

        def _do_http():
            client = self._external_client or httpx.Client(timeout=self.timeout)
            try:
                return client.post(self.api_url, data={"data": query}, headers=headers)
            finally:
                if self._external_client is None:
                    client.close()

        resp, err = self.rate_limiter.execute_with_retry(_do_http)
        if resp is not None and resp.status_code == 200:
            try:
                raw_json = resp.json()
                features = parse_overpass_response(raw_json)
                # Cache normalized records (including empty to avoid query storms on empty regions)
                self.cache.set(
                    "osm",
                    cache_key,
                    [f.model_dump() for f in features]
                )
                status = OSMStatus.SUCCESS_NON_EMPTY if features else OSMStatus.SUCCESS_EMPTY
                return OverpassResult(
                    features=features,
                    status=status,
                    is_cached=False,
                    is_stale=False,
                    source_url=str(resp.url),
                    provenance=Provenance(
                        provider="OpenStreetMap",
                        product="Overpass_API",
                        observed_at_utc=fetch_time,
                        fetched_at_utc=fetch_time,
                        freshness_state=FreshnessState.FRESH,
                        ttl_seconds=86400,
                        reference=str(resp.url)
                    )
                )
            except Exception as e:
                network_error = f"Malformed Overpass JSON response: {e}"
        else:
            network_error = err or "Overpass network call failed"

        # 3. Fallback to stale cache on network failure
        stale_data = self.cache.get("osm", cache_key, allow_stale=True)
        if stale_data is not None:
            logger.info("Using stale cached Overpass data for key %s", cache_key)
            features = [OSMFeature(**item) for item in stale_data]
            return OverpassResult(
                features=features,
                status=OSMStatus.STALE_CACHE,
                error_message=f"Live API failed ({network_error}); loaded stale cache",
                is_cached=True,
                is_stale=True,
                source_url=self.api_url,
                provenance=Provenance(
                    provider="OpenStreetMap",
                    product="Overpass_API",
                    observed_at_utc=fetch_time,
                    fetched_at_utc=fetch_time,
                    freshness_state=FreshnessState.STALE,
                    ttl_seconds=86400,
                    reference=reference or cache_key
                )
            )

        # 4. Return explicit provider failure - do not allow empty to masquerade as success
        return OverpassResult(
            features=[],
            status=OSMStatus.PROVIDER_FAILURE,
            error_message=network_error or "Overpass provider failed",
            source_url=self.api_url,
            provenance=Provenance(
                provider="OpenStreetMap",
                product="Overpass_API",
                observed_at_utc=fetch_time,
                fetched_at_utc=fetch_time,
                freshness_state=FreshnessState.UNAVAILABLE,
                ttl_seconds=0,
                reference=reference or cache_key
            )
        )

    def _execute_query(self, query: str, cache_key: str) -> List[OSMFeature]:
        """Backward-compatible method returning list of features."""
        res = self._execute_query_rich(query, cache_key)
        return res.features

    def query_radius(
        self,
        lat: float,
        lon: float,
        radius_meters: float = DEFAULT_SEARCH_RADIUS_METERS
    ) -> OverpassResult:
        """Fetch OSM features in circular radius, returning typed OverpassResult."""
        try:
            validate_coordinates(lat, lon)
        except ValueError as e:
            return OverpassResult(
                features=[],
                status=OSMStatus.UNAVAILABLE,
                error_message=f"Invalid coordinates: {e}"
            )

        from services.api.enrichment.cache import generate_cache_key
        cache_key = generate_cache_key("radius", lat=lat, lon=lon, radius=radius_meters)
        query = build_overpass_radius_query(lat, lon, radius_meters, int(self.timeout))
        return self._execute_query_rich(query, cache_key, reference=f"radius:{lat:.4f},{lon:.4f}:{radius_meters}m")

    def fetch_features_radius(
        self,
        lat: float,
        lon: float,
        radius_meters: float = DEFAULT_SEARCH_RADIUS_METERS
    ) -> List[OSMFeature]:
        """Fetch OSM features in circular radius (backward-compatible list return)."""
        res = self.query_radius(lat, lon, radius_meters)
        self._last_radius_result = res
        return res.features

    def query_bbox(
        self,
        south: float,
        west: float,
        north: float,
        east: float
    ) -> OverpassResult:
        """Fetch OSM features within bounding box, returning typed OverpassResult."""
        try:
            validate_coordinates(south, west)
            validate_coordinates(north, east)
        except ValueError as e:
            return OverpassResult(
                features=[],
                status=OSMStatus.UNAVAILABLE,
                error_message=f"Invalid bounding box: {e}"
            )

        from services.api.enrichment.cache import generate_cache_key
        cache_key = generate_cache_key("bbox", south=south, west=west, north=north, east=east)
        query = build_overpass_bbox_query(south, west, north, east, int(self.timeout))
        return self._execute_query_rich(query, cache_key, reference=f"bbox:{south:.4f},{west:.4f},{north:.4f},{east:.4f}")

    def fetch_features_bbox(
        self,
        south: float,
        west: float,
        north: float,
        east: float
    ) -> List[OSMFeature]:
        """Fetch OSM features within bounding box (backward-compatible list return)."""
        res = self.query_bbox(south, west, north, east)
        self._last_bbox_result = res
        return res.features


def derive_geospatial_context(
    target_lat: float,
    target_lon: float,
    features: List[OSMFeature],
    max_search_radius_meters: float = 10000.0,
    source_status: Optional[str] = None,
    asset_store: Optional[Any] = None
) -> Tuple[GeospatialContext, Dict[str, Any]]:
    """Synthesize a frozen GeospatialContext and metadata dict for a hotspot.
    
    Args:
        target_lat: Hotspot latitude.
        target_lon: Hotspot longitude.
        features: Pre-fetched OSM features (e.g. from regional bbox query).
        max_search_radius_meters: Search horizon in meters.
        source_status: Optional explicit status override ('successful_non_empty', 'stale_cache', etc.).
        asset_store: Optional AssetStoreInterface instance for polygon containment checks.
        
    Returns:
        Tuple of (GeospatialContext, detailed_metrics_dict).
    """
    try:
        validate_coordinates(target_lat, target_lon)
    except ValueError:
        # Invalid coordinate safety fallback
        return (
            GeospatialContext(
                land_cover="unknown",
                nearest_infrastructure=None,
                distance_to_infrastructure_meters=None,
                nearest_settlement=None,
                distance_to_settlement_meters=None,
                is_protected_area=False,
                protected_area_name=None,
                elevation_meters=None,
                slope_degrees=None,
                fuel_load_estimate="unknown"
            ),
            {
                "nearest_industrial_facility": None,
                "distance_to_industrial_meters": None,
                "nearby_industrial_count": 0,
                "nearby_infrastructure_count": 0,
                "nearby_settlement_count": 0,
                "status": "unavailable",
                "protected_area_geometry_status": "unavailable"
            }
        )

    # Convert features to dict representation for spatial utility functions
    feature_dicts = [
        {
            "id": f.id,
            "name": f.name,
            "category": f.category.value,
            "feature_type": f.feature_type,
            "latitude": f.latitude,
            "longitude": f.longitude,
            "tags": f.tags
        }
        for f in features
    ]

    # Partition by category
    industrial_feats = [f for f in feature_dicts if f["category"] == FeatureCategory.INDUSTRIAL.value]
    infra_feats = [f for f in feature_dicts if f["category"] == FeatureCategory.INFRASTRUCTURE.value]
    settlement_feats = [f for f in feature_dicts if f["category"] == FeatureCategory.SETTLEMENT.value]
    protected_feats = [
        f for f in feature_dicts
        if f["category"] in (FeatureCategory.PROTECTED_AREA.value, FeatureCategory.NATURAL.value)
    ]

    # Find nearest elements
    nearest_ind = find_nearest_feature(target_lat, target_lon, industrial_feats, max_search_radius_meters)
    nearest_inf = find_nearest_feature(target_lat, target_lon, infra_feats, max_search_radius_meters)
    nearest_set = find_nearest_feature(target_lat, target_lon, settlement_feats, max_search_radius_meters)
    nearest_prot = find_nearest_feature(target_lat, target_lon, protected_feats, 3000.0)

    # Nearby counts within practical horizons
    nearby_ind_count = len(filter_features_in_radius(target_lat, target_lon, industrial_feats, 5000.0))
    nearby_inf_count = len(filter_features_in_radius(target_lat, target_lon, infra_feats, 5000.0))
    nearby_set_count = len(filter_features_in_radius(target_lat, target_lon, settlement_feats, 10000.0))

    # Evaluate Protected Area
    is_protected = False
    protected_name: Optional[str] = None
    geom_status = "none"

    # 1. First check local asset store polygon containment if store available
    store = asset_store
    if store is None:
        try:
            from services.api.geospatial.asset_store import GeoJSONAssetStore
            store = GeoJSONAssetStore(auto_load=True)
        except Exception:
            store = None

    if store is not None:
        is_in_prot, prot_n, g_status = store.check_protected_area(target_lat, target_lon)
        if is_in_prot:
            is_protected = True
            protected_name = prot_n
            geom_status = g_status
        elif g_status == "degraded_centroid":
            is_protected = False
            protected_name = prot_n
            geom_status = "degraded_centroid"

    # 2. If not already verified inside polygon, inspect candidate protected features
    if not is_protected and nearest_prot is not None:
        prot_feat, prot_dist = nearest_prot
        if prot_dist <= 1500.0:
            # Centroid proximity without verified polygon boundary -> explicit degraded state
            is_protected = False
            protected_name = prot_feat.get("name")
            geom_status = "degraded_centroid"

    # Determine land cover estimate
    land_cover = "chaparral_scrubland"
    fuel_load = "moderate"

    if nearest_ind is not None and nearest_ind[1] <= 400.0:
        land_cover = "industrial_site"
        fuel_load = "non_vegetated"
    elif nearest_prot is not None and nearest_prot[1] <= 1000.0:
        land_cover = "dense_coniferous_forest"
        fuel_load = "extreme_dry_chaparral"
    elif nearest_set is not None and nearest_set[1] <= 1000.0:
        land_cover = "urban_wildland_interface"
        fuel_load = "moderate_mixed"

    nearest_infra_name = nearest_inf[0]["name"] if nearest_inf else None
    dist_infra = round(nearest_inf[1], 1) if nearest_inf else None

    nearest_set_name = nearest_set[0]["name"] if nearest_set else None
    dist_set = round(nearest_set[1], 1) if nearest_set else None

    nearest_ind_name = nearest_ind[0]["name"] if nearest_ind else None
    dist_ind = round(nearest_ind[1], 1) if nearest_ind else None

    context = GeospatialContext(
        land_cover=land_cover,
        nearest_infrastructure=nearest_infra_name,
        distance_to_infrastructure_meters=dist_infra,
        nearest_settlement=nearest_set_name,
        distance_to_settlement_meters=dist_set,
        is_protected_area=is_protected,
        protected_area_name=protected_name,
        elevation_meters=None,
        slope_degrees=None,
        fuel_load_estimate=fuel_load
    )

    # Correct status semantics: distinguish non-empty, empty, stale, provider failure
    if source_status:
        final_status = source_status
    elif features:
        final_status = OSMStatus.SUCCESS_NON_EMPTY.value
    else:
        final_status = OSMStatus.SUCCESS_EMPTY.value

    metadata = {
        "nearest_industrial_facility": nearest_ind_name,
        "distance_to_industrial_meters": dist_ind,
        "nearby_industrial_count": nearby_ind_count,
        "nearby_infrastructure_count": nearby_inf_count,
        "nearby_settlement_count": nearby_set_count,
        "status": final_status,
        "protected_area_geometry_status": geom_status
    }

    return (context, metadata)


def derive_geospatial_v2(
    target_lat: float,
    target_lon: float,
    features: List[OSMFeature],
    status: OSMStatus = OSMStatus.SUCCESS_NON_EMPTY,
    observed_at_utc: Optional[str] = None,
    provenance: Optional[Provenance] = None,
    asset_store: Optional[Any] = None
) -> GeospatialEnrichment:
    """Construct canonical V2 GeospatialEnrichment with atomic EnrichmentDatum per attribute."""
    context, meta = derive_geospatial_context(
        target_lat=target_lat,
        target_lon=target_lon,
        features=features,
        source_status=status.value,
        asset_store=asset_store
    )

    obs_time = observed_at_utc or now_utc_iso()
    fetch_time = now_utc_iso()
    is_avail = status in (OSMStatus.SUCCESS_NON_EMPTY, OSMStatus.SUCCESS_EMPTY, OSMStatus.STALE_CACHE)
    freshness = (
        FreshnessState.STALE if status == OSMStatus.STALE_CACHE
        else (FreshnessState.FRESH if is_avail else FreshnessState.UNAVAILABLE)
    )
    datum_status = "available" if is_avail else "unavailable"

    prov = provenance or Provenance(
        provider="OpenStreetMap",
        product="Overpass_API",
        observed_at_utc=obs_time,
        fetched_at_utc=fetch_time,
        freshness_state=freshness,
        ttl_seconds=86400,
        reference=f"lat={target_lat:.4f},lon={target_lon:.4f}"
    )

    # Handle protected area geometry status: if degraded_centroid, status='degraded'
    geom_status = meta.get("protected_area_geometry_status", "none")
    if geom_status == "verified_polygon":
        prot_datum = EnrichmentDatum[bool](
            value=context.is_protected_area,
            status="available",
            provenance=prov
        )
    elif geom_status == "degraded_centroid":
        prot_datum = EnrichmentDatum[bool](
            value=None,
            status="degraded",
            provenance=prov,
            error_message="Centroid proximity only; exact boundary polygon unavailable"
        )
    else:
        prot_datum = EnrichmentDatum[bool](
            value=False if is_avail else None,
            status=datum_status,
            provenance=prov,
            error_message=None if is_avail else "Geospatial telemetry unavailable"
        )

    return GeospatialEnrichment(
        land_cover=EnrichmentDatum[str](
            value=context.land_cover if is_avail else "unknown",
            status=datum_status,
            provenance=prov,
            error_message=None if is_avail else "Geospatial telemetry unavailable"
        ),
        nearest_settlement=EnrichmentDatum[str](
            value=context.nearest_settlement,
            status=datum_status,
            provenance=prov,
            error_message=None if is_avail else "Settlement telemetry unavailable"
        ),
        distance_to_settlement_meters=EnrichmentDatum[float](
            value=context.distance_to_settlement_meters,
            status=datum_status,
            provenance=prov,
            error_message=None if is_avail else "Settlement telemetry unavailable"
        ),
        nearest_infrastructure=EnrichmentDatum[str](
            value=context.nearest_infrastructure,
            status=datum_status,
            provenance=prov,
            error_message=None if is_avail else "Infrastructure telemetry unavailable"
        ),
        distance_to_infrastructure_meters=EnrichmentDatum[float](
            value=context.distance_to_infrastructure_meters,
            status=datum_status,
            provenance=prov,
            error_message=None if is_avail else "Infrastructure telemetry unavailable"
        ),
        is_protected_area=prot_datum,
        protected_area_name=EnrichmentDatum[str](
            value=context.protected_area_name,
            status="available" if context.protected_area_name else datum_status,
            provenance=prov,
            error_message=None
        ) if context.protected_area_name else None
    )

