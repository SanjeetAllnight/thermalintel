"""Topographic terrain provider for elevation and slope derivation.

Provides genuinely working topographic calculations without phantom values:
- Hyperlocal elevation retrieval from Open-Meteo Elevation API or forecast telemetry
- Gradient slope calculation (in degrees) using finite-difference spatial elevation sampling
- Explicit status tracking: AVAILABLE vs. UNAVAILABLE vs. DEGRADED
- Zero fabrication: missing elevation or slope is explicitly None with status='unavailable'
"""

import logging
import math
import os
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING
import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.api.enrichment.cache import EnrichmentCache

from services.api.geospatial.spatial import (
    haversine_distance_meters,
    validate_coordinates,
)
from services.api.schemas.v2.common import FreshnessState, Provenance, now_utc_iso
from services.api.schemas.v2.enrichment import EnrichmentDatum, TerrainEnrichment

logger = logging.getLogger(__name__)

DEFAULT_ELEVATION_API_URL = "https://api.open-meteo.com/v1/elevation"
DEFAULT_TIMEOUT_SECONDS = 8.0


class TerrainResult(BaseModel):
    """Normalized container for terrain parameters and availability provenance."""
    elevation_meters: Optional[float] = Field(None, description="Elevation above sea level in meters")
    slope_degrees: Optional[float] = Field(None, ge=0.0, le=90.0, description="Terrain slope angle in degrees")
    aspect_degrees: Optional[float] = Field(None, ge=0.0, le=360.0, description="Slope aspect compass heading")
    fuel_load_estimate: str = Field(default="unknown", description="Vegetation fuel category")
    status: str = Field(default="available", description="'available', 'degraded', or 'unavailable'")
    provenance: Optional[Provenance] = None
    error_message: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return self.status == "available" and self.elevation_meters is not None

    def to_v2_enrichment(
        self,
        observed_at_utc: Optional[str] = None
    ) -> TerrainEnrichment:
        """Convert result to canonical V2 TerrainEnrichment contract."""
        obs_time = observed_at_utc or now_utc_iso()
        fetch_time = now_utc_iso()

        is_elev_avail = self.elevation_meters is not None and self.status in ("available", "degraded")
        is_slope_avail = self.slope_degrees is not None and self.status == "available"

        prov = self.provenance or Provenance(
            provider="Open-Meteo_Terrain",
            product="Elevation_API",
            observed_at_utc=obs_time,
            fetched_at_utc=fetch_time,
            freshness_state=FreshnessState.FRESH if is_elev_avail else FreshnessState.UNAVAILABLE,
            ttl_seconds=86400 * 7,
            reference=f"elev_m={self.elevation_meters}"
        )

        return TerrainEnrichment(
            elevation_meters=EnrichmentDatum[float](
                value=self.elevation_meters if is_elev_avail else None,
                status="available" if is_elev_avail else "unavailable",
                provenance=prov,
                error_message=None if is_elev_avail else (self.error_message or "Elevation unavailable")
            ),
            slope_degrees=EnrichmentDatum[float](
                value=self.slope_degrees if is_slope_avail else None,
                status="available" if is_slope_avail else "unavailable",
                provenance=prov,
                error_message=None if is_slope_avail else "Terrain slope gradient calculation unavailable"
            ),
            aspect_degrees=EnrichmentDatum[float](
                value=self.aspect_degrees if self.aspect_degrees is not None else None,
                status="available" if self.aspect_degrees is not None else "unavailable",
                provenance=prov,
                error_message=None if self.aspect_degrees is not None else "Aspect unavailable"
            ) if self.aspect_degrees is not None else None,
            fuel_load_estimate=EnrichmentDatum[str](
                value=self.fuel_load_estimate if is_elev_avail else "unknown",
                status="available" if is_elev_avail else "unavailable",
                provenance=prov,
                error_message=None if is_elev_avail else "Fuel load estimate unavailable"
            )
        )


