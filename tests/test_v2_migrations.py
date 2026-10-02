"""Tests for ThermalIntel V2 Database Migration Runner.

Verifies:
- Fresh database migration from scratch creates all schema tables.
- Upgrading a legacy V1 database preserves existing data and adds V2 tables.
- Migration version tracking in schema_migrations.
- Idempotency: repeated execution does not re-apply or error.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.api.migrations.runner import MigrationRunner, run_migrations


class TestDatabaseMigrations(unittest.TestCase):
    """Test suite for numbered SQL migration runner and version tracking."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_migration.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fresh_database_migration(self):
        """A brand new database should apply all migrations (0001, 0002) in order."""
        runner = MigrationRunner(self.db_path)
        self.assertEqual(runner.get_current_version(), 0)

        applied = runner.apply_migrations()
        self.assertEqual(applied, [1, 2])
        self.assertEqual(runner.get_current_version(), 2)

        # Verify tables created
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "schema_migrations",
            "hotspots",
            "incident_details",
            "alerts",
            "system_meta",
            "raw_payloads",
            "provider_runs",
            "observations",
            "enrichment_snapshots",
            "assessments",
            "incidents",
            "incident_observations",
            "incident_events",
            "alerts_v2",
        }
        self.assertTrue(expected_tables.issubset(tables))

    def test_upgrade_from_v1_database(self):
        """Simulate an existing V1 database with pre-populated data and upgrade to V2."""
        # Create legacy V1 database manually without schema_migrations table
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE hotspots (
                    id TEXT PRIMARY KEY,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    brightness REAL NOT NULL,
                    acq_date TEXT NOT NULL,
                    acq_time TEXT NOT NULL,
                    satellite TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    frp REAL NOT NULL,
                    daynight TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            cursor.execute("""
                INSERT INTO hotspots (
                    id, latitude, longitude, brightness, acq_date, acq_time,
                    satellite, confidence, frp, daynight, source_type,
                    risk_score, risk_level, last_updated
                ) VALUES (
                    'V1-HOTSPOT-001', 34.05, -118.25, 330.5, '2026-10-01', '1200',
                    'Suomi-NPP', 'high', 45.2, 'D', 'wildfire', 65.0, 'high', '2026-10-01T12:05:00Z'
                )
            """)
            conn.commit()

        # Run migration on the existing V1 database
        runner = MigrationRunner(self.db_path)
        applied = runner.apply_migrations()

        # Should detect V1, backfill migration 1, and apply only migration 2
        self.assertEqual(applied, [2])
        self.assertEqual(runner.get_current_version(), 2)

        # Verify that original V1 data is 100% preserved
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hotspots WHERE id = 'V1-HOTSPOT-001'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["id"], "V1-HOTSPOT-001")
            self.assertEqual(row["frp"], 45.2)

            # And verify V2 tables were created
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='observations'")
            self.assertIsNotNone(cursor.fetchone())

    def test_migration_version_tracking(self):
        """Verify schema_migrations tracks versions and applied timestamps."""
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schema_migrations ORDER BY version ASC")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["version"], 1)
            self.assertEqual(rows[0]["name"], "0001_v1_baseline.sql")
            self.assertTrue(rows[0]["applied_at_utc"].endswith("+00:00") or "T" in rows[0]["applied_at_utc"])
            self.assertEqual(rows[1]["version"], 2)
            self.assertEqual(rows[1]["name"], "0002_v2_canonical_schema.sql")

    def test_idempotent_repeated_invocation(self):
        """Running migrations multiple times should be safe and return empty list."""
        runner = MigrationRunner(self.db_path)
        first_applied = runner.apply_migrations()
        self.assertEqual(first_applied, [1, 2])

        second_applied = runner.apply_migrations()
        self.assertEqual(second_applied, [])
        self.assertEqual(runner.get_current_version(), 2)


if __name__ == "__main__":
    unittest.main()
