"""High-level Enrichment Service orchestrating geospatial, weather, and historical telemetry.

Provides the primary public API for Phase 2:
- enrich_hotspot(hotspot, prior_hotspots=None) -> EnrichmentResult
- enrich_hotspots(hotspots, prior_hotspots=None) -> List[EnrichmentResult]

Performance & Reliability:
- Single bounding-box Overpass query for batches, amortizing network cost
- Grid-discretized caching for hyperlocal weather observations
- Zero-crash fallback handling across network, timeout, and coordinate errors
"""

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Union

from services.api.enrichment.cache import EnrichmentCache
from services.api.enrichment.models import EnrichmentResult, EnrichmentStatus
from services.api.geospatial.overpass import (
    OSMFeature,
    OverpassClient,
    derive_geospatial_context,
)
from services.api.geospatial.spatial import (
    calculate_bounding_box,
    validate_coordinates,
)
from services.api.history.recurrence import (
    HistoricalRecurrenceAnalyzer,
)
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import GeospatialContext, HistoricalContext, WeatherContext
from services.api.weather.open_meteo import (
    OpenMeteoClient,
    WeatherStatus,
    create_unavailable_weather_context,
)

logger = logging.getLogger(__name__)


def _extract_coords_and_id(record: Union[Hotspot, Dict[str, Any]]) -> Tuple_Coords:
    """Helper to extract id, lat, lon from either Hotspot model or dict."""
    if isinstance(record, Hotspot):
        return record.id, record.latitude, record.longitude
    return (
        str(record.get("id", "UNKNOWN")),
        float(record["latitude"]),
        float(record["longitude"])
    )


Tuple_Coords = tuple[str, float, float]


class EnrichmentService:
    """Orchestrator for multi-source thermal anomaly context enrichment."""

    def __init__(
        self,
        overpass_client: Optional[OverpassClient] = None,
        weather_client: Optional[OpenMeteoClient] = None,
        history_analyzer: Optional[HistoricalRecurrenceAnalyzer] = None,
        cache: Optional[EnrichmentCache] = None,
        db_path: Optional[str] = None
    ):
        self.cache = cache or EnrichmentCache()
        self.overpass_client = overpass_client or OverpassClient(cache=self.cache)
        self.weather_client = weather_client or OpenMeteoClient(cache=self.cache)
        self.history_analyzer = history_analyzer or HistoricalRecurrenceAnalyzer()
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
        """Enrich a single hotspot with geospatial, weather, and historical context.
        
        Args:
            hotspot: Hotspot instance or dictionary.
            prior_hotspots: Optional sequence of prior hotspots for recurrence calculation.
            
        Returns:
            EnrichmentResult containing all context blocks and availability status.
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
                    "historical": "unavailable"
                }
            )

        sources_status: Dict[str, str] = {}

        # 1. Geospatial context (OSM Overpass)
        try:
            osm_features = self.overpass_client.fetch_features_radius(lat, lon)
            geo_ctx, geo_meta = derive_geospatial_context(lat, lon, osm_features)
            sources_status["osm"] = "available" if osm_features else "empty"
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
                "status": "unavailable"
            }
            sources_status["osm"] = "unavailable"

        # 2. Weather telemetry (Open-Meteo)
        try:
            weather_res = self.weather_client.fetch_weather(lat, lon)
            weather_ctx = weather_res.context
            sources_status["weather"] = weather_res.status.value
        except Exception as e:
            logger.warning("Weather enrichment failed for %s: %s", hid, e)
            weather_ctx = create_unavailable_weather_context("Weather service exception")
            sources_status["weather"] = "unavailable"

        # 3. Historical recurrence
        conn = None
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

        # Overall status derivation
        unavail_count = sum(1 for v in sources_status.values() if v == "unavailable")
        if unavail_count == 0:
            overall_status = EnrichmentStatus.COMPLETE
        elif unavail_count == len(sources_status):
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
            repeated_activity=repeated
        )

    def enrich_hotspots(
        self,
        hotspots: Sequence[Union[Hotspot, Dict[str, Any]]],
        prior_hotspots: Optional[Sequence[Union[Hotspot, Dict[str, Any]]]] = None
    ) -> List[EnrichmentResult]:
        """Enrich a batch of hotspots with bounding-box optimization.
        
        Minimizes external Overpass calls by executing a single regional query
        for the entire cluster bounding box, then performing fast local spatial
        distance calculations.
        
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
        if lats and lons:
            try:
                south, west, north, east = calculate_bounding_box(lats, lons, buffer_km=6.0)
                regional_features = self.overpass_client.fetch_features_bbox(south, west, north, east)
            except Exception as e:
                logger.warning("Regional bounding-box OSM query failed: %s", e)

        # 3. Enrich each hotspot
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

                # Geospatial via regional feature cache
                if regional_features:
                    geo_ctx, geo_meta = derive_geospatial_context(lat, lon, regional_features)
                    sources_status["osm"] = "available"
                else:
                    # Fallback to local radius or empty
                    try:
                        features = self.overpass_client.fetch_features_radius(lat, lon)
                        geo_ctx, geo_meta = derive_geospatial_context(lat, lon, features)
                        sources_status["osm"] = "available" if features else "empty"
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
                            "status": "unavailable"
                        }
                        sources_status["osm"] = "unavailable"

                # Weather (reuses grid cell cache automatically)
                try:
                    w_res = self.weather_client.fetch_weather(lat, lon)
                    weather_ctx = w_res.context
                    sources_status["weather"] = w_res.status.value
                except Exception:
                    weather_ctx = create_unavailable_weather_context("Weather service exception")
                    sources_status["weather"] = "unavailable"

                # Historical recurrence
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

                unavail_count = sum(1 for v in sources_status.values() if v == "unavailable")
                if unavail_count == 0:
                    overall_status = EnrichmentStatus.COMPLETE
                elif unavail_count == len(sources_status):
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
                    repeated_activity=repeated
                ))

        finally:
            if db_conn:
                db_conn.close()

        return results
