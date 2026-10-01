"""Feature extraction, normalization, and vectorization for thermal intelligence."""

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from services.intelligence.context import HotspotContext, NormalizedHotspotInput


@dataclass
class FeatureVector:
    """Normalized feature representation of a thermal hotspot and its surrounding context."""

    # Hotspot identifiers
    hotspot_id: str

    # Raw Radiometric
    frp: float
    brightness: float
    confidence_label: str
    satellite_confidence: float  # 0.0 to 1.0
    is_night: Optional[bool]

    # Normalized Radiometric (0.0 to 1.0)
    frp_norm: float
    brightness_norm: float

    # Geospatial
    land_cover: str
    is_vegetation_land_cover: bool
    is_industrial_land_cover: bool
    is_agricultural_land_cover: bool
    is_urban_land_cover: bool
    is_protected_area: bool
    slope_degrees: Optional[float]
    slope_factor: float  # 0.0 to 1.0
    industrial_dist_m: Optional[float]
    industrial_count: Optional[int]
    industrial_proximity_score: float  # 0.0 to 1.0
    settlement_dist_m: Optional[float]
    settlement_proximity_score: float  # 0.0 to 1.0
    infra_dist_m: Optional[float]
    infra_proximity_score: float  # 0.0 to 1.0

    # Historical
    prior_detections_30d: Optional[int]
    prior_detections_90d: Optional[int]
    is_recurrent_site: bool
    persistence_score: float  # 0.0 to 1.0

    # Environmental / Weather
    temperature_c: Optional[float]
    relative_humidity_pct: Optional[float]
    wind_speed_kmh: Optional[float]
    precipitation_mm: Optional[float]
    fire_weather_score: Optional[float]  # 0.0 to 1.0, or None if weather missing

    # Availability Flags
    has_thermal: bool
    has_geospatial: bool
    has_weather: bool
    has_history: bool
    has_industrial_context: bool

    def to_ml_vector(self) -> List[float]:
        """Compact numerical vector for ML anomaly detection / clustering."""
        return [
            self.frp_norm,
            self.brightness_norm,
            self.satellite_confidence,
            self.industrial_proximity_score,
            self.persistence_score,
            self.fire_weather_score if self.fire_weather_score is not None else 0.35,
            self.settlement_proximity_score,
            self.slope_factor,
        ]


