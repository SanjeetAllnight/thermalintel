"""Canonical Data Converters between V1 Hotspot and V2 Domain Models.

Provides centralized, bidirectional mapping between legacy V1 composite Hotspots
and decomposed V2 canonical entities (Observation, Assessment, Incident).
"""

import sqlite3
from typing import Optional, Dict, Any

from services.api.schemas.common import RiskLevel, SourceType, DataMode
from services.api.schemas.hotspot import Hotspot
from .observation import Observation
from .assessment import Assessment
from .common import now_utc_iso


def row_to_hotspot_canonical(r: sqlite3.Row) -> Hotspot:
    """Consolidated canonical conversion from an SQLite Row to a validated V1 Hotspot model.
    
    Robust against missing columns and handles enum lookups safely.
    """
    keys = r.keys()
    
    st_val = r["source_type"] if "source_type" in keys else "unknown"
    source_type = (
        SourceType(st_val)
        if st_val in SourceType._value2member_map_
        else SourceType.UNKNOWN
    )

    rl_val = r["risk_level"] if "risk_level" in keys else "medium"
    risk_level = (
        RiskLevel(rl_val)
        if rl_val in RiskLevel._value2member_map_
        else RiskLevel.MEDIUM
    )

    return Hotspot(
        id=r["id"],
        latitude=float(r["latitude"]),
        longitude=float(r["longitude"]),
        brightness=float(r["brightness"]),
        scan=float(r["scan"]) if "scan" in keys and r["scan"] is not None else 0.375,
        track=float(r["track"]) if "track" in keys and r["track"] is not None else 0.375,
        acq_date=r["acq_date"],
        acq_time=r["acq_time"],
        satellite=r["satellite"],
        instrument=r["instrument"] if "instrument" in keys and r["instrument"] else "VIIRS",
        confidence=str(r["confidence"]),
        version=r["version"] if "version" in keys and r["version"] else "2.0NRT",
        bright_t31=float(r["bright_t31"]) if "bright_t31" in keys and r["bright_t31"] is not None else None,
        frp=float(r["frp"]),
        daynight=r["daynight"],
        source_type=source_type,
        risk_score=float(r["risk_score"]) if "risk_score" in keys else 50.0,
        risk_level=risk_level,
        is_anomaly=bool(r["is_anomaly"]) if "is_anomaly" in keys else False,
        cluster_id=r["cluster_id"] if "cluster_id" in keys else None,
        cluster_size=int(r["cluster_size"]) if "cluster_size" in keys and r["cluster_size"] is not None else 1,
        nearest_place=r["nearest_place"] if "nearest_place" in keys else None,
        last_updated=r["last_updated"] if "last_updated" in keys else now_utc_iso(),
    )


def observation_from_hotspot(hotspot: Hotspot) -> Observation:
    """Extract pure sensor evidence from a composite V1 Hotspot into a canonical V2 Observation."""
    # Combine acq_date and acq_time into standardized ISO 8601 UTC string
    time_str = hotspot.acq_time.zfill(4)
    hh = time_str[:2]
    mm = time_str[2:]
    acq_utc = f"{hotspot.acq_date}T{hh}:{mm}:00Z"
    
    return Observation(
        observation_id=f"OBS-{hotspot.id}",
        provider="NASA_FIRMS",
        product=f"{hotspot.instrument}_{hotspot.satellite}_NRT",
        satellite=hotspot.satellite,
        instrument=hotspot.instrument,
        latitude=hotspot.latitude,
        longitude=hotspot.longitude,
        acquisition_time_utc=acq_utc,
        ingestion_time_utc=hotspot.last_updated,
        brightness=hotspot.brightness,
        bright_t31=hotspot.bright_t31,
        scan=hotspot.scan,
        track=hotspot.track,
        frp=hotspot.frp,
        daynight=hotspot.daynight,
        detection_confidence=hotspot.confidence,
        source_attributes={
            "legacy_v1_id": hotspot.id,
            "version": hotspot.version,
        },
        schema_version="2.0",
    )


def hotspot_from_v2(
    observation: Observation,
    assessment: Optional[Assessment] = None,
    nearest_place: Optional[str] = None,
    cluster_id: Optional[str] = None,
    cluster_size: int = 1,
) -> Hotspot:
    """Project a V2 Observation + Assessment back to a backward-compatible V1 Hotspot model."""
    # Extract YYYY-MM-DD and HHMM from acquisition_time_utc
    acq_str = observation.acquisition_time_utc
    date_part = acq_str[:10]
    time_part = acq_str[11:16].replace(":", "") if len(acq_str) >= 16 else "0000"

    source_type = assessment.classification.predicted_source if assessment else SourceType.UNKNOWN
    risk_score = assessment.risk.risk_score if assessment else 50.0
    risk_level = assessment.risk.severity if assessment else RiskLevel.MEDIUM
    is_anomaly = assessment.anomaly.is_anomaly if assessment else False

    # Extract base ID
    obs_id = observation.observation_id
    legacy_id = obs_id[4:] if obs_id.startswith("OBS-") else obs_id

    return Hotspot(
        id=legacy_id,
        latitude=observation.latitude,
        longitude=observation.longitude,
        brightness=observation.brightness,
        scan=observation.scan or 0.375,
        track=observation.track or 0.375,
        acq_date=date_part,
        acq_time=time_part,
        satellite=observation.satellite or "Suomi-NPP",
        instrument=observation.instrument or "VIIRS",
        confidence=observation.detection_confidence,
        version="2.0NRT",
        bright_t31=observation.bright_t31,
        frp=observation.frp,
        daynight=observation.daynight,
        source_type=source_type,
        risk_score=risk_score,
        risk_level=risk_level,
        is_anomaly=is_anomaly,
        cluster_id=cluster_id,
        cluster_size=cluster_size,
        nearest_place=nearest_place,
        last_updated=now_utc_iso(),
    )
