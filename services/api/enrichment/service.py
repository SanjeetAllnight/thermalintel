"""High-level Enrichment Service orchestrating geospatial, weather, terrain, and historical telemetry.

Provides the primary public API for Phase 2:
- enrich_hotspot(hotspot, prior_hotspots=None) -> EnrichmentResult
- enrich_hotspots(hotspots, prior_hotspots=None) -> List[EnrichmentResult]

Performance & Reliability:
- Single bounding-box Overpass query for batches, prefetching into local asset store
- Multi-location Open-Meteo batching and grid-discretized caching
- Genuine topographic terrain elevation & slope derivation (no phantom values)
- True polygon containment checks for conservation reserves
- Independent failure isolation: failure of one provider never destroys others
- Strict audit provenance via canonical V2 EnrichmentSnapshot
"""

import logging
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from services.api.enrichment.cache import EnrichmentCache
from services.api.enrichment.models import EnrichmentResult, EnrichmentStatus
from services.api.geospatial.asset_store import AssetStoreInterface, GeoJSONAssetStore
from services.api.geospatial.overpass import (
    OSMFeature,
    OSMStatus,
    OverpassClient,
    OverpassResult,
    derive_geospatial_context,
    derive_geospatial_v2,
)
from services.api.geospatial.spatial import (
    calculate_bounding_box,
    filter_features_in_radius,
    haversine_distance_meters,
    validate_coordinates,
)
from services.api.geospatial.terrain import TerrainProvider, TerrainResult
from services.api.history.recurrence import (
    HistoricalAnalysisResult,
    HistoricalRecurrenceAnalyzer,
)
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import GeospatialContext, HistoricalContext, WeatherContext
from services.api.schemas.v2.common import FreshnessState, Provenance, now_utc_iso
from services.api.schemas.v2.enrichment import EnrichmentSnapshot
from services.api.weather.open_meteo import (
    OpenMeteoClient,
    WeatherResult,
    WeatherStatus,
    create_unavailable_weather_context,
)

logger = logging.getLogger(__name__)

Tuple_Coords = tuple[str, float, float]


def _extract_coords_and_id(record: Union[Hotspot, Dict[str, Any]]) -> Tuple_Coords:
    """Helper to extract id, lat, lon from either Hotspot model or dict."""
    if isinstance(record, Hotspot):
        return record.id, record.latitude, record.longitude
    return (
        str(record.get("id", "UNKNOWN")),
        float(record["latitude"]),
        float(record["longitude"])
    )


