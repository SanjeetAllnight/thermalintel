"""SQLite persistence repository for ThermalIntel V2 alerts.

Directly manages the canonical 'alerts_v2' table with robust transactional integrity,
indexing, state tracking (active -> acknowledged -> resolved -> suppressed),
and cross-table bridge synchronization with legacy 'alerts' where present.
"""

import json
import sqlite3
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime, timezone

from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import AlertSeverity, AlertState, now_utc_iso


class AlertV2Repository:
    """Provides strongly typed CRUD and query capabilities for AlertV2 against SQLite."""

    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]):
        self.connection_factory = connection_factory

    def insert(self, alert: AlertV2) -> bool:
        """Insert a new AlertV2 into alerts_v2.
        
        Returns:
            True if inserted successfully, False if duplicate dedupe_key or alert_id.
        """
        evidence_str = json.dumps(alert.evidence) if alert.evidence else "{}"
        metadata_str = json.dumps(alert.metadata) if alert.metadata else "{}"

        query = """
            INSERT INTO alerts_v2 (
                alert_id, incident_id, observation_id, rule_id, dedupe_key,
                priority, state, title, message, evidence_json, metadata_json,
                created_at_utc, acknowledged_at_utc, resolved_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    query,
                    (
                        alert.alert_id,
                        alert.incident_id,
                        alert.observation_id,
                        alert.rule_id,
                        alert.dedupe_key,
                        alert.priority.value,
                        alert.state.value,
                        alert.title,
                        alert.message,
                        evidence_str,
                        metadata_str,
                        alert.created_at_utc,
                        alert.acknowledged_at_utc,
                        alert.resolved_at_utc,
                    ),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # Duplicate dedupe_key or primary key
            return False
        except Exception:
            return False

    def save_or_update(self, alert: AlertV2) -> bool:
        """Insert or replace AlertV2, preserving acknowledgement if already acknowledged."""
        existing = self.get_by_dedupe_key(alert.dedupe_key) or self.get_by_id(alert.alert_id)
        if existing and existing.state == AlertState.ACKNOWLEDGED and alert.state != AlertState.ACKNOWLEDGED:
            # Preserve acknowledgement
            alert = alert.model_copy(
                update={
                    "state": AlertState.ACKNOWLEDGED,
                    "acknowledged_at_utc": existing.acknowledged_at_utc or now_utc_iso(),
                }
            )

        evidence_str = json.dumps(alert.evidence) if alert.evidence else "{}"
        metadata_str = json.dumps(alert.metadata) if alert.metadata else "{}"

        query = """
            INSERT OR REPLACE INTO alerts_v2 (
                alert_id, incident_id, observation_id, rule_id, dedupe_key,
                priority, state, title, message, evidence_json, metadata_json,
                created_at_utc, acknowledged_at_utc, resolved_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    query,
                    (
                        alert.alert_id,
                        alert.incident_id,
                        alert.observation_id,
                        alert.rule_id,
                        alert.dedupe_key,
                        alert.priority.value,
                        alert.state.value,
                        alert.title,
                        alert.message,
                        evidence_str,
                        metadata_str,
                        alert.created_at_utc,
                        alert.acknowledged_at_utc,
                        alert.resolved_at_utc,
                    ),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def get_by_id(self, alert_id: str) -> Optional[AlertV2]:
        """Fetch AlertV2 by alert_id."""
        query = "SELECT * FROM alerts_v2 WHERE alert_id = ?"
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (alert_id,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_alert(row)
        except Exception:
            pass
        return None

    def get_by_dedupe_key(self, dedupe_key: str) -> Optional[AlertV2]:
        """Fetch AlertV2 by dedupe_key."""
        query = "SELECT * FROM alerts_v2 WHERE dedupe_key = ?"
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (dedupe_key,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_alert(row)
        except Exception:
            pass
        return None

    def list_alerts(
        self,
        incident_id: Optional[str] = None,
        priority: Optional[AlertSeverity] = None,
        state: Optional[AlertState] = None,
        unread_only: bool = False,
        limit: int = 200,
    ) -> List[AlertV2]:
        """Query AlertV2 rows with multi-attribute filtering."""
        clauses = []
        params: List[Any] = []

        if incident_id:
            clauses.append("incident_id = ?")
            params.append(incident_id)
        if priority:
            clauses.append("priority = ?")
            params.append(priority.value)
        if state:
            clauses.append("state = ?")
            params.append(state.value)
        if unread_only:
            clauses.append("state = 'active'")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM alerts_v2 {where_sql} ORDER BY created_at_utc DESC LIMIT ?"
        params.append(limit)

        results: List[AlertV2] = []
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                for row in cursor.fetchall():
                    results.append(self._row_to_alert(row))
        except Exception:
            pass
        return results

    def update_state(
        self,
        alert_id: str,
        new_state: AlertState,
        timestamp_utc: Optional[str] = None,
    ) -> bool:
        """Transition alert state persistently in the database."""
        now_ts = timestamp_utc or now_utc_iso()
        updated = False

        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                if new_state == AlertState.ACKNOWLEDGED:
                    cursor.execute(
                        """
                        UPDATE alerts_v2
                        SET state = ?, acknowledged_at_utc = ?
                        WHERE alert_id = ?
                        """,
                        (new_state.value, now_ts, alert_id),
                    )
                elif new_state == AlertState.RESOLVED:
                    cursor.execute(
                        """
                        UPDATE alerts_v2
                        SET state = ?, resolved_at_utc = ?
                        WHERE alert_id = ?
                        """,
                        (new_state.value, now_ts, alert_id),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE alerts_v2
                        SET state = ?
                        WHERE alert_id = ?
                        """,
                        (new_state.value, alert_id),
                    )

                if cursor.rowcount > 0:
                    updated = True

                # Also synchronize with legacy 'alerts' table if present
                try:
                    cursor.execute(
                        "UPDATE alerts SET is_acknowledged = ? WHERE id = ?",
                        (1 if new_state in (AlertState.ACKNOWLEDGED, AlertState.RESOLVED) else 0, alert_id),
                    )
                    if cursor.rowcount > 0:
                        updated = True
                except Exception:
                    pass

                conn.commit()
        except Exception:
            pass

        return updated

    def get_unread_count(self) -> int:
        """Count currently active (unacknowledged, unresolved) alerts in database."""
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as cnt FROM alerts_v2 WHERE state = 'active'")
                row = cursor.fetchone()
                if row and row["cnt"] > 0:
                    return int(row["cnt"])

                # Fallback to legacy alerts table if alerts_v2 has 0 active
                cursor.execute("SELECT COUNT(*) as cnt FROM alerts WHERE is_acknowledged = 0")
                row = cursor.fetchone()
                if row:
                    return int(row["cnt"])
        except Exception:
            pass
        return 0

    def get_recent_alerts_for_incident(
        self, incident_id: str, limit: int = 50
    ) -> List[AlertV2]:
        """Fetch chronological alerts for an incident to evaluate cooldown and chatter."""
        return self.list_alerts(incident_id=incident_id, limit=limit)

    def _row_to_alert(self, r: sqlite3.Row) -> AlertV2:
        """Deserialize an SQLite Row into a validated AlertV2 instance."""
        evidence = json.loads(r["evidence_json"]) if r["evidence_json"] else {}
        metadata = json.loads(r["metadata_json"]) if r["metadata_json"] else {}

        return AlertV2(
            alert_id=r["alert_id"],
            incident_id=r["incident_id"],
            observation_id=r["observation_id"],
            rule_id=r["rule_id"],
            dedupe_key=r["dedupe_key"],
            priority=AlertSeverity(r["priority"]),
            state=AlertState(r["state"]),
            title=r["title"],
            message=r["message"],
            evidence=evidence,
            metadata=metadata,
            created_at_utc=r["created_at_utc"],
            acknowledged_at_utc=r["acknowledged_at_utc"],
            resolved_at_utc=r["resolved_at_utc"],
        )
