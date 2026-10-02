"""Canonical Raw Payload Contract for ThermalIntel V2.

Represents immutable metadata for stored raw provider responses (CSV text, JSON payloads)
persisted on disk or in object storage for forensic auditing and historical replay.
"""

from typing import Optional
from pydantic import BaseModel, Field
from .common import now_utc_iso


class RawPayloadMetadata(BaseModel):
    """Metadata tracking an immutable raw provider response payload."""
    payload_id: str = Field(..., description="Unique payload identifier (e.g. 'PAYLOAD-20261001-085000-FIRMS')")
    provider: str = Field(..., description="Provider organization name")
    product: str = Field(..., description="Data product or query endpoint")
    fetched_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when raw response was received")
    content_hash: str = Field(..., description="SHA-256 hexadecimal checksum of payload bytes for integrity verification")
    storage_path: str = Field(..., description="Local filesystem path or object storage URI referencing the raw file")
    content_type: str = Field(..., description="MIME content type (e.g. 'text/csv', 'application/json')")
    size_bytes: int = Field(..., ge=0, description="Payload content size in bytes")
    retention_days: Optional[int] = Field(default=90, ge=1, description="Audit retention lifespan in days before archival/purge")
