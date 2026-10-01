"""Tests for Phase 4 Incidents Subsystem.

Covers:
1. hotspot -> incident conversion
2. deterministic incident IDs
3. complete incident detail dossier construction
4. repeated event deduplication
5. distinct-event spatial/temporal separation
6. preservation of intelligence explainable factors
7. graceful handling of missing enrichment
8. graceful handling of missing intelligence
Edge cases: 0 risk, 100 risk, single incident, empty set, multiple clusters.
"""

import pytest
from datetime import datetime, timezone

from services.api.schemas.common import RiskLevel, SourceType, DataMode, RiskFactor
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import (
    GeospatialContext,
    WeatherContext,
    HistoricalContext,
    TimelineEvent,
    IncidentDetail,
)
from services.api.schemas.intelligence import (
    ClassificationResult,
    AnomalyResult,
    RiskAssessment,
    IntelligenceResult,
)
from services.api.incidents.models import AggregatedIncident, IncidentStatus
from services.api.incidents.aggregator import IncidentAggregator, haversine_distance_km
from services.api.incidents.service import IncidentService
from services.api.incidents.adapters import InMemoryIncidentAdapter, SQLiteIncidentAdapter


def create_sample_hotspot(
    hid: str = "VIIRS-SNPP-20261001-001",
    lat: float = 38.7421,
    lon: float = -122.8105,
    frp: float = 120.0,
    risk_score: float = 88.0,
    risk_level: RiskLevel = RiskLevel.CRITICAL,
    source_type: SourceType = SourceType.WILDFIRE,
    is_anomaly: bool = True,
    cluster_id: str = "CL-SONOMA-01",
    acq_date: str = "2026-10-01",
    acq_time: str = "0845",
) -> Hotspot:
    """Helper to generate a valid Hotspot instance."""
    return Hotspot(
        id=hid,
        latitude=lat,
        longitude=lon,
        brightness=348.5,
        scan=0.38,
        track=0.36,
        acq_date=acq_date,
        acq_time=acq_time,
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=298.0,
        frp=frp,
        daynight="N",
        source_type=source_type,
        risk_score=risk_score,
        risk_level=risk_level,
        is_anomaly=is_anomaly,
        cluster_id=cluster_id,
        cluster_size=1,
        nearest_place="Geysers Basin, Sonoma County, CA",
        last_updated=f"{acq_date}T08:50:00Z",
    )


def test_hotspot_to_incident_aggregation():
    """Requirement 1: Test hotspot -> incident aggregation."""
    hotspot = create_sample_hotspot()
    aggregator = IncidentAggregator()
    incidents = aggregator.aggregate([hotspot])

    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.primary_hotspot_id == hotspot.id
    assert inc.incident_id == f"INC-{hotspot.id}"
    assert inc.detection_count == 1
    assert inc.risk_score == 88.0
    assert inc.risk_level == RiskLevel.CRITICAL
    assert inc.source_type == SourceType.WILDFIRE
    assert inc.peak_frp == 120.0
    assert inc.status == IncidentStatus.ACTIVE


def test_deterministic_incident_ids():
    """Requirement 2: Incident IDs must be stable and deterministic."""
    h1 = create_sample_hotspot(hid="TEST-HOTSPOT-999")
    aggregator = IncidentAggregator()

    id1 = aggregator.generate_incident_id(h1)
    id2 = aggregator.generate_incident_id(h1)
    assert id1 == id2
    assert id1 == "INC-TEST-HOTSPOT-999"

    # Aggregating twice produces identical incident IDs
    res1 = aggregator.aggregate([h1])
    res2 = aggregator.aggregate([h1])
    assert res1[0].incident_id == res2[0].incident_id


