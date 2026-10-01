"""Enrichment Cache manager for ThermalIntel.

Provides resilient, file-backed caching in `data/cache/` for:
- OpenStreetMap Overpass bounding box & radius query results
- Open-Meteo hyperlocal weather snapshots
- Full derived enrichment payloads

Features:
- Deterministic SHA-256 hashing for cache keys
- Configurable TTL (Time-To-Live) per namespace
- Graceful recovery from corrupted or partial cache files
- Stale entry retrieval for offline / network failure fallback
- Non-blocking error handling (cache failure never crashes application)
"""

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cache"
DEFAULT_OSM_TTL = 86400  # 24 hours
DEFAULT_WEATHER_TTL = 3600  # 1 hour
DEFAULT_ENRICHMENT_TTL = 3600  # 1 hour


def generate_cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Generate a deterministic SHA-256 cache key based on inputs.
    
    Args:
        prefix: Namespace or identifier prefix.
        *args: Positional components to hash.
        **kwargs: Keyword components to hash.
        
    Returns:
        Hex-encoded SHA-256 digest string truncated to 32 chars.
    """
    hasher = hashlib.sha256()
    hasher.update(prefix.encode("utf-8"))

    for arg in args:
        if isinstance(arg, float):
            # Round floats to 4 decimal places (~11 meters) to stabilize keys
            hasher.update(f"{arg:.4f}".encode("utf-8"))
        else:
            hasher.update(str(arg).encode("utf-8"))

    for k in sorted(kwargs.keys()):
        val = kwargs[k]
        if isinstance(val, float):
            hasher.update(f"{k}={val:.4f}".encode("utf-8"))
        else:
            hasher.update(f"{k}={val}".encode("utf-8"))

    return hasher.hexdigest()[:32]


class EnrichmentCache:
    """Thread-safe, failure-resilient disk cache for enrichment telemetry."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize the cache with a designated directory."""
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            env_path = os.getenv("ENRICHMENT_CACHE_DIR")
            self.cache_dir = Path(env_path) if env_path else DEFAULT_CACHE_DIR

        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if missing."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Failed to create cache directory %s: %s", self.cache_dir, e)

    def _get_file_path(self, namespace: str, key: str) -> Path:
        """Get file path for given namespace and key."""
        safe_ns = "".join(c for c in namespace if c.isalnum() or c in ("_", "-"))
        safe_key = "".join(c for c in key if c.isalnum() or c in ("_", "-"))
        filename = f"{safe_ns}_{safe_key}.json"
        return self.cache_dir / filename

    def get(
        self,
        namespace: str,
        key: str,
        allow_stale: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached payload by namespace and key.
        
        Args:
            namespace: Cache domain ('osm', 'weather', 'enrichment').
            key: Deterministic cache key.
            allow_stale: If True, return payload even if TTL has expired
                         (essential for offline fallback).
                         
        Returns:
            Cached dictionary payload, or None if unavailable or corrupted.
        """
        file_path = self._get_file_path(namespace, key)
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                envelope = json.load(f)

            if not isinstance(envelope, dict):
                logger.warning("Corrupted cache file format at %s, discarding.", file_path)
                self.delete(namespace, key)
                return None

            created_at = envelope.get("created_at", 0)
            ttl = envelope.get("ttl_seconds", 0)
            payload = envelope.get("payload")

            is_expired = (time.time() - created_at) > ttl
            if is_expired and not allow_stale:
                return None

            return payload

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Error reading cache file %s: %s. Discarding entry.", file_path, e)
            self.delete(namespace, key)
            return None

    def set(
        self,
        namespace: str,
        key: str,
        payload: Any,
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Persist payload to disk cache with atomic write.
        
        Args:
            namespace: Cache domain ('osm', 'weather', 'enrichment').
            key: Deterministic cache key.
            payload: Serializable data to store.
            ttl_seconds: Time to live in seconds.
            
        Returns:
            True if write succeeded, False otherwise.
        """
        if ttl_seconds is None:
            if namespace == "osm":
                ttl_seconds = DEFAULT_OSM_TTL
            elif namespace == "weather":
                ttl_seconds = DEFAULT_WEATHER_TTL
            else:
                ttl_seconds = DEFAULT_ENRICHMENT_TTL

        envelope = {
            "key": key,
            "namespace": namespace,
            "created_at": time.time(),
            "ttl_seconds": ttl_seconds,
            "payload": payload
        }

        self._ensure_cache_dir()
        target_path = self._get_file_path(namespace, key)

        try:
            # Atomic write via temporary file
            temp_dir = self.cache_dir
            with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
                json.dump(envelope, tf, default=str)
                temp_name = tf.name

            os.replace(temp_name, target_path)
            return True
        except Exception as e:
            logger.warning("Failed to write cache entry %s: %s", target_path, e)
            return False

    def delete(self, namespace: str, key: str) -> bool:
        """Delete a specific cache entry."""
        file_path = self._get_file_path(namespace, key)
        try:
            if file_path.exists():
                file_path.unlink()
                return True
        except Exception as e:
            logger.warning("Failed to delete cache file %s: %s", file_path, e)
        return False

    def clear(self, namespace: Optional[str] = None) -> int:
        """Clear cached files, optionally filtered by namespace."""
        count = 0
        if not self.cache_dir.exists():
            return count

        prefix = f"{namespace}_" if namespace else ""
        try:
            for file_path in self.cache_dir.glob("*.json"):
                if file_path.name.startswith(prefix):
                    try:
                        file_path.unlink()
                        count += 1
                    except OSError:
                        pass
        except Exception as e:
            logger.warning("Error clearing cache: %s", e)
        return count
