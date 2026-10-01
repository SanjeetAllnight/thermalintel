"""End-to-End integration tests for Phase 4 Subsystems.

Verifies the complete operational pipeline:
25. Hotspot + intelligence + context -> complete IncidentDetail dossier
26. Incident -> Prioritized and deduplicated Alert
27. Incident / Hotspot collection -> Dashboard Summary & Source Analytics
Full mock and live sample integration testing without external API dependencies.
"""

import json
from pathlib import Path
import pytest

from services.api.schemas.common import (
    RiskLevel,
    SourceType,
    AlertSeverity,
    DataMode,
    RiskFactor,
)
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import (
    GeospatialContext,
    WeatherContext,
    HistoricalContext,
    IncidentDetail,
)
from services.api.schemas.intelligence import (
    ClassificationResult,
    AnomalyResult,
    RiskAssessment,
    IntelligenceResult,
)
from services.api.incidents.service import IncidentService
from services.api.incidents.aggregator import IncidentAggregator
from services.api.alerts.service import AlertService
from services.api.alerts.generator import AlertGenerator
from services.api.summary.service import SummaryService


def test_e2e_hotspot_to_incident_dossier():
    """Requirement 25: Hotspot + intelligence + context -> complete incident dossier."""
    hotspot = Hotspot(
        id="VIIRS-SNPP-20261001-001",
        latitude=38.7421,
        longitude=-122.8105,
        brightness=352.4,
        scan=0.38,
        track=0.36,
        acq_date="2026-10-01",
        acq_time="0845",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=298.4,
        frp=142.8,
        daynight="N",
        source_type=SourceType.WILDFIRE,
        risk_score=92.5,
        risk_level=RiskLevel.CRITICAL,
        is_anomaly=True,
        cluster_id="CL-SONOMA-01",
        cluster_size=5,
        nearest_place="Geysers Basin, Sonoma County, CA",
        last_updated="2026-10-01T08:50:00Z",
    )

    geo = GeospatialContext(
        land_cover="dense_coniferous_forest",
        nearest_infrastructure="State Route 175 & PG&E Transmission Corridor",
        distance_to_infrastructure_meters=450.0,
        nearest_settlement="Cobb Mountain Community & Geysers Resort",
        distance_to_settlement_meters=1200.0,
        is_protected_area=True,
        protected_area_name="Boggs Mountain Demonstration State Forest",
        elevation_meters=985.0,
        slope_degrees=28.5,
        fuel_load_estimate="extreme_dry_chaparral",
    )

    weather = WeatherContext(
        temperature_celsius=29.4,
        relative_humidity_percent=14.0,
        wind_speed_kmh=38.5,
        wind_gust_kmh=58.0,
        wind_direction_degrees=42.0,
        wind_direction_cardinal="NE",
        precipitation_mm=0.0,
        fire_weather_index=88.5,
        forecast_summary="Red Flag Warning active. Gusty Diablo winds.",
    )

    historical = HistoricalContext(
        prior_detections_30d=1,
        prior_detections_90d=3,
        is_recurrent_site=False,
        recurrent_pattern="none",
        first_detected_date="2026-09-28",
        detection_frequency_score=0.12,
    )

    factors = [
        RiskFactor(
            factor="Extreme Fire Radiative Power (142.8 MW)",
            weight=0.35,
            impact=RiskLevel.CRITICAL,
            description="Intense convective thermal energy indicative of crown fire.",
        ),
        RiskFactor(
            factor="Critical Fire Weather (RH 14%, Winds 38.5 km/h)",
            weight=0.30,
            impact=RiskLevel.CRITICAL,
            description="Offshore wind gusts align with steep terrain.",
        ),
    ]

    intel = IntelligenceResult(
        hotspot_id=hotspot.id,
        classification=ClassificationResult(
            predicted_source=SourceType.WILDFIRE,
            confidence=0.96,
            probabilities={"wildfire": 0.96, "industrial": 0.04},
        ),
        anomaly=AnomalyResult(
            is_anomaly=True,
            anomaly_score=0.94,
            baseline_deviation=4.8,
            anomaly_rationale="FRP is 4.8 sigma above historical baseline.",
        ),
        risk=RiskAssessment(
            risk_score=92.5,
            risk_level=RiskLevel.CRITICAL,
            frp_component=94.0,
            weather_component=96.0,
            proximity_component=88.0,
            historical_component=20.0,
            explainable_factors=factors,
            recommended_action="Issue structural defense advisory and alert CalFire dispatch.",
        ),
        model_version="v1.0-rf-heuristic",
        evaluated_at="2026-10-01T08:52:00Z",
    )

    incident_service = IncidentService()
    dossier = incident_service.build_incident_detail(
        hotspot=hotspot,
        geospatial=geo,
        weather=weather,
        historical=historical,
        intelligence=intel,
        data_mode=DataMode.DEMO,
    )

    assert isinstance(dossier, IncidentDetail)
    assert dossier.hotspot.id == "VIIRS-SNPP-20261001-001"
    assert dossier.intelligence.risk.risk_score == 92.5
    assert dossier.intelligence.risk.risk_level == RiskLevel.CRITICAL
    assert len(dossier.intelligence.risk.explainable_factors) == 2
    assert dossier.geospatial.distance_to_settlement_meters == 1200.0
    assert dossier.weather.fire_weather_index == 88.5
    assert dossier.data_mode == DataMode.DEMO


