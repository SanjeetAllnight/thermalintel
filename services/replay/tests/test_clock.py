"""Unit tests for Clock abstraction and AS_OF timestamp semantics."""

import unittest
from datetime import datetime, timezone, timedelta
import time

from services.replay.clock import Clock, RealClock, SimulatedClock


class TestClockAbstraction(unittest.TestCase):
    """Test RealClock and SimulatedClock behavior."""

    def test_real_clock_basic(self):
        clock = RealClock()
        t1 = clock.now_utc()
        self.assertIsInstance(t1, datetime)
        self.assertEqual(t1.tzinfo, timezone.utc)
        iso_str = clock.now_iso()
        self.assertIn("+00:00", iso_str)

    def test_real_clock_sleep(self):
        clock = RealClock()
        start = time.time()
        clock.sleep(0.05)
        elapsed = time.time() - start
        self.assertGreaterEqual(elapsed, 0.04)

    def test_simulated_clock_initialization(self):
        # From ISO string with Z
        clock = SimulatedClock("2026-10-01T12:00:00Z")
        self.assertEqual(clock.now_utc(), datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(clock.now_iso(), "2026-10-01T12:00:00+00:00")

        # From datetime without tzinfo (auto-assigns UTC)
        clock2 = SimulatedClock(datetime(2026, 10, 1, 15, 30))
        self.assertEqual(clock2.now_utc().tzinfo, timezone.utc)
        self.assertEqual(clock2.now_utc().hour, 15)

    def test_simulated_clock_advance(self):
        clock = SimulatedClock("2026-10-01T12:00:00Z")
        # Advance with seconds (float)
        clock.advance(3600.0)
        self.assertEqual(clock.now_utc(), datetime(2026, 10, 1, 13, 0, 0, tzinfo=timezone.utc))

        # Advance with timedelta
        clock.advance(timedelta(minutes=30))
        self.assertEqual(clock.now_utc(), datetime(2026, 10, 1, 13, 30, 0, tzinfo=timezone.utc))

    def test_simulated_clock_sleep_advances_simulated_time(self):
        clock = SimulatedClock("2026-10-01T12:00:00Z")
        clock.sleep(120.0)
        self.assertEqual(clock.now_utc(), datetime(2026, 10, 1, 12, 2, 0, tzinfo=timezone.utc))

    def test_simulated_clock_set_time(self):
        clock = SimulatedClock("2026-10-01T12:00:00Z")
        clock.set_time("2026-10-02T08:00:00Z")
        self.assertEqual(clock.now_utc(), datetime(2026, 10, 2, 8, 0, 0, tzinfo=timezone.utc))

    def test_simulated_clock_reset(self):
        clock = SimulatedClock("2026-10-01T12:00:00Z")
        clock.advance(7200)
        self.assertEqual(clock.now_utc().hour, 14)
        clock.reset()
        self.assertEqual(clock.now_utc(), datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc))

    def test_as_of_semantics_distinct_from_created_at(self):
        """Verify Requirement 2: as_of_utc != created_at_utc."""
        simulated_clock = SimulatedClock("2020-05-15T09:30:00Z")
        real_clock = RealClock()

        as_of_utc = simulated_clock.now_iso()
        created_at_utc = real_clock.now_iso()

        self.assertNotEqual(as_of_utc, created_at_utc)
        self.assertTrue(as_of_utc.startswith("2020-05-15"))
        # Real clock year is current year (2026)
        self.assertTrue(created_at_utc.startswith("2026"))


if __name__ == "__main__":
    unittest.main()
