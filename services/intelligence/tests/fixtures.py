"""Deterministic test fixtures representing all 10 required operational scenarios.

1. potential industrial fire
2. vegetation fire
3. persistent industrial heat
4. controlled heat source
5. unknown/ambiguous event
6. highly anomalous event
7. routine low-risk event
8. missing contextual data
9. very small dataset
10. single-hotspot case
"""

from typing import Dict, Any, List, Tuple
from services.intelligence.context import HotspotContext


# 1. Potential Industrial Fire
# High FRP, high brightness, close to industrial infrastructure, sudden emergence
FIXTURE_POTENTIAL_INDUSTRIAL_FIRE = {
    "hotspot": {
        "id": "SCENARIO-01-IND-FIRE",
        "latitude": 29.7214,
        "longitude": -95.1235,
        "frp": 165.0,
        "brightness": 395.0,
        "confidence": "high",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "N",
    },
    "context": HotspotContext(
        distance_to_industrial_m=120.0,
        nearby_industrial_count=4,
        nearest_infrastructure="Houston Petrochemical Refining Complex Unit 4",
        distance_to_infrastructure_m=150.0,
        distance_to_settlement_m=2800.0,
        land_cover="heavy_industrial",
        temperature_c=28.0,
        relative_humidity_pct=35.0,
        wind_speed_kmh=24.0,
        prior_detections_30d=2,  # Sudden surge, not routine flare
        is_recurrent_site=False,
    ),
}

# 2. Vegetation Fire
# High FRP, forest land cover, remote from industry, adverse fire weather, steep slope
FIXTURE_VEGETATION_FIRE = {
    "hotspot": {
        "id": "SCENARIO-02-VEG-FIRE",
        "latitude": 38.7421,
        "longitude": -122.8105,
        "frp": 142.8,
        "brightness": 365.2,
        "confidence": "high",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "daynight": "N",
    },
    "context": HotspotContext(
        land_cover="dense_coniferous_forest",
        distance_to_industrial_m=15000.0,
        distance_to_settlement_m=1200.0,
        nearest_settlement="Cobb Mountain Community",
        distance_to_infrastructure_m=450.0,
        is_protected_area=True,
        slope_degrees=28.5,
        temperature_c=31.5,
        relative_humidity_pct=14.0,
        wind_speed_kmh=42.0,
        prior_detections_30d=1,
        is_recurrent_site=False,
    ),
}

# 3. Persistent Industrial Heat
# Moderate/high FRP, stationary emitter, continuous 30d/90d detections, stable baseline
FIXTURE_PERSISTENT_INDUSTRIAL_HEAT = {
    "hotspot": {
        "id": "SCENARIO-03-PERSISTENT-HEAT",
        "latitude": 30.0123,
        "longitude": -94.2345,
        "frp": 38.0,
        "brightness": 332.0,
        "confidence": "nominal",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "N",
    },
    "context": HotspotContext(
        distance_to_industrial_m=80.0,
        nearby_industrial_count=8,
        nearest_infrastructure="Beaumont Crude Cracker Flare Stack #2",
        distance_to_infrastructure_m=100.0,
        distance_to_settlement_m=8500.0,
        land_cover="industrial",
        temperature_c=24.0,
        relative_humidity_pct=60.0,
        wind_speed_kmh=12.0,
        prior_detections_30d=32,  # Continuous daily detections
        prior_detections_90d=88,
        is_recurrent_site=True,
        persistence_score=0.92,
    ),
}

# 4. Controlled Heat Source
# Low-to-moderate FRP, managed park or agricultural land, low abnormality
FIXTURE_CONTROLLED_HEAT_SOURCE = {
    "hotspot": {
        "id": "SCENARIO-04-CONTROLLED-BURN",
        "latitude": 37.1234,
        "longitude": -119.5678,
        "frp": 18.5,
        "brightness": 318.0,
        "confidence": "nominal",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "D",
    },
    "context": HotspotContext(
        land_cover="managed_conifer_forest",
        is_protected_area=True,
        protected_area_name="Sierra National Forest Unit 12",
        distance_to_settlement_m=12000.0,
        distance_to_industrial_m=35000.0,
        temperature_c=18.0,
        relative_humidity_pct=48.0,
        wind_speed_kmh=10.0,
        prior_detections_30d=2,
        is_recurrent_site=False,
    ),
}