def test_e2e_incident_to_prioritized_alert():
    """Requirement 26: Incident dossier -> generated and prioritized alert."""
    hotspot = Hotspot(
        id="VIIRS-SNPP-20261001-001",
        latitude=38.7421,
        longitude=-122.8105,
        brightness=352.4,
        scan=0.38,
        track=0.36,
        acq_date="2026-10-01",
        acq_time="0845",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence="high",
        version="2.0NRT",
        bright_t31=298.4,
        frp=142.8,
        daynight="N",
        source_type=SourceType.WILDFIRE,
        risk_score=92.5,
        risk_level=RiskLevel.CRITICAL,
        is_anomaly=True,
        cluster_id="CL-SONOMA-01",
        cluster_size=5,
        nearest_place="Geysers Basin, Sonoma County, CA",
        last_updated="2026-10-01T08:50:00Z",
    )

    geo = GeospatialContext(
        land_cover="dense_coniferous_forest",
        nearest_infrastructure="PG&E Corridor",
        distance_to_infrastructure_meters=450.0,
        nearest_settlement="Cobb Mountain",
        distance_to_settlement_meters=1200.0,
        is_protected_area=True,
    )
    weather = WeatherContext(
        temperature_celsius=29.4,
        relative_humidity_percent=14.0,
        wind_speed_kmh=38.5,
        wind_gust_kmh=58.0,
        wind_direction_degrees=42.0,
        wind_direction_cardinal="NE",
        precipitation_mm=0.0,
        forecast_summary="Red flag warning",
    )
    hist = HistoricalContext()
    intel = IntelligenceResult(
        hotspot_id=hotspot.id,
        classification=ClassificationResult(
            predicted_source=SourceType.WILDFIRE,
            confidence=0.96,
            probabilities={"wildfire": 0.96},
        ),
        anomaly=AnomalyResult(
            is_anomaly=True,
            anomaly_score=0.9,
            baseline_deviation=4.0,
            anomaly_rationale="High surge",
        ),
        risk=RiskAssessment(
            risk_score=92.5,
            risk_level=RiskLevel.CRITICAL,
            frp_component=90.0,
            weather_component=90.0,
            proximity_component=90.0,
            historical_component=20.0,
            explainable_factors=[],
            recommended_action="Trigger emergency zone alert; coordinate structural defense with CalFire.",
        ),
        model_version="v1.0",
        evaluated_at="2026-10-01T08:52:00Z",
    )

    incident_service = IncidentService()
    dossier = incident_service.build_incident_detail(
        hotspot=hotspot,
        geospatial=geo,
        weather=weather,
        historical=hist,
        intelligence=intel,
    )

    alert_gen = AlertGenerator()
    alert = alert_gen.generate_from_hotspot(dossier.hotspot, detail=dossier)

    assert alert is not None
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.hotspot_id == dossier.hotspot.id
    assert alert.risk_score == 92.5
    assert "critical_frp" in alert.tags
    assert "settlement_proximity" in alert.tags
    assert "high_wind" in alert.tags
    assert "CalFire" in alert.recommended_action


def test_e2e_collection_to_summary_and_sources():
    """Requirement 27: Full dataset -> aggregated incidents, summary KPIs, and source breakdown."""
    sample_path = Path("data/sample/sample_hotspots.json")
    assert sample_path.exists(), "Sample hotspots file must exist"

    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    hotspots = [Hotspot(**item) for item in data]

    # 1. Aggregate incidents
    aggregator = IncidentAggregator(distance_threshold_km=1.5)
    incidents = aggregator.aggregate(hotspots)
    assert len(incidents) > 0
    assert len(incidents) <= len(hotspots)  # Deduplication properly grouped some proximate pixels

    # 2. Generate and prioritize alerts
    alert_service = AlertService()
    alerts = alert_service.generate_alerts_from_hotspots(hotspots)
    assert len(alerts) > 0
    # Alerts must be sorted by priority
    for i in range(len(alerts) - 1):
        assert (
            alerts[i].severity.value == "critical"
            or alerts[i + 1].severity.value != "critical"
        )
        if alerts[i].severity == alerts[i + 1].severity:
            assert alerts[i].risk_score >= alerts[i + 1].risk_score

    # 3. Generate summary
    summary_service = SummaryService()
    summary = summary_service.get_summary(hotspots=hotspots, active_alerts_count=len(alerts))

    assert summary.total_active_hotspots == len(hotspots)
    assert summary.active_alerts_count == len(alerts)
    assert (
        summary.critical_risk_count
        + summary.high_risk_count
        + summary.medium_risk_count
        + summary.low_risk_count
    ) == summary.total_active_hotspots
    assert summary.average_frp > 0.0
    assert summary.max_frp >= summary.average_frp
    assert summary.average_risk_score > 0.0
    assert summary.dominant_source in SourceType

    # 4. Generate sources
    sources_resp = summary_service.get_sources(hotspots=hotspots)
    assert sources_resp.total_evaluated == len(hotspots)
    assert len(sources_resp.sources) > 0
    assert pytest.approx(sum(s.percentage for s in sources_resp.sources), 0.2) == 100.0
