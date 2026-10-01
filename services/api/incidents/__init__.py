"""ThermalIntel Phase 4 Incident Subsystem.

Provides:
- Incident aggregation and deduplication (IncidentAggregator)
- Operational incident models (AggregatedIncident, IncidentStatus)
- Dossier synthesis service (IncidentService)
- Adapters for SQLite and in-memory test fixtures
"""

from services.api.incidents.models import (
    IncidentStatus,
    AggregatedIncident,
)
from services.api.incidents.aggregator import (
    IncidentAggregator,
    haversine_distance_km,
)
from services.api.incidents.adapters import (
    SQLiteIncidentAdapter,
    InMemoryIncidentAdapter,
)
from services.api.incidents.service import IncidentService

__all__ = [
    "IncidentStatus",
    "AggregatedIncident",
    "IncidentAggregator",
    "haversine_distance_km",
    "SQLiteIncidentAdapter",
    "InMemoryIncidentAdapter",
    "IncidentService",
]
