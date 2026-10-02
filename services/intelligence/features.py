"""Feature extraction, normalization, and vectorization for thermal intelligence.

Features are explicitly organized across five canonical categories:
1. THERMAL: Satellite radiometric measurements, spectral bands, confidence.
2. GEOSPATIAL: Land cover, asset exposure, settlement distance, topography.
3. WEATHER: Ambient atmospheric parameters, wind vectors, fire weather index.
4. HISTORICAL: Multi-temporal overpass recurrence, 30d/90d persistence, site profile.
5. DATA QUALITY: Explicit missingness tracking, completeness score, uncertainty score.

Missing data is explicitly flagged and never disguised as observed zeros.
Feature extraction is strictly deterministic.
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.thresholds import (
    FRP_SATURATION_MAX_MW,
    BRIGHTNESS_BASELINE_MIN_K,
    BRIGHTNESS_RANGE_K,
    SETTLEMENT_CRITICAL_M,
    SETTLEMENT_MEDIUM_M,
    INFRA_CRITICAL_M,
    INFRA_MEDIUM_M,
    INDUSTRIAL_IMMEDIATE_M,
    INDUSTRIAL_VICINITY_M,
    SLOPE_MAX_FACTOR_DEG,
    WIND_NORM_MAX_KMH,
    PRECIP_DAMPENING_MAX_MM,
)


@dataclass
class FeatureVector:
    """Normalized feature representation of a thermal hotspot and its surrounding context."""

    # Identifiers
    hotspot_id: str

    # ==========================================================================
    # 1. THERMAL FEATURES
    # ==========================================================================
    frp: float
    brightness: float
    confidence_label: str
    satellite_confidence: float  # 0.0 to 1.0
    is_night: Optional[bool]
    frp_norm: float  # 0.0 to 1.0
    brightness_norm: float  # 0.0 to 1.0
    bright_t31: Optional[float] = None
    satellite: str = "VIIRS"
    instrument: str = "VIIRS"

    # ==========================================================================
    # 2. GEOSPATIAL FEATURES
    # ==========================================================================
    land_cover: str = "unknown"
    is_vegetation_land_cover: bool = False
    is_industrial_land_cover: bool = False
    is_agricultural_land_cover: bool = False
    is_urban_land_cover: bool = False
    is_protected_area: bool = False
    protected_area_name: Optional[str] = None
    slope_degrees: Optional[float] = None
    slope_factor: float = 0.0  # 0.0 to 1.0
    elevation_m: Optional[float] = None
    industrial_dist_m: Optional[float] = None
    industrial_count: Optional[int] = None
    industrial_proximity_score: float = 0.0  # 0.0 to 1.0
    settlement_dist_m: Optional[float] = None
    settlement_proximity_score: float = 0.0  # 0.0 to 1.0
    infra_dist_m: Optional[float] = None
    infra_proximity_score: float = 0.0  # 0.0 to 1.0

    # ==========================================================================
    # 3. WEATHER FEATURES
    # ==========================================================================
    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_gust_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    precipitation_mm: Optional[float] = None
    fire_weather_index: Optional[float] = None
    fire_weather_score: Optional[float] = None  # None if weather is unavailable

    # ==========================================================================
    # 4. HISTORICAL FEATURES
    # ==========================================================================
    prior_detections_30d: Optional[int] = None
    prior_detections_90d: Optional[int] = None
    is_recurrent_site: bool = False
    recurrent_pattern: Optional[str] = None
    persistence_score: float = 0.0  # 0.0 to 1.0
    detection_frequency: Optional[float] = None

    # ==========================================================================
    # 5. DATA QUALITY & AVAILABILITY
    # ==========================================================================
    has_thermal: bool = True
    has_geospatial: bool = False
    has_weather: bool = False
    has_history: bool = False
    has_industrial_context: bool = False
    missing_features: List[str] = field(default_factory=list)
    available_features: List[str] = field(default_factory=list)
    missing_domains: List[str] = field(default_factory=list)
    completeness_score: float = 1.0  # 0.0 to 1.0
    uncertainty_score: float = 0.0   # 0.0 to 1.0

    @property
    def thermal_features(self) -> Dict[str, Any]:
        """Dictionary of thermal radiometric measurements."""
        return {
            "frp": self.frp,
            "brightness": self.brightness,
            "bright_t31": self.bright_t31,
            "frp_norm": self.frp_norm,
            "brightness_norm": self.brightness_norm,
            "satellite_confidence": self.satellite_confidence,
            "confidence_label": self.confidence_label,
            "is_night": self.is_night,
            "satellite": self.satellite,
            "instrument": self.instrument,
        }

    @property
    def geospatial_features(self) -> Dict[str, Any]:
        """Dictionary of geospatial and topographic features."""
        return {
            "land_cover": self.land_cover,
            "is_vegetation": self.is_vegetation_land_cover,
            "is_industrial": self.is_industrial_land_cover,
            "is_agricultural": self.is_agricultural_land_cover,
            "is_urban": self.is_urban_land_cover,
            "is_protected_area": self.is_protected_area,
            "protected_area_name": self.protected_area_name,
            "settlement_dist_m": self.settlement_dist_m,
            "settlement_proximity_score": self.settlement_proximity_score,
            "infra_dist_m": self.infra_dist_m,
            "infra_proximity_score": self.infra_proximity_score,
            "industrial_dist_m": self.industrial_dist_m,
            "industrial_proximity_score": self.industrial_proximity_score,
            "slope_degrees": self.slope_degrees,
            "slope_factor": self.slope_factor,
            "elevation_m": self.elevation_m,
        }

    @property
    def weather_features(self) -> Dict[str, Any]:
        """Dictionary of atmospheric weather features."""
        return {
            "temperature_c": self.temperature_c,
            "relative_humidity_pct": self.relative_humidity_pct,
            "wind_speed_kmh": self.wind_speed_kmh,
            "wind_gust_kmh": self.wind_gust_kmh,
            "wind_direction_deg": self.wind_direction_deg,
            "precipitation_mm": self.precipitation_mm,
            "fire_weather_index": self.fire_weather_index,
            "fire_weather_score": self.fire_weather_score,
        }

    @property
    def historical_features(self) -> Dict[str, Any]:
        """Dictionary of temporal and historical features."""
        return {
            "prior_detections_30d": self.prior_detections_30d,
            "prior_detections_90d": self.prior_detections_90d,
            "is_recurrent_site": self.is_recurrent_site,
            "recurrent_pattern": self.recurrent_pattern,
            "persistence_score": self.persistence_score,
            "detection_frequency": self.detection_frequency,
        }

    @property
    def data_quality_features(self) -> Dict[str, Any]:
        """Dictionary of data quality and provenance completeness metrics."""
        return {
            "completeness_score": self.completeness_score,
            "uncertainty_score": self.uncertainty_score,
            "missing_features": list(self.missing_features),
            "available_features": list(self.available_features),
            "missing_domains": list(self.missing_domains),
        }

    def to_ml_vector(self) -> List[float]:
        """Compact numerical vector for secondary ML anomaly detection / clustering.
        
        Deterministic: strictly fixed length and reproducible value representation.
        """
        # Neutral imputation (0.35) used exclusively for secondary vector math when weather is missing
        weather_comp = self.fire_weather_score if self.fire_weather_score is not None else 0.35
        return [
            float(self.frp_norm),
            float(self.brightness_norm),
            float(self.satellite_confidence),
            float(self.industrial_proximity_score),
            float(self.persistence_score),
            float(weather_comp),
            float(self.settlement_proximity_score),
            float(self.slope_factor),
        ]


class FeatureExtractor:
    """Extracts, normalizes, and validates features deterministically from raw thermal and context inputs."""

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
        """Extract a structured, categorized FeatureVector from normalized input and context.
        
        Guarantees:
        - Deterministic output.
        - Missing features are explicitly recorded in missing_features, not faked as zeros.
        """
        ctx = context or HotspotContext()

        # Track explicit availability
        available_features: List[str] = ["thermal.frp", "thermal.brightness", "thermal.confidence"]
        missing_features: List[str] = []
        missing_domains: List[str] = []

        # 1. Thermal Normalization
        frp = max(0.0, float(hotspot.frp)) if hotspot.frp is not None else 0.0
        brightness = max(0.0, float(hotspot.brightness)) if hotspot.brightness is not None else 310.0
        frp_norm = cls._normalize_frp(frp)
        brightness_norm = cls._normalize_brightness(brightness)
        conf_score = max(0.0, min(1.0, float(hotspot.confidence_score)))
        is_night = True if hotspot.daynight == "N" else (False if hotspot.daynight == "D" else None)

        if hotspot.bright_t31 is not None:
            available_features.append("thermal.bright_t31")
        else:
            missing_features.append("thermal.bright_t31")

        # 2. Land Cover Parsing
        raw_lc = (ctx.land_cover or "unknown").strip().lower()
        if raw_lc != "unknown":
            available_features.append("geospatial.land_cover")
        else:
            missing_features.append("geospatial.land_cover")

        is_veg = any(kw in raw_lc for kw in cls.VEGETATION_KEYWORDS)
        is_ind = any(kw in raw_lc for kw in cls.INDUSTRIAL_KEYWORDS)
        is_agr = any(kw in raw_lc for kw in cls.AGRICULTURAL_KEYWORDS)
        is_urb = any(kw in raw_lc for kw in cls.URBAN_KEYWORDS)

        # 3. Geospatial Proximities
        industrial_dist = ctx.distance_to_industrial_m
        if industrial_dist is not None:
            available_features.append("geospatial.distance_to_industrial_m")
            ind_prox_score = cls._normalize_proximity(
                industrial_dist,
                max_dist=INDUSTRIAL_VICINITY_M,
                immediate_dist=INDUSTRIAL_IMMEDIATE_M,
            )
        else:
            missing_features.append("geospatial.distance_to_industrial_m")
            ind_prox_score = 0.0

        if ctx.nearby_industrial_count is not None and ctx.nearby_industrial_count > 0:
            count_boost = min(0.3, ctx.nearby_industrial_count * 0.1)
            ind_prox_score = min(1.0, ind_prox_score + count_boost)
            available_features.append("geospatial.nearby_industrial_count")
        if is_ind:
            ind_prox_score = max(ind_prox_score, 0.85)

        settlement_dist = ctx.distance_to_settlement_m
        if settlement_dist is not None:
            available_features.append("geospatial.distance_to_settlement_m")
            settlement_prox_score = cls._normalize_proximity(
                settlement_dist,
                max_dist=SETTLEMENT_MEDIUM_M,
                immediate_dist=SETTLEMENT_CRITICAL_M,
            )
        else:
            missing_features.append("geospatial.distance_to_settlement_m")
            settlement_prox_score = 0.0

        infra_dist = ctx.distance_to_infrastructure_m
        if infra_dist is not None:
            available_features.append("geospatial.distance_to_infrastructure_m")
            infra_prox_score = cls._normalize_proximity(
                infra_dist,
                max_dist=INFRA_MEDIUM_M,
                immediate_dist=INFRA_CRITICAL_M,
            )
        else:
            missing_features.append("geospatial.distance_to_infrastructure_m")
            infra_prox_score = 0.0

        # Protected Area & Slope
        is_protected = bool(ctx.is_protected_area)
        if ctx.is_protected_area is not None:
            available_features.append("geospatial.is_protected_area")

        slope = ctx.slope_degrees
        if slope is not None:
            available_features.append("geospatial.slope_degrees")
            slope_factor = min(1.0, max(0.0, slope / SLOPE_MAX_FACTOR_DEG))
        else:
            missing_features.append("geospatial.slope_degrees")
            slope_factor = 0.0

        # 4. Historical Persistence
        hist_30d = ctx.prior_detections_30d
        hist_90d = ctx.prior_detections_90d
        if hist_30d is not None:
            available_features.append("historical.prior_detections_30d")
        else:
            missing_features.append("historical.prior_detections_30d")

        if hist_90d is not None:
            available_features.append("historical.prior_detections_90d")
        else:
            missing_features.append("historical.prior_detections_90d")

        is_recurrent = bool(ctx.is_recurrent_site or (hist_30d is not None and hist_30d >= 10))

        if ctx.persistence_score is not None:
            persistence_score = min(1.0, max(0.0, float(ctx.persistence_score)))
            available_features.append("historical.persistence_score")
        elif hist_30d is not None:
            persistence_score = min(1.0, max(0.0, hist_30d / 20.0))
        elif hist_90d is not None:
            persistence_score = min(1.0, max(0.0, hist_90d / 45.0))
        else:
            persistence_score = 0.0

        # 5. Environmental / Weather Normalization
        weather_score = cls._compute_fire_weather_score(
            temp_c=ctx.temperature_c,
            rh_pct=ctx.relative_humidity_pct,
            wind_kmh=ctx.wind_speed_kmh,
            precip_mm=ctx.precipitation_mm,
            fwi=ctx.fire_weather_index,
        )

        for w_field, val in [
            ("weather.temperature_c", ctx.temperature_c),
            ("weather.relative_humidity_pct", ctx.relative_humidity_pct),
            ("weather.wind_speed_kmh", ctx.wind_speed_kmh),
            ("weather.precipitation_mm", ctx.precipitation_mm),
        ]:
            if val is not None:
                available_features.append(w_field)
            else:
                missing_features.append(w_field)

        # Domain Availability Tracking
        has_geospatial = ctx.has_geospatial
        has_weather = ctx.has_weather
        has_history = ctx.has_history
        has_industrial_context = (
            industrial_dist is not None or ctx.nearby_industrial_count is not None or is_ind
        )

        if not has_geospatial:
            missing_domains.append("geospatial")
        if not has_weather:
            missing_domains.append("weather")
        if not has_history:
            missing_domains.append("historical")

        # Completeness & Uncertainty Scores
        # 4 Core Domains: Thermal (0.25), Geospatial (0.25), Weather (0.25), History (0.25)
        completeness = 0.25  # Satellite radiometric is always present
        if has_geospatial:
            completeness += 0.25
        if has_weather:
            completeness += 0.25
        if has_history:
            completeness += 0.25

        completeness_score = round(completeness, 2)
        # Uncertainty rises if context is missing or provider confidence is low
        uncertainty = 1.0 - completeness_score
        if conf_score < 0.5:
            uncertainty += 0.15
        uncertainty_score = round(min(1.0, max(0.0, uncertainty)), 2)

        return FeatureVector(
            hotspot_id=hotspot.id,
            frp=frp,
            brightness=brightness,
            confidence_label=hotspot.confidence,
            satellite_confidence=conf_score,
            is_night=is_night,
            frp_norm=round(frp_norm, 4),
            brightness_norm=round(brightness_norm, 4),
            bright_t31=hotspot.bright_t31,
            satellite=hotspot.satellite,
            instrument=hotspot.instrument,
            land_cover=raw_lc,
            is_vegetation_land_cover=is_veg,
            is_industrial_land_cover=is_ind,
            is_agricultural_land_cover=is_agr,
            is_urban_land_cover=is_urb,
            is_protected_area=is_protected,
            protected_area_name=ctx.protected_area_name,
            slope_degrees=slope,
            slope_factor=round(slope_factor, 4),
            elevation_m=ctx.elevation_m,
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
            recurrent_pattern=ctx.recurrent_pattern,
            persistence_score=round(persistence_score, 4),
            detection_frequency=ctx.detection_frequency,
            temperature_c=ctx.temperature_c,
            relative_humidity_pct=ctx.relative_humidity_pct,
            wind_speed_kmh=ctx.wind_speed_kmh,
            wind_gust_kmh=ctx.wind_gust_kmh,
            wind_direction_deg=ctx.wind_direction_deg,
            precipitation_mm=ctx.precipitation_mm,
            fire_weather_index=ctx.fire_weather_index,
            fire_weather_score=round(weather_score, 4) if weather_score is not None else None,
            has_thermal=True,
            has_geospatial=has_geospatial,
            has_weather=has_weather,
            has_history=has_history,
            has_industrial_context=has_industrial_context,
            missing_features=sorted(missing_features),
            available_features=sorted(available_features),
            missing_domains=sorted(missing_domains),
            completeness_score=completeness_score,
            uncertainty_score=uncertainty_score,
        )

    @staticmethod
    def _normalize_frp(frp: float) -> float:
        """Calibrated logarithmic mapping of FRP in MW to [0.0, 1.0]."""
        if frp <= 0.0:
            return 0.0
        return min(1.0, max(0.0, math.log1p(frp) / math.log1p(FRP_SATURATION_MAX_MW)))

    @staticmethod
    def _normalize_brightness(brightness: float) -> float:
        """Normalize brightness temperature in Kelvin (typically 290K-430K) to [0.0, 1.0]."""
        if brightness <= BRIGHTNESS_BASELINE_MIN_K:
            return 0.0
        return min(1.0, max(0.0, (brightness - BRIGHTNESS_BASELINE_MIN_K) / BRIGHTNESS_RANGE_K))

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
        return (max_dist - distance_m) / (max_dist - immediate_dist)

    @staticmethod
    def _compute_fire_weather_score(
        temp_c: Optional[float],
        rh_pct: Optional[float],
        wind_kmh: Optional[float],
        precip_mm: Optional[float],
        fwi: Optional[float],
    ) -> Optional[float]:
        """Compute composite fire weather danger score (0.0 to 1.0), or None if weather telemetry is unavailable."""
        if fwi is not None:
            return min(1.0, max(0.0, fwi / 100.0))

        if temp_c is None and rh_pct is None and wind_kmh is None:
            return None

        rh_score = 0.5
        if rh_pct is not None:
            # Low humidity (< 20%) is critical
            rh_score = max(0.0, min(1.0, (100.0 - rh_pct) / 85.0))

        wind_score = 0.2
        if wind_kmh is not None:
            wind_score = min(1.0, max(0.0, wind_kmh / WIND_NORM_MAX_KMH))

        temp_score = 0.3
        if temp_c is not None:
            temp_score = min(1.0, max(0.0, (temp_c - 12.0) / 28.0))

        score = (wind_score * 0.45) + (rh_score * 0.40) + (temp_score * 0.15)

        # Precipitation dampening
        if precip_mm is not None and precip_mm > 0.0:
            dampening = max(0.1, 1.0 - (precip_mm / PRECIP_DAMPENING_MAX_MM))
            score *= dampening

        return min(1.0, max(0.0, score))
