"""ThermalIntel Incident Subsystem (Phase 4 & V2 Persistent Engine).

Provides:
- Incident aggregation and clustering (IncidentAggregator, haversine_distance_km)
- Persistent incident engine with stable identity and correlation (IncidentEngine)
- Canonical SQLite & in-memory repositories (IncidentRepository, InMemoryIncidentRepository)
- Operational and V2 models (Incident, IncidentObservation, IncidentEvent, AggregatedIncident, IncidentStatus, CorrelationResult, IncidentHistory)
- Dossier synthesis and lifecycle management service (IncidentService)
- Adapters for SQLite and in-memory test fixtures (SQLiteIncidentAdapter, InMemoryIncidentAdapter)
"""

from services.api.incidents.models import (
    IncidentStatus,
    AggregatedIncident,
    CorrelationResult,
    IncidentHistory,
    Incident,
    IncidentObservation,
    IncidentEvent,
)
from services.api.incidents.aggregator import (
    IncidentAggregator,
    haversine_distance_km,
    parse_hotspot_datetime,
    parse_observation_datetime,
)
from services.api.incidents.repository import (
    IncidentRepository,
    InMemoryIncidentRepository,
)
from services.api.incidents.engine import (
    IncidentEngine,
    generate_stable_incident_id,
    generate_event_id,
)
from services.api.incidents.adapters import (
    SQLiteIncidentAdapter,
    InMemoryIncidentAdapter,
)
from services.api.incidents.service import IncidentService

__all__ = [
    "IncidentStatus",
    "AggregatedIncident",
    "CorrelationResult",
    "IncidentHistory",
    "Incident",
    "IncidentObservation",
    "IncidentEvent",
    "IncidentAggregator",
    "haversine_distance_km",
    "parse_hotspot_datetime",
    "parse_observation_datetime",
    "IncidentRepository",
    "InMemoryIncidentRepository",
    "IncidentEngine",
    "generate_stable_incident_id",
    "generate_event_id",
    "SQLiteIncidentAdapter",
    "InMemoryIncidentAdapter",
    "IncidentService",
]
