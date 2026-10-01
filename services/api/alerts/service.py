"""Alert management service for ThermalIntel Phase 4.

Responsible for:
- Operational alert generation, deduplication, prioritization, and acknowledgment
- Serving filtered and sorted AlertsResponse compliant with frozen API contract
- Connecting to persistence layer or operating purely in-memory
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Callable, Dict, Any
import sqlite3

from services.api.schemas.alert import Alert, AlertsResponse
from services.api.schemas.common import AlertSeverity, RiskLevel
from services.api.schemas.hotspot import Hotspot
from services.api.incidents.models import AggregatedIncident
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.deduplication import AlertDeduplicator
from services.api.alerts.priority import AlertPriorityComparator


class AlertService:
    """Core service for generating, prioritizing, deduplicating, and querying operational alerts."""

    def __init__(
        self,
        connection_factory: Optional[Callable[[], sqlite3.Connection]] = None,
        generator: Optional[AlertGenerator] = None,
    ):
        """Initialize AlertService.
        
        Args:
            connection_factory: Optional callable providing an SQLite connection.
            generator: Optional custom AlertGenerator instance.
        """
        self.connection_factory = connection_factory
        self.generator = generator or AlertGenerator()
        self.deduplicator = AlertDeduplicator()
        self._in_memory_alerts: Dict[str, Alert] = {}

    def add_alert(self, alert: Alert) -> None:
        """Add or update an in-memory alert."""
        self._in_memory_alerts[alert.id] = alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged.
        
        Returns:
            True if alert was found and acknowledged, False otherwise.
        """
        updated = False
        # Update in memory
        if alert_id in self._in_memory_alerts:
            self._in_memory_alerts[alert_id] = self._in_memory_alerts[alert_id].model_copy(
                update={"is_acknowledged": True}
            )
            updated = True

        # Update in database if connected
        if self.connection_factory:
            try:
                with self.connection_factory() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE alerts SET is_acknowledged = 1 WHERE id = ?", (alert_id,)
                    )
                    conn.commit()
                    if cursor.rowcount > 0:
                        updated = True
            except Exception:
                pass

        return updated

    def generate_alerts_from_hotspots(
        self, hotspots: List[Hotspot]
    ) -> List[Alert]:
        """Generate, deduplicate, and prioritize alerts from a list of hotspots."""
        raw_alerts: List[Alert] = []
        for h in hotspots:
            alert = self.generator.generate_from_hotspot(h)
            if alert:
                raw_alerts.append(alert)

        deduped = self.deduplicator.deduplicate(raw_alerts)
        return AlertPriorityComparator.sort(deduped)

    def generate_alerts_from_incidents(
        self, incidents: List[AggregatedIncident]
    ) -> List[Alert]:
        """Generate, deduplicate, and prioritize alerts from aggregated incidents."""
        raw_alerts: List[Alert] = []
        for inc in incidents:
            alert = self.generator.generate_from_incident(inc)
            if alert:
                raw_alerts.append(alert)

        deduped = self.deduplicator.deduplicate(raw_alerts)
        return AlertPriorityComparator.sort(deduped)

    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        unread_only: bool = False,
    ) -> AlertsResponse:
        """Retrieve operational alerts adhering to filtering, deduplication, and priority sorting."""
        alerts: List[Alert] = []

        if self.connection_factory:
            try:
                with self.connection_factory() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM alerts")
                    rows = cursor.fetchall()
                    for r in rows:
                        tags = json.loads(r["tags_json"]) if r["tags_json"] else []
                        alerts.append(
                            Alert(
                                id=r["id"],
                                hotspot_id=r["hotspot_id"],
                                severity=AlertSeverity(r["severity"]),
                                title=r["title"],
                                message=r["message"],
                                risk_score=r["risk_score"],
                                location_name=r["location_name"],
                                latitude=r["latitude"],
                                longitude=r["longitude"],
                                timestamp=r["timestamp"],
                                is_acknowledged=bool(r["is_acknowledged"]),
                                recommended_action=r["recommended_action"],
                                tags=tags,
                            )
                        )
            except Exception:
                alerts = list(self._in_memory_alerts.values())
        else:
            alerts = list(self._in_memory_alerts.values())

        # Deduplicate
        deduped = self.deduplicator.deduplicate(alerts)

        # Apply filtering
        filtered = deduped
        if severity:
            filtered = [a for a in filtered if a.severity == severity]
        if unread_only:
            filtered = [a for a in filtered if not a.is_acknowledged]

        # Prioritize
        sorted_alerts = AlertPriorityComparator.sort(filtered)
        unread_count = sum(1 for a in deduped if not a.is_acknowledged)

        return AlertsResponse(
            items=sorted_alerts,
            total=len(sorted_alerts),
            unread_count=unread_count,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
