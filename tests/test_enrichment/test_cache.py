"""Tests for resilient file-backed EnrichmentCache."""

import time
from pathlib import Path
import pytest

from services.api.enrichment.cache import EnrichmentCache, generate_cache_key


@pytest.fixture
def temp_cache(tmp_path: Path) -> EnrichmentCache:
    """Provide an isolated temporary cache instance."""
    return EnrichmentCache(cache_dir=tmp_path)


def test_generate_cache_key_deterministic():
    """Identical parameters must generate identical cache keys."""
    k1 = generate_cache_key("test", 38.7421, -122.8105, radius=5000)
    k2 = generate_cache_key("test", 38.7421, -122.8105, radius=5000)
    assert k1 == k2
    assert len(k1) == 32

    # Different inputs must produce different keys
    k3 = generate_cache_key("test", 38.7422, -122.8105, radius=5000)
    assert k1 != k3


def test_cache_set_and_get(temp_cache: EnrichmentCache):
    """Test standard write and read operations."""
    key = "key123"
    payload = {"status": "ok", "features": ["substation", "plant"], "count": 2}

    assert temp_cache.set("osm", key, payload, ttl_seconds=60)
    cached = temp_cache.get("osm", key)
    assert cached == payload


def test_cache_miss(temp_cache: EnrichmentCache):
    """Non-existent key returns None."""
    assert temp_cache.get("osm", "nonexistent_key") is None


def test_cache_ttl_and_stale_fallback(temp_cache: EnrichmentCache):
    """Verify TTL expiry and allow_stale fallback."""
    key = "expiring_key"
    payload = {"temperature": 32.5}

    # Set TTL of 1 second
    temp_cache.set("weather", key, payload, ttl_seconds=1)
    assert temp_cache.get("weather", key, allow_stale=False) == payload

    # Sleep past TTL
    time.sleep(1.1)

    # Standard get should return None because it is expired
    assert temp_cache.get("weather", key, allow_stale=False) is None

    # Offline / resilient mode with allow_stale=True should still return the data
    stale = temp_cache.get("weather", key, allow_stale=True)
    assert stale == payload


def test_corrupted_cache_file_recovery(temp_cache: EnrichmentCache):
    """Corrupted JSON cache files must be safely discarded without crashing."""
    key = "corrupted_key"
    file_path = temp_cache._get_file_path("osm", key)
    # Write garbage non-JSON content
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{this is not valid json content!!!")

    # get() must handle the error gracefully and return None
    assert temp_cache.get("osm", key) is None
    # Corrupt file should be removed
    assert not file_path.exists()


def test_cache_clear(temp_cache: EnrichmentCache):
    """Verify namespace-specific and global clearing."""
    temp_cache.set("osm", "k1", {"a": 1})
    temp_cache.set("osm", "k2", {"b": 2})
    temp_cache.set("weather", "k3", {"c": 3})

    # Clear only OSM
    cleared = temp_cache.clear("osm")
    assert cleared == 2
    assert temp_cache.get("osm", "k1") is None
    assert temp_cache.get("weather", "k3") is not None

    # Clear all
    temp_cache.clear()
    assert temp_cache.get("weather", "k3") is None
