"""Context and input adapters for the Thermal Intelligence Engine.

Provides clean data contracts for Phase 2 geospatial, environmental, and
historical enrichment without requiring Phase 2 implementation code.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union
from services.api.schemas.hotspot import Hotspot


@dataclass
class HotspotContext:
    """Enrichment context encapsulating geospatial, environmental, and historical telemetry."""

    # Geospatial Context
    distance_to_industrial_m: Optional[float] = None
    nearby_industrial_count: Optional[int] = None
    distance_to_settlement_m: Optional[float] = None
    nearest_settlement: Optional[str] = None
    distance_to_infrastructure_m: Optional[float] = None
    nearest_infrastructure: Optional[str] = None
    is_protected_area: Optional[bool] = None
    protected_area_name: Optional[str] = None
    slope_degrees: Optional[float] = None
    elevation_m: Optional[float] = None
    land_cover: Optional[str] = None

    # Environmental / Weather Context
    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_gust_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    precipitation_mm: Optional[float] = None
    fire_weather_index: Optional[float] = None

    # Historical Context
    prior_detections_30d: Optional[int] = None
    prior_detections_90d: Optional[int] = None
    is_recurrent_site: Optional[bool] = None
    recurrent_pattern: Optional[str] = None
    persistence_score: Optional[float] = None
    detection_frequency: Optional[float] = None

    # Custom attributes / extensions
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_geospatial(self) -> bool:
        """Check if any geospatial enrichment signals are available."""
        return any(
            v is not None
            for v in (
                self.distance_to_industrial_m,
                self.nearby_industrial_count,
                self.distance_to_settlement_m,
                self.distance_to_infrastructure_m,
                self.is_protected_area,
                self.land_cover,
            )
        )

    @property
    def has_weather(self) -> bool:
        """Check if any environmental weather signals are available."""
        return any(
            v is not None
            for v in (
                self.temperature_c,
                self.relative_humidity_pct,
                self.wind_speed_kmh,
                self.precipitation_mm,
                self.fire_weather_index,
            )
        )

    @property
    def has_history(self) -> bool:
        """Check if any historical persistence signals are available."""
        return any(
            v is not None
            for v in (
                self.prior_detections_30d,
                self.prior_detections_90d,
                self.is_recurrent_site,
                self.persistence_score,
            )
        )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "HotspotContext":
        """Instantiate HotspotContext from nested or flat dictionary safely."""
        if not data:
            return cls()

        ctx = cls()
        # Handle nested Phase 2 style dict: {"geospatial": {...}, "weather": {...}, "historical": {...}}
        geo = data.get("geospatial") if isinstance(data.get("geospatial"), dict) else {}
        weather = data.get("weather") if isinstance(data.get("weather"), dict) else {}
        hist = data.get("historical") if isinstance(data.get("historical"), dict) else {}

        def get_val(*keys: str, default: Any = None) -> Any:
            """Try top-level keys first, then nested sub-dictionaries."""
            for key in keys:
                if key in data and data[key] is not None:
                    return data[key]
                if key in geo and geo[key] is not None:
                    return geo[key]
                if key in weather and weather[key] is not None:
                    return weather[key]
                if key in hist and hist[key] is not None:
                    return hist[key]
            return default

        # Geospatial mappings
        ctx.distance_to_industrial_m = _to_float(
            get_val("distance_to_industrial_m", "distance_to_industrial_meters", "industrial_dist_m")
        )
        ctx.nearby_industrial_count = _to_int(
            get_val("nearby_industrial_count", "industrial_count")
        )
        ctx.distance_to_settlement_m = _to_float(
            get_val("distance_to_settlement_m", "distance_to_settlement_meters", "settlement_dist_m")
        )
        ctx.nearest_settlement = get_val("nearest_settlement")
        ctx.distance_to_infrastructure_m = _to_float(
            get_val("distance_to_infrastructure_m", "distance_to_infrastructure_meters", "distance_to_infra_m", "infra_dist_m")
        )
        ctx.nearest_infrastructure = get_val("nearest_infrastructure")
        ctx.is_protected_area = _to_bool(get_val("is_protected_area"))
        ctx.protected_area_name = get_val("protected_area_name")
        ctx.slope_degrees = _to_float(get_val("slope_degrees", "slope_deg", "slope"))
        ctx.elevation_m = _to_float(get_val("elevation_meters", "elevation_m", "elevation"))
        ctx.land_cover = get_val("land_cover", "landcover")

        # Weather mappings
        ctx.temperature_c = _to_float(get_val("temperature_celsius", "temperature_c", "temp_c", "temp"))
        ctx.relative_humidity_pct = _to_float(
            get_val("relative_humidity_percent", "relative_humidity_pct", "rh", "humidity")
        )
        ctx.wind_speed_kmh = _to_float(get_val("wind_speed_kmh", "wind_speed"))
        ctx.wind_gust_kmh = _to_float(get_val("wind_gust_kmh", "wind_gust"))
        ctx.wind_direction_deg = _to_float(get_val("wind_direction_degrees", "wind_direction_deg"))
        ctx.precipitation_mm = _to_float(get_val("precipitation_mm", "precipitation"))
        ctx.fire_weather_index = _to_float(get_val("fire_weather_index", "fwi"))

        # Historical mappings
        ctx.prior_detections_30d = _to_int(
            get_val("prior_detections_30d", "historical_recurrence", "historical_detections_30d", "prior_detections")
        )
        ctx.prior_detections_90d = _to_int(get_val("prior_detections_90d"))
        ctx.is_recurrent_site = _to_bool(get_val("is_recurrent_site", "is_recurrent"))
        ctx.recurrent_pattern = get_val("recurrent_pattern")
        ctx.persistence_score = _to_float(get_val("persistence_score", "detection_frequency_score"))
        ctx.detection_frequency = _to_float(get_val("detection_frequency"))

        return ctx


@dataclass
class NormalizedHotspotInput:
    """Standardized representation of a thermal hotspot observation."""

    id: str
    frp: float
    brightness: float
    confidence: str = "nominal"
    confidence_score: float = 0.65
    satellite: str = "VIIRS"
    instrument: str = "VIIRS"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    daynight: Optional[str] = None
    bright_t31: Optional[float] = None
    acq_date: Optional[str] = None
    acq_time: Optional[str] = None

    @classmethod
    def from_input(cls, hotspot: Union[Hotspot, Dict[str, Any], Any], **kwargs: Any) -> "NormalizedHotspotInput":
        """Normalize hotspot from Hotspot Pydantic object, dict, or loose kwargs."""
        if isinstance(hotspot, Hotspot):
            data = hotspot.model_dump()
        elif isinstance(hotspot, dict):
            data = {**hotspot, **kwargs}
        elif hasattr(hotspot, "__dict__"):
            data = {**hotspot.__dict__, **kwargs}
        else:
            data = kwargs

        hotspot_id = str(data.get("id") or data.get("hotspot_id") or "UNKNOWN-HOTSPOT")
        frp = _to_float(data.get("frp"), default=0.0)
        brightness = _to_float(data.get("brightness") or data.get("bright_ti4"), default=310.0)
        raw_conf = data.get("confidence", "nominal")
        conf_str = str(raw_conf).lower()

        # Parse confidence score (0 to 1)
        if conf_str in ("high", "h"):
            conf_score = 0.95
            conf_label = "high"
        elif conf_str in ("low", "l"):
            conf_score = 0.35
            conf_label = "low"
        else:
            try:
                numeric_val = float(conf_str)
                if numeric_val > 1.0:
                    conf_score = max(0.0, min(1.0, numeric_val / 100.0))
                else:
                    conf_score = max(0.0, min(1.0, numeric_val))
                conf_label = "high" if conf_score >= 0.8 else ("low" if conf_score < 0.4 else "nominal")
            except (ValueError, TypeError):
                conf_score = 0.65
                conf_label = "nominal"

        return cls(
            id=hotspot_id,
            frp=max(0.0, frp),
            brightness=max(0.0, brightness),
            confidence=conf_label,
            confidence_score=conf_score,
            satellite=str(data.get("satellite") or "VIIRS"),
            instrument=str(data.get("instrument") or "VIIRS"),
            latitude=_to_float(data.get("latitude")),
            longitude=_to_float(data.get("longitude")),
            daynight=str(data.get("daynight")).upper() if data.get("daynight") else None,
            bright_t31=_to_float(data.get("bright_t31")),
            acq_date=str(data.get("acq_date")) if data.get("acq_date") else None,
            acq_time=str(data.get("acq_time")) if data.get("acq_time") else None,
        )


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        val = float(value)
        return val if not (val != val) else default  # Handles NaN
    except (ValueError, TypeError):
        return default


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _to_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "t")
    return bool(value)
