"""Local ephemeral cache for raw and normalized satellite thermal anomaly data.

Provides fast response retrieval, graceful offline fallback, and stale-data inspection.
Ensures cache age is knowable, stale data is distinguishable from fresh data, and
stale cache can be used intentionally during provider outages without pretending to be live.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, Dict, Tuple

from services.api.ingestion.config import config, IngestionConfig
from services.api.schemas.v2.common import FreshnessState

logger = logging.getLogger(__name__)


@dataclass
class CacheMetadata:
    """Detailed metadata for a cached payload."""
    key: str
    timestamp: float
    age_seconds: float
    ttl: int
    is_stale: bool
    size_bytes: int


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

    def get_metadata(self, key: str) -> Optional[CacheMetadata]:
        """Inspect cache entry metadata to know its age, TTL, and stale state."""
        path = self._entry_path(key)
        if not path.is_file():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)

            cached_at = entry.get("timestamp", 0)
            ttl = entry.get("ttl", self.default_ttl)
            age = max(0.0, time.time() - cached_at)
            is_stale = age > ttl

            return CacheMetadata(
                key=key,
                timestamp=cached_at,
                age_seconds=round(age, 2),
                ttl=ttl,
                is_stale=is_stale,
                size_bytes=path.stat().st_size,
            )
        except Exception as e:
            logger.warning(f"Error reading cache metadata for {key}: {e}")
            return None

    def get(
        self,
        key: str,
        max_age_seconds: Optional[int] = None,
        allow_stale: bool = False,
    ) -> Optional[str]:
        """Retrieve cached text content if present.
        
        Args:
            key: Cache entry key.
            max_age_seconds: Optional explicit maximum age override.
            allow_stale: If True, return payload even if expired (e.g. for intentional
                         fallback during provider failure).
        
        Returns:
            Cached payload string if valid (or if allow_stale=True and entry exists),
            or None if missing, corrupted, or expired when allow_stale=False.
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
            age = time.time() - cached_at

            # Check expiration
            if age > effective_ttl:
                if not allow_stale:
                    logger.debug(f"Cache expired for key: {key} (age={age:.1f}s > ttl={effective_ttl}s)")
                    return None
                logger.info(f"Serving stale cache for key: {key} (age={age:.1f}s > ttl={effective_ttl}s)")

            payload = entry.get("payload")
            if payload is None:
                return None
            return str(payload)
        except Exception as e:
            logger.warning(f"Error reading cache entry {path}: {e}")
            return None

    def get_with_freshness(
        self,
        key: str,
        max_age_seconds: Optional[int] = None,
    ) -> Tuple[Optional[str], FreshnessState, float]:
        """Retrieve cached payload alongside its explicit FreshnessState and age in seconds.
        
        Returns:
            Tuple of (payload, FreshnessState, age_seconds).
            FreshnessState will be:
            - FRESH / CACHED if unexpired
            - STALE if expired but readable
            - UNAVAILABLE if missing or corrupt
        """
        meta = self.get_metadata(key)
        if not meta:
            return None, FreshnessState.UNAVAILABLE, 0.0

        effective_ttl = max_age_seconds if max_age_seconds is not None else meta.ttl
        is_stale = meta.age_seconds > effective_ttl

        payload = self.get(key, allow_stale=True)
        if payload is None:
            return None, FreshnessState.UNAVAILABLE, meta.age_seconds

        state = FreshnessState.STALE if is_stale else FreshnessState.CACHED
        return payload, state, meta.age_seconds

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
        return self.get(key, max_age_seconds=max_age_seconds, allow_stale=False) is not None

    def is_stale(self, key: str, max_age_seconds: Optional[int] = None) -> bool:
        """Check whether a cache entry exists but is expired."""
        meta = self.get_metadata(key)
        if not meta:
            return False
        effective_ttl = max_age_seconds if max_age_seconds is not None else meta.ttl
        return meta.age_seconds > effective_ttl

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
