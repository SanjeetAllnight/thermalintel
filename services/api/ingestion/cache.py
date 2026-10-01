"""Local ephemeral cache for raw and normalized satellite thermal anomaly data."""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Any

from services.api.ingestion.config import config, IngestionConfig

logger = logging.getLogger(__name__)


class DataCache:
    """Manages file-based local caching for external API responses."""

    def __init__(self, cache_dir: Optional[Path] = None, default_ttl: Optional[int] = None):
        self.cache_dir = Path(cache_dir or config.cache_dir)
        self.default_ttl = default_ttl or config.cache_ttl_seconds
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it does not exist."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create cache directory {self.cache_dir}: {e}")

    def make_key(self, prefix: str, **kwargs: Any) -> str:
        """Generate a deterministic, filesystem-safe cache key from parameters."""
        sorted_items = sorted((str(k), str(v)) for k, v in kwargs.items() if v is not None)
        key_str = f"{prefix}_" + "_".join(f"{k}={v}" for k, v in sorted_items)
        # Hash to avoid filesystem naming issues with special characters / coords
        hash_digest = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]
        safe_prefix = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in prefix)
        return f"{safe_prefix}_{hash_digest}"

    def _entry_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str, max_age_seconds: Optional[int] = None) -> Optional[str]:
        """Retrieve cached text content if present and unexpired.
        
        Returns:
            Cached payload string if valid, or None if expired/corrupted/missing.
        """
        path = self._entry_path(key)
        if not path.is_file():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)

            cached_at = entry.get("timestamp", 0)
            ttl = entry.get("ttl", self.default_ttl)
            effective_ttl = max_age_seconds if max_age_seconds is not None else ttl

            # Check expiration
            if time.time() - cached_at > effective_ttl:
                logger.debug(f"Cache expired for key: {key}")
                return None

            payload = entry.get("payload")
            if payload is None:
                return None
            return str(payload)
        except Exception as e:
            logger.warning(f"Error reading cache entry {path}: {e}")
            return None

    def set(self, key: str, payload: str, ttl_seconds: Optional[int] = None) -> bool:
        """Store text payload in cache with timestamp and TTL.
        
        Returns:
            True if successfully cached, False otherwise.
        """
        self._ensure_cache_dir()
        path = self._entry_path(key)
        entry = {
            "key": key,
            "timestamp": time.time(),
            "ttl": ttl_seconds or self.default_ttl,
            "payload": payload,
        }
        try:
            # Write to a temporary file then replace atomically
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(entry, f)
            temp_path.replace(path)
            return True
        except Exception as e:
            logger.warning(f"Failed to write cache entry {path}: {e}")
            return False

    def is_valid(self, key: str, max_age_seconds: Optional[int] = None) -> bool:
        """Check whether a cache entry exists and is not expired."""
        return self.get(key, max_age_seconds=max_age_seconds) is not None

    def clear(self, key: Optional[str] = None) -> int:
        """Clear a specific cache entry, or all cache entries if key is None.
        
        Returns:
            Number of files removed.
        """
        count = 0
        if key is not None:
            path = self._entry_path(key)
            if path.is_file():
                try:
                    path.unlink()
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {path}: {e}")
            return count

        # Clear all cache json files
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"Failed to remove cache file {p}: {e}")
        return count


# Default singleton instance
cache = DataCache()
