"""ThermalIntel Phase 4 Alert Subsystem.

Provides:
- Evidence-based alert generation (AlertGenerator)
- Alert prioritization and ranking (AlertPriorityComparator)
- Deterministic deduplication (AlertDeduplicator)
- Complete alert management service (AlertService)
"""

from services.api.alerts.priority import (
    AlertPriorityComparator,
    alert_priority_key,
)
from services.api.alerts.deduplication import AlertDeduplicator
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.service import AlertService

__all__ = [
    "AlertPriorityComparator",
    "alert_priority_key",
    "AlertDeduplicator",
    "AlertGenerator",
    "AlertService",
]
