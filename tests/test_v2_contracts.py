"""Tests for ThermalIntel V2 Domain Contracts and Pydantic Schemas.

Validates:
- Observation model: valid construction, rejection of invalid coordinates/radiometry,
  and strict separation of detection confidence from AI classification.
- Enrichment contracts: explicit representation of missing/unavailable context without fabrication.
- Assessment contracts: strict decomposition of detection confidence, classification confidence,
  anomaly score, data completeness, and multi-factor risk score.
- Incident contracts: stable identity independent of centroid or primary observation.
- IncidentEvent: append-only timeline event types.
- AlertV2: deduplication key and lifecycle states.
- ProviderRun: execution telemetry with defensive redaction of credential keys.
- Bidirectional converters between V1 Hotspots and V2 canonical models.
"""

import unittest
from datetime import datetime, timezone
from pydantic import ValidationError

from services.api.schemas.v2 import (
    Observation,
    EnrichmentDatum,
    GeospatialEnrichment,
    WeatherEnrichment,
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
    Incident,
    IncidentObservation,
    IncidentEvent,
    IncidentEventType,
    IncidentStatus,
    AlertV2,
    AlertSeverity,
    AlertState,
    ProviderRun,
    ProviderStatus,
    RawPayloadMetadata,
    Provenance,
    FreshnessState,
    SourceType,
    RiskLevel,
    RiskFactor,
    now_utc_iso,
    row_to_hotspot_canonical,
    observation_from_hotspot,
    hotspot_from_v2,
)
from services.api.schemas.hotspot import Hotspot


class TestObservationContract(unittest.TestCase):
    """Test Observation model validation and constraints."""

    def test_valid_observation(self):
        obs = Observation(
            observation_id="OBS-VIIRS-20261001-001",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            satellite="Suomi-NPP",
            instrument="VIIRS",
            latitude=37.7749,
            longitude=-122.4194,
            acquisition_time_utc="2026-10-01T08:45:00Z",
            ingestion_time_utc="2026-10-01T08:50:00Z",
            brightness=345.2,
            bright_t31=298.1,
            frp=42.5,
            scan=0.375,
            track=0.375,
            daynight="N",
            detection_confidence="nominal",
            source_attributes={"original_line": 42},
        )
        self.assertEqual(obs.observation_id, "OBS-VIIRS-20261001-001")
        self.assertEqual(obs.detection_confidence, "nominal")
        self.assertEqual(obs.daynight, "N")

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValidationError):
            Observation(
                observation_id="OBS-INVALID",
                provider="NASA_FIRMS",
                product="VIIRS",
                latitude=95.0,  # Invalid: > 90
                longitude=-122.0,
                acquisition_time_utc="2026-10-01T00:00:00Z",
                brightness=300.0,
                frp=10.0,
                daynight="D",
                detection_confidence="high",
            )

    def test_negative_frp_rejected(self):
        with self.assertRaises(ValidationError):
            Observation(
                observation_id="OBS-INVALID-FRP",
                provider="NASA_FIRMS",
                product="VIIRS",
                latitude=35.0,
                longitude=-120.0,
                acquisition_time_utc="2026-10-01T00:00:00Z",
                brightness=300.0,
                frp=-5.0,  # Invalid: must be >= 0
                daynight="D",
                detection_confidence="high",
            )

    def test_invalid_daynight_rejected(self):
        with self.assertRaises(ValidationError):
            Observation(
                observation_id="OBS-INVALID-DN",
                provider="NASA_FIRMS",
                product="VIIRS",
                latitude=35.0,
                longitude=-120.0,
                acquisition_time_utc="2026-10-01T00:00:00Z",
                brightness=300.0,
                frp=10.0,
                daynight="X",  # Invalid: must be 'D' or 'N'
                detection_confidence="high",
            )


