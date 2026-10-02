"""Persistence repository for canonical V2 incidents, observations, and events.

Encapsulates all database interactions for the incident engine against canonical
V2 SQLite tables:
- incidents
- incident_observations
- incident_events
- observations
- assessments
- enrichment_snapshots
"""

import json
import sqlite3
from typing import Optional, List, Dict, Any, Union, Callable
from pathlib import Path

from services.api.schemas.v2 import (
    Incident,
    IncidentObservation,
    IncidentEvent,
    IncidentStatus,
    IncidentEventType,
    Observation,
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
    RiskFactor,
    RiskLevel,
    SourceType,
    now_utc_iso,
)


class IncidentRepository:
    """SQLite-backed persistence repository for V2 incidents."""

    def __init__(self, connection_factory: Optional[Callable[[], sqlite3.Connection]] = None, db_path: Optional[Union[str, Path]] = None):
        """Initialize repository with either a connection factory or db_path."""
        if connection_factory:
            self._connection_factory = connection_factory
        elif db_path:
            self._db_path = str(db_path)
            self._connection_factory = self._default_connection_factory
        else:
            from services.api.database import get_connection
            self._connection_factory = get_connection

    def _default_connection_factory(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def get_connection(self) -> sqlite3.Connection:
        conn = self._connection_factory()
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # --- Incidents ---

    def save_incident(self, incident: Incident) -> None:
        """Upsert a canonical Incident record."""
        geo_str = json.dumps(incident.geometry_geojson) if incident.geometry_geojson else None
        status_val = incident.status.value if isinstance(incident.status, IncidentStatus) else str(incident.status)
        sev_val = incident.current_severity.value if isinstance(incident.current_severity, RiskLevel) else str(incident.current_severity)
        class_val = incident.current_classification.value if isinstance(incident.current_classification, SourceType) else str(incident.current_classification)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO incidents (
                    incident_id, status, first_seen_utc, last_seen_utc,
                    centroid_latitude, centroid_longitude, geometry_geojson, nearest_place,
                    peak_frp, average_frp, observation_count, current_risk_score,
                    current_severity, current_classification, current_assessment_id,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    status=excluded.status,
                    first_seen_utc=excluded.first_seen_utc,
                    last_seen_utc=excluded.last_seen_utc,
                    centroid_latitude=excluded.centroid_latitude,
                    centroid_longitude=excluded.centroid_longitude,
                    geometry_geojson=excluded.geometry_geojson,
                    nearest_place=excluded.nearest_place,
                    peak_frp=excluded.peak_frp,
                    average_frp=excluded.average_frp,
                    observation_count=excluded.observation_count,
                    current_risk_score=excluded.current_risk_score,
                    current_severity=excluded.current_severity,
                    current_classification=excluded.current_classification,
                    current_assessment_id=excluded.current_assessment_id,
                    updated_at_utc=excluded.updated_at_utc
            """, (
                incident.incident_id, status_val, incident.first_seen_utc, incident.last_seen_utc,
                incident.centroid_latitude, incident.centroid_longitude, geo_str, incident.nearest_place,
                incident.peak_frp, incident.average_frp, incident.observation_count, incident.current_risk_score,
                sev_val, class_val, incident.current_assessment_id,
                incident.created_at_utc, incident.updated_at_utc
            ))
            conn.commit()

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Fetch a single Incident by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def list_incidents(
        self,
        status: Optional[List[Union[IncidentStatus, str]]] = None,
        min_risk: Optional[float] = None,
    ) -> List[Incident]:
        """List incidents with optional status and risk filtering."""
        query = "SELECT * FROM incidents WHERE 1=1"
        params: List[Any] = []

        if status:
            status_vals = [s.value if isinstance(s, IncidentStatus) else str(s) for s in status]
            placeholders = ",".join("?" for _ in status_vals)
            query += f" AND status IN ({placeholders})"
            params.extend(status_vals)

        if min_risk is not None:
            query += " AND current_risk_score >= ?"
            params.append(min_risk)

        query += " ORDER BY current_risk_score DESC, peak_frp DESC, incident_id ASC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_incident(r) for r in rows]

    # --- Incident Observations ---

    def add_incident_observation(self, assoc: IncidentObservation) -> bool:
        """Associate an observation with an incident idempotently.
        
        Returns True if a new link was established, False if already associated.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO incident_observations (
                    incident_id, observation_id, joined_at_utc,
                    association_method, association_reason
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                assoc.incident_id, assoc.observation_id, assoc.joined_at_utc,
                assoc.association_method, assoc.association_reason
            ))
            conn.commit()
            return cursor.rowcount > 0

    def list_incident_observations(self, incident_id: str) -> List[Observation]:
        """Retrieve all observations associated with an incident, ordered by acquisition time."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT o.* FROM observations o
                JOIN incident_observations io ON o.observation_id = io.observation_id
                WHERE io.incident_id = ?
                ORDER BY o.acquisition_time_utc ASC, o.observation_id ASC
            """, (incident_id,))
            rows = cursor.fetchall()
            return [self._row_to_observation(r) for r in rows]

    def list_incident_observation_ids(self, incident_id: str) -> List[str]:
        """Retrieve IDs of all observations linked to an incident."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT observation_id FROM incident_observations
                WHERE incident_id = ?
                ORDER BY observation_id ASC
            """, (incident_id,))
            return [r["observation_id"] for r in cursor.fetchall()]

    def find_incidents_for_observation(self, observation_id: str) -> List[str]:
        """Find all incident IDs associated with an observation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT incident_id FROM incident_observations
                WHERE observation_id = ?
                ORDER BY incident_id ASC
            """, (observation_id,))
            return [r["incident_id"] for r in cursor.fetchall()]

    def delete_incident_observation(self, incident_id: str, observation_id: str) -> bool:
        """Remove an association link (e.g. during split repartitioning)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM incident_observations
                WHERE incident_id = ? AND observation_id = ?
            """, (incident_id, observation_id))
            conn.commit()
            return cursor.rowcount > 0

    # --- Incident Events ---

    def save_incident_event(self, event: IncidentEvent) -> bool:
        """Append an immutable lifecycle timeline event.
        
        Returns True if inserted, False if event_id already exists.
        """
        meta_str = json.dumps(event.metadata) if event.metadata else "{}"
        evt_type = event.event_type.value if isinstance(event.event_type, IncidentEventType) else str(event.event_type)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO incident_events (
                    event_id, incident_id, event_type, timestamp_utc,
                    actor, reason, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id, event.incident_id, evt_type,
                event.timestamp_utc, event.actor, event.reason, meta_str
            ))
            conn.commit()
            return cursor.rowcount > 0

    def list_incident_events(self, incident_id: str) -> List[IncidentEvent]:
        """Retrieve chronological audit timeline for an incident."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM incident_events
                WHERE incident_id = ?
                ORDER BY timestamp_utc ASC, rowid ASC
            """, (incident_id,))
            rows = cursor.fetchall()
            return [self._row_to_event(r) for r in rows]

    def has_observation_event(self, incident_id: str, observation_id: str) -> bool:
        """Check if an observation_added event already exists for an observation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM incident_events
                WHERE incident_id = ? AND event_type = 'observation_added'
                AND metadata_json LIKE ?
                LIMIT 1
            """, (incident_id, f'%"{observation_id}"%'))
            return cursor.fetchone() is not None

    # --- Observations ---

    def save_observation(self, obs: Observation) -> None:
        """Upsert a canonical observation record."""
        source_attrs_str = json.dumps(obs.source_attributes) if obs.source_attributes else "{}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO observations (
                    observation_id, provider, product, satellite, instrument,
                    latitude, longitude, acquisition_time_utc, ingestion_time_utc,
                    brightness, bright_t31, frp, scan, track, daynight,
                    detection_confidence, source_attributes_json, raw_payload_id, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    ingestion_time_utc=excluded.ingestion_time_utc,
                    source_attributes_json=excluded.source_attributes_json
            """, (
                obs.observation_id, obs.provider, obs.product, obs.satellite, obs.instrument,
                obs.latitude, obs.longitude, obs.acquisition_time_utc, obs.ingestion_time_utc,
                obs.brightness, obs.bright_t31, obs.frp, obs.scan, obs.track, obs.daynight,
                obs.detection_confidence, source_attrs_str, obs.raw_payload_id, obs.schema_version
            ))
            conn.commit()

    def get_observation(self, observation_id: str) -> Optional[Observation]:
        """Fetch a single Observation by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM observations WHERE observation_id = ?", (observation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_observation(row)

    # --- Assessments & Enrichment ---

    def get_assessment(self, target_id: str) -> Optional[Assessment]:
        """Retrieve active assessment for an incident or observation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM assessments
                WHERE target_id = ?
                ORDER BY created_at_utc DESC LIMIT 1
            """, (target_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_assessment(row)

    def get_enrichment_snapshots(self, target_id: str) -> Dict[str, Any]:
        """Retrieve contextual enrichment snapshots for a target."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM enrichment_snapshots
                WHERE target_id = ?
                ORDER BY fetched_at_utc DESC
            """, (target_id,))
            rows = cursor.fetchall()
            result: Dict[str, Any] = {}
            for r in rows:
                c_type = r["context_type"]
                if c_type not in result:
                    result[c_type] = json.loads(r["payload_json"])
            return result

    # --- Private Row Mappers ---

    @staticmethod
    def _row_to_incident(r: sqlite3.Row) -> Incident:
        geo = json.loads(r["geometry_geojson"]) if r["geometry_geojson"] else None
        return Incident(
            incident_id=r["incident_id"],
            status=IncidentStatus(r["status"]),
            first_seen_utc=r["first_seen_utc"],
            last_seen_utc=r["last_seen_utc"],
            centroid_latitude=float(r["centroid_latitude"]),
            centroid_longitude=float(r["centroid_longitude"]),
            geometry_geojson=geo,
            nearest_place=r["nearest_place"],
            peak_frp=float(r["peak_frp"]),
            average_frp=float(r["average_frp"]),
            observation_count=int(r["observation_count"]),
            current_risk_score=float(r["current_risk_score"]),
            current_severity=RiskLevel(r["current_severity"]),
            current_classification=SourceType(r["current_classification"]),
            current_assessment_id=r["current_assessment_id"],
            created_at_utc=r["created_at_utc"],
            updated_at_utc=r["updated_at_utc"],
        )

    @staticmethod
    def _row_to_observation(r: sqlite3.Row) -> Observation:
        attrs = json.loads(r["source_attributes_json"]) if r["source_attributes_json"] else {}
        return Observation(
            observation_id=r["observation_id"],
            provider=r["provider"],
            product=r["product"],
            satellite=r["satellite"],
            instrument=r["instrument"],
            latitude=float(r["latitude"]),
            longitude=float(r["longitude"]),
            acquisition_time_utc=r["acquisition_time_utc"],
            ingestion_time_utc=r["ingestion_time_utc"],
            brightness=float(r["brightness"]),
            bright_t31=float(r["bright_t31"]) if r["bright_t31"] is not None else None,
            frp=float(r["frp"]),
            scan=float(r["scan"]) if r["scan"] is not None else None,
            track=float(r["track"]) if r["track"] is not None else None,
            daynight=r["daynight"],
            detection_confidence=r["detection_confidence"],
            source_attributes=attrs,
            raw_payload_id=r["raw_payload_id"],
            schema_version=r["schema_version"] or "2.0",
        )

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> IncidentEvent:
        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        return IncidentEvent(
            event_id=r["event_id"],
            incident_id=r["incident_id"],
            event_type=IncidentEventType(r["event_type"]),
            timestamp_utc=r["timestamp_utc"],
            actor=r["actor"],
            reason=r["reason"],
            metadata=meta,
        )

    @staticmethod
    def _row_to_assessment(r: sqlite3.Row) -> Assessment:
        probs = json.loads(r["class_probabilities_json"]) if r["class_probabilities_json"] else {}
        raw_factors = json.loads(r["risk_factors_json"]) if r["risk_factors_json"] else []
        factors = [
            RiskFactor(
                factor=f["factor"],
                weight=f["weight"],
                impact=RiskLevel(f["impact"]),
                description=f["description"],
            )
            for f in raw_factors
        ]

        return Assessment(
            assessment_id=r["assessment_id"],
            target_id=r["target_id"],
            target_type=r["target_type"],
            classification=ClassificationAssessment(
                predicted_source=SourceType(r["predicted_source"]),
                classification_confidence=float(r["classification_confidence"]),
                probabilities=probs,
            ),
            anomaly=AnomalyAssessment(
                is_anomaly=bool(r["is_anomaly"]),
                anomaly_score=float(r["anomaly_score"]),
                baseline_deviation_sigma=0.0,
                anomaly_rationale=r["anomaly_rationale"] or "Evaluated",
            ),
            risk=RiskAssessmentResult(
                risk_score=float(r["risk_score"]),
                severity=RiskLevel(r["severity"]),
                frp_component=0.0,
                weather_component=0.0,
                proximity_component=0.0,
                historical_component=0.0,
                factors=factors,
                recommended_action="Evaluated action",
            ),
            data_quality=DataQualityAssessment(
                completeness_score=float(r["completeness_score"]),
                uncertainty_score=float(r["uncertainty_score"]),
            ),
            methodology=AssessmentMethodology(
                method=r["method"],
                algorithm_version=r["algorithm_version"],
                input_hash=r["input_hash"],
                as_of_utc=r["as_of_utc"],
            ),
            created_at_utc=r["created_at_utc"],
        )


