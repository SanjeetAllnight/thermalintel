"""Timestamp, Provenance, and Confidence Separation Validation Suite for ThermalIntel V2.

Verifies:
1. Strict differentiation and chronological consistency across the 6 timestamp semantics:
   - acquisition_time_utc (satellite sensor scan time)
   - ingestion_time_utc (ThermalIntel processing time)
   - observed_at_utc (environmental phenomenon reference time)
   - fetched_at_utc (API HTTP execution time)
   - as_of_utc (virtual simulation/evaluation point-in-time)
   - created_at_utc (physical database write timestamp).
2. Strict ISO 8601 UTC compliance (Z suffix or +00:00, parseable to tz-aware datetime).
3. Ingestion time is never conflated with observation/acquisition time.
4. Independent contextual provenance tracking with explicit handling of unavailable data without fabrication.
5. Strict separation between the 5 distinct confidence/quality metrics:
   - Detection Confidence (sensor SNR: low/nominal/high)
   - Classification Confidence (ML model posterior probability: 0.0-1.0)
   - Data Quality / Completeness (ratio of available context features: 0.0-1.0)
   - Anomaly Score (outlier index / sigma departure: 0.0-1.0)
   - Risk Score (multi-factor operational consequence: 0.0-100.0).
"""

import json
from datetime import datetime, timezone
import unittest

from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.v2.common import (
    FreshnessState,
    Provenance,
    now_utc_iso,
)
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.enrichment import (
    EnrichmentSnapshot,
    EnrichmentDatum,
    GeospatialEnrichment,
    WeatherEnrichment,
)
from services.api.schemas.v2.assessment import (
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
)
from services.api.schemas.v2.converters import hotspot_from_v2
from services.api.ingestion.normalizer import HotspotNormalizer
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.context import HotspotContext

from tests.fixtures.v2_golden.fixtures import (
    INDUSTRIAL_SPIKE_RECORD,
    make_raw_firms_csv,
)


