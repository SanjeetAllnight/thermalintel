"""Operational alert health and telemetry computation for ThermalIntel V2.

Computes operational reliability metrics across a given sliding time window:
- Volume and priority mix (critical, warning, info)
- Operational lifecycle progression (acknowledged vs active vs resolved)
- Noise, duplicate, and flood suppression rates
- Identification of chattering/noisy incidents requiring tuning or containment
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import AlertSeverity, AlertState, now_utc_iso


def _parse_utc_epoch(iso_str: str) -> float:
    """Parse ISO UTC timestamp to epoch seconds."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


class ChatteringIncident(BaseModel):
    """Telemetry representation of an incident generating frequent alerts."""
    incident_id: str = Field(..., description="Target incident identifier")
    alert_count: int = Field(..., description="Total alerts triggered within window")
    critical_count: int = Field(default=0, description="Critical alerts count")
    suppressed_count: int = Field(default=0, description="Suppressed alert attempts")
    last_alert_time_utc: str = Field(..., description="Most recent alert timestamp")


class AlertHealthMetrics(BaseModel):
    """Operational health snapshot of the alert subsystem."""
    window_seconds: int = Field(..., description="Sliding evaluation window in seconds")
    as_of_utc: str = Field(..., description="Snapshot reference timestamp in UTC")
    total_alerts: int = Field(..., description="Total alerts recorded in window (including active, acked, resolved, suppressed)")
    critical_count: int = Field(..., description="Count of critical alerts")
    warning_count: int = Field(..., description="Count of warning alerts")
    info_count: int = Field(..., description="Count of informational alerts")
    acknowledged_count: int = Field(..., description="Count of acknowledged alerts")
    unresolved_count: int = Field(..., description="Count of active, unresolved alerts")
    resolved_count: int = Field(..., description="Count of resolved alerts")
    suppressed_count: int = Field(..., description="Count of suppressed/duplicate alerts")
    alert_rate_per_hour: float = Field(..., description="Average alert rate per hour in the window")
    priority_mix: Dict[str, float] = Field(..., description="Percentage mix by priority (0-100%)")
    chattering_incidents: List[ChatteringIncident] = Field(
        default_factory=list,
        description="Incidents exceeding the chatter frequency threshold"
    )


def compute_health_from_alerts(
    alerts: List[AlertV2],
    window_seconds: int = 86400,
    as_of_utc: Optional[str] = None,
    chatter_threshold: int = 3,
) -> AlertHealthMetrics:
    """Deterministically compute operational alert health metrics over a time window.
    
    Args:
        alerts: Collection of AlertV2 instances.
        window_seconds: Duration of analysis window in seconds (default 24h = 86400).
        as_of_utc: Reference time for window end (defaults to current UTC).
        chatter_threshold: Alert count per incident to qualify as chattering.
    """
    now_str = as_of_utc or now_utc_iso()
    as_of_epoch = _parse_utc_epoch(now_str) or datetime.now(timezone.utc).timestamp()
    window_start_epoch = as_of_epoch - window_seconds

    # Filter alerts falling within window
    window_alerts = [
        a for a in alerts
        if _parse_utc_epoch(a.created_at_utc) >= window_start_epoch
        and _parse_utc_epoch(a.created_at_utc) <= as_of_epoch
    ]

    total = len(window_alerts)
    critical_count = 0
    warning_count = 0
    info_count = 0
    acknowledged_count = 0
    unresolved_count = 0
    resolved_count = 0
    suppressed_count = 0

    # Incident chatter aggregator: incident_id -> {total, critical, suppressed, latest_time}
    inc_chatter: Dict[str, Dict[str, Any]] = {}

    for a in window_alerts:
        # Priority counting
        if a.priority == AlertSeverity.CRITICAL:
            critical_count += 1
        elif a.priority == AlertSeverity.WARNING:
            warning_count += 1
        else:
            info_count += 1

        # State counting
        if a.state == AlertState.ACKNOWLEDGED:
            acknowledged_count += 1
        elif a.state == AlertState.ACTIVE:
            unresolved_count += 1
        elif a.state == AlertState.RESOLVED:
            resolved_count += 1
        elif a.state == AlertState.SUPPRESSED:
            suppressed_count += 1

        # Chatter tracking
        if a.incident_id:
            iid = a.incident_id
            if iid not in inc_chatter:
                inc_chatter[iid] = {
                    "count": 0,
                    "critical": 0,
                    "suppressed": 0,
                    "latest_time": a.created_at_utc,
                }
            entry = inc_chatter[iid]
            entry["count"] += 1
            if a.priority == AlertSeverity.CRITICAL:
                entry["critical"] += 1
            if a.state == AlertState.SUPPRESSED:
                entry["suppressed"] += 1
            if a.created_at_utc > entry["latest_time"]:
                entry["latest_time"] = a.created_at_utc

    # Rate calculation
    window_hours = max(window_seconds / 3600.0, 0.001)
    rate_per_hour = round(total / window_hours, 2)

    # Priority mix percentages
    if total > 0:
        crit_pct = round((critical_count / total) * 100.0, 1)
        warn_pct = round((warning_count / total) * 100.0, 1)
        info_pct = round((info_count / total) * 100.0, 1)
    else:
        crit_pct = 0.0
        warn_pct = 0.0
        info_pct = 0.0

    priority_mix = {
        "critical": crit_pct,
        "warning": warn_pct,
        "info": info_pct,
    }

    # Identify chattering incidents (exceeding chatter_threshold)
    chattering: List[ChatteringIncident] = []
    for iid, data in inc_chatter.items():
        if data["count"] >= chatter_threshold:
            chattering.append(
                ChatteringIncident(
                    incident_id=iid,
                    alert_count=data["count"],
                    critical_count=data["critical"],
                    suppressed_count=data["suppressed"],
                    last_alert_time_utc=data["latest_time"],
                )
            )

    # Sort chattering incidents: highest alert count first
    chattering.sort(key=lambda c: (-c.alert_count, -c.critical_count, c.incident_id))

    return AlertHealthMetrics(
        window_seconds=window_seconds,
        as_of_utc=now_str,
        total_alerts=total,
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        acknowledged_count=acknowledged_count,
        unresolved_count=unresolved_count,
        resolved_count=resolved_count,
        suppressed_count=suppressed_count,
        alert_rate_per_hour=rate_per_hour,
        priority_mix=priority_mix,
        chattering_incidents=chattering,
    )
