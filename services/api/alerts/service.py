"""Alert management service for ThermalIntel Phase 4 & V2.

Responsible for:
- Operational alert generation, deduplication, prioritization, and acknowledgment
- Lifecycle state transitions (active -> acknowledged -> resolved -> suppressed)
- Persistent SQLite storage as authoritative source of truth surviving restarts
- Cooldown and flood protection against noisy, chattering incidents
- Serving filtered and sorted alerts compliant with frozen API contracts
- Computing operational alert health metrics
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Callable, Dict, Any
import sqlite3

from services.api.schemas.alert import Alert, AlertsResponse
from services.api.schemas.common import AlertSeverity as V1AlertSeverity, RiskLevel
from services.api.schemas.hotspot import Hotspot
from services.api.incidents.models import AggregatedIncident
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.deduplication import AlertDeduplicator
from services.api.alerts.priority import AlertPriorityComparator
from services.api.alerts.cooldown import FloodProtectionEngine, FloodProtectionConfig
from services.api.alerts.repository import AlertV2Repository
from services.api.alerts.health import AlertHealthMetrics, compute_health_from_alerts
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import (
    AlertSeverity as V2AlertSeverity,
    AlertState,
    IncidentEventType,
    now_utc_iso,
)
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.incident import Incident


class AlertService:
    """Core service managing the operational lifecycle, persistence, and querying of alerts."""

    def __init__(
        self,
        connection_factory: Optional[Callable[[], sqlite3.Connection]] = None,
        generator: Optional[AlertGenerator] = None,
        flood_engine: Optional[FloodProtectionEngine] = None,
        repository: Optional[AlertV2Repository] = None,
    ):
        """Initialize AlertService.
        
        Args:
            connection_factory: Optional callable providing an SQLite connection.
            generator: Optional custom AlertGenerator instance.
            flood_engine: Optional FloodProtectionEngine for cooldown enforcement.
            repository: Optional custom AlertV2Repository.
        """
        self.connection_factory = connection_factory
        self.generator = generator or AlertGenerator()
        self.deduplicator = AlertDeduplicator()
        self.flood_engine = flood_engine or FloodProtectionEngine()

        if repository:
            self.repository = repository
        elif connection_factory:
            self.repository = AlertV2Repository(connection_factory)
        else:
            self.repository = None

        # Fallback memory store when connection_factory is None
        self._in_memory_alerts: Dict[str, Alert] = {}
        self._in_memory_v2_alerts: Dict[str, AlertV2] = {}

    # =========================================================================
    # V2 Transition-Driven Operations
    # =========================================================================

    def process_incident_transition(
        self,
        incident: Incident,
        event: IncidentEvent,
        previous_incident: Optional[Incident] = None,
        extra_evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[AlertV2]:
        """Process an incident lifecycle transition to generate, dedupe, and persist an AlertV2.
        
        Evaluates rules, deduplicates signatures, checks flood/cooldown limits,
        and persists state changes into SQLite.
        """
        # 1. If incident is CLOSED, automatically resolve active alerts on this incident
        if event.event_type == IncidentEventType.CLOSED:
            self._resolve_incident_active_alerts(incident.incident_id, reason=event.reason)

        # 2. Generate candidate alert via rules engine
        candidate = self.generator.generate_from_transition(
            incident=incident,
            event=event,
            previous_incident=previous_incident,
            extra_evidence=extra_evidence,
        )

        if not candidate:
            return None

        # 3. Deterministic deduplication check
        existing_alert = self.get_alert_v2_by_dedupe_key(candidate.dedupe_key)
        if existing_alert:
            # Duplicate event: suppress generating a new active alert
            return None

        # 4. Cooldown and flood protection check
        recent_alerts = self._get_recent_alerts_for_incident(incident.incident_id)
        decision = self.flood_engine.evaluate(candidate, recent_alerts)

        if not decision.allowed:
            # Mark candidate as suppressed to preserve audit trail without alerting operators
            suppressed_alert = candidate.model_copy(
                update={
                    "state": AlertState.SUPPRESSED,
                    "dedupe_key": f"{candidate.dedupe_key}:SUPPRESSED:{candidate.created_at_utc}",
                    "evidence": {
                        **candidate.evidence,
                        "suppression_reason": decision.reason,
                        "suppression_type": decision.suppression_type,
                    },
                }
            )
            self._save_v2_alert(suppressed_alert)
            return suppressed_alert

        # 5. Persist and return active alert
        self._save_v2_alert(candidate)
        return candidate

    def process_event(
        self,
        event: IncidentEvent,
        incident_provider: Optional[Callable[[str], Optional[Incident]]] = None,
    ) -> Optional[AlertV2]:
        """Convenience method to process an IncidentEvent when Incident must be loaded."""
        incident = None
        if incident_provider:
            incident = incident_provider(event.incident_id)
        elif self.connection_factory:
            incident = self._load_incident_from_db(event.incident_id)

        if not incident:
            return None

        return self.process_incident_transition(incident, event)

    def acknowledge_alert_v2(self, alert_id: str, actor: str = "operator") -> bool:
        """Mark an AlertV2 as acknowledged persistently in SQLite."""
        now_ts = now_utc_iso()
        updated = False

        if self.repository:
            updated = self.repository.update_state(alert_id, AlertState.ACKNOWLEDGED, now_ts)

        if alert_id in self._in_memory_v2_alerts:
            self._in_memory_v2_alerts[alert_id] = self._in_memory_v2_alerts[alert_id].model_copy(
                update={"state": AlertState.ACKNOWLEDGED, "acknowledged_at_utc": now_ts}
            )
            updated = True

        # Synchronize with legacy representation if present
        self.acknowledge_alert(alert_id)
        return updated

    def resolve_alert(self, alert_id: str, reason: str = "Condition resolved", actor: str = "operator") -> bool:
        """Mark an alert as resolved persistently in SQLite."""
        now_ts = now_utc_iso()
        updated = False

        if self.repository:
            updated = self.repository.update_state(alert_id, AlertState.RESOLVED, now_ts)

        if alert_id in self._in_memory_v2_alerts:
            self._in_memory_v2_alerts[alert_id] = self._in_memory_v2_alerts[alert_id].model_copy(
                update={"state": AlertState.RESOLVED, "resolved_at_utc": now_ts}
            )
            updated = True

        return updated

    def suppress_alert(self, alert_id: str, reason: str = "Manual suppression", actor: str = "operator") -> bool:
        """Mark an alert as suppressed persistently in SQLite."""
        updated = False

        if self.repository:
            updated = self.repository.update_state(alert_id, AlertState.SUPPRESSED)

        if alert_id in self._in_memory_v2_alerts:
            self._in_memory_v2_alerts[alert_id] = self._in_memory_v2_alerts[alert_id].model_copy(
                update={"state": AlertState.SUPPRESSED}
            )
            updated = True

        return updated

    def get_alert_v2_by_id(self, alert_id: str) -> Optional[AlertV2]:
        """Fetch AlertV2 by alert_id from SQLite or memory."""
        if self.repository:
            db_alert = self.repository.get_by_id(alert_id)
            if db_alert:
                return db_alert
        return self._in_memory_v2_alerts.get(alert_id)

    def get_alert_v2_by_dedupe_key(self, dedupe_key: str) -> Optional[AlertV2]:
        """Fetch AlertV2 by dedupe_key from SQLite or memory."""
        if self.repository:
            db_alert = self.repository.get_by_dedupe_key(dedupe_key)
            if db_alert:
                return db_alert
        for a in self._in_memory_v2_alerts.values():
            if a.dedupe_key == dedupe_key:
                return a
        return None

    def get_alerts_v2(
        self,
        incident_id: Optional[str] = None,
        priority: Optional[V2AlertSeverity] = None,
        state: Optional[AlertState] = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> List[AlertV2]:
        """Retrieve canonical AlertV2 list adhering to filtering and priority sorting."""
        alerts: List[AlertV2] = []
        if self.repository:
            alerts = self.repository.list_alerts(
                incident_id=incident_id,
                priority=priority,
                state=state,
                unread_only=unread_only,
                limit=limit,
            )
        else:
            alerts = list(self._in_memory_v2_alerts.values())
            if incident_id:
                alerts = [a for a in alerts if a.incident_id == incident_id]
            if priority:
                alerts = [a for a in alerts if a.priority == priority]
            if state:
                alerts = [a for a in alerts if a.state == state]
            if unread_only:
                alerts = [a for a in alerts if a.state == AlertState.ACTIVE]

        return AlertPriorityComparator.sort_v2(alerts)[:limit]

    def get_alert_health(
        self,
        window_seconds: int = 86400,
        as_of_utc: Optional[str] = None,
        chatter_threshold: int = 3,
    ) -> AlertHealthMetrics:
        """Compute operational alert health telemetry metrics across a time window."""
        alerts: List[AlertV2] = []
        if self.repository:
            alerts = self.repository.list_alerts(limit=5000)
        else:
            alerts = list(self._in_memory_v2_alerts.values())

        return compute_health_from_alerts(
            alerts=alerts,
            window_seconds=window_seconds,
            as_of_utc=as_of_utc,
            chatter_threshold=chatter_threshold,
        )

    # =========================================================================
    # V1 Backward Compatible Operations & Bridging
    # =========================================================================

    def add_alert(self, alert: Alert) -> None:
        """Add or update an in-memory alert."""
        self._in_memory_alerts[alert.id] = alert
        if self.connection_factory:
            try:
                with self.connection_factory() as conn:
                    cursor = conn.cursor()
                    tags_json = json.dumps(alert.tags) if alert.tags else "[]"
                    cursor.execute("""
                        INSERT OR REPLACE INTO alerts (
                            id, hotspot_id, severity, title, message, risk_score,
                            location_name, latitude, longitude, timestamp,
                            is_acknowledged, recommended_action, tags_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        alert.id, alert.hotspot_id, alert.severity.value,
                        alert.title, alert.message, alert.risk_score,
                        alert.location_name, alert.latitude, alert.longitude,
                        alert.timestamp, 1 if alert.is_acknowledged else 0,
                        alert.recommended_action, tags_json,
                    ))
                    conn.commit()
            except Exception:
                pass

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged in memory and in SQLite database.
        
        Survives restarts by committing directly to the database.
        """
        updated = False

        # Update in-memory representations
        if alert_id in self._in_memory_alerts:
            self._in_memory_alerts[alert_id] = self._in_memory_alerts[alert_id].model_copy(
                update={"is_acknowledged": True}
            )
            updated = True

        if alert_id in self._in_memory_v2_alerts:
            self._in_memory_v2_alerts[alert_id] = self._in_memory_v2_alerts[alert_id].model_copy(
                update={"state": AlertState.ACKNOWLEDGED, "acknowledged_at_utc": now_utc_iso()}
            )
            updated = True

        # Update persistent database if connected
        if self.connection_factory:
            try:
                with self.connection_factory() as conn:
                    cursor = conn.cursor()
                    # 1. Update legacy alerts table
                    cursor.execute(
                        "UPDATE alerts SET is_acknowledged = 1 WHERE id = ?", (alert_id,)
                    )
                    if cursor.rowcount > 0:
                        updated = True

                    # 2. Update canonical alerts_v2 table
                    cursor.execute(
                        "UPDATE alerts_v2 SET state = ?, acknowledged_at_utc = ? WHERE alert_id = ?",
                        (AlertState.ACKNOWLEDGED.value, now_utc_iso(), alert_id),
                    )
                    if cursor.rowcount > 0:
                        updated = True

                    conn.commit()
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
        severity: Optional[V1AlertSeverity] = None,
        unread_only: bool = False,
    ) -> AlertsResponse:
        """Retrieve operational alerts adhering to filtering, deduplication, and priority sorting.
        
        Reads directly from the authoritative database, projecting V2 alerts to V1 contract
        and bridging with legacy table records.
        """
        alerts: List[Alert] = []

        if self.connection_factory:
            try:
                with self.connection_factory() as conn:
                    cursor = conn.cursor()
                    # 1. Check alerts_v2
                    cursor.execute("SELECT * FROM alerts_v2 WHERE state != 'suppressed'")
                    v2_rows = cursor.fetchall()
                    for r in v2_rows:
                        v2_alert = self.repository._row_to_alert(r) if self.repository else None
                        if v2_alert:
                            alerts.append(self._project_v2_to_v1(v2_alert))

                    # 2. Check legacy alerts table
                    cursor.execute("SELECT * FROM alerts")
                    rows = cursor.fetchall()
                    for r in rows:
                        tags = json.loads(r["tags_json"]) if r["tags_json"] else []
                        alerts.append(
                            Alert(
                                id=r["id"],
                                hotspot_id=r["hotspot_id"],
                                severity=V1AlertSeverity(r["severity"]),
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
            # Also include projected in-memory V2 alerts
            for v2_a in self._in_memory_v2_alerts.values():
                if v2_a.state != AlertState.SUPPRESSED:
                    alerts.append(self._project_v2_to_v1(v2_a))

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
            generated_at=now_utc_iso(),
        )

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _save_v2_alert(self, alert: AlertV2) -> None:
        """Persist AlertV2 to SQLite or in-memory dictionary."""
        self._in_memory_v2_alerts[alert.alert_id] = alert
        if self.repository:
            self.repository.save_or_update(alert)

    def _get_recent_alerts_for_incident(self, incident_id: str) -> List[AlertV2]:
        """Fetch recent alerts for an incident."""
        if self.repository:
            return self.repository.get_recent_alerts_for_incident(incident_id)
        return [
            a for a in self._in_memory_v2_alerts.values()
            if a.incident_id == incident_id
        ]

    def _resolve_incident_active_alerts(self, incident_id: str, reason: str = "Incident closed") -> None:
        """Mark active alerts on an incident as resolved."""
        if self.repository:
            try:
                with self.connection_factory() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE alerts_v2
                        SET state = ?, resolved_at_utc = ?
                        WHERE incident_id = ? AND state = 'active'
                        """,
                        (AlertState.RESOLVED.value, now_utc_iso(), incident_id),
                    )
                    conn.commit()
            except Exception:
                pass

        for a in self._in_memory_v2_alerts.values():
            if a.incident_id == incident_id and a.state == AlertState.ACTIVE:
                self._in_memory_v2_alerts[a.alert_id] = a.model_copy(
                    update={"state": AlertState.RESOLVED, "resolved_at_utc": now_utc_iso()}
                )

    def _project_v2_to_v1(self, alert: AlertV2) -> Alert:
        """Project a canonical AlertV2 instance to the backward-compatible V1 Alert model."""
        risk = float(alert.evidence.get("current_risk_score", alert.evidence.get("risk_score", 50.0)))
        loc = str(alert.evidence.get("nearest_place", alert.evidence.get("location_name", "Unknown Locality")))
        lat = float(alert.evidence.get("centroid", {}).get("latitude", alert.evidence.get("latitude", 0.0)))
        lon = float(alert.evidence.get("centroid", {}).get("longitude", alert.evidence.get("longitude", 0.0)))

        return Alert(
            id=alert.alert_id,
            hotspot_id=alert.incident_id or alert.observation_id or alert.alert_id,
            severity=V1AlertSeverity(alert.priority.value),
            title=alert.title,
            message=alert.message,
            risk_score=round(risk, 1),
            location_name=loc,
            latitude=lat,
            longitude=lon,
            timestamp=alert.created_at_utc,
            is_acknowledged=(alert.state in (AlertState.ACKNOWLEDGED, AlertState.RESOLVED)),
            recommended_action=alert.metadata.get("recommended_action", "Monitor incident."),
            tags=alert.metadata.get("tags", []),
        )

    def _load_incident_from_db(self, incident_id: str) -> Optional[Incident]:
        """Fetch Incident from database by incident_id."""
        if not self.connection_factory:
            return None
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
                r = cursor.fetchone()
                if r:
                    return Incident(
                        incident_id=r["incident_id"],
                        status=r["status"],
                        first_seen_utc=r["first_seen_utc"],
                        last_seen_utc=r["last_seen_utc"],
                        centroid_latitude=r["centroid_latitude"],
                        centroid_longitude=r["centroid_longitude"],
                        nearest_place=r["nearest_place"],
                        peak_frp=r["peak_frp"],
                        average_frp=r["average_frp"],
                        observation_count=r["observation_count"],
                        current_risk_score=r["current_risk_score"],
                        current_severity=r["current_severity"],
                        current_classification=r["current_classification"],
                        created_at_utc=r["created_at_utc"],
                        updated_at_utc=r["updated_at_utc"],
                    )
        except Exception:
            pass
        return None
