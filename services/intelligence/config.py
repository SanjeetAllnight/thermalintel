"""Configuration, constants, and thresholds for the Thermal Intelligence Engine."""

from enum import Enum
from typing import Dict
from services.api.schemas.common import SourceType, RiskLevel


class ThermalSourceClass(str, Enum):
    """Core intelligence source classes."""
    VEGETATION_FIRE = "VEGETATION_FIRE"
    POTENTIAL_INDUSTRIAL_FIRE = "POTENTIAL_INDUSTRIAL_FIRE"
    CONTROLLED_HEAT_SOURCE = "CONTROLLED_HEAT_SOURCE"
    PERSISTENT_THERMAL_SOURCE = "PERSISTENT_THERMAL_SOURCE"
    UNKNOWN = "UNKNOWN"


# Bidirectional mapping between intelligence classes and frozen SourceType
INTELLIGENCE_CLASS_TO_SOURCE_TYPE: Dict[ThermalSourceClass, SourceType] = {
    ThermalSourceClass.VEGETATION_FIRE: SourceType.WILDFIRE,
    ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE: SourceType.INDUSTRIAL,
    ThermalSourceClass.CONTROLLED_HEAT_SOURCE: SourceType.PRESCRIBED_BURN,
    ThermalSourceClass.PERSISTENT_THERMAL_SOURCE: SourceType.INDUSTRIAL,
    ThermalSourceClass.UNKNOWN: SourceType.UNKNOWN,
}

SOURCE_TYPE_TO_INTELLIGENCE_CLASS: Dict[SourceType, ThermalSourceClass] = {
    SourceType.WILDFIRE: ThermalSourceClass.VEGETATION_FIRE,
    SourceType.INDUSTRIAL: ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE,
    SourceType.PRESCRIBED_BURN: ThermalSourceClass.CONTROLLED_HEAT_SOURCE,
    SourceType.AGRICULTURAL: ThermalSourceClass.CONTROLLED_HEAT_SOURCE,
    SourceType.URBAN: ThermalSourceClass.UNKNOWN,
    SourceType.VOLCANIC: ThermalSourceClass.UNKNOWN,
    SourceType.UNKNOWN: ThermalSourceClass.UNKNOWN,
}


# Risk Thresholds
# 0 - 24: LOW
# 25 - 49: MEDIUM
# 50 - 74: HIGH
# 75 - 100: CRITICAL
RISK_THRESHOLD_CRITICAL: float = 75.0
RISK_THRESHOLD_HIGH: float = 50.0
RISK_THRESHOLD_MEDIUM: float = 25.0
RISK_THRESHOLD_LOW: float = 0.0


def score_to_risk_level(score: float) -> RiskLevel:
    """Map composite risk score (0-100) to RiskLevel with deterministic boundaries."""
    clamped = max(0.0, min(100.0, score))
    if clamped >= RISK_THRESHOLD_CRITICAL:
        return RiskLevel.CRITICAL
    elif clamped >= RISK_THRESHOLD_HIGH:
        return RiskLevel.HIGH
    elif clamped >= RISK_THRESHOLD_MEDIUM:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW


# Composite Risk Component Weights
DEFAULT_WEIGHT_FRP: float = 0.35
DEFAULT_WEIGHT_WEATHER: float = 0.25
DEFAULT_WEIGHT_PROXIMITY: float = 0.20
DEFAULT_WEIGHT_ANOMALY: float = 0.10
DEFAULT_WEIGHT_HISTORY: float = 0.10

# Proximity Thresholds (in meters)
SETTLEMENT_DISTANCE_CRITICAL_M: float = 1500.0
SETTLEMENT_DISTANCE_HIGH_M: float = 3500.0
SETTLEMENT_DISTANCE_MEDIUM_M: float = 7500.0

INFRA_DISTANCE_CRITICAL_M: float = 500.0
INFRA_DISTANCE_HIGH_M: float = 2000.0
INFRA_DISTANCE_MEDIUM_M: float = 5000.0

INDUSTRIAL_PROXIMITY_IMMEDIATE_M: float = 800.0
INDUSTRIAL_PROXIMITY_VICINITY_M: float = 3000.0

# Anomaly Detection Defaults
DEFAULT_BASELINE_FRP_MEAN: float = 25.0
DEFAULT_BASELINE_FRP_STD: float = 20.0
ANOMALY_SIGMA_THRESHOLD: float = 2.0
ANOMALY_HISTORICAL_SUPPRESSION_COUNT: int = 15
ISOLATION_FOREST_ESTIMATORS: int = 50
ISOLATION_FOREST_CONTAMINATION: float = 0.10
RANDOM_STATE: int = 42

# Confidence Defaults
MIN_CONFIDENCE: float = 0.20
MAX_CONFIDENCE: float = 0.99
DEFAULT_UNKNOWN_CONFIDENCE: float = 0.40
