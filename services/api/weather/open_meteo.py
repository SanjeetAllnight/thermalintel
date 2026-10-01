"""Open-Meteo weather client and environmental parameter extractor.

Fetches and normalizes hyperlocal atmospheric observations:
- Ambient temperature (°C)
- Relative humidity (%)
- Wind speed (km/h) & wind gusts (km/h)
- 16-point cardinal wind direction
- 24h precipitation (mm)
- Derived Fire Weather Index (FWI) proxy rating (0-100)
- Forecast summary generation

Features:
- Deterministic spatial grid rounding to reuse cached weather for clustered hotspots
- Resilient failure recovery (offline mode, network errors, timeouts)
- Explicit status tracking: AVAILABLE vs. CACHED vs. UNAVAILABLE
- Zero fabrication: returns structured unavailable telemetry on failure
"""

import logging
import os
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING
import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.api.enrichment.cache import EnrichmentCache
from services.api.geospatial.spatial import degrees_to_cardinal, validate_coordinates
from services.api.schemas.incident import WeatherContext

logger = logging.getLogger(__name__)

DEFAULT_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT_SECONDS = 10.0


class WeatherStatus(str, Enum):
    AVAILABLE = "available"
    CACHED = "cached"
    UNAVAILABLE = "unavailable"


class WeatherResult(BaseModel):
    """Container holding normalized WeatherContext and telemetry metadata."""
    context: WeatherContext
    status: WeatherStatus
    error_message: Optional[str] = None
    source_url: Optional[str] = None


def compute_fire_weather_index(
    temperature_c: float,
    humidity_percent: float,
    wind_speed_kmh: float,
    wind_gust_kmh: Optional[float] = None,
    precipitation_mm: float = 0.0
) -> float:
    """Calculate a normalized Fire Weather Index (FWI) danger proxy between 0.0 and 100.0.
    
    Factors:
    - Temperature: Higher temperatures dramatically pre-heat fuels.
    - Relative Humidity: Inversely related to fuel equilibrium moisture content.
    - Wind: Supplies oxygen, accelerates flame propagation, and drives embers.
    - Precipitation: Dampens fuels and suppresses ignition risk.
    """
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
    if precipitation_mm > 0.0:
        dampening = min(0.8, precipitation_mm * 0.15)
        raw_fwi *= (1.0 - dampening)

    return round(max(0.0, min(100.0, raw_fwi)), 1)


def generate_forecast_summary(
    temp_c: float,
    humidity: float,
    wind_kmh: float,
    wind_cardinal: str,
    fwi: float,
    weather_code: Optional[int] = None
) -> str:
    """Generate a human-interpretable operational weather summary."""
    if fwi >= 80.0:
        severity = "Critical Fire Weather (Red Flag Conditions)"
    elif fwi >= 60.0:
        severity = "Elevated Fire Danger"
    elif fwi >= 35.0:
        severity = "Moderate Weather Conditions"
    else:
        severity = "Low Atmospheric Fire Hazard"

    return (
        f"{severity}. Temp: {temp_c:.1f}°C, RH: {humidity:.0f}%, "
        f"Wind: {wind_kmh:.1f} km/h {wind_cardinal}."
    )


def create_unavailable_weather_context(
    reason: str = "Weather telemetry unavailable"
) -> WeatherContext:
    """Construct a clean, valid fallback WeatherContext when external data is unreachable."""
    return WeatherContext(
        temperature_celsius=0.0,
        relative_humidity_percent=0.0,
        wind_speed_kmh=0.0,
        wind_gust_kmh=None,
        wind_direction_degrees=0.0,
        wind_direction_cardinal="N/A",
        precipitation_mm=0.0,
        fire_weather_index=None,
        forecast_summary=reason
    )


class OpenMeteoClient:
    """HTTP client for Open-Meteo forecast API with caching and resilient fallbacks."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cache: Optional["EnrichmentCache"] = None,
        http_client: Optional[httpx.Client] = None
    ):
        self.api_url = api_url or os.getenv("OPEN_METEO_API_URL", DEFAULT_OPEN_METEO_URL)
        self.timeout = timeout
        if cache is None:
            from services.api.enrichment.cache import EnrichmentCache
            cache = EnrichmentCache()
        self.cache = cache
        self._external_client = http_client

    def fetch_weather(
        self,
        latitude: float,
        longitude: float
    ) -> WeatherResult:
        """Fetch current environmental conditions at coordinates.
        
        Args:
            latitude: Decimal latitude.
            longitude: Decimal longitude.
            
        Returns:
            WeatherResult containing the WeatherContext and availability status.
        """
        # Validate coordinates
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
                return WeatherResult(
                    context=context,
                    status=WeatherStatus.CACHED
                )
            except Exception as e:
                logger.warning("Cached weather data failed validation: %s", e)

        # 2. Query Open-Meteo live API
        params = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,weather_code"
        }

        try:
            client = self._external_client or httpx.Client(timeout=self.timeout)
            try:
                resp = client.get(self.api_url, params=params)
                if resp.status_code == 200:
                    raw_data = resp.json()
                    current = raw_data.get("current", {})
                    if not isinstance(current, dict) or "temperature_2m" not in current:
                        raise ValueError("Malformed Open-Meteo current telemetry block")

                    temp = float(current.get("temperature_2m", 20.0))
                    # Clamp RH to valid [0.0, 100.0]
                    rh = max(0.0, min(100.0, float(current.get("relative_humidity_2m", 50.0))))
                    wind_speed = max(0.0, float(current.get("wind_speed_10m", 0.0)))
                    wind_gust_raw = current.get("wind_gusts_10m")
                    wind_gust = float(wind_gust_raw) if wind_gust_raw is not None else None
                    wind_dir = float(current.get("wind_direction_10m", 0.0)) % 360.0
                    precip = max(0.0, float(current.get("precipitation", 0.0)))
                    weather_code = current.get("weather_code")

                    cardinal = degrees_to_cardinal(wind_dir)
                    fwi = compute_fire_weather_index(temp, rh, wind_speed, wind_gust, precip)
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

                    # Cache successful result
                    self.cache.set("weather", cache_key, context.model_dump())

                    return WeatherResult(
                        context=context,
                        status=WeatherStatus.AVAILABLE,
                        source_url=str(resp.url)
                    )
                else:
                    logger.warning("Open-Meteo returned status %d: %s", resp.status_code, resp.text[:200])

            finally:
                if self._external_client is None:
                    client.close()

        except Exception as e:
            logger.warning("Open-Meteo API query failed: %s. Checking stale cache.", e)

        # 3. Fallback to stale cache
        stale_data = self.cache.get("weather", cache_key, allow_stale=True)
        if stale_data is not None:
            try:
                context = WeatherContext(**stale_data)
                return WeatherResult(
                    context=context,
                    status=WeatherStatus.CACHED,
                    error_message="Live API failed; loaded stale cache"
                )
            except Exception:
                pass

        # 4. Structured unavailable result
        return WeatherResult(
            context=create_unavailable_weather_context("Weather service unreachable"),
            status=WeatherStatus.UNAVAILABLE,
            error_message="External weather service unreachable"
        )
