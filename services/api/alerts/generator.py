"""Alert generation engine for ThermalIntel Phase 4.

Transforms validated incidents, hotspots, and intelligence evaluations into
evidence-based operational alerts for the command-center feed.
"""

from typing import List, Optional, Union
from datetime import datetime, timezone

from services.api.schemas.alert import Alert
from services.api.schemas.common import AlertSeverity, RiskLevel, SourceType
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import IncidentDetail
from services.api.incidents.models import AggregatedIncident
from services.api.alerts.deduplication import AlertDeduplicator


class AlertGenerator:
    """Evaluates thermal events against operational thresholds to generate structured alerts."""

    def __init__(self, include_medium: bool = False):
        """Initialize generator.
        
        Args:
            include_medium: If True, also generates informational/advisory alerts for medium risk events.
        """
        self.include_medium = include_medium
        self.deduplicator = AlertDeduplicator()

    def generate_from_hotspot(
        self,
        hotspot: Hotspot,
        detail: Optional[IncidentDetail] = None,
    ) -> Optional[Alert]:
        """Generate an Alert from a Hotspot, utilizing IncidentDetail context if available."""
        # Risk threshold evaluation
        if hotspot.risk_level == RiskLevel.CRITICAL or hotspot.risk_score >= 75.0:
            severity = AlertSeverity.CRITICAL
        elif hotspot.risk_level == RiskLevel.HIGH or hotspot.risk_score >= 50.0:
            severity = AlertSeverity.WARNING
        elif self.include_medium and (hotspot.risk_level == RiskLevel.MEDIUM or hotspot.risk_score >= 25.0):
            severity = AlertSeverity.INFO
        else:
            # Low risk or non-alertable events do not generate alerts
            return None

        alert_id = self.deduplicator.generate_alert_id(hotspot.id)
        location = hotspot.nearest_place or f"Coordinates ({round(hotspot.latitude, 3)}, {round(hotspot.longitude, 3)})"
        timestamp = hotspot.last_updated or datetime.now(timezone.utc).isoformat()

        # Build evidence-based title and message
        title, message, tags = self._synthesize_content(hotspot, detail, severity, location)

        # Recommended action preservation
        if detail and detail.intelligence and detail.intelligence.risk and detail.intelligence.risk.recommended_action:
            action = detail.intelligence.risk.recommended_action
        elif severity == AlertSeverity.CRITICAL:
            action = "Dispatch immediate field reconnaissance unit; coordinate evacuation staging and perimeter defense."
        elif severity == AlertSeverity.WARNING:
            action = "Monitor sector progression via next orbital satellite pass and notify regional dispatch."
        else:
            action = "Log baseline detection in thermal surveillance catalog."

        return Alert(
            id=alert_id,
            hotspot_id=hotspot.id,
            severity=severity,
            title=title,
            message=message,
            risk_score=round(hotspot.risk_score, 1),
            location_name=location,
            latitude=hotspot.latitude,
            longitude=hotspot.longitude,
            timestamp=timestamp,
            is_acknowledged=False,
            recommended_action=action,
            tags=tags,
        )

    def generate_from_incident(self, incident: AggregatedIncident) -> Optional[Alert]:
        """Generate an Alert from an AggregatedIncident."""
        if incident.primary_hotspot:
            alert = self.generate_from_hotspot(incident.primary_hotspot)
            if alert:
                # Update with aggregated metrics
                return alert.model_copy(
                    update={
                        "risk_score": round(incident.risk_score, 1),
                        "latitude": incident.latitude,
                        "longitude": incident.longitude,
                        "location_name": incident.nearest_place or alert.location_name,
                    }
                )
            return None

        # Fallback if primary_hotspot object not attached
        if incident.risk_level == RiskLevel.CRITICAL or incident.risk_score >= 75.0:
            severity = AlertSeverity.CRITICAL
        elif incident.risk_level == RiskLevel.HIGH or incident.risk_score >= 50.0:
            severity = AlertSeverity.WARNING
        elif self.include_medium and incident.risk_level == RiskLevel.MEDIUM:
            severity = AlertSeverity.INFO
        else:
            return None

        alert_id = self.deduplicator.generate_alert_id(incident.incident_id)
        location = incident.nearest_place or f"Coordinates ({round(incident.latitude, 3)}, {round(incident.longitude, 3)})"
        timestamp = incident.last_seen

        title = f"{severity.value.upper()}: {incident.source_type.value.replace('_', ' ').title()} - {location}"
        message = f"Aggregated {incident.detection_count} detection(s) with peak FRP of {incident.peak_frp} MW."
        tags = [incident.source_type.value, "aggregated_incident"]
        if incident.peak_frp >= 100.0:
            tags.append("critical_frp")

        return Alert(
            id=alert_id,
            hotspot_id=incident.primary_hotspot_id,
            severity=severity,
            title=title,
            message=message,
            risk_score=round(incident.risk_score, 1),
            location_name=location,
            latitude=incident.latitude,
            longitude=incident.longitude,
            timestamp=timestamp,
            is_acknowledged=False,
            recommended_action="Initiate operational monitoring for aggregated cluster area.",
            tags=tags,
        )

    def _synthesize_content(
        self,
        hotspot: Hotspot,
        detail: Optional[IncidentDetail],
        severity: AlertSeverity,
        location: str,
    ) -> tuple[str, str, List[str]]:
        """Synthesize evidence-driven headline, explanatory message, and tags."""
        tags = [hotspot.source_type.value]
        source_label = hotspot.source_type.value.replace("_", " ").title()

        # Check contextual factors
        dist_settlement: Optional[float] = None
        wind_gust: Optional[float] = None
        wind_speed: Optional[float] = None
        wind_cardinal: Optional[str] = None
        humidity: Optional[float] = None

        if detail and detail.geospatial:
            dist_settlement = detail.geospatial.distance_to_settlement_meters
            if detail.geospatial.is_protected_area:
                tags.append("protected_area")

        if detail and detail.weather:
            wind_speed = detail.weather.wind_speed_kmh
            wind_gust = detail.weather.wind_gust_kmh or detail.weather.wind_speed_kmh
            wind_cardinal = detail.weather.wind_direction_cardinal
            humidity = detail.weather.relative_humidity_percent

        if hotspot.frp >= 100.0:
            tags.append("critical_frp")
        if hotspot.is_anomaly:
            tags.append("statistical_anomaly")
        if dist_settlement and dist_settlement <= 2000.0:
            tags.append("settlement_proximity")
        if wind_speed and wind_speed >= 30.0:
            tags.append("high_wind")

        # Title formatting
        if severity == AlertSeverity.CRITICAL:
            if hotspot.source_type == SourceType.WILDFIRE:
                if dist_settlement and dist_settlement <= 2000.0:
                    title = f"Rapid Convective Flare & Settlement Threat - {location}"
                else:
                    title = f"High-Intensity Canopy Wildfire Detected - {location}"
            elif hotspot.source_type == SourceType.INDUSTRIAL:
                title = f"Unusual High-Radiance Industrial Surge - {location}"
            elif hotspot.source_type == SourceType.VOLCANIC:
                title = f"Major Volcanic Effusion & Thermal Outlier - {location}"
            else:
                title = f"Critical Thermal Anomaly - {location}"
        elif severity == AlertSeverity.WARNING:
            if hotspot.source_type == SourceType.WILDFIRE:
                title = f"Active Thermal Anomaly in Wildland Area - {location}"
            elif hotspot.source_type == SourceType.INDUSTRIAL:
                title = f"Elevated Thermal Stack Radiance - {location}"
            elif hotspot.source_type == SourceType.VOLCANIC:
                title = f"Elevated Effusive Thermal Activity - {location}"
            else:
                title = f"High-Risk {source_label} Detected - {location}"
        else:
            title = f"Notice: {source_label} Under Surveillance - {location}"

        # Message formatting: Evidence-based explanation
        parts = [f"FRP measured at {hotspot.frp} MW."]
        if dist_settlement:
            dist_km = round(dist_settlement / 1000.0, 1)
            parts.append(f"Located {dist_km} km from {detail.geospatial.nearest_settlement or 'settlement area'}.")
        if wind_speed:
            wind_desc = f"{wind_speed} km/h"
            if wind_cardinal:
                wind_desc += f" {wind_cardinal}"
            if wind_gust and wind_gust > wind_speed:
                wind_desc += f" (gusts {wind_gust} km/h)"
            parts.append(f"Winds recorded at {wind_desc}.")
        if humidity is not None and humidity <= 20.0:
            parts.append(f"Critically dry relative humidity ({humidity}%).")

        message = " ".join(parts)
        return title, message, tags
