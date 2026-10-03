"""Profile configuration schema models for ThermalIntel V2.

Defines strongly-typed, schema-validated configuration contracts governing
domain-specific operational behavior across:
- Metadata & identity
- Providers & ingestion products
- Taxonomy & category mappings
- Classification deterministic rules & thresholds
- Risk weights, factor thresholds, and source modulations
- Incident spatiotemporal clustering & compatibility rules
- Alert policy, cooldowns, and flood protection
- Domain-specific assets & geospatial context
- Associated replay scenarios
"""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.api.schemas.common import RiskLevel, SourceType


class ProfileMetadata(BaseModel):
    """Authoritative identity and versioning for an operational profile."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^[a-z0-9-]+$", description="Unique lowercase kebab-case profile identifier")
    display_name: str = Field(..., description="Human-readable title of the operational domain")
    description: str = Field(..., description="Scope and operational narrative for this profile")
    version: str = Field(default="1.0.0", description="Semantic version of this profile configuration")
    author: Optional[str] = Field(default="ThermalIntel Team", description="Author or maintainer organization")
    tags: List[str] = Field(default_factory=list, description="Categorical tags for filtering and discovery")


class ProvidersConfig(BaseModel):
    """External provider ingestion and data source declarations."""
    model_config = ConfigDict(extra="forbid")

    enabled_providers: List[str] = Field(
        default_factory=lambda: ["NASA_FIRMS", "OPEN_METEO", "OVERPASS_OSM"],
        description="List of enabled external telemetry providers",
    )
    default_source: str = Field(default="VIIRS_SNPP_NRT", description="Primary satellite product or sensor feed")
    supported_products: List[str] = Field(
        default_factory=lambda: ["VIIRS_SNPP_NRT", "MODIS_NRT"],
        description="Supported satellite sensor feeds or data products",
    )
    provider_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific tuning (e.g. timeouts, rate limits, caching)",
    )


class TaxonomyConfig(BaseModel):
    """Categorical source taxonomy and compatibility mapping."""
    model_config = ConfigDict(extra="forbid")

    supported_classes: List[str] = Field(
        ...,
        description="Internal intelligence classification category identifiers",
    )
    default_class: str = Field(default="UNKNOWN", description="Fallback class for weak or unresolved detections")
    class_to_source_type: Dict[str, SourceType] = Field(
        ...,
        description="Mapping from internal intelligence class to frozen canonical SourceType",
    )
    source_type_to_class: Dict[str, str] = Field(
        ...,
        description="Inverse mapping from canonical SourceType to primary intelligence class",
    )
    incompatible_incident_pairs: List[Tuple[str, str]] = Field(
        default_factory=list,
        description="Pairs of SourceTypes that cannot be merged into the same incident unless co-located",
    )


class ClassificationThresholds(BaseModel):
    """Deterministic radiometric and contextual classification thresholds."""
    model_config = ConfigDict(extra="forbid")

    frp_high_mw: float = Field(default=50.0, gt=0.0, description="High combustion intensity threshold in MW")
    frp_extreme_mw: float = Field(default=100.0, gt=0.0, description="Extreme thermal radiative power in MW")
    frp_moderate_mw: float = Field(default=20.0, gt=0.0, description="Moderate combustion intensity threshold in MW")
    frp_low_mw: float = Field(default=8.0, ge=0.0, description="Low thermal radiance boundary in MW")
    recurrent_min_passes_30d: int = Field(default=8, ge=1, description="Minimum overpasses to qualify as recurrent")
    persistence_score_threshold: float = Field(default=0.50, ge=0.0, le=1.0, description="Score threshold for site permanence")
    wind_high_kmh: float = Field(default=30.0, ge=0.0, description="High wind speed threshold in km/h")
    rh_critical_pct: float = Field(default=25.0, ge=0.0, le=100.0, description="Critical low relative humidity in %")
    industrial_immediate_m: float = Field(default=500.0, gt=0.0, description="Immediate industrial perimeter buffer in meters")
    industrial_vicinity_m: float = Field(default=2000.0, gt=0.0, description="Broader industrial vicinity buffer in meters")


class ClassificationRulesConfig(BaseModel):
    """Rule-based evidence accumulation priors, thresholds, and rule IDs."""
    model_config = ConfigDict(extra="forbid")

    evidence_priors: Dict[str, float] = Field(
        ...,
        description="Initial base evidence scores for each supported intelligence class",
    )
    thresholds: ClassificationThresholds = Field(default_factory=ClassificationThresholds)
    rule_identifiers: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from winning intelligence class to explainable rule identifier string",
    )


class RiskWeights(BaseModel):
    """Contribution weights for the multi-criteria composite risk heuristic."""
    model_config = ConfigDict(extra="forbid")

    frp: float = Field(default=0.35, ge=0.0, le=1.0)
    weather: float = Field(default=0.25, ge=0.0, le=1.0)
    proximity: float = Field(default=0.20, ge=0.0, le=1.0)
    anomaly: float = Field(default=0.10, ge=0.0, le=1.0)
    history: float = Field(default=0.10, ge=0.0, le=1.0)

    @field_validator("history")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        # Sum of weights should be approximately 1.0 (allow small float deviation)
        data = info.data
        if "frp" in data and "weather" in data and "proximity" in data and "anomaly" in data:
            total = data["frp"] + data["weather"] + data["proximity"] + data["anomaly"] + v
            if abs(total - 1.0) > 0.05:
                raise ValueError(f"Sum of risk weights must be approximately 1.0 (got {total:.3f})")
        return v


class RiskThresholds(BaseModel):
    """Categorical risk tier boundaries on the 0-100 operational scale."""
    model_config = ConfigDict(extra="forbid")

    critical: float = Field(default=75.0, ge=0.0, le=100.0)
    high: float = Field(default=50.0, ge=0.0, le=100.0)
    medium: float = Field(default=25.0, ge=0.0, le=100.0)
    low: float = Field(default=0.0, ge=0.0, le=100.0)


class RiskProfileConfig(BaseModel):
    """Operational risk scoring weights, boundaries, and modulation factors."""
    model_config = ConfigDict(extra="forbid")

    weights: RiskWeights = Field(default_factory=RiskWeights)
    thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    source_modulations: Dict[str, float] = Field(
        default_factory=dict,
        description="Multiplicative modulation factors for specific sources (e.g. prescribed burn = 0.75)",
    )
    settlement_distance_critical_m: float = Field(default=1000.0, gt=0.0)
    infra_distance_critical_m: float = Field(default=500.0, gt=0.0)


class FloodProtectionProfileConfig(BaseModel):
    """Alert cooldown, pacing, and flood protection rate limits."""
    model_config = ConfigDict(extra="forbid")

    per_rule_cooldown_seconds: int = Field(default=900, ge=0, description="Minimum delay between fires of the same rule")
    per_incident_cooldown_seconds: int = Field(default=180, ge=0, description="Minimum spacing between alerts on the same incident")
    max_alerts_per_window: int = Field(default=5, ge=1, description="Hard ceiling on alerts per incident per window")
    window_seconds: int = Field(default=3600, ge=10, description="Sliding evaluation window in seconds")


class AlertProfileConfig(BaseModel):
    """Operational alert dispatch policy and protection parameters."""
    model_config = ConfigDict(extra="forbid")

    enabled_rules: List[str] = Field(
        default_factory=lambda: [
            "RULE_NEW_INCIDENT",
            "RULE_INCIDENT_ESCALATED",
            "RULE_INCIDENT_DEESCALATED",
            "RULE_INCIDENT_REOPENED",
            "RULE_INCIDENT_CLOSED",
            "RULE_EXTREME_FRP",
        ],
        description="Active alert rule identifiers evaluated during incident lifecycle transitions",
    )
    extreme_frp_threshold: float = Field(default=100.0, gt=0.0, description="FRP threshold triggering CRITICAL alerts")
    flood_protection: FloodProtectionProfileConfig = Field(default_factory=FloodProtectionProfileConfig)
    alertable_severities: List[str] = Field(
        default_factory=lambda: ["critical", "high"],
        description="Incident severities eligible to trigger new incident notifications",
    )


class IncidentProfileConfig(BaseModel):
    """Spatiotemporal correlation thresholds and incident lifecycle configuration."""
    model_config = ConfigDict(extra="forbid")

    spatial_threshold_km: float = Field(default=2.0, gt=0.0, description="Maximum clustering distance for observations in km")
    temporal_window_hours: float = Field(default=24.0, gt=0.0, description="Maximum time separation between observations in hours")
    merge_distance_km: float = Field(default=3.0, gt=0.0, description="Proximity threshold for merging adjacent incidents in km")
    reopen_window_hours: float = Field(default=72.0, gt=0.0, description="Window within which new activity reopens a resolved incident")
    incompatible_pairs: List[Tuple[str, str]] = Field(
        default_factory=lambda: [
            ("volcanic", "agricultural"),
            ("volcanic", "urban"),
            ("industrial", "wildfire"),
        ],
        description="Pairs of classifications that prevent automatic incident correlation",
    )


class AssetsProfileConfig(BaseModel):
    """Geospatial context and static asset categories for this domain."""
    model_config = ConfigDict(extra="forbid")

    asset_categories: List[str] = Field(
        default_factory=lambda: ["settlement", "infrastructure", "protected_area", "industrial"],
        description="Relevant asset categories queried and scored for spatial proximity",
    )
    static_assets_path: Optional[str] = Field(
        default=None,
        description="Optional path to a domain-specific GeoJSON asset store file",
    )
    proximity_priority: str = Field(
        default="settlement",
        description="Primary asset focus for proximity scoring ('settlement', 'facility', or 'infrastructure')",
    )


class ScenariosProfileConfig(BaseModel):
    """Replay scenarios associated with this operational domain."""
    model_config = ConfigDict(extra="forbid")

    scenario_ids: List[str] = Field(
        default_factory=list,
        description="List of scenario IDs associated with and tested against this profile",
    )
    default_scenario_id: Optional[str] = Field(
        default=None,
        description="Default scenario used for golden replay determinism verification",
    )


class ProfileConfig(BaseModel):
    """Authoritative, comprehensive operational domain configuration profile."""
    model_config = ConfigDict(extra="forbid")

    metadata: ProfileMetadata
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    taxonomy: TaxonomyConfig
    rules: ClassificationRulesConfig
    risk: RiskProfileConfig = Field(default_factory=RiskProfileConfig)
    incidents: IncidentProfileConfig = Field(default_factory=IncidentProfileConfig)
    alerts: AlertProfileConfig = Field(default_factory=AlertProfileConfig)
    assets: AssetsProfileConfig = Field(default_factory=AssetsProfileConfig)
    scenarios: ScenariosProfileConfig = Field(default_factory=ScenariosProfileConfig)