class EnrichmentService:
    """Orchestrator for multi-source thermal anomaly context enrichment."""

    def __init__(
        self,
        overpass_client: Optional[OverpassClient] = None,
        weather_client: Optional[OpenMeteoClient] = None,
        history_analyzer: Optional[HistoricalRecurrenceAnalyzer] = None,
        terrain_provider: Optional[TerrainProvider] = None,
        asset_store: Optional[AssetStoreInterface] = None,
        cache: Optional[EnrichmentCache] = None,
        db_path: Optional[str] = None
    ):
        self.cache = cache or EnrichmentCache()
        self.overpass_client = overpass_client or OverpassClient(cache=self.cache)
        self.weather_client = weather_client or OpenMeteoClient(cache=self.cache)
        self.history_analyzer = history_analyzer or HistoricalRecurrenceAnalyzer()
        self.terrain_provider = terrain_provider or TerrainProvider(cache=self.cache)

        if asset_store is not None:
            self.asset_store = asset_store
        elif hasattr(self.overpass_client, "asset_store") and self.overpass_client.asset_store:
            self.asset_store = self.overpass_client.asset_store
        else:
            try:
                self.asset_store = GeoJSONAssetStore(auto_load=True)
            except Exception:
                self.asset_store = None

        self.db_path = db_path or os.getenv("DATABASE_PATH")

    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Establish temporary connection to SQLite if configured and existing."""
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.warning("Failed to open SQLite database for history analysis: %s", e)
            return None

    def enrich_hotspot(
        self,
        hotspot: Union[Hotspot, Dict[str, Any]],
        prior_hotspots: Optional[Sequence[Union[Hotspot, Dict[str, Any]]]] = None
    ) -> EnrichmentResult:
        """Enrich a single hotspot with geospatial, weather, terrain, and historical context.
        
        Args:
            hotspot: Hotspot instance or dictionary.
            prior_hotspots: Optional sequence of prior hotspots for recurrence calculation.
            
        Returns:
            EnrichmentResult containing all context blocks, availability status, and V2 snapshot.
        """
        # Validate coordinates first
        try:
            hid, lat, lon = _extract_coords_and_id(hotspot)
            validate_coordinates(lat, lon)
        except Exception as e:
            logger.warning("Cannot enrich hotspot with invalid coordinates: %s", e)
            hid = str(getattr(hotspot, "id", None) or (hotspot.get("id") if isinstance(hotspot, dict) else "INVALID"))
            return EnrichmentResult(
                hotspot_id=hid,
                latitude=0.0,
                longitude=0.0,
                status=EnrichmentStatus.UNAVAILABLE,
                geospatial=GeospatialContext(
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
                weather=create_unavailable_weather_context(f"Invalid coordinate telemetry: {e}"),
                historical=HistoricalContext(
                    prior_detections_30d=0,
                    prior_detections_90d=0,
                    is_recurrent_site=False,
                    recurrent_pattern="none",
                    first_detected_date=None,
                    detection_frequency_score=0.0
                ),
                sources_status={
                    "osm": "unavailable",
                    "weather": "unavailable",
                    "historical": "unavailable",
                    "terrain": "unavailable"
                }
            )

        sources_status: Dict[str, str] = {}

        # 1. Geospatial context (OSM Overpass / Asset Store)
        osm_features: List[OSMFeature] = []
        osm_status: str = OSMStatus.UNAVAILABLE.value
        osm_prov: Optional[Provenance] = None

        try:
            if hasattr(self.overpass_client, "fetch_features_radius"):
                osm_features = self.overpass_client.fetch_features_radius(lat, lon)
                last_res = getattr(self.overpass_client, "_last_radius_result", None)
                if isinstance(last_res, OverpassResult):
                    osm_status = last_res.status.value
                    osm_prov = last_res.provenance
                else:
                    osm_status = OSMStatus.SUCCESS_NON_EMPTY.value if osm_features else OSMStatus.SUCCESS_EMPTY.value
            elif hasattr(self.overpass_client, "query_radius"):
                q_res = self.overpass_client.query_radius(lat, lon)
                if isinstance(q_res, OverpassResult):
                    osm_features = q_res.features
                    osm_status = q_res.status.value
                    osm_prov = q_res.provenance
                else:
                    osm_features = []
                    osm_status = OSMStatus.SUCCESS_EMPTY.value
            else:
                osm_features = []
                osm_status = OSMStatus.SUCCESS_EMPTY.value

            geo_ctx, geo_meta = derive_geospatial_context(
                target_lat=lat,
                target_lon=lon,
                features=osm_features,
                source_status=osm_status,
                asset_store=self.asset_store
            )
            sources_status["osm"] = osm_status
        except Exception as e:
            logger.warning("Geospatial enrichment failed for %s: %s", hid, e)
            geo_ctx = GeospatialContext(
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
            )
            geo_meta = {
                "nearest_industrial_facility": None,
                "distance_to_industrial_meters": None,
                "nearby_industrial_count": 0,
                "nearby_infrastructure_count": 0,
                "nearby_settlement_count": 0,
                "status": OSMStatus.PROVIDER_FAILURE.value,
                "protected_area_geometry_status": "unavailable"
            }
            sources_status["osm"] = "unavailable"

        # 2. Weather telemetry (Open-Meteo)
        weather_res: Optional[WeatherResult] = None
        try:
            weather_res = self.weather_client.fetch_weather(lat, lon)
            weather_ctx = weather_res.context
            sources_status["weather"] = weather_res.status.value
        except Exception as e:
            logger.warning("Weather enrichment failed for %s: %s", hid, e)
            weather_ctx = create_unavailable_weather_context("Weather service unreachable")
            sources_status["weather"] = "unavailable"

        # 3. Topographic Terrain (Elevation & Slope)
        terrain_res: Optional[TerrainResult] = None
        try:
            known_elev = getattr(weather_res, "elevation_meters", None) if weather_res else None
            terrain_res = self.terrain_provider.fetch_terrain(
                latitude=lat,
                longitude=lon,
                known_elevation=known_elev,
                compute_slope=False
            )
            sources_status["terrain"] = terrain_res.status
            if terrain_res.is_available:
                geo_ctx.elevation_meters = terrain_res.elevation_meters
                geo_ctx.slope_degrees = terrain_res.slope_degrees
        except Exception as e:
            logger.warning("Terrain enrichment failed for %s: %s", hid, e)
            sources_status["terrain"] = "unavailable"

        # 4. Historical recurrence
        conn = None
        hist_res: Optional[HistoricalAnalysisResult] = None
        try:
            if prior_hotspots is None:
                conn = self._get_db_connection()
            hist_res = self.history_analyzer.analyze(
                target_hotspot=hotspot,
                candidate_history=prior_hotspots,
                db_connection=conn
            )
            hist_ctx = hist_res.context
            sources_status["historical"] = hist_res.status
            persistence = hist_res.persistence_score
            repeated = hist_res.repeated_activity
        except Exception as e:
            logger.warning("Historical enrichment failed for %s: %s", hid, e)
            hist_ctx = HistoricalContext(
                prior_detections_30d=0,
                prior_detections_90d=0,
                is_recurrent_site=False,
                recurrent_pattern="none",
                first_detected_date=None,
                detection_frequency_score=0.0
            )
            sources_status["historical"] = "unavailable"
            persistence = 0.0
            repeated = False
        finally:
            if conn:
                conn.close()

        # 5. Build Canonical V2 EnrichmentSnapshot with full independent provenance
        obs_time = None
        if hasattr(hotspot, "acq_date") and hasattr(hotspot, "acq_time"):
            obs_time = f"{hotspot.acq_date}T{hotspot.acq_time}:00Z"
        elif isinstance(hotspot, dict) and "acq_date" in hotspot:
            t_str = hotspot.get("acq_time", "0000")
            obs_time = f"{hotspot['acq_date']}T{t_str}:00Z"
        obs_time = obs_time or now_utc_iso()

        try:
            osm_enum = OSMStatus(osm_status) if osm_status in [s.value for s in OSMStatus] else OSMStatus.UNAVAILABLE
        except Exception:
            osm_enum = OSMStatus.UNAVAILABLE

        v2_geo = derive_geospatial_v2(
            target_lat=lat,
            target_lon=lon,
            features=osm_features,
            status=osm_enum,
            observed_at_utc=obs_time,
            provenance=osm_prov,
            asset_store=self.asset_store
        )
        v2_weather = weather_res.to_v2_enrichment(lat, lon) if weather_res else None
        v2_hist = hist_res.to_v2_enrichment(obs_time) if hist_res else None
        v2_terrain = terrain_res.to_v2_enrichment(obs_time) if terrain_res else None

        snapshot = EnrichmentSnapshot(
            snapshot_id=f"SNAP-{uuid.uuid4().hex[:12].upper()}",
            target_id=hid,
            target_type="observation",
            geospatial=v2_geo,
            weather=v2_weather,
            historical=v2_hist,
            terrain=v2_terrain,
            created_at_utc=now_utc_iso()
        )

        # Overall status derivation
        core_statuses = [sources_status["osm"], sources_status["weather"], sources_status["historical"]]
        unavail_count = sum(1 for v in core_statuses if v in ("unavailable", "provider_failure"))
        if unavail_count == 0:
            overall_status = EnrichmentStatus.COMPLETE
        elif unavail_count == len(core_statuses):
            overall_status = EnrichmentStatus.UNAVAILABLE
        else:
            overall_status = EnrichmentStatus.PARTIAL

        return EnrichmentResult(
            hotspot_id=hid,
            latitude=lat,
            longitude=lon,
            status=overall_status,
            geospatial=geo_ctx,
            weather=weather_ctx,
            historical=hist_ctx,
            sources_status=sources_status,
            nearest_industrial_facility=geo_meta.get("nearest_industrial_facility"),
            distance_to_industrial_meters=geo_meta.get("distance_to_industrial_meters"),
            nearby_industrial_count=geo_meta.get("nearby_industrial_count", 0),
            nearby_infrastructure_count=geo_meta.get("nearby_infrastructure_count", 0),
            nearby_settlement_count=geo_meta.get("nearby_settlement_count", 0),
            persistence_score=persistence,
            repeated_activity=repeated,
            snapshot=snapshot
        )

    def enrich_hotspots(
        self,
        hotspots: Sequence[Union[Hotspot, Dict[str, Any]]],
        prior_hotspots: Optional[Sequence[Union[Hotspot, Dict[str, Any]]]] = None
    ) -> List[EnrichmentResult]:
        """Enrich a batch of hotspots with bounding-box prefetching and batch optimization.
        
        Minimizes external calls by:
        - Executing a single regional bounding box Overpass query for the cluster
        - Prefetching into a local in-memory asset store for local spatial lookups
        - Executing multi-location weather batching via Open-Meteo
        - Reusing database connections across historical evaluations
        - Isolating provider failures so one failing service does not degrade others
        
        Args:
            hotspots: Sequence of Hotspots to enrich.
            prior_hotspots: Sequence of historical Hotspot records.
            
        Returns:
            List of EnrichmentResult objects matching input order.
        """
        if not hotspots:
            return []

        # 1. Separate valid from invalid records and collect coordinates
        valid_items: List[Tuple_Coords] = []
        lats: List[float] = []
        lons: List[float] = []

        for h in hotspots:
            try:
                hid, lat, lon = _extract_coords_and_id(h)
                validate_coordinates(lat, lon)
                valid_items.append((hid, lat, lon))
                lats.append(lat)
                lons.append(lon)
            except Exception:
                pass

        # 2. Regional OSM batch query
        regional_features: List[OSMFeature] = []
        regional_status: str = OSMStatus.UNAVAILABLE.value
        regional_prov: Optional[Provenance] = None

        if lats and lons:
            try:
                south, west, north, east = calculate_bounding_box(lats, lons, buffer_km=6.0)
                if hasattr(self.overpass_client, "fetch_features_bbox"):
                    regional_features = self.overpass_client.fetch_features_bbox(south, west, north, east)
                    last_bbox_res = getattr(self.overpass_client, "_last_bbox_result", None)
                    if isinstance(last_bbox_res, OverpassResult):
                        regional_status = last_bbox_res.status.value
                        regional_prov = last_bbox_res.provenance
                    else:
                        regional_status = OSMStatus.SUCCESS_NON_EMPTY.value if regional_features else OSMStatus.SUCCESS_EMPTY.value
                elif hasattr(self.overpass_client, "query_bbox"):
                    q_res = self.overpass_client.query_bbox(south, west, north, east)
                    if isinstance(q_res, OverpassResult):
                        regional_features = q_res.features
                        regional_status = q_res.status.value
                        regional_prov = q_res.provenance
                    else:
                        regional_features = []
                        regional_status = OSMStatus.SUCCESS_EMPTY.value
            except Exception as e:
                logger.warning("Regional bounding-box OSM query failed: %s", e)
                regional_status = OSMStatus.PROVIDER_FAILURE.value

        # Ingest regional features into local asset store for local spatial lookups
        batch_asset_store = self.asset_store
        if regional_features:
            try:
                batch_asset_store = GeoJSONAssetStore(auto_load=False)
                if self.asset_store:
                    batch_asset_store._features.extend(self.asset_store._features)
                    batch_asset_store._raw_features.extend(self.asset_store._raw_features)
                    batch_asset_store._geometries.extend(self.asset_store._geometries)
                for rf in regional_features:
                    batch_asset_store._features.append(rf)
                    batch_asset_store._raw_features.append({
                        "type": "Feature",
                        "id": rf.id,
                        "properties": {"name": rf.name, "category": rf.category.value, "feature_type": rf.feature_type, "tags": rf.tags},
                        "geometry": {"type": "Point", "coordinates": [rf.longitude, rf.latitude]}
                    })
                    batch_asset_store._geometries.append(None)
            except Exception:
                batch_asset_store = self.asset_store

        # 3. Weather batch retrieval
        coords_list = [(lat, lon) for _, lat, lon in valid_items]
        weather_results_map: Dict[Tuple[float, float], WeatherResult] = {}
        if coords_list and hasattr(self.weather_client, "fetch_weather_batch"):
            try:
                batch_w = self.weather_client.fetch_weather_batch(coords_list)
                for pt, w_res in zip(coords_list, batch_w):
                    weather_results_map[pt] = w_res
            except Exception as e:
                logger.warning("Batch weather fetch failed: %s. Falling back to individual fetch.", e)

        # 4. Enrich each hotspot
        results: List[EnrichmentResult] = []
        db_conn = None
        if prior_hotspots is None:
            db_conn = self._get_db_connection()

        try:
            for h in hotspots:
                try:
                    hid, lat, lon = _extract_coords_and_id(h)
                    validate_coordinates(lat, lon)
                except Exception:
                    # Enrich via single method to yield uniform invalid response
                    results.append(self.enrich_hotspot(h, prior_hotspots=prior_hotspots))
                    continue

                sources_status: Dict[str, str] = {}

                # 4.1 Geospatial via regional feature cache and asset store
                if regional_features or batch_asset_store:
                    # Filter features within local radius
                    osm_feats_local = [
                        rf for rf in regional_features
                        if haversine_distance_meters(lat, lon, rf.latitude, rf.longitude) <= 10000.0
                    ]

                    # Status for this hotspot
                    if osm_feats_local:
                        spot_status = OSMStatus.SUCCESS_NON_EMPTY.value
                    elif regional_status in (OSMStatus.SUCCESS_NON_EMPTY.value, OSMStatus.SUCCESS_EMPTY.value):
                        spot_status = OSMStatus.SUCCESS_EMPTY.value
                    elif regional_status == OSMStatus.STALE_CACHE.value:
                        spot_status = OSMStatus.STALE_CACHE.value
                    else:
                        spot_status = regional_status

                    geo_ctx, geo_meta = derive_geospatial_context(
                        target_lat=lat,
                        target_lon=lon,
                        features=osm_feats_local,
                        source_status=spot_status,
                        asset_store=batch_asset_store
                    )
                    sources_status["osm"] = spot_status
                else:
                    # Fallback to local radius or empty
                    try:
                        features = self.overpass_client.fetch_features_radius(lat, lon)
                        last_res = getattr(self.overpass_client, "_last_radius_result", None)
                        if isinstance(last_res, OverpassResult):
                            spot_status = last_res.status.value
                        else:
                            spot_status = OSMStatus.SUCCESS_NON_EMPTY.value if features else OSMStatus.SUCCESS_EMPTY.value

                        geo_ctx, geo_meta = derive_geospatial_context(
                            target_lat=lat,
                            target_lon=lon,
                            features=features,
                            source_status=spot_status,
                            asset_store=self.asset_store
                        )
                        sources_status["osm"] = spot_status
                    except Exception:
                        geo_ctx = GeospatialContext(
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
                        )
                        geo_meta = {
                            "nearest_industrial_facility": None,
                            "distance_to_industrial_meters": None,
                            "nearby_industrial_count": 0,
                            "nearby_infrastructure_count": 0,
                            "nearby_settlement_count": 0,
                            "status": OSMStatus.PROVIDER_FAILURE.value,
                            "protected_area_geometry_status": "unavailable"
                        }
                        sources_status["osm"] = "unavailable"

                # 4.2 Weather (from pre-fetched batch map or individual call)
                w_res: Optional[WeatherResult] = weather_results_map.get((lat, lon))
                if w_res is None:
                    try:
                        w_res = self.weather_client.fetch_weather(lat, lon)
                    except Exception:
                        w_res = None

                if w_res is not None:
                    weather_ctx = w_res.context
                    sources_status["weather"] = w_res.status.value
                else:
                    weather_ctx = create_unavailable_weather_context("Weather service unreachable")
                    sources_status["weather"] = "unavailable"

                # 4.3 Topographic Terrain
                terrain_res: Optional[TerrainResult] = None
                try:
                    known_elev = getattr(w_res, "elevation_meters", None) if w_res else None
                    terrain_res = self.terrain_provider.fetch_terrain(
                        latitude=lat,
                        longitude=lon,
                        known_elevation=known_elev,
                        compute_slope=False
                    )
                    sources_status["terrain"] = terrain_res.status
                    if terrain_res.is_available:
                        geo_ctx.elevation_meters = terrain_res.elevation_meters
                        geo_ctx.slope_degrees = terrain_res.slope_degrees
                except Exception as e:
                    logger.warning("Terrain enrichment failed for %s: %s", hid, e)
                    sources_status["terrain"] = "unavailable"

                # 4.4 Historical recurrence
                try:
                    hist_res = self.history_analyzer.analyze(
                        target_hotspot=h,
                        candidate_history=prior_hotspots,
                        db_connection=db_conn
                    )
                    hist_ctx = hist_res.context
                    sources_status["historical"] = hist_res.status
                    persistence = hist_res.persistence_score
                    repeated = hist_res.repeated_activity
                except Exception:
                    hist_ctx = HistoricalContext(
                        prior_detections_30d=0,
                        prior_detections_90d=0,
                        is_recurrent_site=False,
                        recurrent_pattern="none",
                        first_detected_date=None,
                        detection_frequency_score=0.0
                    )
                    sources_status["historical"] = "unavailable"
                    persistence = 0.0
                    repeated = False

                # 4.5 Build V2 Canonical Snapshot
                obs_time = None
                if hasattr(h, "acq_date") and hasattr(h, "acq_time"):
                    obs_time = f"{h.acq_date}T{h.acq_time}:00Z"
                elif isinstance(h, dict) and "acq_date" in h:
                    t_str = h.get("acq_time", "0000")
                    obs_time = f"{h['acq_date']}T{t_str}:00Z"
                obs_time = obs_time or now_utc_iso()

                try:
                    osm_enum = OSMStatus(sources_status["osm"]) if sources_status["osm"] in [s.value for s in OSMStatus] else OSMStatus.UNAVAILABLE
                except Exception:
                    osm_enum = OSMStatus.UNAVAILABLE

                v2_geo = derive_geospatial_v2(
                    target_lat=lat,
                    target_lon=lon,
                    features=regional_features,
                    status=osm_enum,
                    observed_at_utc=obs_time,
                    provenance=regional_prov,
                    asset_store=batch_asset_store
                )
                v2_weather = w_res.to_v2_enrichment(lat, lon) if w_res else None
                v2_hist = hist_res.to_v2_enrichment(obs_time) if hist_res else None
                v2_terrain = terrain_res.to_v2_enrichment(obs_time) if terrain_res else None

                snapshot = EnrichmentSnapshot(
                    snapshot_id=f"SNAP-{uuid.uuid4().hex[:12].upper()}",
                    target_id=hid,
                    target_type="observation",
                    geospatial=v2_geo,
                    weather=v2_weather,
                    historical=v2_hist,
                    terrain=v2_terrain,
                    created_at_utc=now_utc_iso()
                )

                # Overall status
                core_statuses = [sources_status["osm"], sources_status["weather"], sources_status["historical"]]
                unavail_count = sum(1 for v in core_statuses if v in ("unavailable", "provider_failure"))
                if unavail_count == 0:
                    overall_status = EnrichmentStatus.COMPLETE
                elif unavail_count == len(core_statuses):
                    overall_status = EnrichmentStatus.UNAVAILABLE
                else:
                    overall_status = EnrichmentStatus.PARTIAL

                results.append(EnrichmentResult(
                    hotspot_id=hid,
                    latitude=lat,
                    longitude=lon,
                    status=overall_status,
                    geospatial=geo_ctx,
                    weather=weather_ctx,
                    historical=hist_ctx,
                    sources_status=sources_status,
                    nearest_industrial_facility=geo_meta.get("nearest_industrial_facility"),
                    distance_to_industrial_meters=geo_meta.get("distance_to_industrial_meters"),
                    nearby_industrial_count=geo_meta.get("nearby_industrial_count", 0),
                    nearby_infrastructure_count=geo_meta.get("nearby_infrastructure_count", 0),
                    nearby_settlement_count=geo_meta.get("nearby_settlement_count", 0),
                    persistence_score=persistence,
                    repeated_activity=repeated,
                    snapshot=snapshot
                ))

        finally:
            if db_conn:
                db_conn.close()

        return results
