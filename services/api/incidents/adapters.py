"""Integration adapters and provider protocols for Phase 4 Incidents & V2 Engine.

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
from services.api.schemas.v2 import row_to_hotspot_canonical
from services.api.incidents.repository import IncidentRepository, InMemoryIncidentRepository


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
    """SQLite-backed adapter reading from established database tables."""

    def __init__(self, connection_factory):
        """Initialize with a callable returning an open sqlite3.Connection with Row factory."""
        self.connection_factory = connection_factory
        self.repository = IncidentRepository(connection_factory=connection_factory)

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
        return row_to_hotspot_canonical(r)


class InMemoryIncidentAdapter:
    """In-memory mock adapter for decoupled unit tests and standalone verification."""

    def __init__(self):
        self.hotspots: Dict[str, Hotspot] = {}
        self.details: Dict[str, Dict[str, Any]] = {}
        self.data_mode: DataMode = DataMode.DEMO
        self.repository = InMemoryIncidentRepository()

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
