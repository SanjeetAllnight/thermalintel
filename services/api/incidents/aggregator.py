"""Incident aggregation and deduplication engine for ThermalIntel Phase 4 & V2.

Provides deterministic grouping of proximate thermal detections (both V1 Hotspot
and V2 Observation records) to prevent duplicate incidents on the operational dashboard.
"""

import math
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Set

from services.api.schemas.hotspot import Hotspot
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.v2 import Observation
from services.api.incidents.models import AggregatedIncident, IncidentStatus


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    radius_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_earth_km * c


def parse_hotspot_datetime(hotspot: Hotspot) -> datetime:
    """Extract or construct a timezone-aware datetime for a hotspot."""
    if hotspot.last_updated:
        try:
            dt = datetime.fromisoformat(hotspot.last_updated.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass

    try:
        time_str = hotspot.acq_time.zfill(4)
        hour = int(time_str[:2])
        minute = int(time_str[2:])
        dt = datetime.strptime(hotspot.acq_date, "%Y-%m-%d").replace(
            hour=hour, minute=minute, tzinfo=timezone.utc
        )
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def parse_observation_datetime(obs: Observation) -> datetime:
    """Parse canonical Observation acquisition timestamp into a timezone-aware UTC datetime."""
    try:
        dt = datetime.fromisoformat(obs.acquisition_time_utc.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class IncidentAggregator:
    """Aggregates and deduplicates raw thermal hotspots and observations into unified operational incidents."""

    def __init__(
        self,
        distance_threshold_km: float = 1.5,
        time_window_hours: float = 24.0,
    ):
        """Initialize aggregator with spatial and temporal deduplication limits.
        
        Args:
            distance_threshold_km: Maximum distance in km to consider same physical incident.
            time_window_hours: Maximum time delta in hours for clustering detections.
        """
        self.distance_threshold_km = distance_threshold_km
        self.time_window_hours = time_window_hours

    def are_detections_proximate(self, h1: Hotspot, h2: Hotspot) -> bool:
        """Evaluate if two V1 hotspot detections represent the same physical thermal event."""
        # 1. Exact ID match
        if h1.id == h2.id:
            return True

        dist_km = haversine_distance_km(h1.latitude, h1.longitude, h2.latitude, h2.longitude)

        # 2. Shared cluster ID assigned upstream (valid if within cluster envelope)
        if h1.cluster_id and h2.cluster_id and h1.cluster_id == h2.cluster_id:
            if dist_km <= max(self.distance_threshold_km * 2.5, 5.0):
                return True

        # 3. Spatial proximity check
        if dist_km > self.distance_threshold_km:
            return False

        # 4. Temporal proximity check
        dt1 = parse_hotspot_datetime(h1)
        dt2 = parse_hotspot_datetime(h2)
        diff_hours = abs((dt1 - dt2).total_seconds()) / 3600.0
        if diff_hours > self.time_window_hours:
            return False

        # 5. Classification compatibility (if both are classified, avoid grouping wildly different sources)
        incompatible_pairs = {
            (SourceType.VOLCANIC, SourceType.AGRICULTURAL),
            (SourceType.VOLCANIC, SourceType.URBAN),
            (SourceType.INDUSTRIAL, SourceType.WILDFIRE),
        }
        pair = (h1.source_type, h2.source_type)
        reverse_pair = (h2.source_type, h1.source_type)
        if pair in incompatible_pairs or reverse_pair in incompatible_pairs:
            if dist_km > 0.3:
                return False

        return True

    def are_observations_proximate(
        self,
        o1: Observation,
        o2: Observation,
        s1: Optional[SourceType] = None,
        s2: Optional[SourceType] = None,
    ) -> bool:
        """Evaluate if two canonical V2 observations represent the same physical thermal incident."""
        # 1. Exact ID match
        if o1.observation_id == o2.observation_id:
            return True

        dist_km = haversine_distance_km(o1.latitude, o1.longitude, o2.latitude, o2.longitude)

        # 2. Spatial proximity check
        if dist_km > self.distance_threshold_km:
            return False

        # 3. Temporal proximity check
        dt1 = parse_observation_datetime(o1)
        dt2 = parse_observation_datetime(o2)
        diff_hours = abs((dt1 - dt2).total_seconds()) / 3600.0
        if diff_hours > self.time_window_hours:
            return False

        # 4. Classification compatibility
        src1 = s1 or o1.source_attributes.get("source_type")
        src2 = s2 or o2.source_attributes.get("source_type")
        if src1 and src2:
            try:
                st1 = SourceType(src1) if not isinstance(src1, SourceType) else src1
                st2 = SourceType(src2) if not isinstance(src2, SourceType) else src2
                incompatible_pairs = {
                    (SourceType.VOLCANIC, SourceType.AGRICULTURAL),
                    (SourceType.VOLCANIC, SourceType.URBAN),
                    (SourceType.INDUSTRIAL, SourceType.WILDFIRE),
                }
                if (st1, st2) in incompatible_pairs or (st2, st1) in incompatible_pairs:
                    if dist_km > 0.3:
                        return False
            except (ValueError, KeyError):
                pass

        return True

    def cluster_observations(
        self,
        observations: List[Observation],
        observation_sources: Optional[Dict[str, SourceType]] = None,
    ) -> List[List[Observation]]:
        """Deterministically cluster a collection of canonical V2 Observation records.
        
        Applies strict spatiotemporal limits and transitive correlation.
        """
        if not observations:
            return []

        # Sort deterministically: highest FRP, then highest brightness, acquisition time, observation_id
        sorted_obs = sorted(
            observations,
            key=lambda o: (-o.frp, -o.brightness, o.acquisition_time_utc, o.observation_id),
        )

        clusters: List[List[Observation]] = []
        assigned: Set[str] = set()

        for i, obs in enumerate(sorted_obs):
            if obs.observation_id in assigned:
                continue

            current_cluster = [obs]
            assigned.add(obs.observation_id)

            for j in range(i + 1, len(sorted_obs)):
                candidate = sorted_obs[j]
                if candidate.observation_id in assigned:
                    continue

                s_cand = observation_sources.get(candidate.observation_id) if observation_sources else None

                # Transitive grouping: candidate matches if proximate to any cluster member
                is_match = False
                for member in current_cluster:
                    s_mem = observation_sources.get(member.observation_id) if observation_sources else None
                    if self.are_observations_proximate(member, candidate, s_mem, s_cand):
                        is_match = True
                        break

                if is_match:
                    current_cluster.append(candidate)
                    assigned.add(candidate.observation_id)

            clusters.append(current_cluster)

        return clusters

    def generate_incident_id(self, primary_hotspot: Hotspot) -> str:
        """Derive an incident identifier for legacy V1 callers.
        
        NOTE: In V2, persistent incident identity is minted once upon initial creation
        and remains permanent regardless of primary detection changes.
        """
        if primary_hotspot.id.startswith("INC-"):
            return primary_hotspot.id
        return f"INC-{primary_hotspot.id}"

    def aggregate(self, hotspots: List[Hotspot]) -> List[AggregatedIncident]:
        """Aggregate a collection of hotspots into deduplicated operational incidents.
        
        Deterministically groups proximate detections, selects a primary representative,
        and computes aggregate statistics.
        """
        if not hotspots:
            return []

        # Sort input deterministically: highest risk first, then highest FRP, then ID
        sorted_hotspots = sorted(
            hotspots,
            key=lambda h: (-h.risk_score, -h.frp, h.id),
        )

        clusters: List[List[Hotspot]] = []
        assigned = set()

        # Greedy deterministic clustering
        for i, h in enumerate(sorted_hotspots):
            if h.id in assigned:
                continue

            current_cluster = [h]
            assigned.add(h.id)

            for j in range(i + 1, len(sorted_hotspots)):
                candidate = sorted_hotspots[j]
                if candidate.id in assigned:
                    continue

                # Check proximity to any member of current cluster (transitive grouping)
                if any(self.are_detections_proximate(member, candidate) for member in current_cluster):
                    current_cluster.append(candidate)
                    assigned.add(candidate.id)

            clusters.append(current_cluster)

        # Build AggregatedIncident for each cluster
        incidents: List[AggregatedIncident] = []
        for cluster in clusters:
            primary = max(
                cluster,
                key=lambda h: (h.risk_score, h.frp, parse_hotspot_datetime(h), -ord(h.id[0]) if h.id else 0),
            )

            detection_count = len(cluster)
            hotspot_ids = sorted([h.id for h in cluster])
            peak_frp = max(h.frp for h in cluster)
            avg_frp = round(sum(h.frp for h in cluster) / detection_count, 2)
            has_anomaly = any(h.is_anomaly for h in cluster)

            # Determine dominant source
            source_freq: Dict[SourceType, int] = {}
            for h in cluster:
                source_freq[h.source_type] = source_freq.get(h.source_type, 0) + 1
            dominant_source = max(
                source_freq.keys(),
                key=lambda s: (source_freq[s], s == primary.source_type)
            )

            # Centroid coordinates
            centroid_lat = round(sum(h.latitude for h in cluster) / detection_count, 4)
            centroid_lon = round(sum(h.longitude for h in cluster) / detection_count, 4)

            # Timestamps
            dates = [parse_hotspot_datetime(h) for h in cluster]
            first_dt = min(dates)
            last_dt = max(dates)

            # Status determination
            if primary.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                status = IncidentStatus.ACTIVE
            elif primary.risk_level == RiskLevel.MEDIUM:
                status = IncidentStatus.ACTIVE if has_anomaly else IncidentStatus.MONITORING
            else:
                status = IncidentStatus.MONITORING

            incident_id = self.generate_incident_id(primary)

            incidents.append(
                AggregatedIncident(
                    incident_id=incident_id,
                    primary_hotspot_id=primary.id,
                    cluster_id=primary.cluster_id,
                    hotspot_ids=hotspot_ids,
                    detection_count=detection_count,
                    latitude=centroid_lat,
                    longitude=centroid_lon,
                    nearest_place=primary.nearest_place,
                    first_seen=first_dt.isoformat().replace("+00:00", "Z"),
                    last_seen=last_dt.isoformat().replace("+00:00", "Z"),
                    source_type=dominant_source,
                    risk_score=primary.risk_score,
                    risk_level=primary.risk_level,
                    peak_frp=peak_frp,
                    average_frp=avg_frp,
                    is_anomaly=has_anomaly,
                    status=status,
                    primary_hotspot=primary,
                )
            )

        incidents.sort(key=lambda inc: (-inc.risk_score, -inc.peak_frp, inc.incident_id))
        return incidents
