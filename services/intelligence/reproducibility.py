"""Reproducibility and Audit Lineage for ThermalIntel Intelligence Decisions.

Guarantees:
- Every assessment produces a deterministic SHA-256 input hash over its inputs.
- Same input + same algorithm version + same as_of_utc produces bitwise-identical output.
- Pins random seeds for any stochastic or pseudo-random components.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.intelligence.config import (
    ALGORITHM_VERSION,
    METHODOLOGY_V2_COMPOSITE,
    RANDOM_STATE_PINNED,
)
from services.intelligence.context import HotspotContext, NormalizedHotspotInput


def compute_input_hash(
    hotspot: NormalizedHotspotInput,
    context: Optional[HotspotContext] = None,
) -> str:
    """Compute a deterministic SHA-256 digest of input observation and enrichment context.
    
    Guarantees that any identical set of inputs produces the exact same hash,
    enabling historical verification and replay integrity checks.
    """
    ctx = context or HotspotContext()

    canonical_repr: Dict[str, Any] = {
        "hotspot_id": str(hotspot.id),
        "frp": round(float(hotspot.frp), 4) if hotspot.frp is not None else None,
        "brightness": round(float(hotspot.brightness), 4) if hotspot.brightness is not None else None,
        "satellite": str(hotspot.satellite),
        "instrument": str(hotspot.instrument),
        "confidence": str(hotspot.confidence),
        "daynight": str(hotspot.daynight) if hotspot.daynight else None,
        "latitude": round(float(hotspot.latitude), 6) if hotspot.latitude is not None else None,
        "longitude": round(float(hotspot.longitude), 6) if hotspot.longitude is not None else None,
        # Context
        "land_cover": str(ctx.land_cover) if ctx.land_cover else None,
        "is_protected_area": bool(ctx.is_protected_area) if ctx.is_protected_area is not None else None,
        "settlement_dist_m": round(float(ctx.distance_to_settlement_m), 1) if ctx.distance_to_settlement_m is not None else None,
        "infra_dist_m": round(float(ctx.distance_to_infrastructure_m), 1) if ctx.distance_to_infrastructure_m is not None else None,
        "industrial_dist_m": round(float(ctx.distance_to_industrial_m), 1) if ctx.distance_to_industrial_m is not None else None,
        "slope_degrees": round(float(ctx.slope_degrees), 2) if ctx.slope_degrees is not None else None,
        "temperature_c": round(float(ctx.temperature_c), 2) if ctx.temperature_c is not None else None,
        "relative_humidity_pct": round(float(ctx.relative_humidity_pct), 2) if ctx.relative_humidity_pct is not None else None,
        "wind_speed_kmh": round(float(ctx.wind_speed_kmh), 2) if ctx.wind_speed_kmh is not None else None,
        "precipitation_mm": round(float(ctx.precipitation_mm), 2) if ctx.precipitation_mm is not None else None,
        "fire_weather_index": round(float(ctx.fire_weather_index), 2) if ctx.fire_weather_index is not None else None,
        "prior_detections_30d": int(ctx.prior_detections_30d) if ctx.prior_detections_30d is not None else None,
        "prior_detections_90d": int(ctx.prior_detections_90d) if ctx.prior_detections_90d is not None else None,
        "is_recurrent_site": bool(ctx.is_recurrent_site) if ctx.is_recurrent_site is not None else None,
    }

    serialized = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def generate_assessment_id(target_id: str, input_hash: str) -> str:
    """Generate deterministic assessment identifier linking target entity and input hash."""
    clean_target = target_id.replace("OBS-", "").replace("INC-", "").replace("HOTSPOT-", "")
    short_hash = input_hash[:8].upper()
    return f"ASM-{clean_target}-{short_hash}"


def now_utc_iso() -> str:
    """Return ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()
