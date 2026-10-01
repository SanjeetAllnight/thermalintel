"""Historical thermal anomaly recurrence and persistence analyzer.

Computes explainable, deterministic historical context for thermal hotspots:
- Detection count within configurable spatial radius (default 1000m / 1km)
- 30-day and 90-day recurrence windows
- First observed detection date
- Recurrence index and persistence score
- Recurrent pattern classification:
  - 'known_industrial_stack' (high frequency, steady thermal recurrence)
  - 'persistent_burn' (sustained high-intensity multi-day wildland event)
  - 'agricultural_clearing' (seasonal episodic clearing)
  - 'none' (isolated or emergent anomaly)
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Union
from pydantic import BaseModel, Field

from services.api.geospatial.spatial import haversine_distance_meters, validate_coordinates
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import HistoricalContext

logger = logging.getLogger(__name__)

DEFAULT_SPATIAL_RADIUS_METERS = 1000.0
DEFAULT_WINDOW_30D = 30
DEFAULT_WINDOW_90D = 90


class HistoricalAnalysisResult(BaseModel):
    """Rich container for historical analysis metrics."""
    context: HistoricalContext
    persistence_score: float = Field(..., ge=0.0, le=1.0, description="Persistence index (0-1)")
    repeated_activity: bool = Field(..., description="True if multiple detections in past 30 days")
    temporal_span_days: int = Field(default=0, ge=0, description="Span between first and last observation")
    total_detections_in_radius: int = Field(default=0, ge=0, description="Total satellite detections within radius")
    status: str = Field(default="computed", description="'computed', 'empty', or 'unavailable'")


def parse_date(date_val: Union[str, datetime]) -> datetime:
    """Parse a date string or object into a date datetime."""
    if isinstance(date_val, datetime):
        return date_val
    clean_str = str(date_val).strip()
    # Try YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(clean_str[:10], "%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(clean_str)
    except ValueError:
        return datetime.now(timezone.utc)


class HistoricalRecurrenceAnalyzer:
    """Deterministic analyzer of satellite thermal anomaly recurrence."""

    def __init__(
        self,
        spatial_radius_meters: float = DEFAULT_SPATIAL_RADIUS_METERS,
        window_30d: int = DEFAULT_WINDOW_30D,
        window_90d: int = DEFAULT_WINDOW_90D
    ):
        self.spatial_radius_meters = spatial_radius_meters
        self.window_30d = window_30d
        self.window_90d = window_90d

    def _extract_hotspot_props(self, record: Union[Hotspot, Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize hotspot representation into standard dictionary."""
        if isinstance(record, Hotspot):
            return {
                "id": record.id,
                "latitude": record.latitude,
                "longitude": record.longitude,
                "acq_date": record.acq_date,
                "acq_time": record.acq_time,
                "frp": record.frp,
                "brightness": record.brightness
            }
        return {
            "id": str(record.get("id", "")),
            "latitude": float(record["latitude"]),
            "longitude": float(record["longitude"]),
            "acq_date": str(record.get("acq_date", "")),
            "acq_time": str(record.get("acq_time", "")),
            "frp": float(record.get("frp", 0.0)),
            "brightness": float(record.get("brightness", 0.0))
        }

    def analyze(
        self,
        target_hotspot: Union[Hotspot, Dict[str, Any]],
        candidate_history: Optional[Sequence[Union[Hotspot, Dict[str, Any]]]] = None,
        db_connection: Optional[sqlite3.Connection] = None
    ) -> HistoricalAnalysisResult:
        """Perform historical recurrence analysis for a target hotspot.
        
        Args:
            target_hotspot: The hotspot currently undergoing evaluation.
            candidate_history: Optional in-memory sequence of historical Hotspot records.
            db_connection: Optional active SQLite connection to query the hotspots table.
            
        Returns:
            HistoricalAnalysisResult containing the populated HistoricalContext.
        """
        try:
            target = self._extract_hotspot_props(target_hotspot)
            t_lat = target["latitude"]
            t_lon = target["longitude"]
            validate_coordinates(t_lat, t_lon)
            t_date = parse_date(target["acq_date"])
            t_id = target["id"]
        except Exception as e:
            logger.warning("Invalid target hotspot for historical recurrence: %s", e)
            return HistoricalAnalysisResult(
                context=HistoricalContext(
                    prior_detections_30d=0,
                    prior_detections_90d=0,
                    is_recurrent_site=False,
                    recurrent_pattern="none",
                    first_detected_date=None,
                    detection_frequency_score=0.0
                ),
                persistence_score=0.0,
                repeated_activity=False,
                temporal_span_days=0,
                total_detections_in_radius=0,
                status="unavailable"
            )

        # 1. Gather candidate records
        candidates: List[Dict[str, Any]] = []

        if candidate_history is not None:
            for item in candidate_history:
                try:
                    c = self._extract_hotspot_props(item)
                    # Exclude the exact target itself
                    if c["id"] and c["id"] == t_id:
                        continue
                    candidates.append(c)
                except Exception:
                    continue

        elif db_connection is not None:
            # Query database with bounding box rough pre-filter
            # ~0.02 degrees latitude is ~2.2 km
            try:
                cursor = db_connection.cursor()
                cursor.execute("""
                    SELECT id, latitude, longitude, acq_date, acq_time, frp, brightness
                    FROM hotspots
                    WHERE latitude BETWEEN ? AND ?
                      AND longitude BETWEEN ? AND ?
                      AND id != ?
                """, (t_lat - 0.02, t_lat + 0.02, t_lon - 0.02, t_lon + 0.02, t_id))
                for row in cursor.fetchall():
                    candidates.append(dict(row))
            except Exception as e:
                logger.warning("Database query for historical recurrence failed: %s", e)

        # 2. Filter by distance and prior temporal window
        prior_records: List[Tuple[Dict[str, Any], float, int]] = []  # (record, distance, days_ago)

        for c in candidates:
            try:
                c_lat = c["latitude"]
                c_lon = c["longitude"]
                dist = haversine_distance_meters(t_lat, t_lon, c_lat, c_lon)
                if dist > self.spatial_radius_meters:
                    continue

                c_date = parse_date(c["acq_date"])
                delta_days = (t_date - c_date).days

                # Only include detections on or before target date
                if delta_days >= 0:
                    prior_records.append((c, dist, delta_days))
            except Exception:
                continue

        if not prior_records:
            return HistoricalAnalysisResult(
                context=HistoricalContext(
                    prior_detections_30d=0,
                    prior_detections_90d=0,
                    is_recurrent_site=False,
                    recurrent_pattern="none",
                    first_detected_date=None,
                    detection_frequency_score=0.0
                ),
                persistence_score=0.0,
                repeated_activity=False,
                temporal_span_days=0,
                total_detections_in_radius=0,
                status="empty"
            )

        # 3. Compute temporal statistics
        count_30d = sum(1 for _, _, days in prior_records if days <= self.window_30d)
        count_90d = sum(1 for _, _, days in prior_records if days <= self.window_90d)
        total_count = len(prior_records)

        all_dates = [parse_date(rec["acq_date"]) for rec, _, _ in prior_records]
        earliest_date = min(all_dates)
        latest_date = max(all_dates)
        temporal_span = max(0, (latest_date - earliest_date).days)
        first_detected_str = earliest_date.strftime("%Y-%m-%d")

        # 4. Persistence and Recurrence Scoring
        # Frequency score normalized 0.0 - 1.0 (saturates around 20 prior 30d detections)
        raw_freq = (count_30d * 0.05) + (max(0, count_90d - count_30d) * 0.015)
        frequency_score = round(max(0.0, min(1.0, raw_freq)), 2)

        is_recurrent = (count_30d >= 3) or (count_90d >= 6)
        repeated_activity = (count_30d >= 1)

        # Persistence score: ratio of distinct observation days
        distinct_days_30d = len(set(
            parse_date(rec["acq_date"]).strftime("%Y-%m-%d")
            for rec, _, days in prior_records
            if days <= self.window_30d
        ))
        persistence_score = round(min(1.0, distinct_days_30d / 7.0), 2)

        # 5. Explainable Recurrent Pattern Classification
        frp_values = [rec["frp"] for rec, _, days in prior_records if days <= self.window_30d]
        frp_mean = sum(frp_values) / len(frp_values) if frp_values else 0.0

        if count_30d >= 8 and frp_mean < 45.0:
            # Steady low/moderate thermal radiance persistently detected
            pattern = "known_industrial_stack"
        elif count_30d >= 3 and temporal_span <= 5 and (frp_mean >= 45.0 or target["frp"] >= 50.0):
            # Concentrated multi-day intense burn
            pattern = "persistent_burn"
        elif count_30d >= 3 and 10.0 <= frp_mean <= 60.0:
            pattern = "agricultural_clearing"
        elif count_30d >= 2:
            pattern = "persistent_burn"
        else:
            pattern = "none"

        context = HistoricalContext(
            prior_detections_30d=count_30d,
            prior_detections_90d=count_90d,
            is_recurrent_site=is_recurrent,
            recurrent_pattern=pattern,
            first_detected_date=first_detected_str,
            detection_frequency_score=frequency_score
        )

        return HistoricalAnalysisResult(
            context=context,
            persistence_score=persistence_score,
            repeated_activity=repeated_activity,
            temporal_span_days=temporal_span,
            total_detections_in_radius=total_count,
            status="computed"
        )
