"""Raw Payload Metadata Repository for SQLite persistence.

Tracks content hash, storage path, and forensic lineage for raw external responses.
CRITICAL: Never stores API keys, authentication credentials, or secrets.
"""

import logging
import sqlite3
from typing import List, Optional

from services.api.database import get_connection, init_db
from services.api.schemas.v2.payload import RawPayloadMetadata

logger = logging.getLogger(__name__)


def row_to_raw_payload(r: sqlite3.Row) -> RawPayloadMetadata:
    """Convert an SQLite Row to a validated V2 RawPayloadMetadata model."""
    keys = r.keys()
    return RawPayloadMetadata(
        payload_id=r["payload_id"],
        provider=r["provider"],
        product=r["product"],
        fetched_at_utc=r["fetched_at_utc"],
        content_hash=r["content_hash"],
        storage_path=r["storage_path"],
        content_type=r["content_type"],
        size_bytes=int(r["size_bytes"]),
        retention_days=int(r["retention_days"]) if "retention_days" in keys and r["retention_days"] is not None else 90,
    )


class RawPayloadRepository:
    """Repository managing persistence and retrieval for raw payload metadata."""

    def __init__(self):
        init_db()

    def save_payload_metadata(self, meta: RawPayloadMetadata) -> RawPayloadMetadata:
        """Insert or replace a RawPayloadMetadata record."""
        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO raw_payloads (
                        payload_id, provider, product, fetched_at_utc,
                        content_hash, storage_path, content_type,
                        size_bytes, retention_days
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        meta.payload_id,
                        meta.provider,
                        meta.product,
                        meta.fetched_at_utc,
                        meta.content_hash,
                        meta.storage_path,
                        meta.content_type,
                        meta.size_bytes,
                        meta.retention_days,
                    ),
                )
        return meta

    def get_by_id(self, payload_id: str) -> Optional[RawPayloadMetadata]:
        """Fetch raw payload metadata by payload_id."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_payloads WHERE payload_id = ?", (payload_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return row_to_raw_payload(row)

    def get_by_content_hash(self, content_hash: str) -> Optional[RawPayloadMetadata]:
        """Fetch raw payload metadata by content SHA-256 hash."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_payloads WHERE content_hash = ?", (content_hash,))
            row = cursor.fetchone()
            if not row:
                return None
            return row_to_raw_payload(row)

    def count(self) -> int:
        """Count total raw payloads registered."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM raw_payloads")
            return cursor.fetchone()["cnt"]

    def clear(self) -> int:
        """Clear all raw payload metadata from database."""
        with get_connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as cnt FROM raw_payloads")
                cnt = cursor.fetchone()["cnt"]
                cursor.execute("DELETE FROM raw_payloads")
                return cnt


# Singleton instance
raw_payload_repo = RawPayloadRepository()
