"""Canonical Replay Pipeline Runner for ThermalIntel V2.

Orchestrates the complete unidirectional processing pipeline:
Scenario/Provider Evidence
  → Normalization
  → Contextual Enrichment
  → Machine Learning Intelligence (Classification, Anomaly, Risk)
  → Incident Correlation & Lifecycle Tracking
  → Operational Alert Generation

Ensures simulated time (as_of_utc) is strictly separated from database write
time (created_at_utc) and guarantees 100% deterministic reproducibility.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Tuple

from services.replay.clock import Clock, SimulatedClock
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.assessment import (
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
)
from services.api.schemas.v2.incident import Incident, IncidentObservation
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import (
    IncidentStatus,
    IncidentEventType,
    AlertSeverity,
    AlertState,
    RiskLevel,
    SourceType,
    RiskFactor,
    now_utc_iso,
)
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.v2.converters import hotspot_from_v2
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.context import HotspotContext
from services.api.incidents.aggregator import IncidentAggregator, haversine_distance_km
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.deduplication import AlertDeduplicator

logger = logging.getLogger(__name__)


@dataclass
class StepExecutionResult:
    """Artifacts produced by a single discrete simulation step."""
    as_of_utc: str
    observations: List[Observation] = field(default_factory=list)
    assessments: List[Assessment] = field(default_factory=list)
    active_incidents: List[Incident] = field(default_factory=list)
    new_events: List[IncidentEvent] = field(default_factory=list)
    new_alerts: List[AlertV2] = field(default_factory=list)


class ReplayPipeline:
    """Deterministic simulation pipeline executing the canonical ThermalIntel workflow."""

    def __init__(
        self,
        clock: Optional[Clock] = None,
        intelligence_engine: Optional[ThermalIntelligenceEngine] = None,
        aggregator: Optional[IncidentAggregator] = None,
        alert_generator: Optional[AlertGenerator] = None,
        seed: int = 42,
        profile: Optional[Union[str, Any]] = None,
    ):
        resolved_profile = None
        if profile is not None:
            if isinstance(profile, str):
                from profiles.loader import load_profile_by_id
                resolved_profile = load_profile_by_id(profile)
            else:
                resolved_profile = profile
        self.profile = resolved_profile

        spatial_thresh = resolved_profile.incidents.spatial_threshold_km if resolved_profile else 2.0
        temp_window = resolved_profile.incidents.temporal_window_hours if resolved_profile else 24.0
        alert_cfg = resolved_profile.alerts if resolved_profile else None

        self.clock = clock or SimulatedClock(now_utc_iso())
        self.seed = seed
        self.intelligence_engine = intelligence_engine or ThermalIntelligenceEngine(
            profile=resolved_profile,
            random_state=seed,
        )
        self.aggregator = aggregator or IncidentAggregator(
            distance_threshold_km=spatial_thresh,
            time_window_hours=temp_window,
        )
        self.alert_generator = alert_generator or AlertGenerator(
            include_medium=True,
            alert_config=alert_cfg,
        )
        self.alert_deduplicator = AlertDeduplicator()

        # Cumulative persistent state across steps
        self._incidents: Dict[str, Incident] = {}
        self._incident_observations: List[IncidentObservation] = []
        self._events: List[IncidentEvent] = []
        self._alerts: List[AlertV2] = []
        self._assessments: Dict[str, Assessment] = {}
        self._incident_counter: int = 0
        self._event_counter: int = 0
        self._alert_counter: int = 0

    @property
    def incidents(self) -> List[Incident]:
        """All current persistent incidents."""
        return list(self._incidents.values())

    @property
    def events(self) -> List[IncidentEvent]:
        """Chronological audit trail of all incident lifecycle events."""
        return list(self._events)

    @property
    def alerts(self) -> List[AlertV2]:
        """All operational alerts emitted across the simulation."""
        return list(self._alerts)

    @property
    def assessments(self) -> List[Assessment]:
        """All assessments generated across the simulation."""
        return list(self._assessments.values())

    def reset(self) -> None:
        """Reset internal accumulator state for clean deterministic replay."""
        self._incidents.clear()
        self._incident_observations.clear()
        self._events.clear()
        self._alerts.clear()
        self._assessments.clear()
        self._incident_counter = 0
        self._event_counter = 0
        self._alert_counter = 0

    def process_observations(
        self,
        observations: List[Observation],
        as_of_utc: Optional[str] = None,
    ) -> StepExecutionResult:
        """Process a batch of observations arriving at the current simulation timestamp."""
        sim_time = as_of_utc or self.clock.now_iso()
        db_created_at = now_utc_iso()  # Rule 2: as_of_utc != created_at_utc

        step_assessments: List[Assessment] = []
        step_events: List[IncidentEvent] = []
        step_alerts: List[AlertV2] = []

        for obs in observations:
            # 1. Normalization check: Ensure V2 Observation -> Hotspot model compatibility
            nearest_place = obs.source_attributes.get("nearest_place")
            hotspot = hotspot_from_v2(obs, nearest_place=nearest_place)

            # 2. Context Extraction: Build HotspotContext from enriched metadata
            raw_ctx = obs.source_attributes.get("context") or {}
            ctx = HotspotContext.from_dict(raw_ctx) if isinstance(raw_ctx, dict) else HotspotContext()

            # 3. Machine Learning Intelligence Inference
            intel_res = self.intelligence_engine.analyze_hotspot(hotspot, context=ctx)

            # Compute reproducible input hash for Assessment methodology
            hash_input = f"{obs.observation_id}:{obs.latitude}:{obs.longitude}:{obs.frp}:{sim_time}"
            input_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

            # Construct canonical V2 Assessment
            predicted_source = SourceType(intel_res.classification.predicted_source.value)
            severity = RiskLevel(intel_res.risk.risk_level.value)

            assessment_id = f"ASM-{obs.observation_id}"
            asm = Assessment(
                assessment_id=assessment_id,
                target_id=obs.observation_id,
                target_type="observation",
                classification=ClassificationAssessment(
                    predicted_source=predicted_source,
                    classification_confidence=intel_res.classification.confidence,
                    probabilities=intel_res.classification.probabilities,
                    feature_importance=intel_res.classification.feature_importance,
                ),
                anomaly=AnomalyAssessment(
                    is_anomaly=intel_res.anomaly.is_anomaly,
                    anomaly_score=intel_res.anomaly.anomaly_score,
                    baseline_deviation_sigma=float(intel_res.anomaly.baseline_deviation or 0.0),
                    anomaly_rationale=intel_res.anomaly.anomaly_rationale or "Evaluated against regional baseline",
                ),
                risk=RiskAssessmentResult(
                    risk_score=intel_res.risk.risk_score,
                    severity=severity,
                    frp_component=intel_res.risk.frp_component,
                    weather_component=intel_res.risk.weather_component,
                    proximity_component=intel_res.risk.proximity_component,
                    historical_component=intel_res.risk.historical_component,
                    factors=[
                        RiskFactor(
                            factor=f.factor,
                            weight=float(f.weight),
                            impact=RiskLevel(f.impact.value),
                            description=f.description,
                        )
                        for f in intel_res.risk.explainable_factors
                    ],
                    recommended_action=intel_res.risk.recommended_action,
                ),
                data_quality=DataQualityAssessment(
                    completeness_score=0.95 if ctx.has_geospatial and ctx.has_weather else 0.70,
                    uncertainty_score=0.15,
                    missing_sources=[] if ctx.has_geospatial else ["geospatial_enrichment"],
                ),
                methodology=AssessmentMethodology(
                    method="ThermalIntelligenceEngine-V2",
                    algorithm_version=self.intelligence_engine.model_version,
                    input_hash=input_hash,
                    as_of_utc=sim_time,
                ),
                created_at_utc=db_created_at,
            )
            self._assessments[assessment_id] = asm
            step_assessments.append(asm)

            # 4. Spatiotemporal Incident Correlation
            matched_incident = self._correlate_observation(obs, hotspot)

            if matched_incident is None:
                # Create a new persistent Incident (Stable Identity Rule)
                self._incident_counter += 1
                new_incident_id = f"INC-{sim_time[:10].replace('-', '')}-{self._incident_counter:04d}"
                
                new_incident = Incident(
                    incident_id=new_incident_id,
                    status=IncidentStatus.ACTIVE,
                    first_seen_utc=obs.acquisition_time_utc,
                    last_seen_utc=obs.acquisition_time_utc,
                    centroid_latitude=obs.latitude,
                    centroid_longitude=obs.longitude,
                    nearest_place=nearest_place,
                    peak_frp=obs.frp,
                    average_frp=obs.frp,
                    observation_count=1,
                    current_risk_score=asm.risk.risk_score,
                    current_severity=asm.risk.severity,
                    current_classification=asm.classification.predicted_source,
                    current_assessment_id=asm.assessment_id,
                    created_at_utc=db_created_at,
                    updated_at_utc=db_created_at,
                )
                self._incidents[new_incident_id] = new_incident
                target_incident = new_incident

                # Emit 'created' timeline event
                self._event_counter += 1
                evt = IncidentEvent(
                    event_id=f"EVT-{new_incident_id}-{self._event_counter:04d}",
                    incident_id=new_incident_id,
                    event_type=IncidentEventType.CREATED,
                    timestamp_utc=sim_time,
                    actor="replay_pipeline",
                    reason=f"Incident established from initial observation {obs.observation_id}",
                    metadata={
                        "observation_id": obs.observation_id,
                        "initial_frp": obs.frp,
                        "risk_score": asm.risk.risk_score,
                    },
                )
                self._events.append(evt)
                step_events.append(evt)

            else:
                target_incident = matched_incident
                old_severity = target_incident.current_severity
                old_risk = target_incident.current_risk_score

                # Update running centroid & FRP stats
                new_count = target_incident.observation_count + 1
                new_avg_frp = (
                    (target_incident.average_frp * target_incident.observation_count) + obs.frp
                ) / new_count
                new_peak_frp = max(target_incident.peak_frp, obs.frp)

                # Centroid shift
                new_lat = (
                    (target_incident.centroid_latitude * target_incident.observation_count) + obs.latitude
                ) / new_count
                new_lon = (
                    (target_incident.centroid_longitude * target_incident.observation_count) + obs.longitude
                ) / new_count

                # Update incident state
                target_incident.observation_count = new_count
                target_incident.average_frp = round(new_avg_frp, 2)
                target_incident.peak_frp = round(new_peak_frp, 2)
                target_incident.centroid_latitude = round(new_lat, 6)
                target_incident.centroid_longitude = round(new_lon, 6)
                target_incident.last_seen_utc = obs.acquisition_time_utc
                target_incident.current_risk_score = asm.risk.risk_score
                target_incident.current_severity = asm.risk.severity
                target_incident.current_classification = asm.classification.predicted_source
                target_incident.current_assessment_id = asm.assessment_id
                target_incident.updated_at_utc = db_created_at

                # Emit 'observation_added' event
                self._event_counter += 1
                evt_add = IncidentEvent(
                    event_id=f"EVT-{target_incident.incident_id}-{self._event_counter:04d}",
                    incident_id=target_incident.incident_id,
                    event_type=IncidentEventType.OBSERVATION_ADDED,
                    timestamp_utc=sim_time,
                    actor="replay_pipeline",
                    reason=f"Observation {obs.observation_id} correlated to incident",
                    metadata={
                        "observation_id": obs.observation_id,
                        "observation_count": new_count,
                        "frp": obs.frp,
                    },
                )
                self._events.append(evt_add)
                step_events.append(evt_add)

                # Check for escalation
                if self._is_escalated(old_severity, asm.risk.severity):
                    self._event_counter += 1
                    evt_esc = IncidentEvent(
                        event_id=f"EVT-{target_incident.incident_id}-{self._event_counter:04d}",
                        incident_id=target_incident.incident_id,
                        event_type=IncidentEventType.ESCALATED,
                        timestamp_utc=sim_time,
                        actor="replay_pipeline",
                        reason=f"Incident escalated from {old_severity.value} to {asm.risk.severity.value}",
                        metadata={
                            "previous_severity": old_severity.value,
                            "new_severity": asm.risk.severity.value,
                            "previous_risk": old_risk,
                            "new_risk": asm.risk.risk_score,
                        },
                    )
                    self._events.append(evt_esc)
                    step_events.append(evt_esc)

            # Link observation to incident
            self._incident_observations.append(
                IncidentObservation(
                    incident_id=target_incident.incident_id,
                    observation_id=obs.observation_id,
                    joined_at_utc=sim_time,
                    association_method="dbscan_spatiotemporal",
                )
            )

            # 5. Operational Alert Generation & Deduplication
            alert = self._evaluate_and_generate_alert(obs, target_incident, asm, sim_time, db_created_at)
            if alert:
                self._alerts.append(alert)
                step_alerts.append(alert)

        return StepExecutionResult(
            as_of_utc=sim_time,
            observations=observations,
            assessments=step_assessments,
            active_incidents=list(self._incidents.values()),
            new_events=step_events,
            new_alerts=step_alerts,
        )

    def _correlate_observation(self, obs: Observation, hotspot: Hotspot) -> Optional[Incident]:
        """Find an existing proximate incident for the observation."""
        for inc in self._incidents.values():
            dist_km = haversine_distance_km(
                obs.latitude, obs.longitude, inc.centroid_latitude, inc.centroid_longitude
            )
            if dist_km <= self.aggregator.distance_threshold_km:
                if self.profile and hasattr(self.profile, "incidents"):
                    obs_src = obs.source_attributes.get("source_type", obs.source_attributes.get("expected_source"))
                    if obs_src and inc.current_classification != SourceType.UNKNOWN:
                        incomp_set = {
                            (p[0].lower(), p[1].lower())
                            for p in self.profile.incidents.incompatible_pairs
                        }
                        pair = (str(obs_src).lower(), inc.current_classification.value.lower())
                        reverse_pair = (pair[1], pair[0])
                        if (pair in incomp_set or reverse_pair in incomp_set) and dist_km > 0.3:
                            continue
                return inc
        return None

    @staticmethod
    def _is_escalated(old_sev: RiskLevel, new_sev: RiskLevel) -> bool:
        """Check if severity tier stepped up."""
        severity_rank = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }
        return severity_rank.get(new_sev, 0) > severity_rank.get(old_sev, 0)

    def _evaluate_and_generate_alert(
        self,
        obs: Observation,
        incident: Incident,
        asm: Assessment,
        sim_time: str,
        db_created_at: str,
    ) -> Optional[AlertV2]:
        """Generate deduplicated AlertV2 if hazard threshold is satisfied."""
        risk_score = asm.risk.risk_score
        severity = asm.risk.severity

        if severity == RiskLevel.CRITICAL or risk_score >= 75.0:
            priority = AlertSeverity.CRITICAL
        elif severity == RiskLevel.HIGH or risk_score >= 50.0:
            priority = AlertSeverity.WARNING
        elif severity == RiskLevel.MEDIUM or risk_score >= 25.0:
            priority = AlertSeverity.INFO
        else:
            return None

        # Build deterministic deduplication key
        dedupe_key = f"{incident.incident_id}:{priority.value}:{asm.classification.predicted_source.value}"

        # Prevent duplicate identical alert emissions for the same incident condition
        if any(a.dedupe_key == dedupe_key for a in self._alerts):
            return None

        self._alert_counter += 1
        alert_id = f"ALT-{incident.incident_id}-{self._alert_counter:04d}"

        title = f"{priority.value.upper()}: {asm.classification.predicted_source.value.replace('_', ' ').title()} near {incident.nearest_place or 'Monitored Sector'}"
        message = (
            f"Thermal anomaly detected with FRP {obs.frp:.1f} MW. "
            f"Composite risk score: {risk_score:.1f}/100 ({severity.value.upper()}). "
            f"Recommended action: {asm.risk.recommended_action}"
        )

        return AlertV2(
            alert_id=alert_id,
            incident_id=incident.incident_id,
            observation_id=obs.observation_id,
            rule_id=f"RULE_{priority.value.upper()}_{asm.classification.predicted_source.value.upper()}",
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.ACTIVE,
            title=title,
            message=message,
            evidence={
                "measured_frp": obs.frp,
                "brightness_kelvin": obs.brightness,
                "risk_score": risk_score,
                "severity": severity.value,
                "as_of_utc": sim_time,
            },
            metadata={
                "recommended_action": asm.risk.recommended_action,
                "incident_observation_count": incident.observation_count,
            },
            created_at_utc=db_created_at,
        )