class FeatureExtractor:
    """Extracts and normalizes features from raw thermal and context inputs."""

    VEGETATION_KEYWORDS = (
        "forest", "woodland", "trees", "chaparral", "shrub", "bush",
        "grass", "grassland", "jungle", "taiga", "savanna", "scrub",
    )
    INDUSTRIAL_KEYWORDS = (
        "industrial", "refinery", "factory", "plant", "manufacturing",
        "chemical", "smelter", "foundry", "stack", "quarry", "mine", "power_plant",
    )
    AGRICULTURAL_KEYWORDS = (
        "agri", "crop", "cropland", "farmland", "field", "stubble", "paddy", "pasture",
    )
    URBAN_KEYWORDS = (
        "urban", "residential", "commercial", "city", "town", "building",
    )

    @classmethod
    def extract(
        cls,
        hotspot: NormalizedHotspotInput,
        context: Optional[HotspotContext] = None,
    ) -> FeatureVector:
        """Extract a structured FeatureVector from normalized input and context."""
        ctx = context or HotspotContext()

        # Thermal normalization
        frp = max(0.0, hotspot.frp)
        brightness = max(0.0, hotspot.brightness)
        frp_norm = cls._normalize_frp(frp)
        brightness_norm = cls._normalize_brightness(brightness)
        conf_score = max(0.0, min(1.0, hotspot.confidence_score))
        is_night = True if hotspot.daynight == "N" else (False if hotspot.daynight == "D" else None)

        # Land cover parsing
        raw_lc = (ctx.land_cover or "unknown").strip().lower()
        is_veg = any(kw in raw_lc for kw in cls.VEGETATION_KEYWORDS)
        is_ind = any(kw in raw_lc for kw in cls.INDUSTRIAL_KEYWORDS)
        is_agr = any(kw in raw_lc for kw in cls.AGRICULTURAL_KEYWORDS)
        is_urb = any(kw in raw_lc for kw in cls.URBAN_KEYWORDS)

        # Geospatial proximity normalization
        industrial_dist = ctx.distance_to_industrial_m
        ind_prox_score = cls._normalize_proximity(industrial_dist, max_dist=3000.0, immediate_dist=800.0)
        if ctx.nearby_industrial_count and ctx.nearby_industrial_count > 0:
            count_boost = min(0.3, ctx.nearby_industrial_count * 0.1)
            ind_prox_score = min(1.0, ind_prox_score + count_boost)
        if is_ind:
            ind_prox_score = max(ind_prox_score, 0.85)

        settlement_dist = ctx.distance_to_settlement_m
        settlement_prox_score = cls._normalize_proximity(settlement_dist, max_dist=7500.0, immediate_dist=1500.0)

        infra_dist = ctx.distance_to_infrastructure_m
        infra_prox_score = cls._normalize_proximity(infra_dist, max_dist=5000.0, immediate_dist=500.0)

        # Protected area & slope
        is_protected = bool(ctx.is_protected_area)
        slope = ctx.slope_degrees
        slope_factor = min(1.0, max(0.0, slope / 45.0)) if slope is not None else 0.0

        # Historical persistence normalization
        hist_30d = ctx.prior_detections_30d
        hist_90d = ctx.prior_detections_90d
        is_recurrent = bool(ctx.is_recurrent_site or (hist_30d is not None and hist_30d >= 10))

        if ctx.persistence_score is not None:
            persistence_score = min(1.0, max(0.0, ctx.persistence_score))
        elif hist_30d is not None:
            persistence_score = min(1.0, max(0.0, hist_30d / 20.0))
        elif hist_90d is not None:
            persistence_score = min(1.0, max(0.0, hist_90d / 45.0))
        else:
            persistence_score = 0.0

        # Environmental / Weather normalization
        weather_score = cls._compute_fire_weather_score(
            temp_c=ctx.temperature_c,
            rh_pct=ctx.relative_humidity_pct,
            wind_kmh=ctx.wind_speed_kmh,
            precip_mm=ctx.precipitation_mm,
            fwi=ctx.fire_weather_index,
        )

        has_industrial_context = (
            industrial_dist is not None or ctx.nearby_industrial_count is not None or is_ind
        )

        return FeatureVector(
            hotspot_id=hotspot.id,
            frp=frp,
            brightness=brightness,
            confidence_label=hotspot.confidence,
            satellite_confidence=conf_score,
            is_night=is_night,
            frp_norm=round(frp_norm, 4),
            brightness_norm=round(brightness_norm, 4),
            land_cover=raw_lc,
            is_vegetation_land_cover=is_veg,
            is_industrial_land_cover=is_ind,
            is_agricultural_land_cover=is_agr,
            is_urban_land_cover=is_urb,
            is_protected_area=is_protected,
            slope_degrees=slope,
            slope_factor=round(slope_factor, 4),
            industrial_dist_m=industrial_dist,
            industrial_count=ctx.nearby_industrial_count,
            industrial_proximity_score=round(ind_prox_score, 4),
            settlement_dist_m=settlement_dist,
            settlement_proximity_score=round(settlement_prox_score, 4),
            infra_dist_m=infra_dist,
            infra_proximity_score=round(infra_prox_score, 4),
            prior_detections_30d=hist_30d,
            prior_detections_90d=hist_90d,
            is_recurrent_site=is_recurrent,
            persistence_score=round(persistence_score, 4),
            temperature_c=ctx.temperature_c,
            relative_humidity_pct=ctx.relative_humidity_pct,
            wind_speed_kmh=ctx.wind_speed_kmh,
            precipitation_mm=ctx.precipitation_mm,
            fire_weather_score=round(weather_score, 4) if weather_score is not None else None,
            has_thermal=True,
            has_geospatial=ctx.has_geospatial,
            has_weather=ctx.has_weather,
            has_history=ctx.has_history,
            has_industrial_context=has_industrial_context,
        )

    @staticmethod
    def _normalize_frp(frp: float) -> float:
        """Calibrated logarithmic mapping of FRP in MW to [0.0, 1.0]."""
        if frp <= 0.0:
            return 0.0
        # 10 MW -> ~0.45, 50 MW -> ~0.74, 150 MW -> ~0.94, >=250 MW -> 1.0
        return min(1.0, max(0.0, math.log1p(frp) / math.log1p(250.0)))

    @staticmethod
    def _normalize_brightness(brightness: float) -> float:
        """Normalize brightness temperature in Kelvin (typically 290K-450K) to [0.0, 1.0]."""
        if brightness <= 290.0:
            return 0.0
        return min(1.0, max(0.0, (brightness - 290.0) / 140.0))

    @staticmethod
    def _normalize_proximity(
        distance_m: Optional[float],
        max_dist: float,
        immediate_dist: float,
    ) -> float:
        """Score spatial proximity from 0.0 (far away or absent) to 1.0 (immediate contact)."""
        if distance_m is None or distance_m < 0.0:
            return 0.0
        if distance_m <= immediate_dist:
            return 1.0
        if distance_m >= max_dist:
            return 0.0
        # Linear decay between immediate and max distance
        return (max_dist - distance_m) / (max_dist - immediate_dist)

    @staticmethod
    def _compute_fire_weather_score(
        temp_c: Optional[float],
        rh_pct: Optional[float],
        wind_kmh: Optional[float],
        precip_mm: Optional[float],
        fwi: Optional[float],
    ) -> Optional[float]:
        """Compute composite fire weather danger score (0.0 to 1.0), or None if telemetry unavailable."""
        if fwi is not None:
            return min(1.0, max(0.0, fwi / 100.0))

        # Check if we have at least wind or humidity
        if temp_c is None and rh_pct is None and wind_kmh is None:
            return None

        rh_score = 0.5
        if rh_pct is not None:
            # Low humidity (< 20%) is critical
            rh_score = max(0.0, min(1.0, (100.0 - rh_pct) / 85.0))

        wind_score = 0.2
        if wind_kmh is not None:
            wind_score = min(1.0, max(0.0, wind_kmh / 55.0))

        temp_score = 0.3
        if temp_c is not None:
            temp_score = min(1.0, max(0.0, (temp_c - 12.0) / 28.0))

        score = (wind_score * 0.45) + (rh_score * 0.40) + (temp_score * 0.15)

        # Precipitation dampening
        if precip_mm is not None and precip_mm > 0.0:
            dampening = max(0.1, 1.0 - (precip_mm / 10.0))
            score *= dampening

        return min(1.0, max(0.0, score))
