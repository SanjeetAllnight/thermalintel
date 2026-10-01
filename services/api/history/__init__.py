"""Historical recurrence and persistence package for ThermalIntel.

Exports the recurrence analyzer and result schemas.
"""

from .recurrence import (
    HistoricalRecurrenceAnalyzer,
    HistoricalAnalysisResult,
    DEFAULT_SPATIAL_RADIUS_METERS,
    DEFAULT_WINDOW_30D,
    DEFAULT_WINDOW_90D,
)

__all__ = [
    "HistoricalRecurrenceAnalyzer",
    "HistoricalAnalysisResult",
    "DEFAULT_SPATIAL_RADIUS_METERS",
    "DEFAULT_WINDOW_30D",
    "DEFAULT_WINDOW_90D",
]
