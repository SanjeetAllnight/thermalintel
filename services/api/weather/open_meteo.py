"""Open-Meteo weather client and environmental parameter extractor.

Fetches and normalizes hyperlocal atmospheric observations:
- Ambient temperature (°C)
- Relative humidity (%)
- Wind speed (km/h) & wind gusts (km/h)
- 16-point cardinal wind direction
- 24h precipitation (mm)
- Derived Fire Weather Danger Proxy rating (0-100)
- Forecast summary generation

Features:
- Deterministic spatial grid rounding to reuse cached weather for clustered hotspots
- Native multi-location batching support
- Resilient failure recovery (offline mode, network errors, bounded retries, timeouts)
- Explicit status tracking: AVAILABLE vs. CACHED vs. UNAVAILABLE
- Zero fabrication: missing or unavailable parameters are represented as None rather than real 0 values
- Full V2 audit provenance and timestamp tracking
"""

from datetime import datetime, timezone
from enum import Enum
import logging
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING
import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.api.enrichment.cache import EnrichmentCache
from services.api.geospatial.spatial import degrees_to_cardinal, validate_coordinates
from services.api.schemas.incident import WeatherContext
from services.api.schemas.v2.common import FreshnessState, Provenance, now_utc_iso
from services.api.schemas.v2.enrichment import EnrichmentDatum, WeatherEnrichment

logger = logging.getLogger(__name__)

DEFAULT_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2


class WeatherStatus(str, Enum):
    AVAILABLE = "available"
    CACHED = "cached"
    UNAVAILABLE = "unavailable"


class WeatherResult(BaseModel):
    """Container holding normalized WeatherContext, availability status, and provenance."""
    context: WeatherContext
    status: WeatherStatus
    error_message: Optional[str] = None
    source_url: Optional[str] = None
    elevation_meters: Optional[float] = None
    observed_at_utc: Optional[str] = None
    fetched_at_utc: Optional[str] = None
    provenance: Optional[Provenance] = None

    def to_v2_enrichment(
        self,
        target_lat: float = 0.0,
        target_lon: float = 0.0
    ) -> WeatherEnrichment:
        """Convert WeatherResult into canonical V2 WeatherEnrichment contract."""
        obs_time = self.observed_at_utc or now_utc_iso()
        fetch_time = self.fetched_at_utc or now_utc_iso()

        is_avail = self.status in (WeatherStatus.AVAILABLE, WeatherStatus.CACHED)
        freshness = (
            FreshnessState.CACHED if self.status == WeatherStatus.CACHED
            else (FreshnessState.FRESH if is_avail else FreshnessState.UNAVAILABLE)
        )
        datum_status = "available" if is_avail else "unavailable"

        prov = self.provenance or Provenance(
            provider="Open-Meteo",
            product="Forecast_API",
            observed_at_utc=obs_time,
            fetched_at_utc=fetch_time,
            freshness_state=freshness,
            ttl_seconds=3600,
            reference=self.source_url or f"coords:{target_lat:.4f},{target_lon:.4f}"
        )

        ctx = self.context
        t_val = ctx.temperature_celsius
        rh_val = ctx.relative_humidity_percent
        ws_val = ctx.wind_speed_kmh
        wg_val = ctx.wind_gust_kmh
        wd_val = ctx.wind_direction_degrees
        wc_val = ctx.wind_direction_cardinal
        p_val = ctx.precipitation_mm
        fwi_val = ctx.fire_weather_index

        return WeatherEnrichment(
            temperature_celsius=EnrichmentDatum[float](
                value=t_val,
                status="available" if t_val is not None else "unavailable",
                provenance=prov,
                error_message=None if t_val is not None else "Temperature unavailable"
            ),
            relative_humidity_percent=EnrichmentDatum[float](
                value=rh_val,
                status="available" if rh_val is not None else "unavailable",
                provenance=prov,
                error_message=None if rh_val is not None else "Humidity unavailable"
            ),
            wind_speed_kmh=EnrichmentDatum[float](
                value=ws_val,
                status="available" if ws_val is not None else "unavailable",
                provenance=prov,
                error_message=None if ws_val is not None else "Wind speed unavailable"
            ),
            wind_gust_kmh=EnrichmentDatum[float](
                value=wg_val,
                status="available" if wg_val is not None else "unavailable",
                provenance=prov,
                error_message=None if wg_val is not None else "Wind gust unavailable"
            ) if wg_val is not None else None,
            wind_direction_degrees=EnrichmentDatum[float](
                value=wd_val,
                status="available" if wd_val is not None else "unavailable",
                provenance=prov,
                error_message=None if wd_val is not None else "Wind direction unavailable"
            ),
            wind_direction_cardinal=EnrichmentDatum[str](
                value=wc_val if wc_val and wc_val != "N/A" else "N/A",
                status="available" if wc_val and wc_val != "N/A" else "unavailable",
                provenance=prov,
                error_message=None if wc_val and wc_val != "N/A" else "Wind heading unavailable"
            ),
            precipitation_mm_24h=EnrichmentDatum[float](
                value=p_val if p_val is not None else 0.0,
                status="available" if p_val is not None else "unavailable",
                provenance=prov,
                error_message=None if p_val is not None else "Precipitation unavailable"
            ),
            fire_weather_index=EnrichmentDatum[float](
                value=fwi_val,
                status="available" if fwi_val is not None else "unavailable",
                provenance=prov,
                error_message=None if fwi_val is not None else "Fire weather index unavailable"
            ) if fwi_val is not None else None
        )


