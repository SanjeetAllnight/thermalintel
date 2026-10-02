"""Centralized operational thresholds and constants for the Thermal Intelligence Engine.

Eliminates duplicated threshold logic between risk, classification, baseline,
and explainability subsystems so they cannot silently diverge.
"""

from typing import Final

# ==============================================================================
# 1. Radiometric (Fire Radiative Power & Brightness) Thresholds
# ==============================================================================

# FRP in Megawatts (MW)
FRP_EXTREME_MW: Final[float] = 100.0
FRP_HIGH_MW: Final[float] = 40.0
FRP_MODERATE_MW: Final[float] = 15.0
FRP_LOW_MW: Final[float] = 5.0
FRP_SATURATION_MAX_MW: Final[float] = 250.0  # Logarithmic normalization asymptote

# Brightness Temperature in Kelvin (K)
BRIGHTNESS_EXTREME_K: Final[float] = 380.0
BRIGHTNESS_ELEVATED_K: Final[float] = 340.0
BRIGHTNESS_BASELINE_MIN_K: Final[float] = 290.0
BRIGHTNESS_RANGE_K: Final[float] = 140.0  # 290K to 430K span for normalization

# ==============================================================================
# 2. Environmental & Weather Thresholds
# ==============================================================================

# Wind Speed at 10m in km/h
WIND_CRITICAL_KMH: Final[float] = 40.0
WIND_HIGH_KMH: Final[float] = 30.0
WIND_BREEZY_KMH: Final[float] = 20.0
WIND_CALM_KMH: Final[float] = 10.0
WIND_NORM_MAX_KMH: Final[float] = 55.0

# Relative Humidity in Percent (%)
RH_CRITICAL_PCT: Final[float] = 20.0
RH_DRY_PCT: Final[float] = 35.0
RH_MODERATE_PCT: Final[float] = 50.0

# Ambient Temperature in Celsius (°C)
TEMP_EXTREME_C: Final[float] = 38.0
TEMP_WARM_C: Final[float] = 28.0
TEMP_BASELINE_MIN_C: Final[float] = 12.0
TEMP_RANGE_C: Final[float] = 28.0

# Precipitation in 24h (mm)
PRECIP_DAMPENING_MAX_MM: Final[float] = 10.0

# ==============================================================================
# 3. Geospatial Exposure & Proximity Thresholds (in meters)
# ==============================================================================

# Settlement Proximity (Populated structures, urban boundaries)
SETTLEMENT_CRITICAL_M: Final[float] = 1500.0
SETTLEMENT_HIGH_M: Final[float] = 3500.0
SETTLEMENT_MEDIUM_M: Final[float] = 7500.0
SETTLEMENT_REMOTE_M: Final[float] = 10000.0

# Critical Infrastructure Proximity (Power plants, transit, utilities)
INFRA_CRITICAL_M: Final[float] = 500.0
INFRA_HIGH_M: Final[float] = 2000.0
INFRA_MEDIUM_M: Final[float] = 5000.0

# Industrial Facility Proximity (Refineries, chemical processing, flares)
INDUSTRIAL_IMMEDIATE_M: Final[float] = 800.0
INDUSTRIAL_VICINITY_M: Final[float] = 3000.0

# Topographic Slope in Degrees
SLOPE_CRITICAL_DEG: Final[float] = 30.0
SLOPE_STEEP_DEG: Final[float] = 20.0
SLOPE_MAX_FACTOR_DEG: Final[float] = 45.0

# ==============================================================================
# 4. Historical Recurrence & Baseline Thresholds
# ==============================================================================

# Satellite Overpass Detections within 1km
RECURRENT_MIN_PASSES_30D: Final[int] = 10
RECURRENT_PERSISTENT_PASSES_90D: Final[int] = 25
RECURRENT_FLARE_SUPPRESSION_COUNT: Final[int] = 15

# Baseline Statistical Anomaly Deviations (Sigma / Standard Deviations)
ANOMALY_SIGMA_THRESHOLD: Final[float] = 2.0
ANOMALY_SIGMA_EXTREME: Final[float] = 4.0
ANOMALY_SIGMA_FLARE_SURGE: Final[float] = 3.0

# Default Regional Radiometric Priors (When local site history is absent)
DEFAULT_BASELINE_FRP_MEAN: Final[float] = 25.0
DEFAULT_BASELINE_FRP_STD: Final[float] = 20.0
MIN_BASELINE_STD_EPSILON: Final[float] = 1.0

# Isolation Forest Hyperparameters
ISOLATION_FOREST_MIN_POPULATION: Final[int] = 5
ISOLATION_FOREST_ESTIMATORS: Final[int] = 50
ISOLATION_FOREST_CONTAMINATION: Final[float] = 0.10
RANDOM_STATE_PINNED: Final[int] = 42

# ==============================================================================
# 5. Operational Risk Bounds & Severities
# ==============================================================================

RISK_SCORE_MIN: Final[float] = 0.0
RISK_SCORE_MAX: Final[float] = 100.0

RISK_TIER_CRITICAL: Final[float] = 75.0
RISK_TIER_HIGH: Final[float] = 50.0
RISK_TIER_MEDIUM: Final[float] = 25.0
RISK_TIER_LOW: Final[float] = 0.0