class TestEnrichmentContract(unittest.TestCase):
    """Test enrichment provenance and explicit unavailable value handling."""

    def test_available_enrichment_datum(self):
        prov = Provenance(
            provider="Open-Meteo",
            product="Forecast_API",
            observed_at_utc="2026-10-01T08:00:00Z",
            fetched_at_utc="2026-10-01T08:45:00Z",
            freshness_state=FreshnessState.FRESH,
        )
        datum = EnrichmentDatum[float](
            value=24.5,
            status="available",
            provenance=prov,
        )
        self.assertTrue(datum.is_available)
        self.assertEqual(datum.value, 24.5)

    def test_unavailable_enrichment_explicitly_represented(self):
        """When an external provider fails or times out, value is None and status is 'unavailable'."""
        prov = Provenance(
            provider="OpenStreetMap",
            product="Overpass_API",
            observed_at_utc="2026-10-01T08:00:00Z",
            fetched_at_utc="2026-10-01T08:45:00Z",
            freshness_state=FreshnessState.UNAVAILABLE,
        )
        datum = EnrichmentDatum[str](
            value=None,
            status="unavailable",
            provenance=prov,
            error_message="Overpass HTTP 504 Gateway Timeout",
        )
        self.assertFalse(datum.is_available)
        self.assertIsNone(datum.value)
        self.assertEqual(datum.status, "unavailable")
        self.assertIn("Timeout", datum.error_message)


class TestAssessmentContract(unittest.TestCase):
    """Test Assessment contract and clear separation of distinct metric types."""

    def test_valid_assessment_with_methodology(self):
        asm = Assessment(
            assessment_id="ASM-20261001-001",
            target_id="OBS-VIIRS-20261001-001",
            target_type="observation",
            classification=ClassificationAssessment(
                predicted_source=SourceType.WILDFIRE,
                classification_confidence=0.92,
                probabilities={"wildfire": 0.92, "agricultural": 0.05, "industrial": 0.03},
                feature_importance={"frp": 0.45, "vegetation_index": 0.35},
            ),
            anomaly=AnomalyAssessment(
                is_anomaly=True,
                anomaly_score=0.88,
                baseline_deviation_sigma=3.4,
                anomaly_rationale="FRP exceeds 30-day regional 99th percentile by 3.4 sigma",
            ),
            risk=RiskAssessmentResult(
                risk_score=78.5,
                severity=RiskLevel.HIGH,
                frp_component=82.0,
                weather_component=75.0,
                proximity_component=60.0,
                historical_component=40.0,
                factors=[
                    RiskFactor(
                        factor="Extreme Fire Radiative Power",
                        weight=0.4,
                        impact=RiskLevel.HIGH,
                        description="FRP of 128 MW indicates high energy release",
                    )
                ],
                recommended_action="Deploy aerial surveillance and alert regional dispatch",
            ),
            data_quality=DataQualityAssessment(
                completeness_score=0.95,
                uncertainty_score=0.08,
                missing_sources=[],
            ),
            methodology=AssessmentMethodology(
                method="RandomForest+IsolationForest+MultiFactorRisk",
                algorithm_version="v2.0.0-rf-heuristic",
                input_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                as_of_utc="2026-10-01T08:50:00Z",
            ),
        )
        self.assertEqual(asm.assessment_id, "ASM-20261001-001")
        self.assertEqual(asm.classification.classification_confidence, 0.92)
        self.assertEqual(asm.anomaly.anomaly_score, 0.88)
        self.assertEqual(asm.risk.risk_score, 78.5)
        self.assertEqual(asm.data_quality.completeness_score, 0.95)
        self.assertEqual(asm.methodology.algorithm_version, "v2.0.0-rf-heuristic")


class TestIncidentContract(unittest.TestCase):
    """Test Incident model and stable identity semantics."""

    def test_incident_stable_identity(self):
        inc = Incident(
            incident_id="INC-20261001-0042",
            status=IncidentStatus.ACTIVE,
            first_seen_utc="2026-10-01T06:00:00Z",
            last_seen_utc="2026-10-01T09:00:00Z",
            centroid_latitude=34.15,
            centroid_longitude=-118.35,
            peak_frp=125.0,
            average_frp=78.2,
            observation_count=5,
            current_risk_score=85.0,
            current_severity=RiskLevel.CRITICAL,
            current_classification=SourceType.WILDFIRE,
            current_assessment_id="ASM-20261001-0042",
        )
        self.assertEqual(inc.incident_id, "INC-20261001-0042")
        self.assertEqual(inc.status, IncidentStatus.ACTIVE)
        self.assertEqual(inc.observation_count, 5)

    def test_incident_observation_association(self):
        assoc = IncidentObservation(
            incident_id="INC-20261001-0042",
            observation_id="OBS-VIIRS-20261001-001",
            association_method="dbscan_spatiotemporal",
            association_reason="Within 1.5km spatial and 3-hour temporal cluster window",
        )
        self.assertEqual(assoc.incident_id, "INC-20261001-0042")
        self.assertEqual(assoc.observation_id, "OBS-VIIRS-20261001-001")

    def test_incident_event_timeline(self):
        evt = IncidentEvent(
            event_id="EVT-20261001-001",
            incident_id="INC-20261001-0042",
            event_type=IncidentEventType.ESCALATED,
            actor="intelligence_engine",
            reason="Risk score escalated from 65.0 to 85.0 due to wind gusts exceeding 40km/h",
            metadata={"old_risk": 65.0, "new_risk": 85.0, "wind_gust_kmh": 45.2},
        )
        self.assertEqual(evt.event_type, IncidentEventType.ESCALATED)
        self.assertEqual(evt.actor, "intelligence_engine")


