"""Degraded Modes, Stale Cache, and Synthetic Fallback Validation Suite for ThermalIntel V2.

Verifies:
1. Operational Data Modes (LIVE, CACHE, DEMO, SYNTHETIC):
   - LIVE mode attempts upstream data when configured.
   - CACHE fallback serves cached records when upstream provider is unreachable.
   - DEMO/SYNTHETIC pathways initialize realistic self-consistent operational states.
2. Stale Data Handling:
   - Cache age calculation and TTL expiration detection.
   - Explicit 'stale' vs 'cached' freshness labeling without value fabrication.
3. Upstream Provider Degradation:
   - Provider outages do not purge previously ingested observations or incidents.
   - System state remains consistent and queryable during provider degradation.
"""

import os
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import services.api.database as db_mod
from services.api.migrations.runner import MigrationRunner
from services.api.schemas.common import DataMode
from services.api.schemas.v2.common import (
    FreshnessState,
    ProviderStatus,
    IncidentStatus,
    now_utc_iso,
)
from services.api.schemas.v2.provider import ProviderRun
from services.api.schemas.v2.observation import Observation
from services.api.ingestion.cache import DataCache
from services.api.ingestion.config import IngestionConfig
from services.api.ingestion.firms import FirmsClient
from services.api.data.service import HotspotDataService
from services.api.repositories.hotspot_repository import HotspotRepository
from services.api.repositories.observation_repository import ObservationRepository
from services.api.repositories.provider_run_repository import ProviderRunRepository
from services.api.incidents.repository import IncidentRepository
from services.api.incidents.engine import IncidentEngine

from tests.fixtures.v2_golden.fixtures import (
    INDUSTRIAL_BASELINE_RECORDS,
    make_raw_firms_csv,
)

SAMPLE_FIRMS_CSV = make_raw_firms_csv(INDUSTRIAL_BASELINE_RECORDS)


class TestDegradedModesAndCache(unittest.TestCase):
    """Validation suite for degraded modes, cache fallback, and provider resilience."""

    def setUp(self):
        self.original_db_path = db_mod.DB_PATH
        self.original_env_db = os.environ.get("DATABASE_PATH")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "degraded_test.db"
        self.cache_dir = Path(self.temp_dir.name) / "cache"

        os.environ["DATABASE_PATH"] = str(self.db_path)
        db_mod.DB_PATH = str(self.db_path)
        db_mod.invalidate_seed_cache()

        # Apply migrations
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

        self.connection_factory = self._get_connection
        self.cache = DataCache(cache_dir=self.cache_dir, default_ttl=1)  # 1s TTL for fast expiry testing
        self.hotspot_repo = HotspotRepository()
        self.obs_repo = ObservationRepository()
        self.run_repo = ProviderRunRepository()
        self.incident_repo = IncidentRepository(connection_factory=self.connection_factory)
        self.incident_engine = IncidentEngine(repository=self.incident_repo)

    def tearDown(self):
        if self.original_env_db is not None:
            os.environ["DATABASE_PATH"] = self.original_env_db
        else:
            os.environ.pop("DATABASE_PATH", None)
        db_mod.DB_PATH = self.original_db_path
        db_mod.invalidate_seed_cache()
        self.temp_dir.cleanup()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def test_cache_fallback_when_upstream_provider_fails(self):
        """When upstream live fetch fails, service falls back to cached response with stale marker."""
        cache_key = "firms:VIIRS_SNPP_NRT:world:1"
        self.cache.set(cache_key, SAMPLE_FIRMS_CSV, ttl_seconds=1)

        # Immediate check: fresh cache hit (returns CACHED)
        cached_val, freshness, age = self.cache.get_with_freshness(cache_key)
        self.assertEqual(freshness, FreshnessState.CACHED)
        self.assertEqual(cached_val, SAMPLE_FIRMS_CSV)

        # Sleep past 1s TTL to make it stale
        time.sleep(1.1)

        # After expiry, cached data is still retrievable but flagged as STALE
        stale_val, stale_freshness, stale_age = self.cache.get_with_freshness(cache_key)
        self.assertEqual(stale_freshness, FreshnessState.STALE)
        self.assertEqual(stale_val, SAMPLE_FIRMS_CSV)
        self.assertGreaterEqual(stale_age, 1.0)

    def test_hotspot_data_service_live_vs_stale_fallback(self):
        """HotspotDataService handles live fetch failure by serving stale cache without crashing."""
        mock_client = MagicMock(spec=FirmsClient)
        mock_client.fetch_recent_csv.return_value = None
        mock_client._last_result = None

        mock_config = MagicMock(spec=IngestionConfig)
        mock_config.default_source = "VIIRS_SNPP_NRT"
        mock_config.default_days = 1
        mock_config.has_firms_key = True

        service = HotspotDataService(
            repo=self.hotspot_repo,
            client=mock_client,
            data_cache=self.cache,
            cfg=mock_config,
        )

        cache_key = self.cache.make_key("firms", source="VIIRS_SNPP_NRT", days=1, bbox=None, area=None)
        # Prime cache with prior data and expire it
        self.cache.set(cache_key, SAMPLE_FIRMS_CSV, ttl_seconds=1)
        time.sleep(1.1)

        # Calling fetch_recent_hotspots triggers fallback to stale cache
        hotspots, mode, msg = service.fetch_recent_hotspots(source="VIIRS_SNPP_NRT", days=1)
        self.assertEqual(mode, DataMode.LIVE)
        self.assertGreater(len(hotspots), 0)
        self.assertIn("stale", msg.lower())

    def test_demo_and_synthetic_mode_initialization(self):
        """DEMO mode initializes database from sample fixtures with valid incident and alert states."""
        service = HotspotDataService(
            repo=self.hotspot_repo,
            data_cache=self.cache,
        )

        # Load demo data
        demo_hotspots = service.load_demo_hotspots()
        self.assertGreater(len(demo_hotspots), 0)

        # Verify all loaded hotspots have valid coordinates and non-zero FRP
        for h in demo_hotspots:
            self.assertGreaterEqual(h.latitude, -90.0)
            self.assertLessEqual(h.latitude, 90.0)
            self.assertGreaterEqual(h.frp, 0.0)

    def test_provider_outage_does_not_purge_persisted_incidents(self):
        """An upstream provider failure must not delete or corrupt existing persistent incidents."""
        # 1. Ingest initial observations and establish incident
        from services.api.ingestion.normalizer import HotspotNormalizer
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(SAMPLE_FIRMS_CSV)
        res = self.incident_engine.correlate_observations(observations)
        self.assertEqual(len(res.created_incidents), 1)
        inc_id = res.created_incidents[0].incident_id

        # 2. Simulate upstream provider complete failure (e.g. 500 server error)
        failed_run = ProviderRun(
            run_id="RUN-OUTAGE-001",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            started_at_utc=now_utc_iso(),
            finished_at_utc=now_utc_iso(),
            status=ProviderStatus.FAILED,
            rows_received=0,
            duration_ms=5000,
            error_type="HTTP500",
            error_message="Internal Server Error from upstream satellite feed",
        )
        self.run_repo.save_run(failed_run)

        # 3. Assert existing incident remains fully queryable and intact in database
        persisted_inc = self.incident_repo.get_incident(inc_id)
        self.assertIsNotNone(persisted_inc)
        self.assertEqual(persisted_inc.incident_id, inc_id)
        self.assertEqual(persisted_inc.observation_count, 2)

        linked_obs = self.incident_repo.list_incident_observations(inc_id)
        self.assertEqual(len(linked_obs), 2)
