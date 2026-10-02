"""Scenario pack loader and validator for ThermalIntel V2.

Loads, validates, and serializes declarative scenario definitions from JSON/YAML
with comprehensive timestamp and schema integrity verification.
"""

import json
import logging
from pathlib import Path
from typing import Union, Dict, Any, List, Optional
from datetime import datetime, timezone

from scenarios.schema import Scenario

logger = logging.getLogger(__name__)

SCENARIOS_DATA_DIR = Path(__file__).resolve().parent / "data"


def _parse_iso_utc(ts_str: str) -> datetime:
    """Validate and parse an ISO timestamp to a UTC-aware datetime."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        raise ValueError(f"Invalid ISO 8601 UTC timestamp '{ts_str}': {e}") from e


def load_scenario_from_dict(data: Dict[str, Any]) -> Scenario:
    """Validate and load a scenario model from a dictionary."""
    scenario = Scenario.model_validate(data)
    
    # Verify start_time_utc is valid ISO UTC
    _parse_iso_utc(scenario.start_time_utc)
    
    # Verify all observation timestamps
    for obs in scenario.observations:
        _parse_iso_utc(obs.acquisition_time_utc)
        
    # Verify all provider control event timestamps
    for evt in scenario.provider_events:
        _parse_iso_utc(evt.timestamp_utc)
        
    return scenario


def load_scenario_from_file(path: Union[str, Path]) -> Scenario:
    """Load and validate a scenario from a JSON (or YAML if installed) file path."""
    file_path = Path(path).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Scenario file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    
    if file_path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(content)
        except ImportError as exc:
            raise ImportError(
                "PyYAML is not installed. Please use JSON scenario format or install PyYAML."
            ) from exc
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to decode JSON scenario from {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Scenario content must be a JSON object, got {type(data)}")

    return load_scenario_from_dict(data)


def save_scenario_to_file(scenario: Scenario, path: Union[str, Path], indent: int = 2) -> None:
    """Save a scenario model to a formatted JSON file."""
    file_path = Path(path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = scenario.model_dump_json(indent=indent)
    file_path.write_text(json_str, encoding="utf-8")
    logger.info("Saved scenario '%s' to %s", scenario.id, file_path)


def list_available_scenarios(directory: Optional[Union[str, Path]] = None) -> List[Scenario]:
    """Scan and load all scenario files in the given or default scenario data directory."""
    target_dir = Path(directory).resolve() if directory else SCENARIOS_DATA_DIR
    if not target_dir.exists():
        return []

    scenarios: List[Scenario] = []
    # Sort files for deterministic loading order
    for path in sorted(target_dir.glob("*.json")):
        try:
            scenarios.append(load_scenario_from_file(path))
        except Exception as e:
            logger.warning("Failed to load scenario from %s: %e", path, e)
    return scenarios