# 5. Unknown / Ambiguous Event
# Very low confidence, contradictory/weak evidence, missing context
FIXTURE_UNKNOWN_AMBIGUOUS_EVENT = {
    "hotspot": {
        "id": "SCENARIO-05-UNKNOWN-AMBIGUOUS",
        "latitude": 42.1234,
        "longitude": -115.5678,
        "frp": 6.2,
        "brightness": 298.0,
        "confidence": "low",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "D",
    },
    "context": HotspotContext(
        land_cover="unknown",
        distance_to_industrial_m=None,
        distance_to_settlement_m=None,
        temperature_c=None,
        relative_humidity_pct=None,
        prior_detections_30d=None,
    ),
}

# 6. Highly Anomalous Event
# Extreme sudden FRP surge at a remote grid cell with 0 prior history
FIXTURE_HIGHLY_ANOMALOUS_EVENT = {
    "hotspot": {
        "id": "SCENARIO-06-HIGH-ANOMALY",
        "latitude": 45.4321,
        "longitude": -121.8765,
        "frp": 320.0,
        "brightness": 445.0,
        "confidence": "high",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "daynight": "N",
    },
    "context": HotspotContext(
        land_cover="mixed_timber",
        distance_to_settlement_m=4200.0,
        distance_to_infrastructure_m=1800.0,
        temperature_c=34.0,
        relative_humidity_pct=11.0,
        wind_speed_kmh=52.0,
        prior_detections_30d=0,
        is_recurrent_site=False,
    ),
}

# 7. Routine Low-Risk Event
# Low FRP, distant from settlements, calm weather, low risk
FIXTURE_ROUTINE_LOW_RISK_EVENT = {
    "hotspot": {
        "id": "SCENARIO-07-ROUTINE-LOW",
        "latitude": 34.1234,
        "longitude": -101.5678,
        "frp": 4.5,
        "brightness": 302.0,
        "confidence": "nominal",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "D",
    },
    "context": HotspotContext(
        land_cover="sparse_shrubland",
        distance_to_settlement_m=22000.0,
        distance_to_infrastructure_m=12000.0,
        temperature_c=16.0,
        relative_humidity_pct=65.0,
        wind_speed_kmh=8.0,
        prior_detections_30d=1,
    ),
}

# 8. Missing Contextual Data
# Bare satellite observation: no OSM, no weather, no historical records
FIXTURE_MISSING_CONTEXTUAL_DATA = {
    "hotspot": {
        "id": "SCENARIO-08-MISSING-CONTEXT",
        "latitude": 36.5432,
        "longitude": -118.4321,
        "frp": 45.0,
        "brightness": 328.0,
        "confidence": "nominal",
    },
    "context": HotspotContext(),  # Empty context
}

# 9. Very Small Dataset (3 items)
FIXTURE_VERY_SMALL_DATASET: List[Dict[str, Any]] = [
    {
        "id": "SMALL-01",
        "frp": 12.0,
        "brightness": 308.0,
        "confidence": "nominal",
    },
    {
        "id": "SMALL-02",
        "frp": 22.0,
        "brightness": 315.0,
        "confidence": "nominal",
    },
    {
        "id": "SMALL-03",
        "frp": 28.0,
        "brightness": 322.0,
        "confidence": "high",
    },
]

# 10. Single-Hotspot Case
FIXTURE_SINGLE_HOTSPOT_CASE = {
    "id": "SINGLE-STANDALONE-001",
    "latitude": 39.1234,
    "longitude": -120.5678,
    "frp": 85.0,
    "brightness": 342.0,
    "confidence": "high",
    "satellite": "Suomi-NPP",
    "instrument": "VIIRS",
    "daynight": "N",
}
