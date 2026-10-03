"""Transition-driven alert rules engine for ThermalIntel V2.

Evaluates meaningful incident lifecycle transitions (CREATED, ESCALATED,
DEESCALATED, REOPENED, CLOSED) against operational criteria to produce
canonical AlertV2 instances with rich forensic evidence.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import (
    AlertSeverity,
    AlertState,
    IncidentEventType,
    IncidentStatus,
    RiskLevel,
    SourceType,
    now_utc_iso,
)
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.incident import Incident


@dataclass
class TransitionContext:
    """Encapsulates the state context surrounding an incident transition."""
    incident: Incident
    event: IncidentEvent
    previous_incident: Optional[Incident] = None
    extra_evidence: Dict[str, Any] = field(default_factory=dict)


class AlertRule(ABC):
    """Abstract base class for operational alert evaluation rules."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Deterministic unique rule identifier."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable explanation of rule criteria."""
        pass

    @abstractmethod
    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        """Evaluate transition context and produce an AlertV2 if criteria are met."""
        pass


class NewIncidentRule(AlertRule):
    """Triggers operational alerts when a new high-severity incident is created."""

    rule_id = "RULE_NEW_INCIDENT"
    description = "Triggers on newly registered incidents exhibiting HIGH or CRITICAL severity."

    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        if ctx.event.event_type != IncidentEventType.CREATED:
            return None

        inc = ctx.incident
        # Only alert on high or critical threat
        if inc.current_severity == RiskLevel.CRITICAL or inc.current_risk_score >= 75.0:
            priority = AlertSeverity.CRITICAL
        elif inc.current_severity == RiskLevel.HIGH or inc.current_risk_score >= 50.0:
            priority = AlertSeverity.WARNING
        else:
            # Low or benign incidents do not generate alerts
            return None

        location = inc.nearest_place or f"({round(inc.centroid_latitude, 3)}, {round(inc.centroid_longitude, 3)})"
        source_title = inc.current_classification.value.replace("_", " ").title()

        title = f"{priority.value.upper()}: New {source_title} Incident Registered - {location}"
        message = (
            f"New incident {inc.incident_id} detected at {location} with peak FRP of {inc.peak_frp} MW "
            f"and risk score of {round(inc.current_risk_score, 1)} ({inc.current_severity.value.upper()}). "
            f"Correlated from {inc.observation_count} observation(s)."
        )

        dedupe_key = f"{inc.incident_id}:{self.rule_id}:{ctx.event.event_id}"
        alert_id = f"ALT-{inc.incident_id}-{ctx.event.event_id}"

        evidence = {
            "incident_id": inc.incident_id,
            "transition": "created",
            "triggering_rule": self.rule_id,
            "current_risk_score": inc.current_risk_score,
            "current_severity": inc.current_severity.value,
            "peak_frp": inc.peak_frp,
            "average_frp": inc.average_frp,
            "observation_count": inc.observation_count,
            "centroid": {
                "latitude": inc.centroid_latitude,
                "longitude": inc.centroid_longitude,
            },
            "nearest_place": inc.nearest_place,
            "event_id": ctx.event.event_id,
            "actor": ctx.event.actor,
            "event_reason": ctx.event.reason,
            "event_timestamp_utc": ctx.event.timestamp_utc,
            **ctx.extra_evidence,
        }

        if priority == AlertSeverity.CRITICAL:
            action = "Dispatch immediate field reconnaissance unit; coordinate evacuation staging and perimeter defense."
        else:
            action = "Monitor sector progression via next orbital satellite pass and notify regional dispatch."

        tags = [inc.current_classification.value, "new_incident", f"severity_{inc.current_severity.value}"]
        if inc.peak_frp >= 100.0:
            tags.append("critical_frp")

        return AlertV2(
            alert_id=alert_id,
            incident_id=inc.incident_id,
            observation_id=None,
            rule_id=self.rule_id,
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.ACTIVE,
            title=title,
            message=message,
            evidence=evidence,
            metadata={
                "recommended_action": action,
                "tags": tags,
                "transition_event": ctx.event.event_type.value,
            },
            created_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
        )


class EscalatedIncidentRule(AlertRule):
    """Triggers when an incident escalates in operational threat or severity."""

    rule_id = "RULE_INCIDENT_ESCALATED"
    description = "Triggers on incident escalation events, prioritizing critical risk transitions."

    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        if ctx.event.event_type != IncidentEventType.ESCALATED:
            return None

        inc = ctx.incident
        old_severity = ctx.event.metadata.get("old_severity")
        old_risk = ctx.event.metadata.get("old_risk")

        if inc.current_severity == RiskLevel.CRITICAL or inc.current_risk_score >= 75.0:
            priority = AlertSeverity.CRITICAL
        elif inc.current_severity == RiskLevel.HIGH or inc.current_risk_score >= 50.0:
            priority = AlertSeverity.WARNING
        else:
            priority = AlertSeverity.INFO

        location = inc.nearest_place or f"({round(inc.centroid_latitude, 3)}, {round(inc.centroid_longitude, 3)})"
        source_title = inc.current_classification.value.replace("_", " ").title()

        title = f"ESCALATION: {source_title} Incident {inc.incident_id} Escalated - {location}"
        old_desc = f"from {old_severity.upper()} ({old_risk})" if old_severity and old_risk else ""
        message = (
            f"Incident {inc.incident_id} escalated {old_desc} to {inc.current_severity.value.upper()} "
            f"(risk {round(inc.current_risk_score, 1)}). Peak FRP currently {inc.peak_frp} MW. "
            f"Escalation rationale: {ctx.event.reason}."
        )

        dedupe_key = f"{inc.incident_id}:{self.rule_id}:{inc.current_severity.value}:{ctx.event.event_id}"
        alert_id = f"ALT-{inc.incident_id}-ESC-{ctx.event.event_id}"

        evidence = {
            "incident_id": inc.incident_id,
            "transition": "escalated",
            "triggering_rule": self.rule_id,
            "current_risk_score": inc.current_risk_score,
            "previous_risk_score": old_risk,
            "current_severity": inc.current_severity.value,
            "previous_severity": old_severity,
            "peak_frp": inc.peak_frp,
            "average_frp": inc.average_frp,
            "observation_count": inc.observation_count,
            "centroid": {
                "latitude": inc.centroid_latitude,
                "longitude": inc.centroid_longitude,
            },
            "nearest_place": inc.nearest_place,
            "event_id": ctx.event.event_id,
            "actor": ctx.event.actor,
            "event_reason": ctx.event.reason,
            "event_timestamp_utc": ctx.event.timestamp_utc,
            **ctx.extra_evidence,
        }

        action = (
            "Escalate regional command alert status; mobilize standby containment resources."
            if priority == AlertSeverity.CRITICAL
            else "Increase satellite scan watch frequency and verify perimeter buffer."
        )

        tags = [inc.current_classification.value, "escalation", f"severity_{inc.current_severity.value}"]
        if inc.peak_frp >= 100.0:
            tags.append("critical_frp")

        return AlertV2(
            alert_id=alert_id,
            incident_id=inc.incident_id,
            observation_id=None,
            rule_id=self.rule_id,
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.ACTIVE,
            title=title,
            message=message,
            evidence=evidence,
            metadata={
                "recommended_action": action,
                "tags": tags,
                "transition_event": ctx.event.event_type.value,
            },
            created_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
        )


class DeescalatedIncidentRule(AlertRule):
    """Triggers advisory notifications when an incident de-escalates or threat subsides."""

    rule_id = "RULE_INCIDENT_DEESCALATED"
    description = "Triggers on incident de-escalation events."

    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        if ctx.event.event_type != IncidentEventType.DEESCALATED:
            return None

        inc = ctx.incident
        old_severity = ctx.event.metadata.get("old_severity")
        old_risk = ctx.event.metadata.get("old_risk")

        # De-escalation alerts are advisory (INFO or WARNING if still elevated)
        priority = (
            AlertSeverity.WARNING
            if inc.current_severity == RiskLevel.HIGH
            else AlertSeverity.INFO
        )

        location = inc.nearest_place or f"({round(inc.centroid_latitude, 3)}, {round(inc.centroid_longitude, 3)})"
        source_title = inc.current_classification.value.replace("_", " ").title()

        title = f"DE-ESCALATION: {source_title} Incident {inc.incident_id} Reduced Threat - {location}"
        message = (
            f"Incident {inc.incident_id} de-escalated to {inc.current_severity.value.upper()} "
            f"(risk {round(inc.current_risk_score, 1)}). Mitigation rationale: {ctx.event.reason}."
        )

        dedupe_key = f"{inc.incident_id}:{self.rule_id}:{inc.current_severity.value}:{ctx.event.event_id}"
        alert_id = f"ALT-{inc.incident_id}-DEESC-{ctx.event.event_id}"

        evidence = {
            "incident_id": inc.incident_id,
            "transition": "deescalated",
            "triggering_rule": self.rule_id,
            "current_risk_score": inc.current_risk_score,
            "previous_risk_score": old_risk,
            "current_severity": inc.current_severity.value,
            "previous_severity": old_severity,
            "peak_frp": inc.peak_frp,
            "centroid": {
                "latitude": inc.centroid_latitude,
                "longitude": inc.centroid_longitude,
            },
            "nearest_place": inc.nearest_place,
            "event_id": ctx.event.event_id,
            "event_reason": ctx.event.reason,
            "event_timestamp_utc": ctx.event.timestamp_utc,
            **ctx.extra_evidence,
        }

        return AlertV2(
            alert_id=alert_id,
            incident_id=inc.incident_id,
            observation_id=None,
            rule_id=self.rule_id,
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.ACTIVE,
            title=title,
            message=message,
            evidence=evidence,
            metadata={
                "recommended_action": "Log de-escalation; maintain standard observation baseline.",
                "tags": [inc.current_classification.value, "deescalation"],
                "transition_event": ctx.event.event_type.value,
            },
            created_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
        )


class ReopenedIncidentRule(AlertRule):
    """Triggers when a contained or closed incident flares up or re-emerges."""

    rule_id = "RULE_INCIDENT_REOPENED"
    description = "Triggers on incident re-open events, warning of renewed activity."

    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        if ctx.event.event_type != IncidentEventType.REOPENED:
            return None

        inc = ctx.incident
        # Reopening is urgent if current severity is HIGH or CRITICAL
        if inc.current_severity == RiskLevel.CRITICAL or inc.current_risk_score >= 75.0:
            priority = AlertSeverity.CRITICAL
        elif inc.current_severity == RiskLevel.HIGH or inc.current_risk_score >= 50.0:
            priority = AlertSeverity.WARNING
        else:
            priority = AlertSeverity.INFO

        location = inc.nearest_place or f"({round(inc.centroid_latitude, 3)}, {round(inc.centroid_longitude, 3)})"
        source_title = inc.current_classification.value.replace("_", " ").title()

        title = f"REOPENED: Previously Inactive {source_title} Incident {inc.incident_id} - {location}"
        message = (
            f"Incident {inc.incident_id} has been REOPENED. Renewed thermal radiance detected "
            f"with FRP of {inc.peak_frp} MW and risk score {round(inc.current_risk_score, 1)}. "
            f"Reopen rationale: {ctx.event.reason}."
        )

        dedupe_key = f"{inc.incident_id}:{self.rule_id}:REOPENED:{ctx.event.event_id}"
        alert_id = f"ALT-{inc.incident_id}-REOPEN-{ctx.event.event_id}"

        evidence = {
            "incident_id": inc.incident_id,
            "transition": "reopened",
            "triggering_rule": self.rule_id,
            "current_risk_score": inc.current_risk_score,
            "current_severity": inc.current_severity.value,
            "peak_frp": inc.peak_frp,
            "centroid": {
                "latitude": inc.centroid_latitude,
                "longitude": inc.centroid_longitude,
            },
            "nearest_place": inc.nearest_place,
            "event_id": ctx.event.event_id,
            "event_reason": ctx.event.reason,
            "event_timestamp_utc": ctx.event.timestamp_utc,
            **ctx.extra_evidence,
        }

        return AlertV2(
            alert_id=alert_id,
            incident_id=inc.incident_id,
            observation_id=None,
            rule_id=self.rule_id,
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.ACTIVE,
            title=title,
            message=message,
            evidence=evidence,
            metadata={
                "recommended_action": "Re-engage suppression/monitoring units; assess rekindle spread vector.",
                "tags": [inc.current_classification.value, "reopened"],
                "transition_event": ctx.event.event_type.value,
            },
            created_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
        )


class ClosedIncidentRule(AlertRule):
    """Triggers resolution notification when an incident is officially closed or contained."""

    rule_id = "RULE_INCIDENT_CLOSED"
    description = "Triggers informational resolution notification on incident closure."

    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        if ctx.event.event_type != IncidentEventType.CLOSED:
            return None

        inc = ctx.incident
        priority = AlertSeverity.INFO
        location = inc.nearest_place or f"({round(inc.centroid_latitude, 3)}, {round(inc.centroid_longitude, 3)})"
        source_title = inc.current_classification.value.replace("_", " ").title()

        title = f"RESOLVED: {source_title} Incident {inc.incident_id} Contained & Closed - {location}"
        message = (
            f"Incident {inc.incident_id} at {location} has been marked CLOSED. "
            f"Total observations tracked: {inc.observation_count}. Closure reason: {ctx.event.reason}."
        )

        dedupe_key = f"{inc.incident_id}:{self.rule_id}:CLOSED:{ctx.event.event_id}"
        alert_id = f"ALT-{inc.incident_id}-CLOSED-{ctx.event.event_id}"

        evidence = {
            "incident_id": inc.incident_id,
            "transition": "closed",
            "triggering_rule": self.rule_id,
            "final_risk_score": inc.current_risk_score,
            "final_severity": inc.current_severity.value,
            "final_peak_frp": inc.peak_frp,
            "observation_count": inc.observation_count,
            "centroid": {
                "latitude": inc.centroid_latitude,
                "longitude": inc.centroid_longitude,
            },
            "nearest_place": inc.nearest_place,
            "event_id": ctx.event.event_id,
            "event_reason": ctx.event.reason,
            "event_timestamp_utc": ctx.event.timestamp_utc,
            **ctx.extra_evidence,
        }

        return AlertV2(
            alert_id=alert_id,
            incident_id=inc.incident_id,
            observation_id=None,
            rule_id=self.rule_id,
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.RESOLVED,
            title=title,
            message=message,
            evidence=evidence,
            metadata={
                "recommended_action": "Archive incident dossier; transition area to post-burn monitoring.",
                "tags": [inc.current_classification.value, "closed", "resolved"],
                "transition_event": ctx.event.event_type.value,
            },
            created_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
            resolved_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
        )


class ExtremeFrpRule(AlertRule):
    """Triggers critical alert when an incident experiences an extreme FRP surge."""

    rule_id = "RULE_EXTREME_FRP"
    description = "Triggers CRITICAL alerts on extreme Fire Radiative Power (>= 100 MW)."

    def __init__(self, frp_threshold: float = 100.0):
        self.frp_threshold = frp_threshold

    def evaluate(self, ctx: TransitionContext) -> Optional[AlertV2]:
        inc = ctx.incident
        # Only evaluate on escalated or newly correlated observations (CREATED is handled by NewIncidentRule)
        if ctx.event.event_type not in (
            IncidentEventType.ESCALATED,
            IncidentEventType.OBSERVATION_ADDED,
        ):
            return None

        if inc.peak_frp < self.frp_threshold:
            return None

        # For newly correlated observations (OBSERVATION_ADDED), ensure the new observation
        # actually caused or contributed extreme FRP, or that previous incident didn't already have it
        if ctx.event.event_type == IncidentEventType.OBSERVATION_ADDED:
            obs_frp = ctx.event.metadata.get("frp", ctx.event.metadata.get("observation_frp"))
            if obs_frp is not None and obs_frp < self.frp_threshold:
                return None
            if ctx.previous_incident and ctx.previous_incident.peak_frp >= self.frp_threshold:
                if inc.peak_frp <= ctx.previous_incident.peak_frp:
                    return None

        priority = AlertSeverity.CRITICAL
        location = inc.nearest_place or f"({round(inc.centroid_latitude, 3)}, {round(inc.centroid_longitude, 3)})"
        source_title = inc.current_classification.value.replace("_", " ").title()

        title = f"EXTREME FRP: {source_title} Reached {round(inc.peak_frp, 1)} MW - {location}"
        message = (
            f"Extreme thermal radiance of {round(inc.peak_frp, 1)} MW detected for incident {inc.incident_id} "
            f"at {location}. High potential for rapid convective spread and severe flame front intensity."
        )

        dedupe_key = f"{inc.incident_id}:{self.rule_id}:PEAK_FRP:{ctx.event.event_id}"
        alert_id = f"ALT-{inc.incident_id}-EXTREME-FRP-{ctx.event.event_id}"

        evidence = {
            "incident_id": inc.incident_id,
            "transition": ctx.event.event_type.value,
            "triggering_rule": self.rule_id,
            "peak_frp": inc.peak_frp,
            "threshold_frp": self.frp_threshold,
            "current_risk_score": inc.current_risk_score,
            "current_severity": inc.current_severity.value,
            "centroid": {
                "latitude": inc.centroid_latitude,
                "longitude": inc.centroid_longitude,
            },
            "nearest_place": inc.nearest_place,
            "event_id": ctx.event.event_id,
            "event_timestamp_utc": ctx.event.timestamp_utc,
            **ctx.extra_evidence,
        }

        return AlertV2(
            alert_id=alert_id,
            incident_id=inc.incident_id,
            observation_id=None,
            rule_id=self.rule_id,
            dedupe_key=dedupe_key,
            priority=priority,
            state=AlertState.ACTIVE,
            title=title,
            message=message,
            evidence=evidence,
            metadata={
                "recommended_action": "Prioritize aerial suppression and establish safety defense perimeter immediately.",
                "tags": [inc.current_classification.value, "extreme_frp", "critical_frp"],
                "transition_event": ctx.event.event_type.value,
            },
            created_at_utc=ctx.event.timestamp_utc or now_utc_iso(),
        )


def get_default_rules(alert_config: Optional[Any] = None) -> List[AlertRule]:
    """Return the suite of operational alert evaluation rules configured for the active or given alert policy."""
    cfg = alert_config
    if cfg is None:
        try:
            from profiles.loader import get_active_profile
            cfg = get_active_profile().alerts
        except Exception:
            cfg = None

    extreme_thresh = 100.0
    enabled_rule_ids = None

    if cfg is not None:
        if hasattr(cfg, "extreme_frp_threshold"):
            extreme_thresh = cfg.extreme_frp_threshold
        if hasattr(cfg, "enabled_rules") and cfg.enabled_rules:
            enabled_rule_ids = set(cfg.enabled_rules)

    all_rules = [
        NewIncidentRule(),
        EscalatedIncidentRule(),
        DeescalatedIncidentRule(),
        ReopenedIncidentRule(),
        ClosedIncidentRule(),
        ExtremeFrpRule(frp_threshold=extreme_thresh),
    ]

    if enabled_rule_ids is not None:
        return [r for r in all_rules if r.rule_id in enabled_rule_ids]
    return all_rules
