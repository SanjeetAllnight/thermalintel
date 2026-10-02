"""Deterministic cooldown and flood protection engine for ThermalIntel V2 alerts.

Prevents alert fatigue and notifications storms on noisy, chattering incidents via:
- Per-rule cooldown: minimum duration before the same rule can fire again for an incident
- Per-incident cooldown: bounded pacing between alerts on the same incident
- Duplicate suppression: suppression of repeated identical condition signatures
- Sliding-window rate limiting: hard ceiling on total alerts per incident per time window
"""

from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime, timezone
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import AlertSeverity, AlertState


def _iso_to_epoch(ts: str) -> float:
    """Safely convert ISO 8601 UTC timestamp to epoch seconds."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


@dataclass
class FloodProtectionConfig:
    """Configuration thresholds for alert flood and chatter protection."""
    per_rule_cooldown_seconds: int = 900       # 15 minutes per rule per incident
    per_incident_cooldown_seconds: int = 180   # 3 minutes pacing per incident
    max_alerts_per_window: int = 5             # Maximum 5 alerts per incident per window
    window_seconds: int = 3600                 # 1 hour evaluation window


@dataclass
class FloodProtectionDecision:
    """Outcome of flood protection evaluation for an alert."""
    allowed: bool
    reason: Optional[str] = None
    suppression_type: Optional[str] = None     # 'DUPLICATE', 'RULE_COOLDOWN', 'INCIDENT_COOLDOWN', 'RATE_LIMITED'


class FloodProtectionEngine:
    """Deterministic, local evaluator enforcing cooldown and flood limits."""

    def __init__(self, config: Optional[FloodProtectionConfig] = None):
        self.config = config or FloodProtectionConfig()

    def evaluate(
        self,
        candidate: AlertV2,
        recent_alerts: List[AlertV2],
        current_time_epoch: Optional[float] = None,
    ) -> FloodProtectionDecision:
        """Evaluate candidate alert against historical alerts for the same incident.
        
        Args:
            candidate: Newly generated AlertV2 attempting to fire.
            recent_alerts: List of already recorded alerts for this incident.
            current_time_epoch: Optional reference epoch (defaults to candidate's timestamp or now).
        """
        # Incident closure notifications always pass through (administrative lifecycle transition)
        if candidate.rule_id == "RULE_INCIDENT_CLOSED" or candidate.state == AlertState.RESOLVED:
            return FloodProtectionDecision(allowed=True)

        now = current_time_epoch or _iso_to_epoch(candidate.created_at_utc) or datetime.now(timezone.utc).timestamp()

        # 1. Exact Dedupe Key Check
        for past in recent_alerts:
            if past.dedupe_key == candidate.dedupe_key:
                return FloodProtectionDecision(
                    allowed=False,
                    reason=f"Exact duplicate dedupe key already exists: {candidate.dedupe_key}",
                    suppression_type="DUPLICATE",
                )

        # Filter recent alerts for the same incident that are NOT already suppressed
        incident_alerts = [
            a for a in recent_alerts
            if a.incident_id == candidate.incident_id and a.state != AlertState.SUPPRESSED
        ]

        # 2. Bounded Alert Generation (Window Rate Limit)
        window_start = now - self.config.window_seconds
        alerts_in_window = [
            a for a in incident_alerts
            if _iso_to_epoch(a.created_at_utc) >= window_start
        ]

        if len(alerts_in_window) >= self.config.max_alerts_per_window:
            return FloodProtectionDecision(
                allowed=False,
                reason=(
                    f"Incident {candidate.incident_id} exceeded maximum alert limit "
                    f"({len(alerts_in_window)}/{self.config.max_alerts_per_window} in {self.config.window_seconds}s)"
                ),
                suppression_type="RATE_LIMITED",
            )

        # 3. Per-Rule Cooldown Check
        same_rule_alerts = [
            a for a in incident_alerts
            if a.rule_id == candidate.rule_id
        ]
        if same_rule_alerts:
            latest_rule_alert = max(same_rule_alerts, key=lambda a: _iso_to_epoch(a.created_at_utc))
            elapsed = now - _iso_to_epoch(latest_rule_alert.created_at_utc)
            if elapsed < self.config.per_rule_cooldown_seconds:
                # Critical escalation can bypass rule cooldown only if previous was not critical
                if candidate.priority == AlertSeverity.CRITICAL and latest_rule_alert.priority != AlertSeverity.CRITICAL:
                    pass  # Allow critical escalation override
                else:
                    return FloodProtectionDecision(
                        allowed=False,
                        reason=(
                            f"Rule {candidate.rule_id} is on cooldown for incident {candidate.incident_id} "
                            f"({int(elapsed)}s elapsed, required {self.config.per_rule_cooldown_seconds}s)"
                        ),
                        suppression_type="RULE_COOLDOWN",
                    )

        # 4. Per-Incident Pacing Cooldown Check
        if incident_alerts:
            latest_incident_alert = max(incident_alerts, key=lambda a: _iso_to_epoch(a.created_at_utc))
            elapsed = now - _iso_to_epoch(latest_incident_alert.created_at_utc)
            if elapsed < self.config.per_incident_cooldown_seconds:
                # Critical alerts can bypass pacing cooldown
                if candidate.priority == AlertSeverity.CRITICAL and latest_incident_alert.priority != AlertSeverity.CRITICAL:
                    pass  # Allow escalation override
                else:
                    return FloodProtectionDecision(
                        allowed=False,
                        reason=(
                            f"Incident {candidate.incident_id} is on pacing cooldown "
                            f"({int(elapsed)}s elapsed, required {self.config.per_incident_cooldown_seconds}s)"
                        ),
                        suppression_type="INCIDENT_COOLDOWN",
                    )

        return FloodProtectionDecision(allowed=True)