def test_incident_detail_construction():
    """Requirement 3: Incident detail construction with full context."""
    hotspot = create_sample_hotspot()
    geo = GeospatialContext(
        land_cover="coniferous_forest",
        nearest_infrastructure="Highway 101",
        distance_to_infrastructure_meters=800.0,
        nearest_settlement="Geyserville",
        distance_to_settlement_meters=2100.0,
        is_protected_area=True,
        protected_area_name="State Reserve",
        elevation_meters=600.0,
        slope_degrees=18.0,
        fuel_load_estimate="high",
    )
    weather = WeatherContext(
        temperature_celsius=31.0,
        relative_humidity_percent=12.0,
        wind_speed_kmh=42.0,
        wind_gust_kmh=60.0,
        wind_direction_degrees=45.0,
        wind_direction_cardinal="NE",
        precipitation_mm=0.0,
        fire_weather_index=85.0,
        forecast_summary="Red Flag fire warning",
    )
    hist = HistoricalContext(
        prior_detections_30d=1,
        prior_detections_90d=2,
        is_recurrent_site=False,
        recurrent_pattern="none",
        first_detected_date="2026-09-20",
        detection_frequency_score=0.1,
    )
    intel = IntelligenceResult(
        hotspot_id=hotspot.id,
        classification=ClassificationResult(
            predicted_source=SourceType.WILDFIRE,
            confidence=0.95,
            probabilities={"wildfire": 0.95, "other": 0.05},
        ),
        anomaly=AnomalyResult(
            is_anomaly=True,
            anomaly_score=0.92,
            baseline_deviation=4.5,
            anomaly_rationale="Sudden high radiance outlier",
        ),
        risk=RiskAssessment(
            risk_score=88.0,
            risk_level=RiskLevel.CRITICAL,
            frp_component=90.0,
            weather_component=95.0,
            proximity_component=80.0,
            historical_component=10.0,
            explainable_factors=[
                RiskFactor(
                    factor="Extreme Wind Gusts (60 km/h)",
                    weight=0.4,
                    impact=RiskLevel.CRITICAL,
                    description="High wind drives rapid flame propagation.",
                )
            ],
            recommended_action="Dispatch immediate aerial tanker drop.",
        ),
        model_version="v1.0",
        evaluated_at="2026-10-01T08:50:00Z",
    )

    service = IncidentService()
    detail = service.build_incident_detail(
        hotspot=hotspot,
        geospatial=geo,
        weather=weather,
        historical=hist,
        intelligence=intel,
        data_mode=DataMode.LIVE,
    )

    assert isinstance(detail, IncidentDetail)
    assert detail.hotspot.id == hotspot.id
    assert detail.geospatial.nearest_infrastructure == "Highway 101"
    assert detail.weather.fire_weather_index == 85.0
    assert detail.historical.prior_detections_30d == 1
    assert detail.intelligence.risk.risk_score == 88.0
    assert len(detail.intelligence.risk.explainable_factors) == 1
    assert detail.data_mode == DataMode.LIVE
    assert len(detail.timeline) > 0


def test_repeated_event_deduplication():
    """Requirement 4: Repeated detections in close proximity merge into single incident."""
    # Two detections 400m apart within 1 hour
    h1 = create_sample_hotspot(
        hid="VIIRS-001",
        lat=38.7420,
        lon=-122.8100,
        frp=80.0,
        risk_score=75.0,
        acq_time="0800",
    )
    h2 = create_sample_hotspot(
        hid="VIIRS-002",
        lat=38.7440,
        lon=-122.8120,
        frp=140.0,
        risk_score=92.0,
        acq_time="0845",
    )

    aggregator = IncidentAggregator(distance_threshold_km=1.5, time_window_hours=6.0)
    incidents = aggregator.aggregate([h1, h2])

    # Should deduplicate into a single operational incident
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.detection_count == 2
    assert set(inc.hotspot_ids) == {"VIIRS-001", "VIIRS-002"}
    # Representative should be the higher-risk observation h2
    assert inc.primary_hotspot_id == "VIIRS-002"
    assert inc.incident_id == "INC-VIIRS-002"
    assert inc.peak_frp == 140.0
    assert inc.risk_score == 92.0


def test_distinct_event_separation():
    """Requirement 5: Sufficiently separated detections remain distinct incidents."""
    # h1 in California, h2 in Los Angeles (~500 km away)
    h1 = create_sample_hotspot(
        hid="VIIRS-NORTH",
        lat=38.7420,
        lon=-122.8100,
        risk_score=90.0,
        cluster_id="CL-NORTH",
    )
    h2 = create_sample_hotspot(
        hid="VIIRS-SOUTH",
        lat=34.1850,
        lon=-118.1500,
        risk_score=80.0,
        cluster_id="CL-SOUTH",
    )

    aggregator = IncidentAggregator(distance_threshold_km=2.0)
    incidents = aggregator.aggregate([h1, h2])

    assert len(incidents) == 2
    ids = {inc.primary_hotspot_id for inc in incidents}
    assert ids == {"VIIRS-NORTH", "VIIRS-SOUTH"}


