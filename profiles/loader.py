"""Deterministic Profile Loader and Active State Manager for ThermalIntel V2.

Guarantees:
- Explicit profile resolution with no silent fallback to unexpected profiles
- Strict schema validation at load time with helpful diagnostics
- Deterministic in-memory caching
- Testable active profile management via environment variable and runtime overrides
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from profiles.schema import ProfileConfig

logger = logging.getLogger(__name__)

PROFILES_ROOT = Path(__file__).resolve().parent
DEFAULT_PROFILE_ID = "wildfire"
ENV_PROFILE_KEY = "THERMALINTEL_PROFILE"

# Process-level cache for validated profile instances
_LOADED_PROFILES: Dict[str, ProfileConfig] = {}
_ACTIVE_PROFILE_OVERRIDE: Optional[str] = None


class ProfileError(Exception):
    """Base exception for profile subsystem errors."""
    pass


class ProfileNotFoundError(ProfileError):
    """Raised when an requested profile ID cannot be resolved on disk."""
    pass


class ProfileValidationError(ProfileError):
    """Raised when a profile configuration file violates the schema contract."""
    pass


def list_available_profiles() -> List[Dict[str, Any]]:
    """Scan the profiles directory and return metadata summaries of all available profiles.
    
    Returns a deterministically sorted list of profile summaries.
    """
    profiles: List[Dict[str, Any]] = []
    
    if not PROFILES_ROOT.exists():
        return profiles

    for child in sorted(PROFILES_ROOT.iterdir(), key=lambda p: p.name):
        if child.is_dir() and not child.name.startswith((".", "_")):
            cfg_file = child / "profile.json"
            if cfg_file.is_file():
                try:
                    profile = load_profile_by_id(child.name)
                    profiles.append({
                        "id": profile.metadata.id,
                        "display_name": profile.metadata.display_name,
                        "description": profile.metadata.description,
                        "version": profile.metadata.version,
                        "tags": profile.metadata.tags,
                        "default_scenario_id": profile.scenarios.default_scenario_id,
                    })
                except Exception as e:
                    logger.warning("Discovered invalid profile in %s: %s", child.name, e)
                    profiles.append({
                        "id": child.name,
                        "display_name": child.name,
                        "description": f"Invalid profile configuration: {e}",
                        "version": "error",
                        "tags": ["invalid"],
                        "default_scenario_id": None,
                    })
    return profiles


def load_profile_by_id(profile_id: str, reload: bool = False) -> ProfileConfig:
    """Load, validate, and cache a profile configuration by its directory identifier.
    
    Args:
        profile_id: Lowercase kebab-case identifier corresponding to profiles/<id>/profile.json.
        reload: If True, bypasses the memory cache and re-reads from disk.
        
    Raises:
        ProfileNotFoundError: If the profile directory or profile.json does not exist.
        ProfileValidationError: If the JSON is invalid or fails schema validation.
    """
    clean_id = profile_id.strip().lower()
    
    if not reload and clean_id in _LOADED_PROFILES:
        return _LOADED_PROFILES[clean_id]

    profile_dir = PROFILES_ROOT / clean_id
    config_path = profile_dir / "profile.json"

    if not config_path.is_file():
        available = [
            d.name for d in sorted(PROFILES_ROOT.iterdir())
            if d.is_dir() and not d.name.startswith((".", "_")) and (d / "profile.json").is_file()
        ]
        raise ProfileNotFoundError(
            f"Profile '{clean_id}' not found at {config_path}. "
            f"Available profiles: {available}"
        )

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ProfileValidationError(
            f"Failed to parse JSON for profile '{clean_id}' at {config_path}: {exc}"
        ) from exc
    except Exception as exc:
        raise ProfileValidationError(
            f"Failed to read profile file '{clean_id}' at {config_path}: {exc}"
        ) from exc

    try:
        profile = ProfileConfig.model_validate(data)
    except Exception as exc:
        raise ProfileValidationError(
            f"Schema validation failed for profile '{clean_id}' ({config_path}): {exc}"
        ) from exc

    if profile.metadata.id != clean_id:
        raise ProfileValidationError(
            f"Profile metadata ID '{profile.metadata.id}' does not match directory name '{clean_id}'"
        )

    _LOADED_PROFILES[clean_id] = profile
    logger.info("Loaded and validated profile '%s' (version %s)", clean_id, profile.metadata.version)
    return profile


def get_active_profile_id() -> str:
    """Determine the currently active profile identifier.
    
    Order of precedence:
    1. Runtime override via set_active_profile(...)
    2. THERMALINTEL_PROFILE environment variable
    3. Default: 'wildfire'
    """
    if _ACTIVE_PROFILE_OVERRIDE is not None:
        return _ACTIVE_PROFILE_OVERRIDE

    env_val = os.getenv(ENV_PROFILE_KEY, "").strip().lower()
    if env_val:
        return env_val

    return DEFAULT_PROFILE_ID


def get_active_profile() -> ProfileConfig:
    """Resolve and return the currently active validated ProfileConfig.
    
    Fails explicitly if the configured active profile cannot be loaded.
    """
    active_id = get_active_profile_id()
    return load_profile_by_id(active_id)


def set_active_profile(profile_id: str) -> ProfileConfig:
    """Explicitly set the active profile for the current process/test execution.
    
    Verifies that the profile can be loaded and validated before switching state.
    """
    profile = load_profile_by_id(profile_id)
    global _ACTIVE_PROFILE_OVERRIDE
    _ACTIVE_PROFILE_OVERRIDE = profile.metadata.id
    logger.info("Active profile switched to '%s'", profile.metadata.id)
    return profile


def reset_active_profile() -> None:
    """Reset any runtime active profile override to restore default/env behavior."""
    global _ACTIVE_PROFILE_OVERRIDE
    _ACTIVE_PROFILE_OVERRIDE = None


def clear_profile_cache() -> None:
    """Clear in-memory profile cache (useful between isolated unit tests)."""
    _LOADED_PROFILES.clear()