def compute_fire_weather_proxy(
    temperature_c: Optional[float],
    humidity_percent: Optional[float],
    wind_speed_kmh: Optional[float],
    wind_gust_kmh: Optional[float] = None,
    precipitation_mm: Optional[float] = 0.0
) -> Optional[float]:
    """Calculate an empirical fire weather danger proxy rating between 0.0 and 100.0.
    
    SEMANTIC NOTE & PROVENANCE WARNING:
    This calculation is an empirical instantaneous atmospheric hazard proxy combining
    dry bulb temperature, relative humidity deficit, effective wind speed/gusts, and
    recent rainfall damping. It is explicitly NOT the official Canadian Forest Fire Weather
    Index (FWI) System, which requires continuous historical bookkeeping of daily fuel
    moisture codes (Fine Fuel Moisture Code - FFMC, Duff Moisture Code - DMC, and Drought
    Code - DC) across antecedent weeks. No multi-day fuel moisture history is fabricated.
    
    Returns:
        Normalized danger proxy rating [0.0, 100.0], or None if mandatory inputs are missing.
    """
    if temperature_c is None or humidity_percent is None or wind_speed_kmh is None:
        return None

    # 1. Thermal factor (0 to 35 points): baseline at 10°C, max at 45°C
    temp_score = max(0.0, min(35.0, (temperature_c - 5.0) * 0.875))

    # 2. Dryness factor (0 to 35 points): 100% RH -> 0 points, <= 10% RH -> 35 points
    dryness_score = max(0.0, min(35.0, (100.0 - humidity_percent) * 0.388))

    # 3. Wind factor (0 to 30 points): incorporating sustained wind and gusts
    effective_wind = wind_speed_kmh
    if wind_gust_kmh is not None and wind_gust_kmh > wind_speed_kmh:
        effective_wind = 0.7 * wind_speed_kmh + 0.3 * wind_gust_kmh

    wind_score = max(0.0, min(30.0, (effective_wind / 50.0) * 30.0))

    # Composite sum
    raw_fwi = temp_score + dryness_score + wind_score

    # Precipitation dampening
    p_mm = precipitation_mm if precipitation_mm is not None else 0.0
    if p_mm > 0.0:
        dampening = min(0.8, p_mm * 0.15)
        raw_fwi *= (1.0 - dampening)

    return round(max(0.0, min(100.0, raw_fwi)), 1)


# Backward-compatible function alias
compute_fire_weather_index = compute_fire_weather_proxy


def generate_forecast_summary(
    temp_c: Optional[float],
    humidity: Optional[float],
    wind_kmh: Optional[float],
    wind_cardinal: Optional[str],
    fwi: Optional[float],
    weather_code: Optional[int] = None
) -> str:
    """Generate a human-interpretable operational weather summary."""
    if temp_c is None and humidity is None:
        return "Weather telemetry unavailable"

    if fwi is not None:
        if fwi >= 80.0:
            severity = "Critical Fire Weather (Red Flag Conditions)"
        elif fwi >= 60.0:
            severity = "Elevated Fire Danger"
        elif fwi >= 35.0:
            severity = "Moderate Weather Conditions"
        else:
            severity = "Low Atmospheric Fire Hazard"
    else:
        severity = "Atmospheric Observations"

    temp_str = f"{temp_c:.1f}°C" if temp_c is not None else "N/A"
    rh_str = f"{humidity:.0f}%" if humidity is not None else "N/A"
    wind_str = f"{wind_kmh:.1f} km/h {wind_cardinal or ''}".strip() if wind_kmh is not None else "N/A"

    return f"{severity}. Temp: {temp_str}, RH: {rh_str}, Wind: {wind_str}."


