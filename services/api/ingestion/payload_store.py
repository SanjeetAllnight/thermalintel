"""Raw Payload Storage Engine for ThermalIntel V2.

Persists raw external API responses (CSV text, JSON payloads) immutably on disk.
Enforces content addressing (SHA-256) so identical payloads yield identical hashes.
Integrates with the frozen RawPayloadMetadata contract.
CRITICAL: Never stores API keys, authentication credentials, or secrets.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Union

from services.api.schemas.v2.common import now_utc_iso
from services.api.schemas.v2.payload import RawPayloadMetadata

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_RAW_DIR = BASE_DIR / "data" / "raw"


class RawPayloadStore:
    """Filesystem-backed content-addressed raw payload store."""

    def __init__(self, raw_dir: Optional[Path] = None):
        self.raw_dir = Path(raw_dir or DEFAULT_RAW_DIR)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create storage root directory if missing."""
        try:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create raw payload directory {self.raw_dir}: {e}")

    def store_payload(
        self,
        content: Union[str, bytes],
        provider: str,
        product: str,
        content_type: str = "text/csv",
        fetched_at_utc: Optional[str] = None,
        retention_days: int = 90,
    ) -> RawPayloadMetadata:
        """Store raw payload bytes immutably using SHA-256 content addressing.
        
        Returns:
            Validated RawPayloadMetadata model matching the frozen V2 contract.
        """
        self._ensure_dir()
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)
        fetched_at = fetched_at_utc or now_utc_iso()

        # Partition directory by provider for clean filesystem organization
        safe_provider = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in provider.lower())
        provider_dir = self.raw_dir / safe_provider
        provider_dir.mkdir(parents=True, exist_ok=True)

        ext = "csv" if "csv" in content_type else "json" if "json" in content_type else "txt"
        file_path = provider_dir / f"{content_hash}.{ext}"

        # Write atomically if not already present (immutable deduplication)
        if not file_path.is_file():
            temp_path = file_path.with_suffix(f".{content_hash[:8]}.tmp")
            try:
                with open(temp_path, "wb") as f:
                    f.write(content_bytes)
                temp_path.replace(file_path)
            except Exception as e:
                logger.error(f"Failed writing raw payload to {file_path}: {e}")
                if temp_path.exists():
                    temp_path.unlink()
                raise

        payload_id = f"PAYLOAD-{content_hash[:16].upper()}"

        return RawPayloadMetadata(
            payload_id=payload_id,
            provider=provider,
            product=product,
            fetched_at_utc=fetched_at,
            content_hash=content_hash,
            storage_path=str(file_path),
            content_type=content_type,
            size_bytes=size_bytes,
            retention_days=retention_days,
        )

    def read_payload(self, storage_path: str) -> Optional[bytes]:
        """Read raw payload bytes from storage path."""
        p = Path(storage_path)
        if not p.is_file():
            return None
        try:
            return p.read_bytes()
        except Exception as e:
            logger.warning(f"Error reading raw payload from {storage_path}: {e}")
            return None

    def read_payload_text(self, storage_path: str, encoding: str = "utf-8") -> Optional[str]:
        """Read raw payload as text string."""
        raw_bytes = self.read_payload(storage_path)
        if raw_bytes is None:
            return None
        return raw_bytes.decode(encoding, errors="replace")


# Singleton instance
payload_store = RawPayloadStore()
