"""Configuration, constants, operational thresholds, and methodology definitions for ThermalIntel Intelligence.

Documents:
- Clear separation between provider detection confidence, rule-based classification support,
  statistical anomaly deviation, and composite operational risk score.
- Methodology identifiers: RULE_BASED, BASELINE_STATISTICAL, ISOLATION_FOREST, WEIGHTED_RISK.
- Explicit operational risk weights and threshold boundaries.
"""

from enum import Enum
from typing import Dict, Final

from services.api.schemas.common import SourceType, RiskLevel
from services.intelligence.thresholds import (
    RISK_TIER_CRITICAL,
    RISK_TIER_HIGH,
    RISK_TIER_MEDIUM,
    RISK_TIER_LOW,
    SETTLEMENT_CRITICAL_M,
    SETTLEMENT_HIGH_M,
    SETTLEMENT_MEDIUM_M,
    SETTLEMENT_REMOTE_M,
    INFRA_CRITICAL_M,
    INFRA_HIGH_M,
    INFRA_MEDIUM_M,
    INDUSTRIAL_IMMEDIATE_M,
    INDUSTRIAL_VICINITY_M,
    DEFAULT_BASELINE_FRP_MEAN,
    DEFAULT_BASELINE_FRP_STD,
    ANOMALY_SIGMA_THRESHOLD,
    RECURRENT_FLARE_SUPPRESSION_COUNT,
    ISOLATION_FOREST_ESTIMATORS,
    ISOLATION_FOREST_CONTAMINATION,
    RANDOM_STATE_PINNED,
)


class ThermalSourceClass(str, Enum):
    """Core intelligence source classes for evidence accumulation."""
    VEGETATION_FIRE = "VEGETATION_FIRE"
    POTENTIAL_INDUSTRIAL_FIRE = "POTENTIAL_INDUSTRIAL_FIRE"
    CONTROLLED_HEAT_SOURCE = "CONTROLLED_HEAT_SOURCE"
    PERSISTENT_THERMAL_SOURCE = "PERSISTENT_THERMAL_SOURCE"
    UNKNOWN = "UNKNOWN"


# Bidirectional mapping between internal intelligence classes and frozen SourceType
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


# ==============================================================================
# Methodology Identifiers & Algorithm Versioning
# ==============================================================================
# The system does NOT pretend to have a supervised ML classifier.
# Methodology is strictly rule-based evidence accumulation, statistical baseline,
# and multi-factor weighted risk heuristic.
METHODOLOGY_RULE_BASED: Final[str] = "RULE_BASED"
METHODOLOGY_BASELINE_STATISTICAL: Final[str] = "BASELINE_STATISTICAL"
METHODOLOGY_ISOLATION_FOREST: Final[str] = "ISOLATION_FOREST"
METHODOLOGY_WEIGHTED_RISK: Final[str] = "WEIGHTED_RISK"

METHODOLOGY_V2_COMPOSITE: Final[str] = "RuleBasedEvidence+BaselineStatistical+WeightedRisk"
ALGORITHM_VERSION: Final[str] = "v2.0.0-explainable-rules"


# ==============================================================================
# Risk Thresholds & Operational Boundaries
# ==============================================================================
# 0.0 - 24.9: LOW (Baseline operational conditions; routine monitoring)
# 25.0 - 49.9: MEDIUM (Noticeable heat or dry conditions; elevated advisory)
# 50.0 - 74.9: HIGH (Strong thermal activity with community/asset exposure; suppression readiness)
# 75.0 - 100.0: CRITICAL (Severe threat to human life or high-value infrastructure; immediate response)
RISK_THRESHOLD_CRITICAL: Final[float] = RISK_TIER_CRITICAL
RISK_THRESHOLD_HIGH: Final[float] = RISK_TIER_HIGH
RISK_THRESHOLD_MEDIUM: Final[float] = RISK_TIER_MEDIUM
RISK_THRESHOLD_LOW: Final[float] = RISK_TIER_LOW


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


# ==============================================================================
# Composite Risk Component Weights
# ==============================================================================
# Justification:
# - FRP (0.35): Direct physical measurement of combustion rate and heat release (MW).
# - Weather (0.25): Atmospheric spread accelerators (wind speed, low relative humidity, ambient heat).
# - Proximity (0.20): Spatial vulnerability of human settlements and critical infrastructure.
# - Anomaly (0.10): Relative surge against local/regional baseline.
# - History (0.10): Temporal permanence/recurrence profile (stationary flare vs uncontained burn).
DEFAULT_WEIGHT_FRP: Final[float] = 0.35
DEFAULT_WEIGHT_WEATHER: Final[float] = 0.25
DEFAULT_WEIGHT_PROXIMITY: Final[float] = 0.20
DEFAULT_WEIGHT_ANOMALY: Final[float] = 0.10
DEFAULT_WEIGHT_HISTORY: Final[float] = 0.10

# Proximity Thresholds (in meters) - backward compatibility aliases
SETTLEMENT_DISTANCE_CRITICAL_M: Final[float] = SETTLEMENT_CRITICAL_M
SETTLEMENT_DISTANCE_HIGH_M: Final[float] = SETTLEMENT_HIGH_M
SETTLEMENT_DISTANCE_MEDIUM_M: Final[float] = SETTLEMENT_MEDIUM_M

INFRA_DISTANCE_CRITICAL_M: Final[float] = INFRA_CRITICAL_M
INFRA_DISTANCE_HIGH_M: Final[float] = INFRA_HIGH_M
INFRA_DISTANCE_MEDIUM_M: Final[float] = INFRA_MEDIUM_M

INDUSTRIAL_PROXIMITY_IMMEDIATE_M: Final[float] = INDUSTRIAL_IMMEDIATE_M
INDUSTRIAL_PROXIMITY_VICINITY_M: Final[float] = INDUSTRIAL_VICINITY_M

# Anomaly Detection Defaults
ANOMALY_HISTORICAL_SUPPRESSION_COUNT: Final[int] = RECURRENT_FLARE_SUPPRESSION_COUNT
RANDOM_STATE: Final[int] = RANDOM_STATE_PINNED

# Confidence Bounds
MIN_CONFIDENCE: Final[float] = 0.20
MAX_CONFIDENCE: Final[float] = 0.99
DEFAULT_UNKNOWN_CONFIDENCE: Final[float] = 0.40
