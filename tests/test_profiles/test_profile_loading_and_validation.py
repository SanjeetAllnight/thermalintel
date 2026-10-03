"""Tests for profile loading, validation, security, and active state management."""

import os
import json
import pytest
from pathlib import Path

from profiles import (
    ProfileConfig,
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


class TestProfileLoadingAndValidation:
    """Validates deterministic loading and error reporting of domain profiles."""

    def setup_method(self):
        reset_active_profile()
        clear_profile_cache()

    def teardown_method(self):
        reset_active_profile()
        clear_profile_cache()

    def test_list_available_profiles_contains_required_profiles(self):
        """Verify discovery returns at least 'wildfire' and 'industrial-safety'."""
        profiles = list_available_profiles()
        ids = [p["id"] for p in profiles]
        
        assert "wildfire" in ids, "wildfire profile must be discovered"
        assert "industrial-safety" in ids, "industrial-safety profile must be discovered"

        # Verify summary contract
        for p in profiles:
            assert "id" in p
            assert "display_name" in p
            assert "description" in p
            assert "version" in p
            assert "tags" in p

    def test_load_wildfire_profile_validates_completely(self):
        """Verify baseline wildfire profile adheres strictly to schema."""
        profile = load_profile_by_id("wildfire")
        assert isinstance(profile, ProfileConfig)
        assert profile.metadata.id == "wildfire"
        assert "Wildfire" in profile.metadata.display_name
        assert profile.metadata.version == "2.0.0"

        # Providers
        assert "NASA_FIRMS" in profile.providers.enabled_providers
        assert profile.providers.default_source == "VIIRS_SNPP_NRT"

        # Taxonomy
        assert "VEGETATION_FIRE" in profile.taxonomy.supported_classes
        assert profile.taxonomy.class_to_source_type["VEGETATION_FIRE"] == "wildfire"

        # Rules
        assert profile.rules.thresholds.frp_high_mw == 40.0
        assert profile.rules.thresholds.recurrent_min_passes_30d == 10
        assert profile.rules.rule_identifiers["VEGETATION_FIRE"] == "RULE_ACTIVE_VEGETATION_WILDFIRE"

        # Risk
        assert profile.risk.weights.frp == 0.35
        assert profile.risk.weights.weather == 0.25
        assert profile.risk.weights.proximity == 0.20
        assert profile.risk.weights.anomaly == 0.10
        assert profile.risk.weights.history == 0.10
        assert profile.risk.thresholds.critical == 75.0
        assert profile.risk.thresholds.high == 50.0

        # Incidents
        assert profile.incidents.spatial_threshold_km == 2.0
        assert profile.incidents.temporal_window_hours == 24.0

        # Alerts
        assert profile.alerts.extreme_frp_threshold == 100.0
        assert profile.alerts.flood_protection.per_rule_cooldown_seconds == 900

    def test_load_industrial_safety_profile_validates_completely(self):
        """Verify second domain industrial-safety profile adheres strictly to schema."""
        profile = load_profile_by_id("industrial-safety")
        assert isinstance(profile, ProfileConfig)
        assert profile.metadata.id == "industrial-safety"
        assert "Industrial" in profile.metadata.display_name
        assert profile.metadata.version == "1.0.0"

        # Providers
        assert "NASA_FIRMS" in profile.providers.enabled_providers
        assert "LOCAL_IR_TELEMETRY" in profile.providers.enabled_providers

        # Taxonomy
        assert "POTENTIAL_INDUSTRIAL_FIRE" in profile.taxonomy.supported_classes
        assert profile.taxonomy.class_to_source_type["POTENTIAL_INDUSTRIAL_FIRE"] == "industrial"

        # Rules
        assert profile.rules.thresholds.frp_high_mw == 25.0
        assert profile.rules.thresholds.industrial_immediate_m == 300.0
        assert profile.rules.rule_identifiers["POTENTIAL_INDUSTRIAL_FIRE"] == "RULE_INDUSTRIAL_HAZARD_SPIKE"

        # Risk
        assert profile.risk.weights.frp == 0.40
        assert profile.risk.weights.proximity == 0.25
        assert profile.risk.thresholds.critical == 70.0

        # Incidents (facility-level spatial scale)
        assert profile.incidents.spatial_threshold_km == 0.6
        assert profile.incidents.temporal_window_hours == 12.0

        # Alerts (faster response pacing)
        assert profile.alerts.extreme_frp_threshold == 40.0
        assert profile.alerts.flood_protection.per_rule_cooldown_seconds == 300

    def test_nonexistent_profile_raises_explicit_not_found_error(self):
        """Verify requesting an unknown profile raises ProfileNotFoundError with available profiles."""
        with pytest.raises(ProfileNotFoundError) as exc_info:
            load_profile_by_id("nuclear-fusion-powerplant")

        err_msg = str(exc_info.value)
        assert "not found" in err_msg
        assert "nuclear-fusion-powerplant" in err_msg
        assert "wildfire" in err_msg
        assert "industrial-safety" in err_msg

    def test_invalid_json_profile_raises_validation_error(self, tmp_path, monkeypatch):
        """Verify malformed JSON or invalid schema raises ProfileValidationError."""
        from profiles import loader

        # Create temporary broken profile directory
        bad_dir = tmp_path / "broken-profile"
        bad_dir.mkdir()
        (bad_dir / "profile.json").write_text("{ broken json : true, }", encoding="utf-8")

        monkeypatch.setattr(loader, "PROFILES_ROOT", tmp_path)

        with pytest.raises(ProfileValidationError) as exc_info:
            loader.load_profile_by_id("broken-profile")
        assert "Failed to parse JSON" in str(exc_info.value)

    def test_schema_violation_raises_validation_error(self, tmp_path, monkeypatch):
        """Verify schema constraint violation (e.g. weights not summing to 1.0) fails validation."""
        from profiles import loader

        # Load valid wildfire dict and corrupt weights
        valid = loader.load_profile_by_id("wildfire").model_dump()
        valid["metadata"]["id"] = "bad-weights"
        valid["risk"]["weights"]["frp"] = 0.90
        valid["risk"]["weights"]["weather"] = 0.90  # sum = 2.30

        bad_dir = tmp_path / "bad-weights"
        bad_dir.mkdir()
        (bad_dir / "profile.json").write_text(json.dumps(valid), encoding="utf-8")

        monkeypatch.setattr(loader, "PROFILES_ROOT", tmp_path)

        with pytest.raises(ProfileValidationError) as exc_info:
            loader.load_profile_by_id("bad-weights")
        assert "Sum of risk weights must be approximately 1.0" in str(exc_info.value)

    def test_active_profile_resolution_order(self, monkeypatch):
        """Verify resolution order: runtime override > env variable > default."""
        # 1. Default when nothing set
        monkeypatch.delenv(ENV_PROFILE_KEY, raising=False)
        reset_active_profile()
        assert get_active_profile_id() == DEFAULT_PROFILE_ID
        assert get_active_profile().metadata.id == "wildfire"

        # 2. Environment variable
        monkeypatch.setenv(ENV_PROFILE_KEY, "industrial-safety")
        assert get_active_profile_id() == "industrial-safety"
        assert get_active_profile().metadata.id == "industrial-safety"

        # 3. Runtime override beats environment variable
        set_active_profile("wildfire")
        assert get_active_profile_id() == "wildfire"
        assert get_active_profile().metadata.id == "wildfire"

        # 4. Reset restores env variable
        reset_active_profile()
        assert get_active_profile_id() == "industrial-safety"

    def test_no_secrets_in_profile_configurations(self):
        """Verify configuration files do not contain passwords, secrets, or API keys."""
        forbidden_keys = ["password", "secret", "api_key", "token", "private_key", "credential"]
        
        for profile_summary in list_available_profiles():
            profile_id = profile_summary["id"]
            if profile_summary.get("version") == "error":
                continue
            profile = load_profile_by_id(profile_id)
            dumped_str = json.dumps(profile.model_dump()).lower()
            
            for fk in forbidden_keys:
                # Ensure no sensitive assignment appears
                assert f'"{fk}":' not in dumped_str
                assert f'"{fk}": "' not in dumped_str
