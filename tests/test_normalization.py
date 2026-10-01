"""Unit tests for HotspotNormalizer and data validation."""

import unittest
from services.api.ingestion.normalizer import HotspotNormalizer, compute_baseline_risk
from services.api.schemas import RiskLevel, SourceType

SAMPLE_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,845,N,h,2.0NRT,298.4,142.8,N
34.1852,-118.1528,341.2,0.38,0.36,2026-10-01,0848,1,nominal,2.0NRT,295.3,76.5,N
"""


class TestHotspotNormalizer(unittest.TestCase):
    def test_normalize_csv_valid(self):
        hotspots = HotspotNormalizer.normalize_csv(SAMPLE_CSV)
        self.assertEqual(len(hotspots), 2)

        h1 = hotspots[0]
        self.assertEqual(h1.latitude, 38.7421)
        self.assertEqual(h1.longitude, -122.8105)
        self.assertEqual(h1.brightness, 352.4)
        self.assertEqual(h1.acq_time, "0845")  # Padded from 845 to 0845
        self.assertEqual(h1.satellite, "Suomi-NPP")  # Normalized from N
        self.assertEqual(h1.confidence, "high")  # Normalized from h
        self.assertEqual(h1.frp, 142.8)
        self.assertEqual(h1.daynight, "N")
        self.assertEqual(h1.risk_level, RiskLevel.CRITICAL)
        self.assertTrue(h1.is_anomaly)

        h2 = hotspots[1]
        self.assertEqual(h2.satellite, "NOAA-20")  # Normalized from 1
        self.assertEqual(h2.confidence, "nominal")
        self.assertEqual(h2.frp, 76.5)
        self.assertEqual(h2.risk_level, RiskLevel.HIGH)

    def test_out_of_bounds_coordinates_rejected(self):
        """Rows with invalid coordinates (lat > 90 or lon < -180) must be discarded."""
        bad_lat_row = {"latitude": "95.0", "longitude": "-120.0", "brightness": "320.0"}
        bad_lon_row = {"latitude": "35.0", "longitude": "-195.0", "brightness": "320.0"}

        self.assertIsNone(HotspotNormalizer.normalize_row(bad_lat_row))
        self.assertIsNone(HotspotNormalizer.normalize_row(bad_lon_row))

    def test_missing_required_fields_rejected(self):
        """Missing latitude, longitude, or brightness returns None."""
        self.assertIsNone(HotspotNormalizer.normalize_row({"latitude": "38.0"}))
        self.assertIsNone(HotspotNormalizer.normalize_row({"longitude": "-120.0"}))
        self.assertIsNone(HotspotNormalizer.normalize_row({"latitude": "38.0", "longitude": "-120.0"}))

    def test_negative_brightness_rejected(self):
        bad_bright_row = {"latitude": "38.0", "longitude": "-120.0", "brightness": "-10.0"}
        self.assertIsNone(HotspotNormalizer.normalize_row(bad_bright_row))

    def test_confidence_normalization(self):
        self.assertEqual(HotspotNormalizer.normalize_confidence("h"), "high")
        self.assertEqual(HotspotNormalizer.normalize_confidence("H"), "high")
        self.assertEqual(HotspotNormalizer.normalize_confidence("high"), "high")
        self.assertEqual(HotspotNormalizer.normalize_confidence("n"), "nominal")
        self.assertEqual(HotspotNormalizer.normalize_confidence("l"), "low")
        self.assertEqual(HotspotNormalizer.normalize_confidence("85"), "high")
        self.assertEqual(HotspotNormalizer.normalize_confidence("45"), "nominal")
        self.assertEqual(HotspotNormalizer.normalize_confidence("15"), "low")
        self.assertEqual(HotspotNormalizer.normalize_confidence(None), "nominal")

    def test_satellite_normalization(self):
        self.assertEqual(HotspotNormalizer.normalize_satellite_name("N"), "Suomi-NPP")
        self.assertEqual(HotspotNormalizer.normalize_satellite_name("1"), "NOAA-20")
        self.assertEqual(HotspotNormalizer.normalize_satellite_name("2"), "NOAA-21")
        self.assertEqual(HotspotNormalizer.normalize_satellite_name("T"), "Terra")
        self.assertEqual(HotspotNormalizer.normalize_satellite_name("A"), "Aqua")

    def test_daynight_normalization(self):
        self.assertEqual(HotspotNormalizer.normalize_daynight("D", "1200"), "D")
        self.assertEqual(HotspotNormalizer.normalize_daynight("day", "1200"), "D")
        self.assertEqual(HotspotNormalizer.normalize_daynight("N", "2200"), "N")
        self.assertEqual(HotspotNormalizer.normalize_daynight(None, "1400"), "D")
        self.assertEqual(HotspotNormalizer.normalize_daynight(None, "0200"), "N")

    def test_deterministic_id_generation(self):
        id1 = HotspotNormalizer.generate_id(
            instrument="VIIRS",
            satellite="Suomi-NPP",
            acq_date="2026-10-01",
            acq_time="0845",
            lat=38.7421,
            lon=-122.8105,
            sequence=1,
        )
        self.assertEqual(id1, "VIIRS-SUOMINPP-20261001-0001")

        id2 = HotspotNormalizer.generate_id(
            instrument="VIIRS",
            satellite="Suomi-NPP",
            acq_date="2026-10-01",
            acq_time="0845",
            lat=38.7421,
            lon=-122.8105,
        )
        id3 = HotspotNormalizer.generate_id(
            instrument="VIIRS",
            satellite="Suomi-NPP",
            acq_date="2026-10-01",
            acq_time="0845",
            lat=38.7421,
            lon=-122.8105,
        )
        self.assertEqual(id2, id3)  # Stable deterministic hash-based ID


if __name__ == "__main__":
    unittest.main()
