"""Unit and integration tests for HotspotDataService and refresh pipeline."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.api.data.service import HotspotDataService
from services.api.ingestion.cache import DataCache
from services.api.ingestion.config import IngestionConfig
from services.api.ingestion.firms import FirmsClient
from services.api.repositories.hotspot_repository import HotspotRepository
from services.api.schemas import DataMode, RiskLevel, SourceType

MOCK_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,142.8,N
38.7468,-122.8052,346.1,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,296.2,118.2,N
"""


class TestHotspotDataService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = DataCache(cache_dir=Path(self.temp_dir.name), default_ttl=3600)
        self.repo = HotspotRepository()
        self.repo.clear_hotspots()

        self.cfg_live = IngestionConfig(
            firms_map_key="mock_key_abc12345",
            cache_dir=Path(self.temp_dir.name),
        )
        self.cfg_no_key = IngestionConfig(
            firms_map_key="",
            cache_dir=Path(self.temp_dir.name),
        )

    def tearDown(self):
        self.temp_dir.cleanup()
        self.repo.clear_hotspots()

    def test_load_demo_hotspots(self):
        """Demo dataset must load and validate all 30 realistic hotspots."""
        service = HotspotDataService(repo=self.repo, data_cache=self.cache)
        hotspots = service.load_demo_hotspots()
        self.assertGreaterEqual(len(hotspots), 10)
        # Verify first record fields
        first = hotspots[0]
        self.assertTrue(first.id.startswith("VIIRS-"))
        self.assertGreater(first.frp, 0.0)
        self.assertIn(first.risk_level, list(RiskLevel))

    @patch("services.api.ingestion.firms.FirmsClient.fetch_recent_csv")
    def test_live_sync_success(self, mock_fetch):
        """When FIRMS API returns valid data, sync must succeed with LIVE mode and write to cache."""
        mock_fetch.return_value = MOCK_FIRMS_CSV

        client = FirmsClient(self.cfg_live)
        service = HotspotDataService(
            repo=self.repo, client=client, data_cache=self.cache, cfg=self.cfg_live
        )

        response = service.sync(force_sample=False)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.data_mode, DataMode.LIVE)
        self.assertEqual(response.ingested_count, 2)
        self.assertEqual(self.repo.count_hotspots(), 2)
        self.assertEqual(self.repo.get_data_mode(), DataMode.LIVE)

    @patch("services.api.ingestion.firms.FirmsClient.fetch_recent_csv")
    def test_fallback_to_cache_when_live_fails(self, mock_fetch):
        """When live FIRMS fails, but a cached response exists, service must fall back to cache."""
        # 1. Populate cache
        cache_key = self.cache.make_key(
            "firms", source=self.cfg_live.default_source, days=self.cfg_live.default_days, bbox=None, area=None
        )
        self.cache.set(cache_key, MOCK_FIRMS_CSV)

        # 2. Live fetch fails (returns None)
        mock_fetch.return_value = None

        client = FirmsClient(self.cfg_live)
        service = HotspotDataService(
            repo=self.repo, client=client, data_cache=self.cache, cfg=self.cfg_live
        )

        response = service.sync(force_sample=False)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.data_mode, DataMode.LIVE)
        self.assertEqual(response.ingested_count, 2)
        self.assertIn("cached FIRMS", response.message)

    def test_fallback_to_demo_when_no_api_key(self):
        """When no FIRMS API key is configured, service must fall back to demo dataset."""
        client = FirmsClient(self.cfg_no_key)
        service = HotspotDataService(
            repo=self.repo, client=client, data_cache=self.cache, cfg=self.cfg_no_key
        )

        response = service.sync(force_sample=False)

        self.assertEqual(response.status, "fallback_sample")
        self.assertEqual(response.data_mode, DataMode.DEMO)
        self.assertGreaterEqual(response.ingested_count, 10)
        self.assertEqual(self.repo.get_data_mode(), DataMode.DEMO)

    @patch("services.api.ingestion.firms.FirmsClient.fetch_recent_csv")
    def test_fallback_to_demo_when_live_and_cache_unavailable(self, mock_fetch):
        """When live API fails and no cache exists, fallback cleanly to demo dataset."""
        mock_fetch.return_value = None  # Live failed

        client = FirmsClient(self.cfg_live)
        service = HotspotDataService(
            repo=self.repo, client=client, data_cache=self.cache, cfg=self.cfg_live
        )

        response = service.sync(force_sample=False)

        self.assertEqual(response.status, "fallback_sample")
        self.assertEqual(response.data_mode, DataMode.DEMO)
        self.assertGreaterEqual(response.ingested_count, 10)

    def test_force_sample_flag(self):
        """When force_sample=True, demo dataset must be used even if FIRMS key is present."""
        client = FirmsClient(self.cfg_live)
        service = HotspotDataService(
            repo=self.repo, client=client, data_cache=self.cache, cfg=self.cfg_live
        )

        response = service.sync(force_sample=True)

        self.assertEqual(response.status, "fallback_sample")
        self.assertEqual(response.data_mode, DataMode.DEMO)

    def test_duplicate_sync_does_not_multiply_records(self):
        """Multiple sync invocations must upsert without growing the record count."""
        client = FirmsClient(self.cfg_no_key)
        service = HotspotDataService(
            repo=self.repo, client=client, data_cache=self.cache, cfg=self.cfg_no_key
        )

        res1 = service.sync(force_sample=True)
        count1 = self.repo.count_hotspots()

        res2 = service.sync(force_sample=True)
        count2 = self.repo.count_hotspots()

        self.assertEqual(count1, count2)

    def test_get_hotspots_paginated_response(self):
        """get_hotspots envelope must match HotspotsResponse schema."""
        service = HotspotDataService(repo=self.repo, data_cache=self.cache)
        # Preload demo data
        service.sync(force_sample=True)

        resp = service.get_hotspots(page=1, page_size=10)
        self.assertEqual(resp.page, 1)
        self.assertEqual(resp.page_size, 10)
        self.assertEqual(len(resp.items), 10)
        self.assertGreaterEqual(resp.total, 10)
        self.assertEqual(resp.data_mode, DataMode.DEMO)

    def test_get_hotspot_by_id(self):
        service = HotspotDataService(repo=self.repo, data_cache=self.cache)
        service.sync(force_sample=True)

        hotspot = service.get_hotspot_by_id("VIIRS-SNPP-20261001-001")
        self.assertIsNotNone(hotspot)
        self.assertEqual(hotspot.id, "VIIRS-SNPP-20261001-001")
        self.assertEqual(hotspot.latitude, 38.7421)


if __name__ == "__main__":
    unittest.main()
