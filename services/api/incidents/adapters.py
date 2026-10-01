"""Integration adapters and provider protocols for Phase 4 Incidents.

Provides clean decoupled abstractions so the IncidentService can consume:
- Hotspots (Agent 1)
- Contextual enrichment (Agent 2)
- Intelligence evaluation (Agent 3)
without direct code coupling across unmerged branches.
"""

import json
from typing import Protocol, Optional, List, Dict, Any, Tuple
import sqlite3

from services.api.schemas.hotspot import Hotspot
from services.api.schemas.incident import (
    GeospatialContext,
    WeatherContext,
    HistoricalContext,
    TimelineEvent,
)
from services.api.schemas.intelligence import IntelligenceResult
from services.api.schemas.common import DataMode, RiskLevel, SourceType


class HotspotProviderProtocol(Protocol):
    """Protocol for fetching normalized satellite hotspots."""

    def get_hotspot_by_id(self, hotspot_id: str) -> Optional[Hotspot]:
        """Fetch a single normalized hotspot by ID."""
        ...

    def list_hotspots(self) -> List[Hotspot]:
        """Fetch all active normalized hotspots."""
        ...


class EnrichmentProviderProtocol(Protocol):
    """Protocol for fetching geospatial, weather, and historical enrichment."""

    def get_enrichment(
        self, hotspot_id: str
    ) -> Optional[Tuple[GeospatialContext, WeatherContext, HistoricalContext]]:
        """Fetch enrichment contexts for a given hotspot."""
        ...


class IntelligenceProviderProtocol(Protocol):
    """Protocol for fetching ML classification, anomaly, and risk evaluation."""

    def get_intelligence(self, hotspot_id: str) -> Optional[IntelligenceResult]:
        """Fetch intelligence evaluation for a given hotspot."""
        ...


class SQLiteIncidentAdapter:
    """SQLite-backed adapter reading from the established Phase 0 tables."""

    def __init__(self, connection_factory):
        """Initialize with a callable returning an open sqlite3.Connection with Row factory."""
        self.connection_factory = connection_factory

    def get_hotspot_by_id(self, hotspot_id: str) -> Optional[Hotspot]:
        with self.connection_factory() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hotspots WHERE id = ?", (hotspot_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_hotspot(row)

    def list_hotspots(self) -> List[Hotspot]:
        with self.connection_factory() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hotspots")
            rows = cursor.fetchall()
            return [self._row_to_hotspot(r) for r in rows]

    def get_incident_detail_data(
        self, hotspot_id: str
    ) -> Optional[
        Tuple[
            GeospatialContext,
            WeatherContext,
            HistoricalContext,
            IntelligenceResult,
            List[TimelineEvent],
        ]
    ]:
        with self.connection_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM incident_details WHERE hotspot_id = ?", (hotspot_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            geospatial = GeospatialContext(**json.loads(row["geospatial_json"]))
            weather = WeatherContext(**json.loads(row["weather_json"]))
            historical = HistoricalContext(**json.loads(row["historical_json"]))
            intelligence = IntelligenceResult(**json.loads(row["intelligence_json"]))
            raw_timeline = json.loads(row["timeline_json"])
            timeline = [TimelineEvent(**t) for t in raw_timeline]
            return geospatial, weather, historical, intelligence, timeline

    def get_data_mode(self) -> DataMode:
        try:
            with self.connection_factory() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
                row = cursor.fetchone()
                if row and row["value"] == "live":
                    return DataMode.LIVE
        except Exception:
            pass
        return DataMode.DEMO

    @staticmethod
    def _row_to_hotspot(r: sqlite3.Row) -> Hotspot:
        return Hotspot(
            id=r["id"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            brightness=r["brightness"],
            scan=r["scan"] if "scan" in r.keys() and r["scan"] is not None else 0.375,
            track=r["track"] if "track" in r.keys() and r["track"] is not None else 0.375,
            acq_date=r["acq_date"],
            acq_time=r["acq_time"],
            satellite=r["satellite"],
            instrument=r["instrument"] if "instrument" in r.keys() and r["instrument"] else "VIIRS",
            confidence=r["confidence"],
            version=r["version"] if "version" in r.keys() and r["version"] else "2.0NRT",
            bright_t31=r["bright_t31"] if "bright_t31" in r.keys() else None,
            frp=r["frp"],
            daynight=r["daynight"],
            source_type=SourceType(r["source_type"]),
            risk_score=r["risk_score"],
            risk_level=RiskLevel(r["risk_level"]),
            is_anomaly=bool(r["is_anomaly"]),
            cluster_id=r["cluster_id"] if "cluster_id" in r.keys() else None,
            cluster_size=r["cluster_size"] if "cluster_size" in r.keys() and r["cluster_size"] else 1,
            nearest_place=r["nearest_place"] if "nearest_place" in r.keys() else None,
            last_updated=r["last_updated"],
        )


class InMemoryIncidentAdapter:
    """In-memory mock adapter for decoupled unit tests and standalone verification."""

    def __init__(self):
        self.hotspots: Dict[str, Hotspot] = {}
        self.details: Dict[str, Dict[str, Any]] = {}
        self.data_mode: DataMode = DataMode.DEMO

    def add_hotspot(self, hotspot: Hotspot):
        self.hotspots[hotspot.id] = hotspot

    def add_detail(
        self,
        hotspot_id: str,
        geospatial: GeospatialContext,
        weather: WeatherContext,
        historical: HistoricalContext,
        intelligence: IntelligenceResult,
        timeline: Optional[List[TimelineEvent]] = None,
    ):
        self.details[hotspot_id] = {
            "geospatial": geospatial,
            "weather": weather,
            "historical": historical,
            "intelligence": intelligence,
            "timeline": timeline or [],
        }

    def get_hotspot_by_id(self, hotspot_id: str) -> Optional[Hotspot]:
        return self.hotspots.get(hotspot_id)

    def list_hotspots(self) -> List[Hotspot]:
        return list(self.hotspots.values())

    def get_incident_detail_data(
        self, hotspot_id: str
    ) -> Optional[
        Tuple[
            GeospatialContext,
            WeatherContext,
            HistoricalContext,
            IntelligenceResult,
            List[TimelineEvent],
        ]
    ]:
        d = self.details.get(hotspot_id)
        if not d:
            return None
        return (
            d["geospatial"],
            d["weather"],
            d["historical"],
            d["intelligence"],
            d["timeline"],
        )

    def get_data_mode(self) -> DataMode:
        return self.data_mode
