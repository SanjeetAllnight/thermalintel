"""Enrichment subsystem for ThermalIntel.

Provides multi-source contextual enrichment for satellite thermal anomalies:
- OpenStreetMap Overpass critical infrastructure & proximity analysis
- Open-Meteo hyperlocal atmospheric observations & fire weather ratings
- Historical detection persistence & recurrence modeling
- Resilient file-backed caching
"""

from .models import EnrichmentResult, EnrichmentStatus
from .service import EnrichmentService
from .cache import EnrichmentCache, generate_cache_key

__all__ = [
    "EnrichmentResult",
    "EnrichmentStatus",
    "EnrichmentService",
    "EnrichmentCache",
    "generate_cache_key",
]
