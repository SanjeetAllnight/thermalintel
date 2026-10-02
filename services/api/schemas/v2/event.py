"""Canonical Incident Event Contract for ThermalIntel V2.

Defines an immutable, append-only audit event log representing the full
lifecycle timeline of an incident.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from .common import IncidentEventType, now_utc_iso


class IncidentEvent(BaseModel):
    """Immutable, append-only timeline event for an incident.
    
    Rules:
    - Events are strictly append-only: once written, they are never updated or deleted.
    - Timestamp is strictly UTC and represents when the transition occurred.
    - Forms the chronological source of truth for the incident timeline.
    """
    event_id: str = Field(..., description="Unique event identifier (e.g. 'EVT-20261001-0001')")
    incident_id: str = Field(..., description="Foreign key to the associated Incident")
    event_type: IncidentEventType = Field(..., description="Standardized event lifecycle classification")
    timestamp_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when the event occurred")
    actor: str = Field(
        default="system_correlator",
        description="Originator of the event (e.g. 'system_correlator', 'intelligence_engine', 'operator_jane', 'api_client')"
    )
    reason: str = Field(..., description="Human or algorithmic explanation of why this event was triggered")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured context and state delta payload (e.g. delta FRP, observation IDs, old/new severity)"
    )
