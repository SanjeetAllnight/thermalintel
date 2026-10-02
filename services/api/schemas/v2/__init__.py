"""ThermalIntel V2 Canonical Domain Contracts and Schemas.

Establishes the foundational entities for ThermalIntel V2:
- Observation (pure provider evidence)
- Enrichment (contextual data with independent provenance)
- Assessment (reproducible intelligence inference results)
- Incident (persistent real-world events with stable identity)
- IncidentObservation (N:M associative relationship)
- IncidentEvent (immutable append-only audit timeline)
- AlertV2 (stateful hazard notifications with deduplication)
- ProviderRun (audit telemetry for external ingestion runs)
- RawPayloadMetadata (immutable raw provider storage metadata)
"""

from .common import (
    SourceType,
    RiskLevel,
    AlertSeverity,
    AlertState,
    IncidentStatus,
    IncidentEventType,
    FreshnessState,
    ProviderStatus,
    EnrichmentType,
    Coordinates,
    RiskFactor,
    Provenance,
    ConfidenceBreakdown,
    now_utc_iso,
)

from .observation import Observation

from .enrichment import (
    EnrichmentDatum,
    GeospatialEnrichment,
    WeatherEnrichment,
    HistoricalEnrichment,
    TerrainEnrichment,
    EnrichmentSnapshot,
)

from .assessment import (
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
    Assessment,
)

from .incident import (
    Incident,
    IncidentObservation,
)

from .event import (
    IncidentEvent,
)

from .alert import (
    AlertV2,
)

from .provider import (
    ProviderRun,
)

from .payload import (
    RawPayloadMetadata,
)

from .converters import (
    row_to_hotspot_canonical,
    observation_from_hotspot,
    hotspot_from_v2,
)

__all__ = [
    # Common Enums & Models
    "SourceType",
    "RiskLevel",
    "AlertSeverity",
    "AlertState",
    "IncidentStatus",
    "IncidentEventType",
    "FreshnessState",
    "ProviderStatus",
    "EnrichmentType",
    "Coordinates",
    "RiskFactor",
    "Provenance",
    "ConfidenceBreakdown",
    "now_utc_iso",
    # Core Domain Entities
    "Observation",
    "EnrichmentDatum",
    "GeospatialEnrichment",
    "WeatherEnrichment",
    "HistoricalEnrichment",
    "TerrainEnrichment",
    "EnrichmentSnapshot",
    "ClassificationAssessment",
    "AnomalyAssessment",
    "RiskAssessmentResult",
    "DataQualityAssessment",
    "AssessmentMethodology",
    "Assessment",
    "Incident",
    "IncidentObservation",
    "IncidentEvent",
    "AlertV2",
    "ProviderRun",
    "RawPayloadMetadata",
    # Shared Converters
    "row_to_hotspot_canonical",
    "observation_from_hotspot",
    "hotspot_from_v2",
]
