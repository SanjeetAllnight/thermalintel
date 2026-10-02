"""SQLite Database integration for ThermalIntel.

Lightweight, self-contained, zero-dependency persistence layer for local development.
Automatically falls back to loading sample seed data if the database has not yet been populated.
"""

import os
import json
import sqlite3
from typing import List, Optional, Dict, Any
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "thermalintel.db"
SAMPLE_HOTSPOTS_PATH = BASE_DIR / "data" / "sample" / "sample_hotspots.json"
SAMPLE_INCIDENTS_PATH = BASE_DIR / "data" / "sample" / "sample_incidents.json"
SAMPLE_ALERTS_PATH = BASE_DIR / "data" / "sample" / "sample_alerts.json"

from services.api.migrations import run_migrations

DB_PATH = os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database and apply pending migrations to ensure canonical schema."""
    run_migrations(DB_PATH)


def seed_if_empty():
    """Populate database from data/sample if empty."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM hotspots")
        count = cursor.fetchone()["cnt"]
        if count > 0:
            return

        # Load sample hotspots
        if SAMPLE_HOTSPOTS_PATH.exists():
            with open(SAMPLE_HOTSPOTS_PATH, "r", encoding="utf-8") as f:
                hotspots = json.load(f)
                for h in hotspots:
                    cursor.execute("""
                        INSERT OR REPLACE INTO hotspots (
                            id, latitude, longitude, brightness, scan, track,
                            acq_date, acq_time, satellite, instrument, confidence,
                            version, bright_t31, frp, daynight, source_type,
                            risk_score, risk_level, is_anomaly, cluster_id,
                            cluster_size, nearest_place, last_updated, data_mode
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        h["id"], h["latitude"], h["longitude"], h["brightness"],
                        h.get("scan", 0.375), h.get("track", 0.375),
                        h["acq_date"], h["acq_time"], h["satellite"],
                        h.get("instrument", "VIIRS"), h["confidence"],
                        h.get("version", "2.0NRT"), h.get("bright_t31"),
                        h["frp"], h["daynight"], h.get("source_type", "unknown"),
                        h.get("risk_score", 50.0), h.get("risk_level", "medium"),
                        1 if h.get("is_anomaly") else 0,
                        h.get("cluster_id"), h.get("cluster_size", 1),
                        h.get("nearest_place"), h.get("last_updated"),
                        "demo"
                    ))

        # Load sample incidents
        if SAMPLE_INCIDENTS_PATH.exists():
            with open(SAMPLE_INCIDENTS_PATH, "r", encoding="utf-8") as f:
                incidents = json.load(f)
                for hid, inc in incidents.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO incident_details (
                            hotspot_id, geospatial_json, weather_json,
                            historical_json, intelligence_json, timeline_json
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        hid,
                        json.dumps(inc.get("geospatial", {})),
                        json.dumps(inc.get("weather", {})),
                        json.dumps(inc.get("historical", {})),
                        json.dumps(inc.get("intelligence", {})),
                        json.dumps(inc.get("timeline", []))
                    ))

        # Load sample alerts
        if SAMPLE_ALERTS_PATH.exists():
            with open(SAMPLE_ALERTS_PATH, "r", encoding="utf-8") as f:
                alerts = json.load(f)
                for a in alerts:
                    cursor.execute("""
                        INSERT OR REPLACE INTO alerts (
                            id, hotspot_id, severity, title, message,
                            risk_score, location_name, latitude, longitude,
                            timestamp, is_acknowledged, recommended_action, tags_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        a["id"], a["hotspot_id"], a["severity"], a["title"],
                        a["message"], a["risk_score"], a["location_name"],
                        a["latitude"], a["longitude"], a["timestamp"],
                        1 if a.get("is_acknowledged") else 0,
                        a["recommended_action"],
                        json.dumps(a.get("tags", []))
                    ))

        cursor.execute("INSERT OR REPLACE INTO system_meta (key, value) VALUES ('data_mode', 'demo')")
        cursor.execute("INSERT OR REPLACE INTO system_meta (key, value) VALUES ('last_sync', '2026-10-01T08:50:00Z')")
        conn.commit()
