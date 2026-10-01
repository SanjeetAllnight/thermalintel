"""ThermalIntel Phase 4 Summary & Analytics Subsystem.

Provides:
- Dashboard KPI analytics & calculations (SummaryAnalytics)
- Source breakdown & risk distribution (SummaryAnalytics.compute_source_breakdown)
- Complete summary service (SummaryService)
"""

from services.api.summary.analytics import (
    SummaryAnalytics,
    SOURCE_METADATA,
)
from services.api.summary.service import SummaryService

__all__ = [
    "SummaryAnalytics",
    "SOURCE_METADATA",
    "SummaryService",
]
