#!/usr/bin/env python3
"""Seed the ThermalIntel SQLite database with sample datasets."""

import os
import sys
from pathlib import Path

# Add project root to python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from services.api.database import init_db, seed_if_empty, get_connection

def main():
    force = "--force" in sys.argv
    print(f"[*] Initializing ThermalIntel SQLite database (force={force})...")
    
    if force:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS hotspots")
            cursor.execute("DROP TABLE IF EXISTS incident_details")
            cursor.execute("DROP TABLE IF EXISTS alerts")
            cursor.execute("DROP TABLE IF EXISTS system_meta")
            conn.commit()
        print("[*] Dropped existing tables.")

    init_db()
    seed_if_empty()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM hotspots")
        hotspot_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM alerts")
        alert_count = cursor.fetchone()["cnt"]

    print(f"[✓] Database populated successfully!")
    print(f"    - Hotspots: {hotspot_count}")
    print(f"    - Alerts: {alert_count}")

if __name__ == "__main__":
    main()
