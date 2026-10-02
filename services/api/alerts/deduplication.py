"""Alert deduplication and deterministic identity engine for ThermalIntel Phase 4 & V2.

Prevents alert flooding by enforcing deterministic alert IDs, transition-based dedupe keys,
and suppressing duplicate notifications for ongoing identical conditions.
"""

from typing import List, Dict, Set, Optional
from services.api.schemas.alert import Alert
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import AlertState, AlertSeverity


class AlertDeduplicator:
    """Deduplicates alert streams based on deterministic entity and condition keys."""

    @staticmethod
    def generate_alert_id(hotspot_id: str, condition_suffix: Optional[str] = None) -> str:
        """Derive a stable, deterministic alert ID from hotspot/incident identifier.
        
        Examples:
            generate_alert_id("VIIRS-SNPP-20261001-001") -> "ALT-VIIRS-SNPP-20261001-001"
            generate_alert_id("ALT-20261001-001") -> "ALT-20261001-001"
        """
        base = hotspot_id
        if base.startswith("INC-"):
            base = base[4:]

        if not base.startswith("ALT-"):
            alert_id = f"ALT-{base}"
        else:
            alert_id = base

        if condition_suffix:
            alert_id = f"{alert_id}-{condition_suffix}"

        return alert_id

    @staticmethod
    def generate_transition_dedupe_key(
        incident_id: str, rule_id: str, transition_context: str
    ) -> str:
        """Generate a canonical, deterministic dedupe key for an incident transition.
        
        Example:
            generate_transition_dedupe_key("INC-20261001-0001", "RULE_INCIDENT_ESCALATED", "ESCALATED:CRITICAL")
            -> "INC-20261001-0001:RULE_INCIDENT_ESCALATED:ESCALATED:CRITICAL"
        """
        return f"{incident_id}:{rule_id}:{transition_context}"

    def deduplicate(self, alerts: List[Alert]) -> List[Alert]:
        """Deduplicate a collection of V1 alerts while preserving acknowledgment status and priority.
        
        If multiple alerts target the same hotspot and severity, the alert with
        higher risk score or acknowledged state is preserved.
        """
        if not alerts:
            return []

        seen_keys: Dict[str, Alert] = {}

        for alert in alerts:
            # Identity key: based on unique alert ID or (hotspot_id, severity)
            key = f"{alert.hotspot_id}:{alert.severity.value}"

            if key not in seen_keys:
                seen_keys[key] = alert
            else:
                existing = seen_keys[key]
                # If existing is acknowledged and new is not, preserve acknowledgment
                if existing.is_acknowledged and not alert.is_acknowledged:
                    if alert.risk_score > existing.risk_score:
                        updated_alert = alert.model_copy(update={"is_acknowledged": True})
                        seen_keys[key] = updated_alert
                elif not existing.is_acknowledged and alert.is_acknowledged:
                    seen_keys[key] = alert
                elif alert.risk_score > existing.risk_score:
                    seen_keys[key] = alert

        return list(seen_keys.values())

    def deduplicate_v2(self, alerts: List[AlertV2]) -> List[AlertV2]:
        """Deduplicate a collection of AlertV2 instances using dedupe_key.
        
        Preserves acknowledged state and suppresses duplicate alerts.
        """
        if not alerts:
            return []

        seen: Dict[str, AlertV2] = {}
        for a in alerts:
            key = a.dedupe_key
            if key not in seen:
                seen[key] = a
            else:
                existing = seen[key]
                # Preserve ACKNOWLEDGED state if already acknowledged
                if existing.state == AlertState.ACKNOWLEDGED and a.state != AlertState.ACKNOWLEDGED:
                    pass  # keep existing acknowledged alert
                elif existing.state != AlertState.ACKNOWLEDGED and a.state == AlertState.ACKNOWLEDGED:
                    seen[key] = a
                else:
                    # Keep the one with newer creation timestamp
                    if a.created_at_utc > existing.created_at_utc:
                        seen[key] = a

        return list(seen.values())
