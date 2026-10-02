"""Quarantine subsystem for invalid and malformed satellite observation records.

Ensures that invalid source records do not silently disappear. Stores structured
forensic records on the filesystem for auditability, telemetry, and debugging.
CRITICAL: Never stores API keys, authentication credentials, or secrets.
"""

import json
import logging
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Base directory for quarantine records
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_QUARANTINE_DIR = BASE_DIR / "data" / "quarantine"


@dataclass
class QuarantineRecord:
    """Audit record for a single rejected source row."""
    quarantine_id: str
    provider: str
    product: str
    run_id: str
    rejection_reason: str
    source_row: Dict[str, Any]
    timestamp_utc: str


class QuarantineManager:
    """Manages filesystem-backed structured quarantine storage."""

    def __init__(self, quarantine_dir: Optional[Path] = None):
        self.quarantine_dir = Path(quarantine_dir or DEFAULT_QUARANTINE_DIR)
        self.records_file = self.quarantine_dir / "quarantine_records.jsonl"
        self._in_memory: List[QuarantineRecord] = []
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure quarantine storage directory exists."""
        try:
            self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create quarantine directory {self.quarantine_dir}: {e}")

    @staticmethod
    def sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """Defensively remove credential-like fields from raw dictionary."""
        prohibited = ("key", "secret", "token", "auth", "password")
        clean: Dict[str, Any] = {}
        for k, v in row.items():
            if k is None:
                continue
            lower_k = str(k).lower()
            if any(sub in lower_k for sub in prohibited):
                continue
            clean[str(k)] = v
        return clean

    def quarantine(
        self,
        provider: str,
        product: str,
        run_id: str,
        reason: str,
        row: Dict[str, Any],
        timestamp_utc: Optional[str] = None,
    ) -> QuarantineRecord:
        """Quarantine a rejected record with reason and sanitized evidence."""
        self._ensure_dir()
        safe_row = self.sanitize_row(row)
        ts = timestamp_utc or datetime.now(timezone.utc).isoformat()

        # Deterministic quarantine record ID derived from run, reason, and content
        evidence_str = f"{provider}|{product}|{run_id}|{reason}|{sorted(safe_row.items())}"
        digest = hashlib.sha256(evidence_str.encode("utf-8")).hexdigest()[:12].upper()
        qid = f"QR-{digest}"

        record = QuarantineRecord(
            quarantine_id=qid,
            provider=provider,
            product=product,
            run_id=run_id,
            rejection_reason=reason,
            source_row=safe_row,
            timestamp_utc=ts,
        )

        self._in_memory.append(record)

        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append quarantine record to {self.records_file}: {e}")

        logger.info(f"Quarantined record {qid}: {reason}")
        return record

    def get_records(self, run_id: Optional[str] = None) -> List[QuarantineRecord]:
        """Retrieve quarantined records, optionally filtered by ingestion run_id."""
        if self._in_memory:
            if run_id:
                return [r for r in self._in_memory if r.run_id == run_id]
            return list(self._in_memory)

        if not self.records_file.is_file():
            return []

        records: List[QuarantineRecord] = []
        try:
            with open(self.records_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    rec = QuarantineRecord(**data)
                    if run_id is None or rec.run_id == run_id:
                        records.append(rec)
        except Exception as e:
            logger.warning(f"Error reading quarantine file {self.records_file}: {e}")

        return records

    def count(self, run_id: Optional[str] = None) -> int:
        """Count quarantined records."""
        return len(self.get_records(run_id=run_id))

    def clear(self) -> int:
        """Clear all quarantine records in-memory and on disk."""
        cnt = len(self._in_memory)
        self._in_memory.clear()
        if self.records_file.is_file():
            try:
                self.records_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete quarantine file: {e}")
        return cnt


# Singleton instance
quarantine_manager = QuarantineManager()
