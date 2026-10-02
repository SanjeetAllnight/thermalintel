"""Tests for health and readiness checks."""

import os
import pytest

from services.observability.health.checks import (
    DatabaseHealthCheck,
    ModeHealthCheck,
    StorageHealthCheck,
)
from services.observability.health.service import HealthService


@pytest.mark.anyio
async def test_database_health_check_healthy(tmp_path):
    import sqlite3

    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE hotspots (id TEXT PRIMARY KEY);")
    conn.commit()
    conn.close()

    check = DatabaseHealthCheck(db_path=str(db_file))
    result = await check.check()

    assert result.status == "healthy"
    assert result.latency_ms >= 0


@pytest.mark.anyio
async def test_database_health_check_missing():
    check = DatabaseHealthCheck(db_path="/path/to/nonexistent/db.db")
    result = await check.check()

    assert result.status == "unhealthy"
    assert "does not exist" in result.error


@pytest.mark.anyio
async def test_storage_health_check(tmp_path):
    cache_dir = tmp_path / "cache"
    check = StorageHealthCheck(cache_dir=str(cache_dir))
    result = await check.check()

    assert result.status == "healthy"
    assert os.path.exists(str(cache_dir))


@pytest.mark.anyio
async def test_mode_health_check():
    check = ModeHealthCheck()
    result = await check.check()

    assert result.status in ("healthy", "degraded")
    assert "data_mode" in result.details


@pytest.mark.anyio
async def test_health_service_aggregation(tmp_path):
    import sqlite3

    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE hotspots (id TEXT PRIMARY KEY);")
    conn.commit()
    conn.close()

    service = HealthService(db_path=str(db_file), cache_dir=str(tmp_path / "cache"))

    liveness = await service.check_liveness()
    assert liveness.status == "healthy"

    readiness = await service.check_readiness()
    assert readiness.status == "healthy"
    assert "database" in readiness.checks
    assert "storage" in readiness.checks
