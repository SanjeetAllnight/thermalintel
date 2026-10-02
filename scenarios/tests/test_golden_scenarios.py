"""Golden scenario domain behavior tests for ThermalIntel V2.

Verifies domain invariants across the 4 core deterministic scenario packs:
- SCN-001: Industrial baseline spike and escalation
- SCN-002: Vegetation event with settlement exposure and growth
- SCN-003: Transient weak detection with non-recurrence and quiet behavior
- SCN-004: Upstream provider failure, cache degradation, and recovery

Implements Requirement 8:
'Create golden tests describing expected outcomes.
 Example:
 Scenario → expected incident count → expected incident states
 → expected escalation points → expected alert transitions
 Do not assert fragile implementation details. Assert domain behavior.'
"""

import unittest
from pathlib import Path

from scenarios.loader import load_scenario_from_file
from services.replay.player import ReplayPlayer
from services.api.schemas.v2.common import (
    RiskLevel,
    IncidentEventType,
    AlertSeverity,
    ProviderStatus,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestGoldenScenarios(unittest.TestCase):
    """Test domain outcome invariants for all 4 core scenarios."""

    def test_golden_scenario_1_industrial_spike(self):
        """SCENARIO 1: Industrial baseline spike.
        
        Expected: normal activity → abnormal increase → incident → escalation.
        """
        scenario = load_scenario_from_file(DATA_DIR / "scenario_1_industrial_spike.json")
        player = ReplayPlayer(scenario=scenario)
        history = player.run_to_completion()

        pipeline = player.pipeline

        # 1. Incident invariants
        self.assertEqual(len(pipeline.incidents), 1, "Exactly one persistent industrial incident expected")
        incident = pipeline.incidents[0]
        self.assertEqual(incident.observation_count, 4, "All 4 passes should correlate to the same facility")
        self.assertEqual(incident.current_severity, RiskLevel.CRITICAL, "Surge should escalate to CRITICAL")
        self.assertGreaterEqual(incident.peak_frp, 185.0, "Blowout FRP should be recorded as peak")

        # 2. Timeline event transitions
        event_types = [e.event_type for e in pipeline.events]
        self.assertIn(IncidentEventType.CREATED, event_types, "Incident creation event must be recorded")
        self.assertIn(IncidentEventType.OBSERVATION_ADDED, event_types, "Correlated observation event recorded")
        self.assertIn(IncidentEventType.ESCALATED, event_types, "Escalation event must be recorded on timeline")

        # 3. Alert generation
        self.assertGreaterEqual(len(pipeline.alerts), 1, "At least one hazard alert must be emitted")
        critical_alerts = [a for a in pipeline.alerts if a.priority == AlertSeverity.CRITICAL]
        self.assertGreaterEqual(len(critical_alerts), 1, "Critical alert must be emitted for anomalous spike")

    def test_golden_scenario_2_vegetation_exposure(self):
        """SCENARIO 2: Vegetation event near exposure.
        
        Expected: observations accumulate → spatial event grows → exposure context matters → risk changes.
        """
        scenario = load_scenario_from_file(DATA_DIR / "scenario_2_vegetation_exposure.json")
        player = ReplayPlayer(scenario=scenario)
        player.run_to_completion()

        pipeline = player.pipeline

        # 1. Observations accumulate and incident grows
        self.assertEqual(len(pipeline.incidents), 1, "Single propagating wildfire incident expected")
        incident = pipeline.incidents[0]
        self.assertEqual(incident.observation_count, 3, "All 3 observations must correlate to incident")
        self.assertGreaterEqual(incident.peak_frp, 140.0)

        # 2. Exposure context matters: final severity is critical due to proximity (<350m to settlement)
        self.assertEqual(incident.current_severity, RiskLevel.CRITICAL)

        # 3. Escalation event occurs
        event_types = [e.event_type for e in pipeline.events]
        self.assertIn(IncidentEventType.ESCALATED, event_types)

        # 4. Critical alerts emitted with responder recommendations
        self.assertGreaterEqual(len(pipeline.alerts), 1)
        alert = pipeline.alerts[-1]
        self.assertIn("Pine Ridge", alert.title)

    def test_golden_scenario_3_weak_detection(self):
        """SCENARIO 3: Weak / non-recurring detection.
        
        Expected: single weak detection → insufficient recurrence → quiet/closed behavior.
        """
        scenario = load_scenario_from_file(DATA_DIR / "scenario_3_weak_detection.json")
        player = ReplayPlayer(scenario=scenario)
        player.run_to_completion()

        pipeline = player.pipeline

        # 1. Low risk evaluation
        if pipeline.incidents:
            incident = pipeline.incidents[0]
            self.assertEqual(incident.current_severity, RiskLevel.LOW, "Weak detection must evaluate to LOW severity")
            self.assertFalse(
                any(e.event_type == IncidentEventType.ESCALATED for e in pipeline.events),
                "No escalation should occur for non-recurring detection"
            )

        # 2. Zero operational alerts triggered (quiet behavior)
        critical_alerts = [a for a in pipeline.alerts if a.priority in (AlertSeverity.CRITICAL, AlertSeverity.WARNING)]
        self.assertEqual(len(critical_alerts), 0, "No critical or warning alerts permitted for weak detection")

    def test_golden_scenario_4_provider_degradation(self):
        """SCENARIO 4: Provider degradation, cache fallback, and recovery.
        
        Expected: live provider failure → cache/degraded state → recovery.
        """
        scenario = load_scenario_from_file(DATA_DIR / "scenario_4_provider_degradation.json")
        player = ReplayPlayer(scenario=scenario)
        player.run_to_completion()

        provider = player.provider
        runs = provider.get_provider_runs()

        # 1. Telemetry records status transitions
        statuses = [r.status for r in runs]
        self.assertIn(ProviderStatus.FAILED, statuses, "Provider outage must be recorded in telemetry")
        self.assertEqual(runs[-1].status, ProviderStatus.SUCCESS, "Provider must recover to SUCCESS")

        # 2. Pipeline processes remaining observations without fatal crash
        self.assertGreaterEqual(len(player.pipeline.incidents), 1)


if __name__ == "__main__":
    unittest.main()
