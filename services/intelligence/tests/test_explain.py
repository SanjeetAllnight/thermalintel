"""Unit tests for explanation factor generation and consistency."""

import pytest
from services.api.schemas.common import RiskLevel, SourceType
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.explain import ExplanationGenerator
from services.intelligence.features import FeatureExtractor


def test_explain_consistency_low_risk():
    """Verify that a low risk score produces calm, contained wording."""
    norm_h = NormalizedHotspotInput(id="LOW-01", frp=8.0, brightness=302.0)
    ctx = HotspotContext(
        distance_to_settlement_m=20000.0,
        wind_speed_kmh=8.0,
        relative_humidity_pct=65.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)

    factors = ExplanationGenerator.generate_factors(
        features=features,
        risk_score=18.0,
        frp_comp=15.0,
        weather_comp=10.0,
        prox_comp=10.0,
        hist_comp=20.0,
        anomaly_score=0.10,
        is_anomaly=False,
    )

    assert 2 <= len(factors) <= 4
    for factor in factors:
        assert factor.impact in (RiskLevel.LOW, RiskLevel.MEDIUM)
        # Must not have sensationalist catastrophic language
        text = (factor.factor + " " + factor.description).lower()
        assert "catastrophic" not in text
        assert "extreme" not in text

    rec = ExplanationGenerator.generate_recommendation(18.0, SourceType.UNKNOWN)
    assert "ADVISORY" in rec or "ROUTINE" in rec


def test_explain_consistency_critical_risk():
    """Verify that a critical risk score highlights the severe drivers."""
    norm_h = NormalizedHotspotInput(id="CRIT-01", frp=160.0, brightness=390.0)
    ctx = HotspotContext(
        distance_to_settlement_m=900.0,
        wind_speed_kmh=45.0,
        relative_humidity_pct=12.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)

    factors = ExplanationGenerator.generate_factors(
        features=features,
        risk_score=92.0,
        frp_comp=95.0,
        weather_comp=90.0,
        prox_comp=92.0,
        hist_comp=30.0,
        anomaly_score=0.92,
        is_anomaly=True,
    )

    assert 2 <= len(factors) <= 4
    has_critical_factor = any(f.impact == RiskLevel.CRITICAL for f in factors)
    assert has_critical_factor is True

    rec = ExplanationGenerator.generate_recommendation(92.0, SourceType.WILDFIRE)
    assert "CRITICAL" in rec
    assert "evacuation" in rec.lower() or "containment" in rec.lower()
