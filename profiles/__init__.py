"""ThermalIntel V2 Domain Profiles Subsystem.

Provides modular domain configuration for genuinely reusable geospatial thermal intelligence:
- Wildfire & Wildland-Urban Interface (wildfire)
- Industrial & Petrochemical Safety (industrial-safety)
"""

from profiles.schema import (
    ProfileConfig,
    ProfileMetadata,
    ProvidersConfig,
    TaxonomyConfig,
    ClassificationRulesConfig,
    ClassificationThresholds,
    RiskProfileConfig,
    RiskWeights,
    RiskThresholds,
    IncidentProfileConfig,
    AlertProfileConfig,
    FloodProtectionProfileConfig,
    AssetsProfileConfig,
    ScenariosProfileConfig,
)
from profiles.loader import (
    ProfileError,
    ProfileNotFoundError,
    ProfileValidationError,
    list_available_profiles,
    load_profile_by_id,
    get_active_profile_id,
    get_active_profile,
    set_active_profile,
    reset_active_profile,
    clear_profile_cache,
    DEFAULT_PROFILE_ID,
    ENV_PROFILE_KEY,
)

__all__ = [
    # Schemas
    "ProfileConfig",
    "ProfileMetadata",
    "ProvidersConfig",
    "TaxonomyConfig",
    "ClassificationRulesConfig",
    "ClassificationThresholds",
    "RiskProfileConfig",
    "RiskWeights",
    "RiskThresholds",
    "IncidentProfileConfig",
    "AlertProfileConfig",
    "FloodProtectionProfileConfig",
    "AssetsProfileConfig",
    "ScenariosProfileConfig",
    # Loader
    "ProfileError",
    "ProfileNotFoundError",
    "ProfileValidationError",
    "list_available_profiles",
    "load_profile_by_id",
    "get_active_profile_id",
    "get_active_profile",
    "set_active_profile",
    "reset_active_profile",
    "clear_profile_cache",
    "DEFAULT_PROFILE_ID",
    "ENV_PROFILE_KEY",
]
