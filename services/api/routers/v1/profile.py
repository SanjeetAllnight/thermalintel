"""Profile discovery and metadata routes for ThermalIntel V2 API.

Exposes read-only inspection of the active operational domain profile and
all registered profiles in the system.
"""

from typing import Dict, Any, List
from fastapi import APIRouter

from profiles.loader import (
    get_active_profile,
    list_available_profiles,
    get_active_profile_id,
)

router = APIRouter(prefix="/profile", tags=["Profiles"])


@router.get("", summary="Get Active Profile Metadata")
def get_current_profile() -> Dict[str, Any]:
    """Retrieve detailed metadata and configuration highlights of the currently active profile."""
    profile = get_active_profile()
    available = [p["id"] for p in list_available_profiles()]

    return {
        "active_profile": {
            "id": profile.metadata.id,
            "display_name": profile.metadata.display_name,
            "description": profile.metadata.description,
            "version": profile.metadata.version,
            "author": profile.metadata.author,
            "tags": profile.metadata.tags,
            "enabled_providers": profile.providers.enabled_providers,
            "default_source": profile.providers.default_source,
            "supported_classes": profile.taxonomy.supported_classes,
            "default_scenario_id": profile.scenarios.default_scenario_id,
            "risk_weights": profile.risk.weights.model_dump(),
            "incident_clustering": {
                "spatial_threshold_km": profile.incidents.spatial_threshold_km,
                "temporal_window_hours": profile.incidents.temporal_window_hours,
            },
            "alerts": {
                "extreme_frp_threshold": profile.alerts.extreme_frp_threshold,
                "cooldown_seconds": profile.alerts.flood_protection.per_rule_cooldown_seconds,
            },
        },
        "available_profiles": available,
    }


@router.get("s", summary="List All Available Profiles")
def get_all_profiles() -> Dict[str, Any]:
    """List summary metadata for all operational profiles registered on the host."""
    profiles = list_available_profiles()
    active_id = get_active_profile_id()
    return {
        "active_profile_id": active_id,
        "count": len(profiles),
        "profiles": profiles,
    }
