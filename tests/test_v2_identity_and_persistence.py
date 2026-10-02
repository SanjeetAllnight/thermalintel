"""Tests for stable deterministic observation identities, idempotent persistence, and V2 repositories."""

import tempfile
import unittest
from pathlib import Path

from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.payload_store import RawPayloadStore
from services.api.repositories.observation_repository import ObservationRepository
from services.api.repositories.provider_run_repository import ProviderRunRepository
from services.api.repositories.raw_payload_repository import RawPayloadRepository
from services.api.schemas.v2.common import ProviderStatus, now_utc_iso
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.provider import ProviderRun

ROW_A = """38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,142.8,N"""
ROW_B = """38.7468,-122.8052,346.1,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,296.2,118.2,N"""
ROW_C = """34.1852,-118.1528,341.2,0.38,0.36,2026-10-01,0848,1,nominal,2.0NRT,295.3,76.5,N"""

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"


class TestV2IdentityAndPersistence(unittest.TestCase):
    def setUp(self):
        self.obs_repo = ObservationRepository()
        self.run_repo = ProviderRunRepository()
        self.payload_repo = RawPayloadRepository()

        self.obs_repo.clear()
        self.run_repo.clear()
        self.payload_repo.clear()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.payload_store = RawPayloadStore(raw_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.obs_repo.clear()
        self.run_repo.clear()
        self.payload_repo.clear()
        self.temp_dir.cleanup()

    # 1. Deterministic Evidence-Based ID Generation
    def test_deterministic_id_across_independent_runs(self):
        """The same provider record must produce the identical ID across independent runs."""
        csv1 = HEADER + ROW_A + "\n"
        csv2 = HEADER + ROW_A + "\n"

        obs1, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv1)
        obs2, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv2)

        self.assertEqual(len(obs1), 1)
        self.assertEqual(len(obs2), 1)
        self.assertEqual(obs1[0].observation_id, obs2[0].observation_id)

    # 2. Batch Order Independence
    def test_id_independence_from_batch_order(self):
        """Record IDs must not depend on row order or batch counter."""
        order_1 = HEADER + ROW_A + "\n" + ROW_B + "\n" + ROW_C + "\n"
        order_2 = HEADER + ROW_C + "\n" + ROW_A + "\n" + ROW_B + "\n"

        obs_order_1, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(order_1)
        obs_order_2, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(order_2)

        ids_1 = {o.latitude: o.observation_id for o in obs_order_1}
        ids_2 = {o.latitude: o.observation_id for o in obs_order_2}

        # Each record's ID is identical regardless of position in the CSV
        self.assertEqual(ids_1[38.7421], ids_2[38.7421])
        self.assertEqual(ids_1[38.7468], ids_2[38.7468])
        self.assertEqual(ids_1[34.1852], ids_2[34.1852])

    # 3. Observation Repository Idempotent Persistence
    def test_observation_persistence_and_upsert_idempotency(self):
        csv_text = HEADER + ROW_A + "\n" + ROW_B + "\n"
        obs_list, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)

        # Initial insert
        count_first = self.obs_repo.save_observations(obs_list)
        self.assertEqual(count_first, 2)
        self.assertEqual(self.obs_repo.count(), 2)

        # Re-ingest the exact same batch: count MUST remain 2 (no duplicates!)
        count_second = self.obs_repo.save_observations(obs_list)
        self.assertEqual(self.obs_repo.count(), 2)

        # Fetch and verify
        first_id = obs_list[0].observation_id
        fetched = self.obs_repo.get_by_id(first_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.observation_id, first_id)
        self.assertEqual(fetched.latitude, 38.7421)
        self.assertEqual(fetched.frp, 142.8)

    # 4. Observation Querying and Filtering
    def test_observation_queries_and_filtering(self):
        csv_text = HEADER + ROW_A + "\n" + ROW_B + "\n" + ROW_C + "\n"
        obs_list, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        self.obs_repo.save_observations(obs_list)

        # Filter by min_frp (ROW_A: 142.8, ROW_B: 118.2, ROW_C: 76.5)
        high_frp, total = self.obs_repo.get_observations(min_frp=100.0)
        self.assertEqual(total, 2)
        self.assertEqual(len(high_frp), 2)

        # Filter by product
        items, total = self.obs_repo.get_observations(product="VIIRS_SNPP_NRT")
        self.assertEqual(total, 3)

    # 5. Provider Run Repository Persistence and Telemetry
    def test_provider_run_persistence(self):
        run = ProviderRun(
            run_id="RUN-TEST-20261001-001",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            started_at_utc=now_utc_iso(),
            finished_at_utc=now_utc_iso(),
            status=ProviderStatus.SUCCESS,
            rows_received=15,
            duration_ms=420,
            error_type=None,
            error_message=None,
            request_metadata={"source": "VIIRS_SNPP_NRT", "days": 1},
        )

        self.run_repo.save_run(run)
        self.assertEqual(self.run_repo.count(), 1)

        fetched = self.run_repo.get_by_id("RUN-TEST-20261001-001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.run_id, "RUN-TEST-20261001-001")
        self.assertEqual(fetched.status, ProviderStatus.SUCCESS)
        self.assertEqual(fetched.rows_received, 15)
        self.assertEqual(fetched.duration_ms, 420)
        self.assertEqual(fetched.request_metadata["source"], "VIIRS_SNPP_NRT")

    # 6. Raw Payload Storage and Metadata Repository
    def test_raw_payload_content_addressing_and_metadata(self):
        content = "test,csv,line1\ntest,csv,line2\n"

        # Store in filesystem
        meta1 = self.payload_store.store_payload(
            content=content,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
        )
        self.payload_repo.save_payload_metadata(meta1)

        # Re-storing same content produces identical hash and payload_id
        meta2 = self.payload_store.store_payload(
            content=content,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
        )
        self.assertEqual(meta1.content_hash, meta2.content_hash)
        self.assertEqual(meta1.payload_id, meta2.payload_id)

        # Lookup by ID
        fetched_by_id = self.payload_repo.get_by_id(meta1.payload_id)
        self.assertIsNotNone(fetched_by_id)
        self.assertEqual(fetched_by_id.content_hash, meta1.content_hash)

        # Lookup by content hash
        fetched_by_hash = self.payload_repo.get_by_content_hash(meta1.content_hash)
        self.assertIsNotNone(fetched_by_hash)
        self.assertEqual(fetched_by_hash.payload_id, meta1.payload_id)

        # Read content back from disk
        disk_content = self.payload_store.read_payload_text(meta1.storage_path)
        self.assertEqual(disk_content, content)


if __name__ == "__main__":
    unittest.main()
