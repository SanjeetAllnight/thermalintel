"""Alert prioritization and ordering engine for ThermalIntel Phase 4 & V2.

Provides deterministic priority ranking for operational alerts based on:
1. Severity hierarchy (CRITICAL > WARNING > INFO)
2. Quantitative risk score (descending)
3. Detection recency (latest timestamp first)
4. Deterministic ID tie-breaking
"""

from datetime import datetime, timezone
from typing import List, Tuple, Union
from services.api.schemas.alert import Alert
from services.api.schemas.common import AlertSeverity as V1AlertSeverity
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import AlertSeverity as V2AlertSeverity


def _parse_alert_timestamp(timestamp_str: str) -> float:
    """Convert ISO timestamp string to epoch seconds for deterministic comparison."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


# Severity weights for deterministic sorting
SEVERITY_WEIGHTS = {
    V1AlertSeverity.CRITICAL: 3,
    V1AlertSeverity.WARNING: 2,
    V1AlertSeverity.INFO: 1,
    V2AlertSeverity.CRITICAL: 3,
    V2AlertSeverity.WARNING: 2,
    V2AlertSeverity.INFO: 1,
}


def alert_priority_key(alert: Alert) -> Tuple[int, float, float, str]:
    """Generate a multi-attribute sorting tuple for deterministic alert ranking.
    
    Higher values indicate higher operational priority.
    Returns:
        (severity_weight, risk_score, timestamp_epoch, alert_id)
    """
    severity_rank = SEVERITY_WEIGHTS.get(alert.severity, 0)
    risk = alert.risk_score
    epoch = _parse_alert_timestamp(alert.timestamp)
    return (severity_rank, risk, epoch, alert.id)


def alert_v2_priority_key(alert: AlertV2) -> Tuple[int, float, float, str]:
    """Generate a multi-attribute sorting tuple for deterministic AlertV2 ranking."""
    severity_rank = SEVERITY_WEIGHTS.get(alert.priority, 0)
    risk = float(alert.evidence.get("current_risk_score", alert.evidence.get("risk_score", 0.0)))
    epoch = _parse_alert_timestamp(alert.created_at_utc)
    return (severity_rank, risk, epoch, alert.alert_id)


class AlertPriorityComparator:
    """Deterministic comparator and ranker for operational alerts."""

    @staticmethod
    def compare(a: Alert, b: Alert) -> int:
        """Compare two V1 alerts.
        
        Returns:
            > 0 if a has higher priority than b
            < 0 if b has higher priority than a
            0 if identical priority
        """
        key_a = alert_priority_key(a)
        key_b = alert_priority_key(b)
        if key_a > key_b:
            return 1
        elif key_a < key_b:
            return -1
        return 0

    @classmethod
    def sort(cls, alerts: List[Alert]) -> List[Alert]:
        """Sort V1 alerts in strictly descending priority order (highest operational threat first)."""
        return sorted(
            alerts,
            key=lambda a: (
                -SEVERITY_WEIGHTS.get(a.severity, 0),
                -a.risk_score,
                -_parse_alert_timestamp(a.timestamp),
                a.id,
            ),
        )

    @classmethod
    def sort_v2(cls, alerts: List[AlertV2]) -> List[AlertV2]:
        """Sort AlertV2 instances in strictly descending priority order."""
        return sorted(
            alerts,
            key=lambda a: (
                -SEVERITY_WEIGHTS.get(a.priority, 0),
                -float(a.evidence.get("current_risk_score", a.evidence.get("risk_score", 0.0))),
                -_parse_alert_timestamp(a.created_at_utc),
                a.alert_id,
            ),
        )