def test_preservation_of_intelligence_factors():
    """Requirement 6: IncidentDetail must preserve intelligence factors and recommendations."""
    hotspot = create_sample_hotspot()
    expected_factor = RiskFactor(
        factor="Proximity to High Voltage Grid",
        weight=0.35,
        impact=RiskLevel.HIGH,
        description="Within 250m of 500kV PG&E transmission lines.",
    )
    intel = IntelligenceResult(
        hotspot_id=hotspot.id,
        classification=ClassificationResult(
            predicted_source=SourceType.WILDFIRE,
            confidence=0.91,
            probabilities={"wildfire": 0.91, "other": 0.09},
        ),
        anomaly=AnomalyResult(
            is_anomaly=False,
            anomaly_score=0.2,
            baseline_deviation=0.8,
            anomaly_rationale="Nominal radiance",
        ),
        risk=RiskAssessment(
            risk_score=85.0,
            risk_level=RiskLevel.CRITICAL,
            frp_component=70.0,
            weather_component=80.0,
            proximity_component=90.0,
            historical_component=15.0,
            explainable_factors=[expected_factor],
            recommended_action="De-energize transmission circuit 44B.",
        ),
        model_version="v2.1",
        evaluated_at="2026-10-01T09:00:00Z",
    )

    service = IncidentService()
    detail = service.build_incident_detail(hotspot=hotspot, intelligence=intel)

    # Factors must match verbatim
    factors = detail.intelligence.risk.explainable_factors
    assert len(factors) == 1
    assert factors[0].factor == expected_factor.factor
    assert factors[0].weight == expected_factor.weight
    assert factors[0].description == expected_factor.description
    assert detail.intelligence.risk.recommended_action == "De-energize transmission circuit 44B."
    assert detail.intelligence.risk.risk_score == 85.0


def test_missing_enrichment_graceful_fallback():
    """Requirement 7: Missing geospatial/weather/history enrichment produces valid incident."""
    hotspot = create_sample_hotspot()
    service = IncidentService()

    # Pass None for all enrichment components
    detail = service.build_incident_detail(
        hotspot=hotspot,
        geospatial=None,
        weather=None,
        historical=None,
        intelligence=None,
    )

    assert detail is not None
    assert isinstance(detail.geospatial, GeospatialContext)
    assert isinstance(detail.weather, WeatherContext)
    assert isinstance(detail.historical, HistoricalContext)
    assert isinstance(detail.intelligence, IntelligenceResult)
    # Underlying hotspot data remains intact
    assert detail.hotspot.id == hotspot.id
    assert detail.hotspot.frp == hotspot.frp


def test_missing_intelligence_graceful_fallback():
    """Requirement 8: Missing intelligence produces truthful fallback without altering risk."""
    hotspot = create_sample_hotspot(risk_score=78.5, risk_level=RiskLevel.CRITICAL, frp=155.0)
    service = IncidentService()

    detail = service.build_incident_detail(hotspot=hotspot, intelligence=None)

    assert detail.intelligence is not None
    # Risk score and level must equal hotspot's intrinsic risk
    assert detail.intelligence.risk.risk_score == 78.5
    assert detail.intelligence.risk.risk_level == RiskLevel.CRITICAL
    assert len(detail.intelligence.risk.explainable_factors) >= 1
    assert "155.0 MW" in detail.intelligence.risk.explainable_factors[0].factor


def test_edge_cases_empty_and_boundaries():
    """Edge cases: empty list, zero risk, 100 risk, unknown source."""
    aggregator = IncidentAggregator()
    assert aggregator.aggregate([]) == []

    # Risk score 0
    h_zero = create_sample_hotspot(
        hid="VIIRS-ZERO",
        risk_score=0.0,
        risk_level=RiskLevel.LOW,
        frp=5.0,
        source_type=SourceType.UNKNOWN,
        is_anomaly=False,
    )
    inc_zero = aggregator.aggregate([h_zero])[0]
    assert inc_zero.risk_score == 0.0
    assert inc_zero.status == IncidentStatus.MONITORING

    # Risk score 100
    h_max = create_sample_hotspot(
        hid="VIIRS-MAX",
        risk_score=100.0,
        risk_level=RiskLevel.CRITICAL,
        frp=350.0,
        is_anomaly=True,
    )
    inc_max = aggregator.aggregate([h_max])[0]
    assert inc_max.risk_score == 100.0
    assert inc_max.status == IncidentStatus.ACTIVE


def test_sqlite_incident_adapter_integration():
    """Test SQLiteIncidentAdapter with seeded database."""
    from services.api.database import get_connection, seed_if_empty
    seed_if_empty()
    adapter = SQLiteIncidentAdapter(connection_factory=get_connection)
    hotspots = adapter.list_hotspots()
    assert len(hotspots) > 0
    h = hotspots[0]
    fetched = adapter.get_hotspot_by_id(h.id)
    assert fetched is not None
    assert fetched.id == h.id

    service = IncidentService(adapter=adapter)
    detail = service.get_incident_detail_by_id(h.id)
    assert detail is not None
    assert detail.hotspot.id == h.id