class InMemoryIncidentRepository:
    """In-memory mock repository for fully isolated unit testing."""

    def __init__(self):
        self.incidents: Dict[str, Incident] = {}
        self.observations: Dict[str, Observation] = {}
        self.incident_observations: Dict[str, Set[str]] = {}  # incident_id -> set of observation_ids
        self.events: Dict[str, List[IncidentEvent]] = {}  # incident_id -> list of events
        self.assessments: Dict[str, Assessment] = {}  # target_id -> Assessment
        self.enrichments: Dict[str, Dict[str, Any]] = {}

    def save_incident(self, incident: Incident) -> None:
        self.incidents[incident.incident_id] = incident.model_copy()

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        inc = self.incidents.get(incident_id)
        return inc.model_copy() if inc else None

    def list_incidents(
        self,
        status: Optional[List[Union[IncidentStatus, str]]] = None,
        min_risk: Optional[float] = None,
    ) -> List[Incident]:
        results = list(self.incidents.values())
        if status:
            status_vals = {s.value if isinstance(s, IncidentStatus) else str(s) for s in status}
            results = [inc for inc in results if inc.status.value in status_vals]
        if min_risk is not None:
            results = [inc for inc in results if inc.current_risk_score >= min_risk]
        results.sort(key=lambda inc: (-inc.current_risk_score, -inc.peak_frp, inc.incident_id))
        return [inc.model_copy() for inc in results]

    def add_incident_observation(self, assoc: IncidentObservation) -> bool:
        s = self.incident_observations.setdefault(assoc.incident_id, set())
        if assoc.observation_id in s:
            return False
        s.add(assoc.observation_id)
        return True

    def list_incident_observations(self, incident_id: str) -> List[Observation]:
        obs_ids = self.incident_observations.get(incident_id, set())
        matched = [self.observations[oid] for oid in obs_ids if oid in self.observations]
        matched.sort(key=lambda o: (o.acquisition_time_utc, o.observation_id))
        return [o.model_copy() for o in matched]

    def list_incident_observation_ids(self, incident_id: str) -> List[str]:
        return sorted(list(self.incident_observations.get(incident_id, set())))

    def find_incidents_for_observation(self, observation_id: str) -> List[str]:
        matched = []
        for inc_id, obs_set in self.incident_observations.items():
            if observation_id in obs_set:
                matched.append(inc_id)
        return sorted(matched)

    def delete_incident_observation(self, incident_id: str, observation_id: str) -> bool:
        s = self.incident_observations.get(incident_id)
        if s and observation_id in s:
            s.remove(observation_id)
            return True
        return False

    def save_incident_event(self, event: IncidentEvent) -> bool:
        evt_list = self.events.setdefault(event.incident_id, [])
        if any(e.event_id == event.event_id for e in evt_list):
            return False
        evt_list.append(event.model_copy())
        return True

    def list_incident_events(self, incident_id: str) -> List[IncidentEvent]:
        events = self.events.get(incident_id, [])
        # Python Timsort is stable: preserves append-only insertion order for events with identical timestamp_utc
        return [e.model_copy() for e in sorted(events, key=lambda e: e.timestamp_utc)]

    def has_observation_event(self, incident_id: str, observation_id: str) -> bool:
        evt_list = self.events.get(incident_id, [])
        for e in evt_list:
            if e.event_type == IncidentEventType.OBSERVATION_ADDED and e.metadata.get("observation_id") == observation_id:
                return True
        return False

    def save_observation(self, obs: Observation) -> None:
        self.observations[obs.observation_id] = obs.model_copy()

    def get_observation(self, observation_id: str) -> Optional[Observation]:
        obs = self.observations.get(observation_id)
        return obs.model_copy() if obs else None

    def get_assessment(self, target_id: str) -> Optional[Assessment]:
        a = self.assessments.get(target_id)
        return a.model_copy() if a else None

    def get_enrichment_snapshots(self, target_id: str) -> Dict[str, Any]:
        return self.enrichments.get(target_id, {})