def create_unavailable_weather_context(
    reason: str = "Weather telemetry unavailable"
) -> WeatherContext:
    """Construct an explicit unavailable WeatherContext when external data is unreachable.
    
    Zero fabrication: unavailable variables are explicitly None so downstream consumers
    can distinguish genuine 0°C from missing weather context.
    """
    return WeatherContext(
        temperature_celsius=None,
        relative_humidity_percent=None,
        wind_speed_kmh=None,
        wind_gust_kmh=None,
        wind_direction_degrees=None,
        wind_direction_cardinal=None,
        precipitation_mm=None,
        fire_weather_index=None,
        forecast_summary=reason
    )


class OpenMeteoClient:
    """HTTP client for Open-Meteo forecast API with caching, batching, and resilient fallbacks."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cache: Optional["EnrichmentCache"] = None,
        http_client: Optional[httpx.Client] = None,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        self.api_url = api_url or os.getenv("OPEN_METEO_API_URL", DEFAULT_OPEN_METEO_URL)
        self.timeout = timeout
        if cache is None:
            from services.api.enrichment.cache import EnrichmentCache
            cache = EnrichmentCache()
        self.cache = cache
        self._external_client = http_client
        self.max_retries = max_retries

    def _parse_current_block(
        self,
        raw_data: Dict[str, Any],
        source_url: str,
        fetch_time: str
    ) -> WeatherResult:
        """Parse raw Open-Meteo JSON into validated WeatherResult with explicit missing value handling."""
        current = raw_data.get("current", {})
        if not isinstance(current, dict):
            return WeatherResult(
                context=create_unavailable_weather_context("Malformed telemetry payload"),
                status=WeatherStatus.UNAVAILABLE,
                error_message="Missing current telemetry object"
            )

        # Explicit handling: distinguish 0.0 from None
        temp_raw = current.get("temperature_2m")
        temp = float(temp_raw) if temp_raw is not None else None

        rh_raw = current.get("relative_humidity_2m")
        rh = max(0.0, min(100.0, float(rh_raw))) if rh_raw is not None else None

        ws_raw = current.get("wind_speed_10m")
        wind_speed = max(0.0, float(ws_raw)) if ws_raw is not None else None

        wind_gust_raw = current.get("wind_gusts_10m")
        wind_gust = float(wind_gust_raw) if wind_gust_raw is not None else None

        wd_raw = current.get("wind_direction_10m")
        wind_dir = (float(wd_raw) % 360.0) if wd_raw is not None else None
        cardinal = degrees_to_cardinal(wind_dir) if wind_dir is not None else "N/A"

        precip_raw = current.get("precipitation")
        precip = max(0.0, float(precip_raw)) if precip_raw is not None else 0.0

        weather_code = current.get("weather_code")
        elev_raw = raw_data.get("elevation")
        elevation = float(elev_raw) if elev_raw is not None else None

        # Time tracking
        time_raw = current.get("time")
        if time_raw and isinstance(time_raw, str):
            try:
                obs_time = datetime.fromisoformat(time_raw.replace("Z", "+00:00")).isoformat()
            except Exception:
                obs_time = fetch_time
        else:
            obs_time = fetch_time

        fwi = compute_fire_weather_proxy(temp, rh, wind_speed, wind_gust, precip)
        summary = generate_forecast_summary(temp, rh, wind_speed, cardinal, fwi, weather_code)

        context = WeatherContext(
            temperature_celsius=temp,
            relative_humidity_percent=rh,
            wind_speed_kmh=wind_speed,
            wind_gust_kmh=wind_gust,
            wind_direction_degrees=wind_dir,
            wind_direction_cardinal=cardinal,
            precipitation_mm=precip,
            fire_weather_index=fwi,
            forecast_summary=summary
        )

        prov = Provenance(
            provider="Open-Meteo",
            product="Forecast_API",
            observed_at_utc=obs_time,
            fetched_at_utc=fetch_time,
            freshness_state=FreshnessState.FRESH,
            ttl_seconds=3600,
            reference=source_url
        )

        return WeatherResult(
            context=context,
            status=WeatherStatus.AVAILABLE,
            source_url=source_url,
            elevation_meters=elevation,
            observed_at_utc=obs_time,
            fetched_at_utc=fetch_time,
            provenance=prov
        )

    def fetch_weather(
        self,
        latitude: float,
        longitude: float
    ) -> WeatherResult:
        """Fetch current environmental conditions at coordinates."""
        try:
            validate_coordinates(latitude, longitude)
        except ValueError as e:
            return WeatherResult(
                context=create_unavailable_weather_context(f"Invalid coordinates: {e}"),
                status=WeatherStatus.UNAVAILABLE,
                error_message=str(e)
            )

        from services.api.enrichment.cache import generate_cache_key
        # Coordinate grid discretization: 2 decimal places (~1.1 km)
        grid_lat = round(latitude, 2)
        grid_lon = round(longitude, 2)
        cache_key = generate_cache_key("weather", lat=grid_lat, lon=grid_lon)

        # 1. Check valid cache
        cached_data = self.cache.get("weather", cache_key, allow_stale=False)
        if cached_data is not None:
            try:
                context = WeatherContext(**cached_data)
                now_str = now_utc_iso()
                prov = Provenance(
                    provider="Open-Meteo",
                    product="Forecast_API",
                    observed_at_utc=cached_data.get("observed_at_utc", now_str),
                    fetched_at_utc=now_str,
                    freshness_state=FreshnessState.CACHED,
                    ttl_seconds=3600,
                    reference=cache_key
                )
                return WeatherResult(
                    context=context,
                    status=WeatherStatus.CACHED,
                    elevation_meters=cached_data.get("elevation_meters"),
                    observed_at_utc=cached_data.get("observed_at_utc", now_str),
                    fetched_at_utc=now_str,
                    provenance=prov
                )
            except Exception as e:
                logger.warning("Cached weather data failed validation: %s", e)

        # 2. Query Open-Meteo live API with bounded retry
        params = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,weather_code"
        }

        last_error: Optional[str] = None
        fetch_time = now_utc_iso()

        for attempt in range(self.max_retries + 1):
            try:
                client = self._external_client or httpx.Client(timeout=self.timeout)
                try:
                    resp = client.get(self.api_url, params=params)
                    if resp.status_code == 200:
                        raw_data = resp.json()
                        result = self._parse_current_block(raw_data, str(resp.url), fetch_time)

                        # Cache valid context
                        cache_payload = result.context.model_dump()
                        cache_payload["elevation_meters"] = result.elevation_meters
                        cache_payload["observed_at_utc"] = result.observed_at_utc
                        self.cache.set("weather", cache_key, cache_payload)

                        return result
                    elif resp.status_code in (429, 502, 503, 504):
                        last_error = f"HTTP {resp.status_code}"
                        if attempt < self.max_retries:
                            time.sleep(1.0 * (attempt + 1))
                            continue
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                        break
                finally:
                    if self._external_client is None:
                        client.close()

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = f"Network {type(e).__name__}: {e}"
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
            except Exception as e:
                last_error = f"Weather query error: {e}"
                break

        # 3. Fallback to stale cache
        stale_data = self.cache.get("weather", cache_key, allow_stale=True)
        if stale_data is not None:
            try:
                context = WeatherContext(**stale_data)
                now_str = now_utc_iso()
                prov = Provenance(
                    provider="Open-Meteo",
                    product="Forecast_API",
                    observed_at_utc=stale_data.get("observed_at_utc", now_str),
                    fetched_at_utc=now_str,
                    freshness_state=FreshnessState.STALE,
                    ttl_seconds=3600,
                    reference=cache_key
                )
                return WeatherResult(
                    context=context,
                    status=WeatherStatus.CACHED,
                    elevation_meters=stale_data.get("elevation_meters"),
                    observed_at_utc=stale_data.get("observed_at_utc", now_str),
                    fetched_at_utc=now_str,
                    provenance=prov,
                    error_message=f"Live API failed ({last_error}); loaded stale cache"
                )
            except Exception:
                pass

        # 4. Structured unavailable result without zero fabrication
        return WeatherResult(
            context=create_unavailable_weather_context("Weather service unreachable"),
            status=WeatherStatus.UNAVAILABLE,
            error_message=last_error or "External weather service unreachable",
            provenance=Provenance(
                provider="Open-Meteo",
                product="Forecast_API",
                observed_at_utc=fetch_time,
                fetched_at_utc=fetch_time,
                freshness_state=FreshnessState.UNAVAILABLE,
                ttl_seconds=0,
                reference=cache_key
            )
        )

    def fetch_weather_batch(
        self,
        coordinates: Sequence[Tuple[float, float]]
    ) -> List[WeatherResult]:
        """Fetch weather observations for multiple coordinates with multi-location batching.
        
        Args:
            coordinates: Sequence of (latitude, longitude) tuples.
            
        Returns:
            List of WeatherResult objects in identical sequence order.
        """
        if not coordinates:
            return []

        results: List[Optional[WeatherResult]] = [None] * len(coordinates)
        uncached_indices: List[int] = []

        from services.api.enrichment.cache import generate_cache_key

        # 1. Fast cache resolution
        for i, (lat, lon) in enumerate(coordinates):
            try:
                validate_coordinates(lat, lon)
            except ValueError as e:
                results[i] = WeatherResult(
                    context=create_unavailable_weather_context(f"Invalid coordinate: {e}"),
                    status=WeatherStatus.UNAVAILABLE,
                    error_message=str(e)
                )
                continue

            grid_lat = round(lat, 2)
            grid_lon = round(lon, 2)
            cache_key = generate_cache_key("weather", lat=grid_lat, lon=grid_lon)
            cached_data = self.cache.get("weather", cache_key, allow_stale=False)
            if cached_data is not None:
                try:
                    context = WeatherContext(**cached_data)
                    now_str = now_utc_iso()
                    results[i] = WeatherResult(
                        context=context,
                        status=WeatherStatus.CACHED,
                        elevation_meters=cached_data.get("elevation_meters"),
                        observed_at_utc=cached_data.get("observed_at_utc", now_str),
                        fetched_at_utc=now_str,
                        provenance=Provenance(
                            provider="Open-Meteo",
                            product="Forecast_API",
                            observed_at_utc=cached_data.get("observed_at_utc", now_str),
                            fetched_at_utc=now_str,
                            freshness_state=FreshnessState.CACHED,
                            ttl_seconds=3600,
                            reference=cache_key
                        )
                    )
                except Exception:
                    uncached_indices.append(i)
            else:
                uncached_indices.append(i)

        if not uncached_indices:
            return [r for r in results if r is not None]

        # 2. Multi-location Open-Meteo query for uncached coordinates
        # Map unique grid cells to requested coordinate indices
        grid_cell_map: Dict[Tuple[float, float], List[int]] = {}
        for idx in uncached_indices:
            lat, lon = coordinates[idx]
            grid_pt = (round(lat, 2), round(lon, 2))
            grid_cell_map.setdefault(grid_pt, []).append(idx)

        unique_grid_pts = list(grid_cell_map.keys())

        # If only 1 unique point, standard single fetch
        if len(unique_grid_pts) == 1:
            pt_lat, pt_lon = unique_grid_pts[0]
            single_res = self.fetch_weather(pt_lat, pt_lon)
            for idx in grid_cell_map[unique_grid_pts[0]]:
                results[idx] = single_res
            return [r for r in results if r is not None]

        # Format multi-coordinate query
        lats_param = ",".join(f"{pt[0]:.4f}" for pt in unique_grid_pts)
        lons_param = ",".join(f"{pt[1]:.4f}" for pt in unique_grid_pts)

        params = {
            "latitude": lats_param,
            "longitude": lons_param,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,weather_code"
        }

        fetch_time = now_utc_iso()
        batch_success = False

        try:
            client = self._external_client or httpx.Client(timeout=self.timeout * 1.5)
            try:
                resp = client.get(self.api_url, params=params)
                if resp.status_code == 200:
                    raw_data = resp.json()
                    # When multiple locations requested, Open-Meteo returns a list of dictionaries
                    if isinstance(raw_data, list) and len(raw_data) == len(unique_grid_pts):
                        for grid_pt, block in zip(unique_grid_pts, raw_data):
                            item_res = self._parse_current_block(block, str(resp.url), fetch_time)
                            cache_key = generate_cache_key("weather", lat=grid_pt[0], lon=grid_pt[1])
                            cache_payload = item_res.context.model_dump()
                            cache_payload["elevation_meters"] = item_res.elevation_meters
                            cache_payload["observed_at_utc"] = item_res.observed_at_utc
                            self.cache.set("weather", cache_key, cache_payload)

                            for idx in grid_cell_map[grid_pt]:
                                results[idx] = item_res
                        batch_success = True
            finally:
                if self._external_client is None:
                    client.close()
        except Exception as e:
            logger.warning("Multi-location Open-Meteo batch query failed: %s. Falling back to individual fetch.", e)

        # 3. Fallback to individual fetches for any remaining unfilled indices
        if not batch_success:
            for grid_pt, indices in grid_cell_map.items():
                single_res = self.fetch_weather(grid_pt[0], grid_pt[1])
                for idx in indices:
                    results[idx] = single_res

        return [r for r in results if r is not None]
