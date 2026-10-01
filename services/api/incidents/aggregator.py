"""Incident aggregation and deduplication engine for ThermalIntel Phase 4.

Provides deterministic grouping of proximate thermal detections to prevent
duplicate incidents on the operational dashboard.
"""

import math
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from services.api.schemas.hotspot import Hotspot
from services.api.schemas.common import RiskLevel, SourceType
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
    # First try last_updated if valid ISO string
    if hotspot.last_updated:
        try:
            dt = datetime.fromisoformat(hotspot.last_updated.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass

    # Fallback to acq_date and acq_time
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


class IncidentAggregator:
    """Aggregates and deduplicates raw thermal hotspots into unified operational incidents."""

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
        """Evaluate if two detections represent the same physical thermal event."""
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

        # 5. Classification compatibility (if both are classified, avoid grouping wildly different sources e.g. volcanic vs agricultural)
        incompatible_pairs = {
            (SourceType.VOLCANIC, SourceType.AGRICULTURAL),
            (SourceType.VOLCANIC, SourceType.URBAN),
            (SourceType.INDUSTRIAL, SourceType.WILDFIRE),
        }
        pair = (h1.source_type, h2.source_type)
        reverse_pair = (h2.source_type, h1.source_type)
        if pair in incompatible_pairs or reverse_pair in incompatible_pairs:
            # If classifications conflict strongly, only group if extremely close (< 300 meters)
            if dist_km > 0.3:
                return False

        return True

    def generate_incident_id(self, primary_hotspot: Hotspot) -> str:
        """Derive a stable, deterministic incident identifier."""
        # Format: INC-<hotspot_id>
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
            # Deterministically select primary representative:
            # highest risk_score -> highest FRP -> latest timestamp -> lowest ID
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
            # Primary's source type breaks ties
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
            # If high risk or critical, it's ACTIVE; if low risk and non-anomalous, MONITORING
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
                    first_seen=first_dt.isoformat(),
                    last_seen=last_dt.isoformat(),
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

        # Sort incidents by risk_score descending, then peak_frp descending
        incidents.sort(key=lambda inc: (-inc.risk_score, -inc.peak_frp, inc.incident_id))
        return incidents
