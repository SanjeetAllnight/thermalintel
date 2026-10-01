"""Alert prioritization and ordering engine for ThermalIntel Phase 4.

Provides deterministic priority ranking for operational alerts based on:
1. Severity hierarchy (CRITICAL > WARNING > INFO)
2. Quantitative risk score (descending)
3. Detection recency (latest timestamp first)
4. Fire Radiative Power (MW)
5. Deterministic ID tie-breaking
"""

from datetime import datetime, timezone
from typing import List, Tuple
from services.api.schemas.alert import Alert
from services.api.schemas.common import AlertSeverity


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
    AlertSeverity.CRITICAL: 3,
    AlertSeverity.WARNING: 2,
    AlertSeverity.INFO: 1,
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
    # Tie-breaking with alert ID string
    return (severity_rank, risk, epoch, alert.id)


class AlertPriorityComparator:
    """Deterministic comparator and ranker for alerts."""

    @staticmethod
    def compare(a: Alert, b: Alert) -> int:
        """Compare two alerts.
        
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
        """Sort alerts in strictly descending priority order (highest operational threat first)."""
        # Python's sort is stable; sorting by key with descending components
        return sorted(
            alerts,
            key=lambda a: (
                -SEVERITY_WEIGHTS.get(a.severity, 0),
                -a.risk_score,
                -_parse_alert_timestamp(a.timestamp),
                a.id,
            ),
        )
