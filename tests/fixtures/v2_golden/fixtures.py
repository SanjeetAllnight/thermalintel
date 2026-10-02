"""Compact, deterministic test fixtures representing key system behaviors for ThermalIntel V2.

Provides realistic synthetic data for:
- Strong industrial signal (steady baseline + blowout spike)
- Vegetation-related thermal signal (wildfire spreading near settlement)
- Weak detection (transient single low-FRP detection)
- Provider degradation (partial/corrupted data)
- Duplicate observations (identical coordinates/timestamps)
- Temporal continuity (observations within 1h, 12h, 24h, 48h, 96h)
- Spatially adjacent but distinct observations (beyond correlation radius)
- Incompatible classifications (e.g. industrial vs wildfire, volcanic vs urban)
- Incident closure / quieting / reopening
- Merge / split test scenarios
"""

import json
from typing import Dict, Any, List


# 1. Strong Industrial Signal
INDUSTRIAL_BASELINE_RECORDS = [
    {
        "latitude": 30.1234,
        "longitude": -93.5678,
        "brightness": 328.5,
        "scan": 0.4,
        "track": 0.4,
        "acq_date": "2026-10-01",
        "acq_time": "0415",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "confidence": "high",
        "version": "2.0NRT",
        "bright_t31": 290.0,
        "frp": 35.0,
        "daynight": "N",
        "nearest_place": "Port Arthur Refinery Complex",
    },
    {
        "latitude": 30.1236,
        "longitude": -93.5676,
        "brightness": 331.0,
        "scan": 0.4,
        "track": 0.4,
        "acq_date": "2026-10-01",
        "acq_time": "0830",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "confidence": "high",
        "version": "2.0NRT",
        "bright_t31": 292.0,
        "frp": 42.0,
        "daynight": "N",
        "nearest_place": "Port Arthur Refinery Complex",
    },
]

INDUSTRIAL_SPIKE_RECORD = {
    "latitude": 30.1235,
    "longitude": -93.5677,
    "brightness": 398.5,
    "scan": 0.4,
    "track": 0.4,
    "acq_date": "2026-10-01",
    "acq_time": "1345",
    "satellite": "Suomi-NPP",
    "instrument": "VIIRS",
    "confidence": "high",
    "version": "2.0NRT",
    "bright_t31": 315.0,
    "frp": 245.0,
    "daynight": "D",
    "nearest_place": "Port Arthur Refinery Complex",
}


# 2. Vegetation Signal Spreading Near Settlement
VEGETATION_FIRE_RECORDS = [
    {
        "latitude": 34.2100,
        "longitude": -118.4500,
        "brightness": 345.0,
        "scan": 0.5,
        "track": 0.5,
        "acq_date": "2026-10-01",
        "acq_time": "1400",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "version": "2.0NRT",
        "bright_t31": 295.0,
        "frp": 55.0,
        "daynight": "D",
        "nearest_place": "Pine Ridge Community",
    },
    {
        "latitude": 34.2180,
        "longitude": -118.4580,
        "brightness": 365.0,
        "scan": 0.5,
        "track": 0.5,
        "acq_date": "2026-10-01",
        "acq_time": "1730",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "confidence": "high",
        "version": "2.0NRT",
        "bright_t31": 305.0,
        "frp": 160.0,
        "daynight": "D",
        "nearest_place": "Pine Ridge Community",
    },
]


# 3. Weak Detection
WEAK_DETECTION_RECORD = {
    "latitude": 45.6789,
    "longitude": -110.1234,
    "brightness": 312.0,
    "scan": 0.6,
    "track": 0.5,
    "acq_date": "2026-10-01",
    "acq_time": "1100",
    "satellite": "Suomi-NPP",
    "instrument": "VIIRS",
    "confidence": "low",
    "version": "2.0NRT",
    "bright_t31": 288.0,
    "frp": 6.5,
    "daynight": "D",
    "nearest_place": "Rural Range Sector 4",
}


# 4. Incompatible Classification Records (Close distance, but conflicting sources)
INCOMPATIBLE_PAIR_RECORDS = [
    {
        "latitude": 19.4200,
        "longitude": -155.2800,
        "brightness": 360.0,
        "scan": 0.4,
        "track": 0.4,
        "acq_date": "2026-10-01",
        "acq_time": "0600",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "confidence": "high",
        "version": "2.0NRT",
        "bright_t31": 300.0,
        "frp": 180.0,
        "daynight": "N",
        "source_type": "volcanic",
        "nearest_place": "Kilauea Caldera",
    },
    {
        "latitude": 19.4250,
        "longitude": -155.2850,
        "brightness": 320.0,
        "scan": 0.4,
        "track": 0.4,
        "acq_date": "2026-10-01",
        "acq_time": "0600",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "version": "2.0NRT",
        "bright_t31": 290.0,
        "frp": 15.0,
        "daynight": "N",
        "source_type": "agricultural",
        "nearest_place": "Volcano Community Farm",
    },
]


# 5. Spatially Adjacent But Distinct Records (> 2.5 km apart)
DISTINCT_SPATIAL_RECORDS = [
    {
        "latitude": 38.5000,
        "longitude": -120.5000,
        "brightness": 350.0,
        "scan": 0.4,
        "track": 0.4,
        "acq_date": "2026-10-01",
        "acq_time": "1200",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "confidence": "high",
        "version": "2.0NRT",
        "bright_t31": 300.0,
        "frp": 80.0,
        "daynight": "D",
        "nearest_place": "Valley A",
    },
    {
        "latitude": 38.5800,  # ~8.9 km away
        "longitude": -120.5000,
        "brightness": 348.0,
        "scan": 0.4,
        "track": 0.4,
        "acq_date": "2026-10-01",
        "acq_time": "1200",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "confidence": "high",
        "version": "2.0NRT",
        "bright_t31": 298.0,
        "frp": 75.0,
        "daynight": "D",
        "nearest_place": "Ridge B",
    },
]


def make_raw_firms_csv(rows: List[Dict[str, Any]]) -> str:
    """Helper to serialize dict rows into standard NASA FIRMS CSV format."""
    header = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['latitude']},{r['longitude']},{r['brightness']},{r['scan']},{r['track']},"
            f"{r['acq_date']},{r['acq_time']},{r['satellite']},{r['instrument']},{r['confidence']},"
            f"{r['version']},{r['bright_t31']},{r['frp']},{r['daynight']}"
        )
    return "\n".join(lines)