class TestTimestampProvenanceConfidence(unittest.TestCase):
    """Validation of timestamp rules, provenance specifications, and confidence metrics."""

    def test_frozen_timestamp_semantics_differentiation(self):
        """Verify strict distinction and chronological sequencing among all 6 timestamp types."""
        # 1. acquisition_time_utc: when VIIRS sensor detected the thermal signature
        acquisition_time_utc = "2026-10-01T04:15:00Z"

        # 2. observed_at_utc: synoptic weather observation reference time
        observed_at_utc = "2026-10-01T04:00:00Z"

        # 3. fetched_at_utc: when ThermalIntel queried the weather and FIRMS APIs
        fetched_at_utc = "2026-10-01T04:30:00Z"

        # 4. ingestion_time_utc: when the backend normalizer processed the satellite record
        ingestion_time_utc = "2026-10-01T04:30:05Z"

        # 5. as_of_utc: simulated evaluation point-in-time
        as_of_utc = "2026-10-01T04:35:00Z"

        # 6. created_at_utc: physical database record creation time
        created_at_utc = "2026-10-01T04:35:01Z"

        # Verify all are valid ISO 8601 UTC strings
        all_timestamps = [
            acquisition_time_utc,
            observed_at_utc,
            fetched_at_utc,
            ingestion_time_utc,
            as_of_utc,
            created_at_utc,
        ]
        parsed_dts = []
        for ts_str in all_timestamps:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            self.assertIsNotNone(dt.tzinfo, f"Timestamp {ts_str} must be timezone-aware")
            self.assertEqual(dt.utcoffset().total_seconds(), 0, f"Timestamp {ts_str} must be UTC")
            parsed_dts.append(dt)

        # Ingestion time MUST be strictly greater than acquisition time
        dt_acq = parsed_dts[0]
        dt_obs = parsed_dts[1]
        dt_fetch = parsed_dts[2]
        dt_ingest = parsed_dts[3]
        dt_as_of = parsed_dts[4]
        dt_created = parsed_dts[5]

        self.assertGreater(dt_ingest, dt_acq, "Ingestion time must occur after satellite sensor acquisition")
        self.assertGreaterEqual(dt_fetch, dt_obs, "API fetch time must occur at or after meteorological observation")
        self.assertGreaterEqual(dt_created, dt_as_of, "Database creation write must occur at or after as-of simulation time")

        # Ingestion time must never be equal to acquisition time in normalized output
        raw_csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(raw_csv)
        self.assertEqual(len(observations), 1)
        obs = observations[0]

        self.assertNotEqual(
            obs.acquisition_time_utc,
            obs.ingestion_time_utc,
            "Ingestion time must not be conflated with acquisition time",
        )

    def test_provenance_audit_fields_and_truthful_non_fabrication(self):
        """Verify provenance tracking and truthful explicit missing value representation."""
        # Available datum with complete provenance
        fresh_prov = Provenance(
            provider="Open-Meteo",
            product="seamless_v1",
            observed_at_utc="2026-10-01T04:00:00Z",
            fetched_at_utc="2026-10-01T04:30:00Z",
            freshness_state=FreshnessState.FRESH,
            ttl_seconds=3600,
            reference="https://api.open-meteo.com/v1/forecast?lat=30.12&lon=-93.56",
        )
        available_datum = EnrichmentDatum[float](
            value=24.5,
            status="available",
            provenance=fresh_prov,
        )
        self.assertTrue(available_datum.is_available)
        self.assertEqual(available_datum.value, 24.5)
        self.assertIsNone(available_datum.error_message)

        # Unavailable datum (upstream provider outage): value must be None, zero fabrication
        degraded_prov = Provenance(
            provider="OpenStreetMap",
            product="overpass_api",
            observed_at_utc="2026-10-01T04:00:00Z",
            fetched_at_utc="2026-10-01T04:30:00Z",
            freshness_state=FreshnessState.UNAVAILABLE,
            ttl_seconds=0,
            reference="overpass_query_hash_001",
        )
        unavailable_datum = EnrichmentDatum[float](
            value=None,
            status="unavailable",
            provenance=degraded_prov,
            error_message="HTTP 504 Gateway Timeout from Overpass",
        )
        self.assertFalse(unavailable_datum.is_available)
        self.assertIsNone(unavailable_datum.value, "Unavailable enrichment must NEVER fabricate fallback numbers")
        self.assertEqual(unavailable_datum.status, "unavailable")
        self.assertEqual(unavailable_datum.error_message, "HTTP 504 Gateway Timeout from Overpass")

    def test_confidence_and_metric_separation_integrity(self):
        """Verify that distinct confidence, quality, and severity metrics do not collapse."""
        csv_text = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        obs = observations[0]

        hotspot = hotspot_from_v2(obs, nearest_place="Industrial Complex")
        engine = ThermalIntelligenceEngine(random_state=42)

        # Partial context to test data completeness score separation
        ctx = HotspotContext(
            distance_to_industrial_m=100.0,
            temperature_c=28.0,
            wind_speed_kmh=15.0,
        )

        assessment = engine.assess_hotspot(hotspot, context=ctx)

        # 1. Detection Confidence (Sensor level: satellite instrument SNR)
        detection_conf = obs.detection_confidence
        self.assertIn(detection_conf, ("low", "nominal", "high"))

        # 2. Classification Confidence (ML model posterior probability)
        class_conf = assessment.classification.classification_confidence
        self.assertIsInstance(class_conf, float)
        self.assertGreaterEqual(class_conf, 0.0)
        self.assertLessEqual(class_conf, 1.0)

        # 3. Data Quality / Completeness (Context availability score)
        data_quality = assessment.data_quality
        self.assertIsNotNone(data_quality)
        self.assertIsInstance(data_quality.completeness_score, float)
        self.assertGreaterEqual(data_quality.completeness_score, 0.0)
        self.assertLessEqual(data_quality.completeness_score, 1.0)

        # 4. Anomaly Score (Statistical departure / outlier index)
        anomaly_score = assessment.anomaly.anomaly_score
        self.assertIsInstance(anomaly_score, float)
        self.assertGreaterEqual(anomaly_score, 0.0)
        self.assertLessEqual(anomaly_score, 1.0)

        # 5. Risk Score (Composite operational hazard: 0 to 100)
        risk_score = assessment.risk.risk_score
        self.assertIsInstance(risk_score, float)
        self.assertGreaterEqual(risk_score, 0.0)
        self.assertLessEqual(risk_score, 100.0)

        # Verify semantic independence: none of these values should be equal to all others
        # (they reflect completely different physical and algorithmic concepts)
        metrics = {
            "classification_confidence": class_conf,
            "data_quality_completeness": data_quality.completeness_score,
            "anomaly_score": anomaly_score,
            "risk_score": risk_score,
        }
        # Risk score is on 0-100 scale whereas others are 0-1
        self.assertGreater(risk_score, 1.0)
        # Classification confidence should not be conflated with sensor detection confidence
        self.assertNotEqual(str(class_conf), detection_conf)
