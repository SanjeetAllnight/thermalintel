"""Weather and environmental enrichment package for ThermalIntel.

Exports Open-Meteo client, Fire Weather Index calculations, and weather schemas.
"""

from .open_meteo import (
    OpenMeteoClient,
    WeatherResult,
    WeatherStatus,
    compute_fire_weather_index,
    generate_forecast_summary,
    create_unavailable_weather_context,
)

__all__ = [
    "OpenMeteoClient",
    "WeatherResult",
    "WeatherStatus",
    "compute_fire_weather_index",
    "generate_forecast_summary",
    "create_unavailable_weather_context",
]
