"""Persistent Incident Engine for ThermalIntel V2.

Transforms transient satellite detections and clusters into persistent, evolving
real-world physical incidents with:
- Stable incident identity (INC-YYYYMMDD-XXXX)
- Spatiotemporal correlation with existing open incidents
- Append-only lifecycle event timeline
- Quantitative and risk state evolution
- Deterministic merge and split semantics
- Strict idempotency under repeated or shuffled ingestion
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Set, Union

from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.v2 import (
    Incident,
    IncidentObservation,
    IncidentEvent,
    IncidentStatus,
    IncidentEventType,
    Observation,
    Assessment,
    now_utc_iso,
)
from services.api.incidents.models import CorrelationResult
from services.api.incidents.aggregator import (
    IncidentAggregator,
    haversine_distance_km,
    parse_observation_datetime,
)
from services.api.incidents.repository import IncidentRepository, InMemoryIncidentRepository

SEVERITY_RANK: Dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def generate_stable_incident_id(first_seen_iso: str, seed_obs_id: str) -> str:
    """Generate a stable, permanent incident identifier conforming to INC-YYYYMMDD-XXXX.
    
    The ID is minted once at creation and NEVER changes even if centroid, risk, or
    representative observations evolve.
    """
    date_part = first_seen_iso[:10].replace("-", "") if len(first_seen_iso) >= 10 else "20261001"
    # Deterministic 4-character hex suffix from root observation ID
    raw_hash = hashlib.sha256(seed_obs_id.encode("utf-8")).hexdigest()
    suffix = raw_hash[:4].upper()
    return f"INC-{date_part}-{suffix}"


def generate_event_id(incident_id: str, event_type: Union[IncidentEventType, str], seed: str) -> str:
    """Derive a deterministic event ID to guarantee idempotent event append operations."""
    evt_type_val = event_type.value if isinstance(event_type, IncidentEventType) else str(event_type)
    date_part = now_utc_iso()[:10].replace("-", "")
    h = hashlib.sha256(f"{incident_id}:{evt_type_val}:{seed}".encode("utf-8")).hexdigest()[:6].upper()
    return f"EVT-{date_part}-{h}"


class IncidentEngine:
    """Core persistent incident lifecycle and correlation engine."""

    def __init__(
        self,
        repository: Optional[Union[IncidentRepository, InMemoryIncidentRepository]] = None,
        aggregator: Optional[IncidentAggregator] = None,
        spatial_threshold_km: float = 2.0,
        temporal_window_hours: float = 24.0,
        merge_distance_km: float = 3.0,
        reopen_window_hours: float = 72.0,
    ):
        """Initialize engine with repository and correlation parameters."""
        self.repository = repository or IncidentRepository()
        self.aggregator = aggregator or IncidentAggregator(
            distance_threshold_km=spatial_threshold_km,
            time_window_hours=temporal_window_hours,
        )
        self.spatial_threshold_km = spatial_threshold_km
        self.temporal_window_hours = temporal_window_hours
        self.merge_distance_km = merge_distance_km
        self.reopen_window_hours = reopen_window_hours

    # -------------------------------------------------------------------------
    # Correlation & Ingestion Pipeline
    # -------------------------------------------------------------------------

    def correlate_observations(
        self,
        observations: List[Observation],
        as_of_utc: Optional[str] = None,
    ) -> CorrelationResult:
        """Correlate a batch of observations against existing persistent incidents.
        
        Guarantees:
        - Input order independence (deterministic sorting).
        - Idempotent repeated ingestion (no duplicate incidents, associations, or events).
        - Persistent stable incident identity.
        - Append-only event tracking for CREATED, OBSERVATION_ADDED, ESCALATED, DEESCALATED.
        """
        if not observations:
            return CorrelationResult()

        eval_time = as_of_utc or now_utc_iso()

        # 1. Deterministic sorting: sort purely on observation data fields
        sorted_obs = sorted(
            observations,
            key=lambda o: (o.acquisition_time_utc, -o.frp, -o.brightness, o.observation_id),
        )

        # 2. Persist raw observations so relational foreign keys are valid
        for obs in sorted_obs:
            self.repository.save_observation(obs)

        # 3. Load active, monitoring, and reopenable incidents, ordered deterministically
        all_incidents = self.repository.list_incidents(
            status=[IncidentStatus.ACTIVE, IncidentStatus.MONITORING, IncidentStatus.RESOLVED, IncidentStatus.CLOSED]
        )
        active_incidents: List[Incident] = []
        for inc in all_incidents:
            if inc.status in (IncidentStatus.ACTIVE, IncidentStatus.MONITORING):
                active_incidents.append(inc)
            elif inc.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                # Exclude incidents absorbed via merge
                events = self.repository.list_incident_events(inc.incident_id)
                is_absorbed = any(
                    e.event_type == IncidentEventType.MERGED and "surviving_incident_id" in e.metadata
                    for e in events
                )
                if not is_absorbed:
                    active_incidents.append(inc)

        active_incidents.sort(key=lambda inc: (inc.first_seen_utc, inc.incident_id))

        # 4. Filter out observations already associated with an incident
        unassociated_obs: List[Observation] = []
        for obs in sorted_obs:
            existing_incs = self.repository.find_incidents_for_observation(obs.observation_id)
            if not existing_incs:
                unassociated_obs.append(obs)

        created_incidents: List[Incident] = []
        updated_incident_map: Dict[str, Incident] = {}
        merged_incidents: List[Incident] = []
        new_assoc_count = 0
        events_emitted: List[IncidentEvent] = []

        if not unassociated_obs:
            # Everything is already ingested and correlated (idempotent no-op)
            return CorrelationResult()

        # 5. Match unassociated observations against existing open incidents
        # Map: observation_id -> matching Incident
        obs_to_incident: Dict[str, Incident] = {}
        unmatched_obs: List[Observation] = []

        for obs in unassociated_obs:
            matched_incs = self._find_matching_incidents(obs, active_incidents)
            if not matched_incs:
                unmatched_obs.append(obs)
            elif len(matched_incs) == 1:
                obs_to_incident[obs.observation_id] = matched_incs[0]
            else:
                # Observation bridges multiple existing incidents -> merge them deterministically!
                survivor = matched_incs[0]
                for other in matched_incs[1:]:
                    if other.incident_id != survivor.incident_id:
                        if any(inc.incident_id == other.incident_id for inc in active_incidents):
                            survivor, absorbed = self.merge_incidents(
                                survivor.incident_id,
                                other.incident_id,
                                reason=f"Merged via bridging observation {obs.observation_id}",
                                actor="system_correlator",
                            )
                            merged_incidents.append(absorbed)
                            active_incidents = [inc for inc in active_incidents if inc.incident_id != absorbed.incident_id]
                            for oid, target_inc in list(obs_to_incident.items()):
                                if target_inc.incident_id == absorbed.incident_id:
                                    obs_to_incident[oid] = survivor
                obs_to_incident[obs.observation_id] = survivor

        # 6. For observations that matched existing incidents: associate them
        for obs in unassociated_obs:
            if obs.observation_id in obs_to_incident:
                target_inc = obs_to_incident[obs.observation_id]
                dist = haversine_distance_km(
                    obs.latitude, obs.longitude,
                    target_inc.centroid_latitude, target_inc.centroid_longitude,
                )
                assoc = IncidentObservation(
                    incident_id=target_inc.incident_id,
                    observation_id=obs.observation_id,
                    joined_at_utc=eval_time,
                    association_method="spatiotemporal_proximity",
                    association_reason=f"Proximity match ({dist:.2f}km from centroid)",
                )
                if self.repository.add_incident_observation(assoc):
                    new_assoc_count += 1
                    # Record OBSERVATION_ADDED event idempotently
                    if not self.repository.has_observation_event(target_inc.incident_id, obs.observation_id):
                        evt = IncidentEvent(
                            event_id=generate_event_id(target_inc.incident_id, IncidentEventType.OBSERVATION_ADDED, obs.observation_id),
                            incident_id=target_inc.incident_id,
                            event_type=IncidentEventType.OBSERVATION_ADDED,
                            timestamp_utc=obs.ingestion_time_utc or eval_time,
                            actor="system_correlator",
                            reason=f"Observation {obs.observation_id} added ({dist:.2f}km from centroid)",
                            metadata={
                                "observation_id": obs.observation_id,
                                "frp": obs.frp,
                                "satellite": obs.satellite,
                                "instrument": obs.instrument,
                                "distance_km": round(dist, 3),
                            },
                        )
                        if self.repository.save_incident_event(evt):
                            events_emitted.append(evt)
                    updated_incident_map[target_inc.incident_id] = target_inc

        # 7. For observations that matched NO existing incident: group into new clusters
        if unmatched_obs:
            clusters = self.aggregator.cluster_observations(unmatched_obs)
            for cluster in clusters:
                # Deterministically select root representative
                root_obs = max(
                    cluster,
                    key=lambda o: (o.frp, o.brightness, o.acquisition_time_utc, o.observation_id),
                )
                dates = [parse_observation_datetime(o) for o in cluster]
                first_seen = min(dates).isoformat().replace("+00:00", "Z")
                last_seen = max(dates).isoformat().replace("+00:00", "Z")
                c_lat = round(sum(o.latitude for o in cluster) / len(cluster), 4)
                c_lon = round(sum(o.longitude for o in cluster) / len(cluster), 4)
                peak_frp = max(o.frp for o in cluster)
                avg_frp = round(sum(o.frp for o in cluster) / len(cluster), 2)
                cnt = len(cluster)

                # Geometry footprint
                if cnt == 1:
                    geom = {"type": "Point", "coordinates": [cluster[0].longitude, cluster[0].latitude]}
                else:
                    geom = {"type": "MultiPoint", "coordinates": [[o.longitude, o.latitude] for o in cluster]}

                # Baseline risk and classification
                init_risk, init_sev = self._calculate_risk_and_severity(peak_frp)
                init_status = IncidentStatus.ACTIVE if (init_sev in (RiskLevel.CRITICAL, RiskLevel.HIGH) or peak_frp >= 100.0) else IncidentStatus.MONITORING

                # Mint stable permanent incident identifier
                inc_id = generate_stable_incident_id(first_seen, root_obs.observation_id)

                # Check if this incident was previously persisted (idempotency guard)
                existing = self.repository.get_incident(inc_id)
                if existing:
                    new_inc = existing
                else:
                    new_inc = Incident(
                        incident_id=inc_id,
                        status=init_status,
                        first_seen_utc=first_seen,
                        last_seen_utc=last_seen,
                        centroid_latitude=c_lat,
                        centroid_longitude=c_lon,
                        geometry_geojson=geom,
                        nearest_place=root_obs.source_attributes.get("nearest_place"),
                        peak_frp=peak_frp,
                        average_frp=avg_frp,
                        observation_count=cnt,
                        current_risk_score=init_risk,
                        current_severity=init_sev,
                        current_classification=SourceType.UNKNOWN,
                        created_at_utc=first_seen,
                        updated_at_utc=eval_time,
                    )
                    self.repository.save_incident(new_inc)
                    created_incidents.append(new_inc)

                    # Emit CREATED event
                    evt_created = IncidentEvent(
                        event_id=generate_event_id(inc_id, IncidentEventType.CREATED, inc_id),
                        incident_id=inc_id,
                        event_type=IncidentEventType.CREATED,
                        timestamp_utc=first_seen,
                        actor="system_correlator",
                        reason="Initial cluster formed from remote sensing observations",
                        metadata={
                            "seed_observation_id": root_obs.observation_id,
                            "detection_count": cnt,
                            "peak_frp": peak_frp,
                        },
                    )
                    if self.repository.save_incident_event(evt_created):
                        events_emitted.append(evt_created)

                # Associate all cluster members
                for obs in cluster:
                    d = haversine_distance_km(obs.latitude, obs.longitude, c_lat, c_lon)
                    assoc = IncidentObservation(
                        incident_id=inc_id,
                        observation_id=obs.observation_id,
                        joined_at_utc=eval_time,
                        association_method="cluster_correlation",
                        association_reason=f"Initial cluster member ({d:.2f}km from centroid)",
                    )
                    if self.repository.add_incident_observation(assoc):
                        new_assoc_count += 1
                        if not self.repository.has_observation_event(inc_id, obs.observation_id):
                            evt_add = IncidentEvent(
                                event_id=generate_event_id(inc_id, IncidentEventType.OBSERVATION_ADDED, obs.observation_id),
                                incident_id=inc_id,
                                event_type=IncidentEventType.OBSERVATION_ADDED,
                                timestamp_utc=obs.ingestion_time_utc or eval_time,
                                actor="system_correlator",
                                reason=f"Observation {obs.observation_id} added via cluster",
                                metadata={
                                    "observation_id": obs.observation_id,
                                    "frp": obs.frp,
                                    "distance_km": round(d, 3),
                                },
                            )
                            if self.repository.save_incident_event(evt_add):
                                events_emitted.append(evt_add)

                active_incidents.append(new_inc)

        # 8. Recalculate metrics & check escalation/deescalation for all updated incidents
        for inc_id, inc_entity in updated_incident_map.items():
            evts = self._recalculate_incident_state(inc_id, eval_time)
            events_emitted.extend(evts)

        return CorrelationResult(
            created_incidents=created_incidents,
            updated_incidents=list(updated_incident_map.values()),
            merged_incidents=merged_incidents,
            associations_count=new_assoc_count,
            events_emitted=events_emitted,
        )

    # -------------------------------------------------------------------------
    # Proximity & Incident Matching
    # -------------------------------------------------------------------------

    def _find_matching_incidents(
        self,
        obs: Observation,
        active_incidents: List[Incident],
    ) -> List[Incident]:
        """Find all matching open incidents for an observation.
        
        Evaluates spatial proximity, temporal continuity, and classification compatibility.
        Returns matching candidates sorted deterministically (closest/preferred first).
        """
        candidates: List[Tuple[float, float, str, Incident]] = []
        dt_obs = parse_observation_datetime(obs)

        for inc in active_incidents:
            # 1. Spatial proximity check: against centroid
            d_centroid = haversine_distance_km(
                obs.latitude, obs.longitude,
                inc.centroid_latitude, inc.centroid_longitude,
            )

            # Also check against member observations if centroid is slightly beyond boundary
            min_dist = d_centroid
            if d_centroid > self.spatial_threshold_km:
                member_obs = self.repository.list_incident_observations(inc.incident_id)
                for m in member_obs:
                    d_m = haversine_distance_km(obs.latitude, obs.longitude, m.latitude, m.longitude)
                    if d_m < min_dist:
                        min_dist = d_m
                    if min_dist <= self.spatial_threshold_km:
                        break

            if min_dist > self.spatial_threshold_km:
                continue

            # 2. Temporal continuity check
            dt_first = parse_observation_datetime(
                Observation(
                    observation_id="temp_first", provider="temp", product="temp",
                    latitude=0, longitude=0, acquisition_time_utc=inc.first_seen_utc,
                    ingestion_time_utc=inc.first_seen_utc, brightness=300, frp=10,
                    daynight="D", detection_confidence="nominal",
                )
            )
            dt_last = parse_observation_datetime(
                Observation(
                    observation_id="temp_last", provider="temp", product="temp",
                    latitude=0, longitude=0, acquisition_time_utc=inc.last_seen_utc,
                    ingestion_time_utc=inc.last_seen_utc, brightness=300, frp=10,
                    daynight="D", detection_confidence="nominal",
                )
            )
            diff_hours = min(
                abs((dt_obs - dt_first).total_seconds()),
                abs((dt_obs - dt_last).total_seconds()),
            ) / 3600.0

            if diff_hours > self.temporal_window_hours:
                continue

            # 3. Classification compatibility check
            obs_src = obs.source_attributes.get("source_type")
            if obs_src and inc.current_classification != SourceType.UNKNOWN:
                incompatible_pairs = {
                    (SourceType.VOLCANIC, SourceType.AGRICULTURAL),
                    (SourceType.VOLCANIC, SourceType.URBAN),
                    (SourceType.INDUSTRIAL, SourceType.WILDFIRE),
                }
                pair = (obs_src, inc.current_classification)
                reverse_pair = (inc.current_classification, obs_src)
                if (pair in incompatible_pairs or reverse_pair in incompatible_pairs) and min_dist > 0.3:
                    continue

            # Candidate match found: record score for deterministic ranking
            # Rank tuple: (distance_km, temporal_diff_hours, first_seen_utc, incident_id)
            candidates.append((min_dist, diff_hours, inc.first_seen_utc, inc))

        if not candidates:
            return []

        # Sort candidates deterministically: lowest distance, lowest time diff, earliest first_seen, lowest ID
        candidates.sort(key=lambda c: (c[0], c[1], c[2], c[3].incident_id))
        return [c[3] for c in candidates]

    def _find_matching_incident(
        self,
        obs: Observation,
        active_incidents: List[Incident],
    ) -> Optional[Incident]:
        """Find the single best matching open incident for an observation."""
        matches = self._find_matching_incidents(obs, active_incidents)
        return matches[0] if matches else None

    # -------------------------------------------------------------------------
    # Recalculation & Evolution
    # -------------------------------------------------------------------------

    def _recalculate_incident_state(
        self,
        incident_id: str,
        evaluation_time: str,
    ) -> List[IncidentEvent]:
        """Recalculate an incident's centroid, FRP, risk score, and emit escalation/deescalation events."""
        events: List[IncidentEvent] = []
        inc = self.repository.get_incident(incident_id)
        if not inc:
            return events

        observations = self.repository.list_incident_observations(incident_id)
        if not observations:
            return events

        count = len(observations)
        dates = [parse_observation_datetime(o) for o in observations]
        first_seen = min(dates).isoformat().replace("+00:00", "Z")
        last_seen = max(dates).isoformat().replace("+00:00", "Z")
        centroid_lat = round(sum(o.latitude for o in observations) / count, 4)
        centroid_lon = round(sum(o.longitude for o in observations) / count, 4)
        peak_frp = max(o.frp for o in observations)
        avg_frp = round(sum(o.frp for o in observations) / count, 2)

        if count == 1:
            geom = {"type": "Point", "coordinates": [observations[0].longitude, observations[0].latitude]}
        else:
            geom = {"type": "MultiPoint", "coordinates": [[o.longitude, o.latitude] for o in observations]}

        # Check for active Assessment
        assessment = self.repository.get_assessment(incident_id)
        if not assessment and inc.current_assessment_id:
            assessment = self.repository.get_assessment(inc.current_assessment_id)

        if assessment:
            new_risk = assessment.risk.risk_score
            new_sev = assessment.risk.severity
            new_class = assessment.classification.predicted_source
        else:
            new_risk, new_sev = self._calculate_risk_and_severity(peak_frp)
            new_class = inc.current_classification

        old_sev = inc.current_severity
        old_risk = inc.current_risk_score

        # Check for meaningful severity tier changes (ESCALATED / DEESCALATED)
        old_rank = SEVERITY_RANK.get(old_sev, 1)
        new_rank = SEVERITY_RANK.get(new_sev, 1)

        if new_rank > old_rank:
            evt_esc = IncidentEvent(
                event_id=generate_event_id(incident_id, IncidentEventType.ESCALATED, f"{old_sev.value}->{new_sev.value}:{count}"),
                incident_id=incident_id,
                event_type=IncidentEventType.ESCALATED,
                timestamp_utc=evaluation_time,
                actor="risk_engine",
                reason=f"Incident risk escalated from {old_sev.value} ({old_risk:.1f}) to {new_sev.value} ({new_risk:.1f})",
                metadata={
                    "old_severity": old_sev.value,
                    "new_severity": new_sev.value,
                    "old_risk_score": old_risk,
                    "new_risk_score": new_risk,
                    "peak_frp": peak_frp,
                },
            )
            if self.repository.save_incident_event(evt_esc):
                events.append(evt_esc)
        elif new_rank < old_rank:
            evt_deesc = IncidentEvent(
                event_id=generate_event_id(incident_id, IncidentEventType.DEESCALATED, f"{old_sev.value}->{new_sev.value}:{count}"),
                incident_id=incident_id,
                event_type=IncidentEventType.DEESCALATED,
                timestamp_utc=evaluation_time,
                actor="risk_engine",
                reason=f"Incident risk deescalated from {old_sev.value} ({old_risk:.1f}) to {new_sev.value} ({new_risk:.1f})",
                metadata={
                    "old_severity": old_sev.value,
                    "new_severity": new_sev.value,
                    "old_risk_score": old_risk,
                    "new_risk_score": new_risk,
                    "peak_frp": peak_frp,
                },
            )
            if self.repository.save_incident_event(evt_deesc):
                events.append(evt_deesc)

        # Reopen if previously resolved/closed
        status = inc.status
        if inc.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
            status = IncidentStatus.ACTIVE if new_sev in (RiskLevel.CRITICAL, RiskLevel.HIGH) else IncidentStatus.MONITORING
            evt_reopen = IncidentEvent(
                event_id=generate_event_id(incident_id, IncidentEventType.REOPENED, f"reopen:{count}"),
                incident_id=incident_id,
                event_type=IncidentEventType.REOPENED,
                timestamp_utc=evaluation_time,
                actor="system_correlator",
                reason="Incident reopened upon arrival of new satellite observations",
                metadata={"new_status": status.value, "observation_count": count},
            )
            if self.repository.save_incident_event(evt_reopen):
                events.append(evt_reopen)

        # Update and persist incident
        updated_inc = Incident(
            incident_id=incident_id,
            status=status,
            first_seen_utc=first_seen,
            last_seen_utc=last_seen,
            centroid_latitude=centroid_lat,
            centroid_longitude=centroid_lon,
            geometry_geojson=geom,
            nearest_place=inc.nearest_place,
            peak_frp=peak_frp,
            average_frp=avg_frp,
            observation_count=count,
            current_risk_score=new_risk,
            current_severity=new_sev,
            current_classification=new_class,
            current_assessment_id=inc.current_assessment_id,
            created_at_utc=inc.created_at_utc,
            updated_at_utc=evaluation_time,
        )
        self.repository.save_incident(updated_inc)
        return events

    @staticmethod
    def _calculate_risk_and_severity(peak_frp: float) -> Tuple[float, RiskLevel]:
        """Derive baseline risk score and severity level directly from sensor measurements."""
        score = min(100.0, peak_frp * 0.7)
        if score >= 75.0:
            sev = RiskLevel.CRITICAL
        elif score >= 50.0:
            sev = RiskLevel.HIGH
        elif score >= 25.0:
            sev = RiskLevel.MEDIUM
        else:
            sev = RiskLevel.LOW
        return round(score, 1), sev

    # -------------------------------------------------------------------------
    # Merge & Split Operations
    # -------------------------------------------------------------------------

    def merge_incidents(
        self,
        incident_a_id: str,
        incident_b_id: str,
        reason: Optional[str] = None,
        actor: str = "system_correlator",
    ) -> Tuple[Incident, Incident]:
        """Deterministically merge two tracked incidents into one.
        
        Requirements:
        - Choose a deterministic surviving incident (earlier first_seen, higher count, higher FRP, lower ID).
        - Preserve both histories and append-only event records.
        - Record MERGED event on both incidents.
        - Retain resolvability of the merged incident ID (retains row in DB, status=closed).
        - Re-associate observations with the survivor.
        """
        if incident_a_id == incident_b_id:
            inc = self.repository.get_incident(incident_a_id)
            if not inc:
                raise ValueError(f"Incident {incident_a_id} does not exist")
            return inc, inc

        inc_a = self.repository.get_incident(incident_a_id)
        inc_b = self.repository.get_incident(incident_b_id)

        if not inc_a or not inc_b:
            raise ValueError(f"Both incidents must exist to merge: {incident_a_id}, {incident_b_id}")

        # Deterministic survivor selection:
        # 1. Earlier first_seen_utc
        # 2. Higher observation_count
        # 3. Higher peak_frp
        # 4. Lexicographically lower incident_id
        survivor, absorbed = (inc_a, inc_b) if self._is_preferred_survivor(inc_a, inc_b) else (inc_b, inc_a)

        merge_time = now_utc_iso()
        absorbed_obs = self.repository.list_incident_observations(absorbed.incident_id)

        # 1. Re-associate all observations from absorbed incident into survivor
        for obs in absorbed_obs:
            assoc = IncidentObservation(
                incident_id=survivor.incident_id,
                observation_id=obs.observation_id,
                joined_at_utc=merge_time,
                association_method="incident_merge",
                association_reason=f"Merged from {absorbed.incident_id}",
            )
            self.repository.add_incident_observation(assoc)

        # 2. Record MERGED event on absorbed incident
        evt_absorbed = IncidentEvent(
            event_id=generate_event_id(absorbed.incident_id, IncidentEventType.MERGED, survivor.incident_id),
            incident_id=absorbed.incident_id,
            event_type=IncidentEventType.MERGED,
            timestamp_utc=merge_time,
            actor=actor,
            reason=reason or f"Merged into surviving incident {survivor.incident_id}",
            metadata={
                "surviving_incident_id": survivor.incident_id,
                "absorbed_incident_id": absorbed.incident_id,
                "observations_transferred": len(absorbed_obs),
            },
        )
        self.repository.save_incident_event(evt_absorbed)

        # 3. Mark absorbed incident as CLOSED (preserving row for historical resolvability)
        updated_absorbed = Incident(
            incident_id=absorbed.incident_id,
            status=IncidentStatus.CLOSED,
            first_seen_utc=absorbed.first_seen_utc,
            last_seen_utc=absorbed.last_seen_utc,
            centroid_latitude=absorbed.centroid_latitude,
            centroid_longitude=absorbed.centroid_longitude,
            geometry_geojson=absorbed.geometry_geojson,
            nearest_place=absorbed.nearest_place,
            peak_frp=absorbed.peak_frp,
            average_frp=absorbed.average_frp,
            observation_count=absorbed.observation_count,
            current_risk_score=absorbed.current_risk_score,
            current_severity=absorbed.current_severity,
            current_classification=absorbed.current_classification,
            current_assessment_id=absorbed.current_assessment_id,
            created_at_utc=absorbed.created_at_utc,
            updated_at_utc=merge_time,
        )
        self.repository.save_incident(updated_absorbed)

        # 4. Record MERGED event on surviving incident
        evt_survivor = IncidentEvent(
            event_id=generate_event_id(survivor.incident_id, IncidentEventType.MERGED, absorbed.incident_id),
            incident_id=survivor.incident_id,
            event_type=IncidentEventType.MERGED,
            timestamp_utc=merge_time,
            actor=actor,
            reason=reason or f"Absorbed merged incident {absorbed.incident_id}",
            metadata={
                "absorbed_incident_id": absorbed.incident_id,
                "surviving_incident_id": survivor.incident_id,
                "added_observations_count": len(absorbed_obs),
            },
        )
        self.repository.save_incident_event(evt_survivor)

        # 5. Recalculate survivor state across all observations
        self._recalculate_incident_state(survivor.incident_id, merge_time)
        refreshed_survivor = self.repository.get_incident(survivor.incident_id) or survivor

        return refreshed_survivor, updated_absorbed

    @staticmethod
    def _is_preferred_survivor(a: Incident, b: Incident) -> bool:
        """Deterministic tie-breaker for incident merge operations."""
        if a.first_seen_utc != b.first_seen_utc:
            return a.first_seen_utc < b.first_seen_utc
        if a.observation_count != b.observation_count:
            return a.observation_count > b.observation_count
        if a.peak_frp != b.peak_frp:
            return a.peak_frp > b.peak_frp
        return a.incident_id < b.incident_id

    def split_incident(
        self,
        incident_id: str,
        split_observation_ids: List[str],
        reason: Optional[str] = None,
        actor: str = "system_correlator",
    ) -> Tuple[Incident, Incident]:
        """Safely split an incident by transferring a subset of observations to a new incident.
        
        Requirements:
        - Preserve original observations and data integrity.
        - Create a new persistent identity for the child incident.
        - Record SPLIT events on both parent and child.
        - Preserve historical resolvability.
        
        Limitation Note:
        The frozen schema does not include a `parent_incident_id` foreign key column on `incidents`.
        Parent-child lineage is preserved in `incident_events` metadata and `incident_observations`
        association reason fields.
        """
        parent = self.repository.get_incident(incident_id)
        if not parent:
            raise ValueError(f"Parent incident {incident_id} not found")

        parent_obs = self.repository.list_incident_observations(incident_id)
        parent_obs_map = {o.observation_id: o for o in parent_obs}

        split_set = set(split_observation_ids)
        if not split_set:
            raise ValueError("Cannot split with empty observation list")
        if not split_set.issubset(parent_obs_map.keys()):
            raise ValueError("All split observation IDs must belong to the parent incident")
        if len(split_set) == len(parent_obs_map):
            raise ValueError("Cannot split all observations from parent incident")

        split_time = now_utc_iso()
        split_obs_list = [parent_obs_map[oid] for oid in sorted(list(split_set))]

        # Deterministic seed for child incident identity
        child_seed = max(
            split_obs_list,
            key=lambda o: (o.frp, o.brightness, o.acquisition_time_utc, o.observation_id),
        )
        child_dates = [parse_observation_datetime(o) for o in split_obs_list]
        child_first_seen = min(child_dates).isoformat().replace("+00:00", "Z")
        child_last_seen = max(child_dates).isoformat().replace("+00:00", "Z")
        child_lat = round(sum(o.latitude for o in split_obs_list) / len(split_obs_list), 4)
        child_lon = round(sum(o.longitude for o in split_obs_list) / len(split_obs_list), 4)
        child_peak_frp = max(o.frp for o in split_obs_list)
        child_avg_frp = round(sum(o.frp for o in split_obs_list) / len(split_obs_list), 2)
        child_risk, child_sev = self._calculate_risk_and_severity(child_peak_frp)

        child_id = generate_stable_incident_id(
            child_first_seen,
            f"{parent.incident_id}:split:{child_seed.observation_id}",
        )

        # 1. Create and persist child incident
        child = Incident(
            incident_id=child_id,
            status=IncidentStatus.ACTIVE if child_sev in (RiskLevel.CRITICAL, RiskLevel.HIGH) else IncidentStatus.MONITORING,
            first_seen_utc=child_first_seen,
            last_seen_utc=child_last_seen,
            centroid_latitude=child_lat,
            centroid_longitude=child_lon,
            geometry_geojson={"type": "MultiPoint", "coordinates": [[o.longitude, o.latitude] for o in split_obs_list]} if len(split_obs_list) > 1 else {"type": "Point", "coordinates": [split_obs_list[0].longitude, split_obs_list[0].latitude]},
            nearest_place=child_seed.source_attributes.get("nearest_place") or parent.nearest_place,
            peak_frp=child_peak_frp,
            average_frp=child_avg_frp,
            observation_count=len(split_obs_list),
            current_risk_score=child_risk,
            current_severity=child_sev,
            current_classification=parent.current_classification,
            created_at_utc=split_time,
            updated_at_utc=split_time,
        )
        self.repository.save_incident(child)

        # 2. Transfer observation links: add to child, remove from parent
        for obs in split_obs_list:
            self.repository.add_incident_observation(
                IncidentObservation(
                    incident_id=child_id,
                    observation_id=obs.observation_id,
                    joined_at_utc=split_time,
                    association_method="incident_split",
                    association_reason=f"Split from parent incident {parent.incident_id}",
                )
            )
            self.repository.delete_incident_observation(parent.incident_id, obs.observation_id)

        # 3. Record SPLIT event on child incident
        evt_child = IncidentEvent(
            event_id=generate_event_id(child_id, IncidentEventType.SPLIT, parent.incident_id),
            incident_id=child_id,
            event_type=IncidentEventType.SPLIT,
            timestamp_utc=split_time,
            actor=actor,
            reason=reason or f"Created via split from parent incident {parent.incident_id}",
            metadata={
                "parent_incident_id": parent.incident_id,
                "transferred_observation_ids": sorted(list(split_set)),
            },
        )
        self.repository.save_incident_event(evt_child)

        # 4. Record SPLIT event on parent incident
        evt_parent = IncidentEvent(
            event_id=generate_event_id(parent.incident_id, IncidentEventType.SPLIT, child_id),
            incident_id=parent.incident_id,
            event_type=IncidentEventType.SPLIT,
            timestamp_utc=split_time,
            actor=actor,
            reason=reason or f"Split off {len(split_set)} observations into child incident {child_id}",
            metadata={
                "child_incident_id": child_id,
                "split_observation_ids": sorted(list(split_set)),
                "remaining_count": len(parent_obs_map) - len(split_set),
            },
        )
        self.repository.save_incident_event(evt_parent)

        # 5. Recalculate parent state from remaining observations
        self._recalculate_incident_state(parent.incident_id, split_time)
        refreshed_parent = self.repository.get_incident(parent.incident_id) or parent

        return refreshed_parent, child

    # -------------------------------------------------------------------------
    # Lifecycle & Explicit State Transitions
    # -------------------------------------------------------------------------

    def close_incident(
        self,
        incident_id: str,
        reason: str = "Operator closed incident",
        actor: str = "operator",
    ) -> Incident:
        """Explicitly transition an incident to CLOSED and record append-only event."""
        inc = self.repository.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident {incident_id} not found")

        t = now_utc_iso()
        updated_inc = Incident(
            incident_id=inc.incident_id,
            status=IncidentStatus.CLOSED,
            first_seen_utc=inc.first_seen_utc,
            last_seen_utc=inc.last_seen_utc,
            centroid_latitude=inc.centroid_latitude,
            centroid_longitude=inc.centroid_longitude,
            geometry_geojson=inc.geometry_geojson,
            nearest_place=inc.nearest_place,
            peak_frp=inc.peak_frp,
            average_frp=inc.average_frp,
            observation_count=inc.observation_count,
            current_risk_score=inc.current_risk_score,
            current_severity=inc.current_severity,
            current_classification=inc.current_classification,
            current_assessment_id=inc.current_assessment_id,
            created_at_utc=inc.created_at_utc,
            updated_at_utc=t,
        )
        self.repository.save_incident(updated_inc)

        evt = IncidentEvent(
            event_id=generate_event_id(incident_id, IncidentEventType.CLOSED, t),
            incident_id=incident_id,
            event_type=IncidentEventType.CLOSED,
            timestamp_utc=t,
            actor=actor,
            reason=reason,
            metadata={"previous_status": inc.status.value},
        )
        self.repository.save_incident_event(evt)
        return updated_inc

    def reopen_incident(
        self,
        incident_id: str,
        reason: str = "Operator reopened incident",
        actor: str = "operator",
    ) -> Incident:
        """Explicitly reopen a resolved or closed incident."""
        inc = self.repository.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident {incident_id} not found")

        t = now_utc_iso()
        new_status = IncidentStatus.ACTIVE if inc.current_severity in (RiskLevel.CRITICAL, RiskLevel.HIGH) else IncidentStatus.MONITORING

        updated_inc = Incident(
            incident_id=inc.incident_id,
            status=new_status,
            first_seen_utc=inc.first_seen_utc,
            last_seen_utc=inc.last_seen_utc,
            centroid_latitude=inc.centroid_latitude,
            centroid_longitude=inc.centroid_longitude,
            geometry_geojson=inc.geometry_geojson,
            nearest_place=inc.nearest_place,
            peak_frp=inc.peak_frp,
            average_frp=inc.average_frp,
            observation_count=inc.observation_count,
            current_risk_score=inc.current_risk_score,
            current_severity=inc.current_severity,
            current_classification=inc.current_classification,
            current_assessment_id=inc.current_assessment_id,
            created_at_utc=inc.created_at_utc,
            updated_at_utc=t,
        )
        self.repository.save_incident(updated_inc)

        evt = IncidentEvent(
            event_id=generate_event_id(incident_id, IncidentEventType.REOPENED, t),
            incident_id=incident_id,
            event_type=IncidentEventType.REOPENED,
            timestamp_utc=t,
            actor=actor,
            reason=reason,
            metadata={"previous_status": inc.status.value, "new_status": new_status.value},
        )
        self.repository.save_incident_event(evt)
        return updated_inc

    def acknowledge_incident(
        self,
        incident_id: str,
        reason: str = "Incident acknowledged by operations",
        actor: str = "operator",
    ) -> Incident:
        """Record an ACKNOWLEDGED audit event without mutating physical incident boundaries."""
        inc = self.repository.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident {incident_id} not found")

        t = now_utc_iso()
        evt = IncidentEvent(
            event_id=generate_event_id(incident_id, IncidentEventType.ACKNOWLEDGED, t),
            incident_id=incident_id,
            event_type=IncidentEventType.ACKNOWLEDGED,
            timestamp_utc=t,
            actor=actor,
            reason=reason,
            metadata={"status": inc.status.value, "risk_score": inc.current_risk_score},
        )
        self.repository.save_incident_event(evt)
        return inc

    def evaluate_lifecycle(
        self,
        as_of_utc: str,
        quiet_threshold_hours: float = 48.0,
        resolution_threshold_hours: float = 96.0,
    ) -> List[IncidentEvent]:
        """Apply deterministic observation-based rules to transition quiet incidents.
        
        Important Principle:
        NO DETECTION does NOT mean: EXTINGUISHED.
        Transitions to MONITORING or RESOLVED require explicit time limits with zero detections.
        """
        events: List[IncidentEvent] = []
        dt_as_of = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00"))
        if dt_as_of.tzinfo is None:
            dt_as_of = dt_as_of.replace(tzinfo=timezone.utc)

        active_incidents = self.repository.list_incidents(
            status=[IncidentStatus.ACTIVE, IncidentStatus.MONITORING]
        )

        for inc in active_incidents:
            dt_last = datetime.fromisoformat(inc.last_seen_utc.replace("Z", "+00:00"))
            if dt_last.tzinfo is None:
                dt_last = dt_last.replace(tzinfo=timezone.utc)

            quiet_hours = (dt_as_of - dt_last).total_seconds() / 3600.0

            if quiet_hours >= resolution_threshold_hours and inc.status != IncidentStatus.RESOLVED:
                # Transition to RESOLVED (long-term inactivity)
                updated = Incident(
                    incident_id=inc.incident_id,
                    status=IncidentStatus.RESOLVED,
                    first_seen_utc=inc.first_seen_utc,
                    last_seen_utc=inc.last_seen_utc,
                    centroid_latitude=inc.centroid_latitude,
                    centroid_longitude=inc.centroid_longitude,
                    geometry_geojson=inc.geometry_geojson,
                    nearest_place=inc.nearest_place,
                    peak_frp=inc.peak_frp,
                    average_frp=inc.average_frp,
                    observation_count=inc.observation_count,
                    current_risk_score=inc.current_risk_score,
                    current_severity=inc.current_severity,
                    current_classification=inc.current_classification,
                    current_assessment_id=inc.current_assessment_id,
                    created_at_utc=inc.created_at_utc,
                    updated_at_utc=as_of_utc,
                )
                self.repository.save_incident(updated)
                evt = IncidentEvent(
                    event_id=generate_event_id(inc.incident_id, IncidentEventType.DEESCALATED, f"resolved:{as_of_utc}"),
                    incident_id=inc.incident_id,
                    event_type=IncidentEventType.DEESCALATED,
                    timestamp_utc=as_of_utc,
                    actor="lifecycle_evaluator",
                    reason=f"Incident marked resolved after {quiet_hours:.1f} hours without thermal detection",
                    metadata={"previous_status": inc.status.value, "quiet_hours": round(quiet_hours, 1)},
                )
                if self.repository.save_incident_event(evt):
                    events.append(evt)

            elif quiet_hours >= quiet_threshold_hours and inc.status == IncidentStatus.ACTIVE:
                # Transition ACTIVE -> MONITORING (thermal activity quieted, not extinguished)
                updated = Incident(
                    incident_id=inc.incident_id,
                    status=IncidentStatus.MONITORING,
                    first_seen_utc=inc.first_seen_utc,
                    last_seen_utc=inc.last_seen_utc,
                    centroid_latitude=inc.centroid_latitude,
                    centroid_longitude=inc.centroid_longitude,
                    geometry_geojson=inc.geometry_geojson,
                    nearest_place=inc.nearest_place,
                    peak_frp=inc.peak_frp,
                    average_frp=inc.average_frp,
                    observation_count=inc.observation_count,
                    current_risk_score=inc.current_risk_score,
                    current_severity=inc.current_severity,
                    current_classification=inc.current_classification,
                    current_assessment_id=inc.current_assessment_id,
                    created_at_utc=inc.created_at_utc,
                    updated_at_utc=as_of_utc,
                )
                self.repository.save_incident(updated)
                evt = IncidentEvent(
                    event_id=generate_event_id(inc.incident_id, IncidentEventType.DEESCALATED, f"monitoring:{as_of_utc}"),
                    incident_id=inc.incident_id,
                    event_type=IncidentEventType.DEESCALATED,
                    timestamp_utc=as_of_utc,
                    actor="lifecycle_evaluator",
                    reason=f"Incident transitioned to monitoring after {quiet_hours:.1f} hours without new detection",
                    metadata={"previous_status": "active", "quiet_hours": round(quiet_hours, 1)},
                )
                if self.repository.save_incident_event(evt):
                    events.append(evt)

        return events
