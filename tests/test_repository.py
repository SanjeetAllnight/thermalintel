"""Unit tests for HotspotRepository persistence and query operations."""

import unittest
from services.api.database import init_db
from services.api.repositories.hotspot_repository import HotspotRepository
from services.api.schemas import Hotspot, RiskLevel, SourceType, DataMode


def make_test_hotspot(
    hid: str,
    lat: float = 38.7421,
    lon: float = -122.8105,
    frp: float = 100.0,
    risk_level: RiskLevel = RiskLevel.CRITICAL,
    source_type: SourceType = SourceType.WILDFIRE,
    cluster_id: str = "CL-TEST",
    is_anomaly: bool = True,
    confidence: str = "high",
) -> Hotspot:
    return Hotspot(
        id=hid,
        latitude=lat,
        longitude=lon,
        brightness=350.0,
        scan=0.38,
        track=0.36,
        acq_date="2026-10-01",
        acq_time="0845",
        satellite="Suomi-NPP",
        instrument="VIIRS",
        confidence=confidence,
        version="2.0NRT",
        bright_t31=298.0,
        frp=frp,
        daynight="N",
        source_type=source_type,
        risk_score=90.0,
        risk_level=risk_level,
        is_anomaly=is_anomaly,
        cluster_id=cluster_id,
        cluster_size=2,
        nearest_place="Test Location, CA",
        last_updated="2026-10-01T08:50:00Z",
    )


class TestHotspotRepository(unittest.TestCase):
    def setUp(self):
        self.repo = HotspotRepository()
        self.repo.clear_hotspots()

    def tearDown(self):
        self.repo.clear_hotspots()

    def test_save_and_get_by_id(self):
        h = make_test_hotspot("TEST-001")
        self.repo.save_hotspot(h, data_mode="demo")

        fetched = self.repo.get_by_id("TEST-001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, "TEST-001")
        self.assertEqual(fetched.latitude, 38.7421)
        self.assertEqual(fetched.frp, 100.0)
        self.assertEqual(fetched.risk_level, RiskLevel.CRITICAL)
        self.assertEqual(fetched.source_type, SourceType.WILDFIRE)

    def test_get_by_id_not_found(self):
        self.assertIsNone(self.repo.get_by_id("NONEXISTENT"))

    def test_upsert_deduplication(self):
        """Duplicate syncs must update existing records rather than endlessly duplicating."""
        h1 = make_test_hotspot("TEST-DUP", frp=50.0)
        self.repo.save_hotspot(h1)
        self.assertEqual(self.repo.count_hotspots(), 1)

        # Upsert modified version with same ID
        h2 = make_test_hotspot("TEST-DUP", frp=150.0)
        self.repo.upsert_hotspots([h2])
        self.assertEqual(self.repo.count_hotspots(), 1)

        fetched = self.repo.get_by_id("TEST-DUP")
        self.assertEqual(fetched.frp, 150.0)

    def test_batch_upsert(self):
        hotspots = [make_test_hotspot(f"BATCH-{i:03d}", frp=float(i * 10)) for i in range(1, 6)]
        count = self.repo.upsert_hotspots(hotspots)
        self.assertEqual(count, 5)
        self.assertEqual(self.repo.count_hotspots(), 5)

    def test_filtering_and_pagination(self):
        h1 = make_test_hotspot("H-1", frp=120.0, risk_level=RiskLevel.CRITICAL, source_type=SourceType.WILDFIRE)
        h2 = make_test_hotspot("H-2", frp=40.0, risk_level=RiskLevel.MEDIUM, source_type=SourceType.INDUSTRIAL, is_anomaly=False, confidence="nominal")
        h3 = make_test_hotspot("H-3", frp=80.0, risk_level=RiskLevel.HIGH, source_type=SourceType.WILDFIRE)
        h4 = make_test_hotspot("H-4", frp=15.0, risk_level=RiskLevel.LOW, source_type=SourceType.URBAN, is_anomaly=False, confidence="low")

        self.repo.upsert_hotspots([h1, h2, h3, h4])

        # Filter by risk_level
        items, total = self.repo.get_hotspots(risk_level=RiskLevel.CRITICAL)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].id, "H-1")

        # Filter by source_type
        items, total = self.repo.get_hotspots(source_type=SourceType.WILDFIRE)
        self.assertEqual(total, 2)

        # Filter by min_frp
        items, total = self.repo.get_hotspots(min_frp=50.0)
        self.assertEqual(total, 2)
        # Verify ordering: H-1 (120 MW) before H-3 (80 MW)
        self.assertEqual(items[0].id, "H-1")
        self.assertEqual(items[1].id, "H-3")

        # Filter by is_anomaly
        items, total = self.repo.get_hotspots(is_anomaly=True)
        self.assertEqual(total, 2)

        # Pagination: 2 items per page
        page1, total = self.repo.get_hotspots(page=1, page_size=2)
        self.assertEqual(total, 4)
        self.assertEqual(len(page1), 2)

        page2, total = self.repo.get_hotspots(page=2, page_size=2)
        self.assertEqual(total, 4)
        self.assertEqual(len(page2), 2)
        self.assertNotEqual(page1[0].id, page2[0].id)

    def test_metadata_operations(self):
        self.repo.set_data_mode(DataMode.LIVE)
        self.assertEqual(self.repo.get_data_mode(), DataMode.LIVE)

        self.repo.set_data_mode(DataMode.DEMO)
        self.assertEqual(self.repo.get_data_mode(), DataMode.DEMO)

        self.repo.set_last_sync("2026-10-01T10:00:00Z")
        self.assertEqual(self.repo.get_last_sync(), "2026-10-01T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
