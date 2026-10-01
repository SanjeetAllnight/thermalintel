"""Unit tests for DataCache."""

import tempfile
import time
import unittest
from pathlib import Path

from services.api.ingestion.cache import DataCache


class TestDataCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = DataCache(cache_dir=Path(self.temp_dir.name), default_ttl=3)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_set_and_get_valid(self):
        key = self.cache.make_key("firms", source="VIIRS_SNPP_NRT", days=1)
        payload = "test,csv,data\n1,2,3"
        self.assertTrue(self.cache.set(key, payload))

        retrieved = self.cache.get(key)
        self.assertEqual(retrieved, payload)
        self.assertTrue(self.cache.is_valid(key))

    def test_cache_expiration(self):
        key = "short_lived_key"
        payload = "temporary"
        self.cache.set(key, payload, ttl_seconds=1)

        # Immediate check: valid
        self.assertEqual(self.cache.get(key), payload)

        # After expiration: invalid
        time.sleep(1.2)
        self.assertIsNone(self.cache.get(key))
        self.assertFalse(self.cache.is_valid(key))

    def test_corrupted_cache_recovery(self):
        """A corrupt JSON file in cache directory must return None without crashing."""
        key = "corrupt_key"
        corrupt_path = Path(self.temp_dir.name) / f"{key}.json"
        with open(corrupt_path, "w", encoding="utf-8") as f:
            f.write("{ incomplete json broken ...")

        self.assertIsNone(self.cache.get(key))

    def test_cache_clear(self):
        self.cache.set("k1", "data1")
        self.cache.set("k2", "data2")

        self.assertEqual(self.cache.clear("k1"), 1)
        self.assertIsNone(self.cache.get("k1"))
        self.assertIsNotNone(self.cache.get("k2"))

        # Clear all
        self.assertGreaterEqual(self.cache.clear(), 1)
        self.assertIsNone(self.cache.get("k2"))


if __name__ == "__main__":
    unittest.main()