class TerrainProvider:
    """Client for terrain elevation retrieval and slope derivation."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cache: Optional["EnrichmentCache"] = None,
        http_client: Optional[httpx.Client] = None
    ):
        self.api_url = api_url or os.getenv("ELEVATION_API_URL", DEFAULT_ELEVATION_API_URL)
        self.timeout = timeout
        if cache is None:
            from services.api.enrichment.cache import EnrichmentCache
            cache = EnrichmentCache()
        self.cache = cache
        self._external_client = http_client

    def fetch_terrain(
        self,
        latitude: float,
        longitude: float,
        known_elevation: Optional[float] = None,
        compute_slope: bool = False
    ) -> TerrainResult:
        """Fetch elevation and optionally calculate slope for given coordinates.
        
        Args:
            latitude: Target latitude in decimal degrees.
            longitude: Target longitude in decimal degrees.
            known_elevation: Optional pre-extracted elevation (e.g. from Open-Meteo forecast JSON).
            compute_slope: If True, executes finite-difference neighborhood queries to derive slope.
            
        Returns:
            TerrainResult with actual values or explicit unavailable status.
        """
        try:
            validate_coordinates(latitude, longitude)
        except ValueError as e:
            return TerrainResult(
                elevation_meters=None,
                slope_degrees=None,
                status="unavailable",
                error_message=f"Invalid coordinates: {e}"
            )

        # 1. Use pre-provided elevation if supplied
        if known_elevation is not None and math.isfinite(known_elevation):
            elev = round(float(known_elevation), 1)
            slope = self._estimate_slope(latitude, longitude, elev) if compute_slope else None
            return TerrainResult(
                elevation_meters=elev,
                slope_degrees=slope,
                status="available",
                provenance=Provenance(
                    provider="Open-Meteo",
                    product="Forecast_Telemetry_Elevation",
                    observed_at_utc=now_utc_iso(),
                    fetched_at_utc=now_utc_iso(),
                    freshness_state=FreshnessState.FRESH,
                    ttl_seconds=86400 * 7
                )
            )

        # 2. Check disk cache
        from services.api.enrichment.cache import generate_cache_key
        cache_key = generate_cache_key("terrain", lat=round(latitude, 3), lon=round(longitude, 3))
        cached = self.cache.get("terrain", cache_key, allow_stale=False)
        if cached is not None and "elevation_meters" in cached:
            return TerrainResult(
                elevation_meters=cached.get("elevation_meters"),
                slope_degrees=cached.get("slope_degrees"),
                status="available",
                provenance=Provenance(
                    provider="Open-Meteo",
                    product="Elevation_API",
                    observed_at_utc=now_utc_iso(),
                    fetched_at_utc=now_utc_iso(),
                    freshness_state=FreshnessState.CACHED,
                    ttl_seconds=86400 * 7
                )
            )

        # 3. Live query to Open-Meteo Elevation API
        try:
            client = self._external_client or httpx.Client(timeout=self.timeout)
            try:
                params = {"latitude": f"{latitude:.4f}", "longitude": f"{longitude:.4f}"}
                resp = client.get(self.api_url, params=params)
                if resp.status_code == 200:
                    raw_data = resp.json()
                    elevation_list = raw_data.get("elevation", [])
                    if elevation_list and isinstance(elevation_list, list):
                        elev_val = elevation_list[0]
                        if elev_val is not None:
                            elev = round(float(elev_val), 1)
                            slope = self._estimate_slope(latitude, longitude, elev) if compute_slope else None
                            
                            # Cache result
                            self.cache.set("terrain", cache_key, {
                                "elevation_meters": elev,
                                "slope_degrees": slope
                            }, ttl_seconds=86400 * 7)

                            return TerrainResult(
                                elevation_meters=elev,
                                slope_degrees=slope,
                                status="available",
                                provenance=Provenance(
                                    provider="Open-Meteo",
                                    product="Elevation_API",
                                    observed_at_utc=now_utc_iso(),
                                    fetched_at_utc=now_utc_iso(),
                                    freshness_state=FreshnessState.FRESH,
                                    ttl_seconds=86400 * 7
                                )
                            )
            finally:
                if self._external_client is None:
                    client.close()
        except Exception as e:
            logger.warning("Elevation API request failed for (%.4f, %.4f): %s", latitude, longitude, e)

        # 4. Check stale cache fallback
        stale = self.cache.get("terrain", cache_key, allow_stale=True)
        if stale is not None and "elevation_meters" in stale:
            return TerrainResult(
                elevation_meters=stale.get("elevation_meters"),
                slope_degrees=stale.get("slope_degrees"),
                status="degraded",
                provenance=Provenance(
                    provider="Open-Meteo",
                    product="Elevation_API",
                    observed_at_utc=now_utc_iso(),
                    fetched_at_utc=now_utc_iso(),
                    freshness_state=FreshnessState.STALE,
                    ttl_seconds=86400 * 7
                )
            )

        # 5. Explicitly unavailable - NO PHANTOM VALUES
        return TerrainResult(
            elevation_meters=None,
            slope_degrees=None,
            status="unavailable",
            error_message="Elevation service unreachable"
        )

    def _estimate_slope(
        self,
        lat: float,
        lon: float,
        center_elev: float
    ) -> Optional[float]:
        """Compute terrain slope using 4-cardinal sampling at ~100m spacing."""
        # Offset ~100m: 100m / 111,000m ~ 0.0009 degrees
        delta = 0.0009
        coords = [
            (lat + delta, lon),
            (lat - delta, lon),
            (lat, lon + delta),
            (lat, lon - delta)
        ]
        
        try:
            client = self._external_client or httpx.Client(timeout=self.timeout)
            try:
                lats_str = ",".join(f"{c[0]:.5f}" for c in coords)
                lons_str = ",".join(f"{c[1]:.5f}" for c in coords)
                resp = client.get(self.api_url, params={"latitude": lats_str, "longitude": lons_str})
                if resp.status_code == 200:
                    elevs = resp.json().get("elevation", [])
                    valid_elevs = [float(e) for e in elevs if e is not None]
                    if len(valid_elevs) >= 2:
                        max_diff = max(abs(e - center_elev) for e in valid_elevs)
                        # Distance to sample is ~100m
                        slope_rad = math.atan(max_diff / 100.0)
                        slope_deg = round(math.degrees(slope_rad), 1)
                        return min(90.0, max(0.0, slope_deg))
            finally:
                if self._external_client is None:
                    client.close()
        except Exception as e:
            logger.debug("Neighborhood slope query failed: %s", e)

        return None
