"""Tests for VIIRS/MODIS normalization, frozen UTC timestamps, and quarantine."""

import tempfile
import unittest
from pathlib import Path

from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.quarantine import QuarantineManager
from services.api.schemas import RiskLevel

VIIRS_CSV_ROW = {
    "latitude": "38.7421",
    "longitude": "-122.8105",
    "bright_ti4": "352.4",
    "scan": "0.38",
    "track": "0.36",
    "acq_date": "2026-10-01",
    "acq_time": "0845",
    "satellite": "N",
    "confidence": "h",
    "version": "2.0NRT",
    "bright_ti5": "298.4",
    "frp": "142.8",
    "daynight": "N",
}

MODIS_CSV_ROW = {
    "latitude": "-33.8688",
    "longitude": "151.2093",
    "brightness": "325.6",
    "scan": "1.2",
    "track": "1.1",
    "acq_date": "2026-10-02",
    "acq_time": "1430",
    "satellite": "Terra",
    "instrument": "MODIS",
    "confidence": "85",
    "version": "6.1NRT",
    "bright_t31": "290.1",
    "frp": "55.0",
    "daynight": "D",
}


class TestV2NormalizationAndQuarantine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.qm = QuarantineManager(quarantine_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. VIIRS Normalization
    def test_viirs_field_mapping(self):
        hotspot, obs, err = HotspotNormalizer.normalize_row_with_diagnostics(VIIRS_CSV_ROW)
        self.assertIsNone(err)
        self.assertIsNotNone(hotspot)
        self.assertIsNotNone(obs)

        # Hotspot checks
        self.assertEqual(hotspot.satellite, "Suomi-NPP")
        self.assertEqual(hotspot.instrument, "VIIRS")
        self.assertEqual(hotspot.brightness, 352.4)
        self.assertEqual(hotspot.bright_t31, 298.4)
        self.assertEqual(hotspot.confidence, "high")
        self.assertEqual(hotspot.frp, 142.8)
        self.assertEqual(hotspot.daynight, "N")

        # Observation checks
        self.assertEqual(obs.provider, "NASA_FIRMS")
        self.assertEqual(obs.satellite, "Suomi-NPP")
        self.assertEqual(obs.instrument, "VIIRS")
        self.assertEqual(obs.brightness, 352.4)
        self.assertEqual(obs.bright_t31, 298.4)
        self.assertEqual(obs.detection_confidence, "high")
        self.assertEqual(obs.acquisition_time_utc, "2026-10-01T08:45:00Z")

    # 2. MODIS Normalization
    def test_modis_field_mapping(self):
        hotspot, obs, err = HotspotNormalizer.normalize_row_with_diagnostics(MODIS_CSV_ROW)
        self.assertIsNone(err)
        self.assertIsNotNone(hotspot)
        self.assertIsNotNone(obs)

        # Hotspot checks
        self.assertEqual(hotspot.satellite, "Terra")
        self.assertEqual(hotspot.instrument, "MODIS")
        self.assertEqual(hotspot.brightness, 325.6)
        self.assertEqual(hotspot.bright_t31, 290.1)
        self.assertEqual(hotspot.confidence, "high")  # 85 numeric -> high
        self.assertEqual(hotspot.daynight, "D")

        # Observation checks
        self.assertEqual(obs.satellite, "Terra")
        self.assertEqual(obs.instrument, "MODIS")
        self.assertEqual(obs.acquisition_time_utc, "2026-10-02T14:30:00Z")
        self.assertEqual(obs.detection_confidence, "high")

    # 3. Missing Required Fields
    def test_missing_coordinates_rejected(self):
        bad_row = dict(VIIRS_CSV_ROW)
        del bad_row["latitude"]
        hotspot, obs, err = HotspotNormalizer.normalize_row_with_diagnostics(bad_row)
        self.assertIsNone(hotspot)
        self.assertIsNone(obs)
        self.assertIn("Missing required coordinate", err)

    def test_missing_brightness_rejected(self):
        bad_row = dict(VIIRS_CSV_ROW)
        del bad_row["bright_ti4"]
        hotspot, obs, err = HotspotNormalizer.normalize_row_with_diagnostics(bad_row)
        self.assertIsNone(hotspot)
        self.assertIsNone(obs)
        self.assertIn("Missing required brightness", err)

    # 4. Invalid Coordinates
    def test_invalid_coordinates_boundary_and_types(self):
        # Lat > 90
        row1 = dict(VIIRS_CSV_ROW, latitude="90.5")
        _, _, err1 = HotspotNormalizer.normalize_row_with_diagnostics(row1)
        self.assertIn("Coordinates out of bounds", err1)

        # Lon < -180
        row2 = dict(VIIRS_CSV_ROW, longitude="-181.0")
        _, _, err2 = HotspotNormalizer.normalize_row_with_diagnostics(row2)
        self.assertIn("Coordinates out of bounds", err2)

        # Non-numeric
        row3 = dict(VIIRS_CSV_ROW, latitude="not_a_number")
        _, _, err3 = HotspotNormalizer.normalize_row_with_diagnostics(row3)
        self.assertIn("Malformed non-numeric coordinates", err3)

        # NaN
        row4 = dict(VIIRS_CSV_ROW, latitude="nan")
        _, _, err4 = HotspotNormalizer.normalize_row_with_diagnostics(row4)
        self.assertIn("Malformed non-finite coordinates", err4)

    # 5. Invalid Timestamps
    def test_invalid_acquisition_date_and_time(self):
        # Invalid date format / month
        row_date = dict(VIIRS_CSV_ROW, acq_date="2026-99-99")
        _, _, err_date = HotspotNormalizer.normalize_row_with_diagnostics(row_date)
        self.assertIn("Invalid acquisition date", err_date)

        # Invalid hour (> 23)
        row_hour = dict(VIIRS_CSV_ROW, acq_time="2500")
        _, _, err_hour = HotspotNormalizer.normalize_row_with_diagnostics(row_hour)
        self.assertIn("Acquisition time out of bounds", err_hour)

        # Invalid minute (> 59)
        row_min = dict(VIIRS_CSV_ROW, acq_time="1265")
        _, _, err_min = HotspotNormalizer.normalize_row_with_diagnostics(row_min)
        self.assertIn("Acquisition time out of bounds", err_min)

        # Non-digits
        row_str = dict(VIIRS_CSV_ROW, acq_time="abcd")
        _, _, err_str = HotspotNormalizer.normalize_row_with_diagnostics(row_str)
        self.assertIn("Malformed acquisition time", err_str)

    # 6. Frozen UTC Timestamp Standard Conformance
    def test_utc_iso8601_policy(self):
        # 3-digit time padded cleanly
        row_padded = dict(VIIRS_CSV_ROW, acq_time="845", acq_date="2026-10-01")
        _, obs, _ = HotspotNormalizer.normalize_row_with_diagnostics(row_padded)
        self.assertEqual(obs.acquisition_time_utc, "2026-10-01T08:45:00Z")

    # 7. Invalid FRP Parsing
    def test_frp_parsing_and_bounds(self):
        # Negative FRP clamped to 0.0
        row_neg = dict(VIIRS_CSV_ROW, frp="-15.0")
        hotspot, obs, _ = HotspotNormalizer.normalize_row_with_diagnostics(row_neg)
        self.assertEqual(hotspot.frp, 0.0)
        self.assertEqual(obs.frp, 0.0)

        # Non-numeric FRP rejected
        row_nan = dict(VIIRS_CSV_ROW, frp="bad_frp")
        hotspot, obs, err = HotspotNormalizer.normalize_row_with_diagnostics(row_nan)
        self.assertIsNone(hotspot)
        self.assertIn("Malformed non-numeric FRP", err)

    # 8. Confidence Semantics
    def test_confidence_normalization(self):
        self.assertEqual(HotspotNormalizer.normalize_confidence("l"), "low")
        self.assertEqual(HotspotNormalizer.normalize_confidence("n"), "nominal")
        self.assertEqual(HotspotNormalizer.normalize_confidence("h"), "high")
        self.assertEqual(HotspotNormalizer.normalize_confidence("15"), "low")
        self.assertEqual(HotspotNormalizer.normalize_confidence("50"), "nominal")
        self.assertEqual(HotspotNormalizer.normalize_confidence("95%"), "high")
        self.assertEqual(HotspotNormalizer.normalize_confidence(None), "nominal")

    # 9. Invalid Data Quarantine with Valid Record Continuation
    def test_mixed_csv_with_quarantine(self):
        mixed_csv = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,142.8,N
999.0,-122.8000,350.0,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,140.0,N
38.7468,-122.8052,346.1,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,296.2,118.2,N
38.7000,-122.8000,not_a_temp,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,140.0,N
"""
        observations, hotspots, quarantined_count = HotspotNormalizer.normalize_csv_with_quarantine(
            csv_text=mixed_csv,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            run_id="RUN-TEST-001",
            quarantine_mgr=self.qm,
        )

        # Exactly 2 valid records proceeded
        self.assertEqual(len(observations), 2)
        self.assertEqual(len(hotspots), 2)
        self.assertEqual(quarantined_count, 2)

        # Quarantine verification
        records = self.qm.get_records(run_id="RUN-TEST-001")
        self.assertEqual(len(records), 2)

        reasons = [r.rejection_reason for r in records]
        self.assertTrue(any("out of bounds" in r for r in reasons))
        self.assertTrue(any("non-numeric brightness" in r for r in reasons))

        # Check records file on disk
        self.assertTrue(self.qm.records_file.is_file())
        self.assertEqual(self.qm.count(run_id="RUN-TEST-001"), 2)


if __name__ == "__main__":
    unittest.main()
