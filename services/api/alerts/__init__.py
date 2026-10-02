"""ThermalIntel Phase 4 & V2 Alert Subsystem.

Provides:
- Evidence-based alert generation (AlertGenerator)
- Alert prioritization and ranking (AlertPriorityComparator)
- Deterministic deduplication (AlertDeduplicator)
- Transition-driven rules engine (AlertRule, TransitionContext, get_default_rules)
- Cooldown and flood protection (FloodProtectionEngine, FloodProtectionConfig)
- Operational alert health telemetry (AlertHealthMetrics, ChatteringIncident, compute_health_from_alerts)
- SQLite persistent repository (AlertV2Repository)
- Complete alert management service (AlertService)
"""

from services.api.alerts.priority import (
    AlertPriorityComparator,
    alert_priority_key,
    alert_v2_priority_key,
)
from services.api.alerts.deduplication import AlertDeduplicator
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.rules import (
    AlertRule,
    TransitionContext,
    NewIncidentRule,
    EscalatedIncidentRule,
    DeescalatedIncidentRule,
    ReopenedIncidentRule,
    ClosedIncidentRule,
    ExtremeFrpRule,
    get_default_rules,
)
from services.api.alerts.cooldown import (
    FloodProtectionEngine,
    FloodProtectionConfig,
    FloodProtectionDecision,
)
from services.api.alerts.health import (
    AlertHealthMetrics,
    ChatteringIncident,
    compute_health_from_alerts,
)
from services.api.alerts.repository import AlertV2Repository
from services.api.alerts.service import AlertService

__all__ = [
    "AlertPriorityComparator",
    "alert_priority_key",
    "alert_v2_priority_key",
    "AlertDeduplicator",
    "AlertGenerator",
    "AlertRule",
    "TransitionContext",
    "NewIncidentRule",
    "EscalatedIncidentRule",
    "DeescalatedIncidentRule",
    "ReopenedIncidentRule",
    "ClosedIncidentRule",
    "ExtremeFrpRule",
    "get_default_rules",
    "FloodProtectionEngine",
    "FloodProtectionConfig",
    "FloodProtectionDecision",
    "AlertHealthMetrics",
    "ChatteringIncident",
    "compute_health_from_alerts",
    "AlertV2Repository",
    "AlertService",
]