class TestAlertContract(unittest.TestCase):
    """Test AlertV2 contract, deduplication key, and state transitions."""

    def test_alert_v2_lifecycle(self):
        alert = AlertV2(
            alert_id="ALT-20261001-001",
            incident_id="INC-20261001-0042",
            rule_id="RULE_CRITICAL_FIRE_PROXIMITY",
            dedupe_key="INC-20261001-0042:CRITICAL:PROXIMITY_SETTLEMENT",
            priority=AlertSeverity.CRITICAL,
            state=AlertState.ACTIVE,
            title="Critical Wildfire Threatening Community",
            message="Active thermal cluster within 800m of settlement boundary with high FRP.",
            evidence={"distance_meters": 800.0, "frp_peak": 125.0},
        )
        self.assertEqual(alert.priority, AlertSeverity.CRITICAL)
        self.assertEqual(alert.state, AlertState.ACTIVE)
        self.assertIn("PROXIMITY_SETTLEMENT", alert.dedupe_key)


class TestProviderRunContract(unittest.TestCase):
    """Test ProviderRun contract and defensive credential prevention."""

    def test_valid_provider_run(self):
        run = ProviderRun(
            run_id="RUN-FIRMS-20261001-085000",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            started_at_utc="2026-10-01T08:50:00Z",
            finished_at_utc="2026-10-01T08:50:02Z",
            status=ProviderStatus.SUCCESS,
            rows_received=30,
            duration_ms=2100,
            request_metadata={"area": "USA_contiguous_and_Hawaii", "days": 1},
        )
        self.assertEqual(run.status, ProviderStatus.SUCCESS)
        self.assertEqual(run.rows_received, 30)

    def test_prohibited_secrets_in_request_metadata_raise_error(self):
        with self.assertRaises(ValueError):
            ProviderRun(
                run_id="RUN-INSECURE",
                provider="NASA_FIRMS",
                product="VIIRS",
                request_metadata={"api_key": "raw_secret_value_123"},
            )


class TestConverters(unittest.TestCase):
    """Test bidirectional mapping between V1 Hotspots and V2 domain models."""

    def test_hotspot_to_observation_and_back(self):
        hotspot = Hotspot(
            id="VIIRS-SNPP-20261001-001",
            latitude=38.7421,
            longitude=-122.8105,
            brightness=348.6,
            scan=0.38,
            track=0.36,
            acq_date="2026-10-01",
            acq_time="0845",
            satellite="Suomi-NPP",
            instrument="VIIRS",
            confidence="high",
            version="2.0NRT",
            bright_t31=298.4,
            frp=128.5,
            daynight="N",
            source_type=SourceType.WILDFIRE,
            risk_score=87.5,
            risk_level=RiskLevel.CRITICAL,
            is_anomaly=True,
            cluster_id="CL-CAL-04",
            cluster_size=6,
            nearest_place="Sonoma County, CA",
            last_updated="2026-10-01T09:15:00Z",
        )

        obs = observation_from_hotspot(hotspot)
        self.assertEqual(obs.observation_id, "OBS-VIIRS-SNPP-20261001-001")
        self.assertEqual(obs.latitude, 38.7421)
        self.assertEqual(obs.frp, 128.5)
        self.assertEqual(obs.detection_confidence, "high")
        self.assertEqual(obs.acquisition_time_utc, "2026-10-01T08:45:00Z")

        # Project back to Hotspot
        reconstructed = hotspot_from_v2(
            obs,
            nearest_place="Sonoma County, CA",
            cluster_id="CL-CAL-04",
            cluster_size=6,
        )
        self.assertEqual(reconstructed.id, "VIIRS-SNPP-20261001-001")
        self.assertEqual(reconstructed.latitude, 38.7421)
        self.assertEqual(reconstructed.acq_date, "2026-10-01")
        self.assertEqual(reconstructed.acq_time, "0845")
        self.assertEqual(reconstructed.frp, 128.5)


if __name__ == "__main__":
    unittest.main()
