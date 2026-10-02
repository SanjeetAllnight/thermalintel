"""Lightweight SQLite Migration Runner for ThermalIntel V2.

Features:
- Pure Python and zero external dependencies (standard library sqlite3).
- Deterministic, ordered execution of numbered SQL migration files.
- Version tracking in 'schema_migrations' table.
- Upgrades existing V1 databases safely without data loss.
- Safe for fresh database initialization and repeated idempotent execution.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Union
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "sql"


class MigrationRunner:
    """Manages ordered SQLite schema migrations and version tracking."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        if db_path is None:
            from services.api.database import DB_PATH
            self.db_path = str(DB_PATH)
        else:
            self.db_path = str(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Create schema_migrations tracking table if absent."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at_utc TEXT NOT NULL
            )
        """)
        conn.commit()

    def _detect_and_backfill_v1(self, conn: sqlite3.Connection) -> None:
        """Detect existing V1 database tables and register migration 1 if not yet recorded."""
        cursor = conn.cursor()
        # Check if legacy 'hotspots' table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='hotspots'
        """)
        has_hotspots = cursor.fetchone() is not None

        if has_hotspots:
            cursor.execute("SELECT version FROM schema_migrations WHERE version = 1")
            if not cursor.fetchone():
                now_utc = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO schema_migrations (version, name, applied_at_utc)
                    VALUES (1, '0001_v1_baseline.sql', ?)
                """, (now_utc,))
                conn.commit()
                logger.info("Detected pre-existing V1 schema; backfilled migration 1.")

    def get_applied_migrations(self) -> List[int]:
        """Return list of applied migration versions sorted ascending."""
        with self._get_connection() as conn:
            self._ensure_migrations_table(conn)
            self._detect_and_backfill_v1(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
            return [row["version"] for row in cursor.fetchall()]

    def get_current_version(self) -> int:
        """Return current database schema version (0 if unmigrated)."""
        applied = self.get_applied_migrations()
        return max(applied) if applied else 0

    def discover_migrations(self) -> List[Path]:
        """Find and return all .sql migration files sorted by numeric prefix."""
        if not MIGRATIONS_DIR.exists():
            return []
        sql_files = list(MIGRATIONS_DIR.glob("*.sql"))
        
        def parse_version(p: Path) -> int:
            prefix = p.stem.split("_")[0]
            try:
                return int(prefix)
            except ValueError:
                return 999999

        return sorted(sql_files, key=parse_version)

    def apply_migrations(self) -> List[int]:
        """Execute all pending migrations in deterministic order.
        
        Returns:
            List[int]: List of newly applied migration versions.
        """
        applied_now: List[int] = []
        migration_files = self.discover_migrations()

        with self._get_connection() as conn:
            self._ensure_migrations_table(conn)
            self._detect_and_backfill_v1(conn)
            cursor = conn.cursor()

            cursor.execute("SELECT version FROM schema_migrations")
            already_applied = {row["version"] for row in cursor.fetchall()}

            for m_path in migration_files:
                prefix = m_path.stem.split("_")[0]
                try:
                    version = int(prefix)
                except ValueError:
                    logger.warning("Skipping migration with non-integer prefix: %s", m_path.name)
                    continue

                if version in already_applied:
                    continue

                logger.info("Applying migration %04d: %s...", version, m_path.name)
                with open(m_path, "r", encoding="utf-8") as f:
                    sql_content = f.read()

                # Execute migration script in transaction
                cursor.executescript(sql_content)

                # Record migration metadata
                now_utc = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO schema_migrations (version, name, applied_at_utc)
                    VALUES (?, ?, ?)
                """, (version, m_path.name, now_utc))
                conn.commit()

                applied_now.append(version)
                already_applied.add(version)
                logger.info("Successfully applied migration %04d (%s)", version, m_path.name)

        return applied_now


def run_migrations(db_path: Optional[Union[str, Path]] = None) -> List[int]:
    """Convenience helper to apply pending database migrations."""
    runner = MigrationRunner(db_path=db_path)
    return runner.apply_migrations()
