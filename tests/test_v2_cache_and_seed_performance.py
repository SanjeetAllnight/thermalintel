"""Tests for cache age inspection, stale cache fallback, and seed initialization performance."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.api.database import seed_if_empty, invalidate_seed_cache, get_connection
from services.api.data.service import HotspotDataService
from services.api.ingestion.cache import DataCache
from services.api.ingestion.config import IngestionConfig
from services.api.ingestion.firms import FirmsClient
from services.api.repositories.hotspot_repository import HotspotRepository
from services.api.repositories.observation_repository import ObservationRepository
from services.api.repositories.provider_run_repository import ProviderRunRepository
from services.api.schemas import DataMode
from services.api.schemas.v2.common import FreshnessState, ProviderStatus

EMPTY_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
"""

MOCK_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,142.8,N
"""


class TestV2CacheAndSeedPerformance(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = DataCache(cache_dir=Path(self.temp_dir.name), default_ttl=2)
        self.repo = HotspotRepository()
        self.obs_repo = ObservationRepository()
        self.run_repo = ProviderRunRepository()
        self.run_repo.clear()
        self.obs_repo.clear()
        self.repo.clear_hotspots()

    def tearDown(self):
        self.run_repo.clear()
        self.obs_repo.clear()
        self.repo.clear_hotspots()
        self.temp_dir.cleanup()

    # 1. Cache Age and Fresh vs Stale Discrimination
    def test_cache_age_and_metadata_inspection(self):
        key = "test_key_001"
        payload = "test_payload_data"
        self.cache.set(key, payload, ttl_seconds=2)

        meta = self.cache.get_metadata(key)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.key, key)
        self.assertGreaterEqual(meta.age_seconds, 0.0)
        self.assertEqual(meta.ttl, 2)
        self.assertFalse(meta.is_stale)

        # Immediate retrieval: fresh
        val, freshness, age = self.cache.get_with_freshness(key)
        self.assertEqual(val, payload)
        self.assertEqual(freshness, FreshnessState.CACHED)

    def test_cache_stale_fallback_behavior(self):
        key = "test_stale_key"
        payload = "stale_payload_data"
        self.cache.set(key, payload, ttl_seconds=1)

        # Wait for expiration
        time.sleep(1.2)

        # Standard get returns None (expired)
        self.assertIsNone(self.cache.get(key, allow_stale=False))
        self.assertTrue(self.cache.is_stale(key))

        # Intentional stale retrieval succeeds
        stale_val = self.cache.get(key, allow_stale=True)
        self.assertEqual(stale_val, payload)

        val, freshness, age = self.cache.get_with_freshness(key)
        self.assertEqual(val, payload)
        self.assertEqual(freshness, FreshnessState.STALE)
        self.assertGreater(age, 1.0)

    # 2. Seed / Initialization Performance
    def test_seed_if_empty_performance_caching(self):
        """seed_if_empty must execute once and avoid COUNT(*) queries on repeated calls."""
        # Ensure cache is invalidated for a clean check
        invalidate_seed_cache()

        # First call: populates / verifies DB
        seed_if_empty()

        # Second call: spy on get_connection to ensure no connection or queries are executed
        with patch("services.api.database.get_connection") as mock_conn:
            seed_if_empty()
            # Fast path was hit: get_connection was never called!
            mock_conn.assert_not_called()

        # Third call: still fast path
        with patch("services.api.database.get_connection") as mock_conn:
            seed_if_empty()
            mock_conn.assert_not_called()

    # 3. Empty Feed Semantics in DataService
    @patch("services.api.ingestion.firms.FirmsClient.fetch_raw")
    def test_data_service_empty_feed_not_an_outage(self, mock_fetch_raw):
        """A valid empty FIRMS response must be recorded as SUCCESS and not fall back to demo data."""
        from services.api.ingestion.firms import FirmsFetchResult

        mock_fetch_raw.return_value = FirmsFetchResult(
            status="empty",
            status_code=200,
            raw_csv=EMPTY_FIRMS_CSV,
            rows_received=0,
            duration_ms=150,
            error_type=None,
            error_message=None,
            request_metadata={"source": "VIIRS_SNPP_NRT", "days": 1},
            started_at_utc="2026-10-01T08:00:00Z",
            finished_at_utc="2026-10-01T08:00:01Z",
            attempts=1,
            is_empty=True,
        )

        cfg_live = IngestionConfig(
            firms_map_key="valid_test_key",
            cache_dir=Path(self.temp_dir.name),
        )
        client = FirmsClient(cfg_live)
        service = HotspotDataService(
            repo=self.repo,
            client=client,
            data_cache=self.cache,
            cfg=cfg_live,
            obs_repo=self.obs_repo,
            run_repo=self.run_repo,
        )

        resp = service.sync(force_sample=False)

        # Empty valid response must maintain LIVE mode and 0 ingested count
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.data_mode, DataMode.LIVE)
        self.assertEqual(resp.ingested_count, 0)
        self.assertIn("0 active thermal anomalies", resp.message)

        # ProviderRun was recorded as SUCCESS with 0 rows
        runs = self.run_repo.get_recent_runs()
        self.assertGreaterEqual(len(runs), 1)
        self.assertEqual(runs[0].status, ProviderStatus.SUCCESS)
        self.assertEqual(runs[0].rows_received, 0)


if __name__ == "__main__":
    unittest.main()
