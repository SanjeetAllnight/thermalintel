#!/usr/bin/env python3
"""CLI utility to query NASA FIRMS API, test connectivity, and inspect thermal anomaly data."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from services.api.data.service import data_service
from services.api.ingestion.config import config


def main():
    parser = argparse.ArgumentParser(description="Fetch and normalize NASA FIRMS thermal anomaly data.")
    parser.add_argument("--source", type=str, default=None, help="FIRMS satellite instrument source (e.g. VIIRS_SNPP_NRT)")
    parser.add_argument("--days", type=int, default=1, help="Number of past days (1-7)")
    parser.add_argument("--area", type=str, default=None, help="Area or country code (e.g. USA_contiguous_and_Hawaii)")
    parser.add_argument("--bbox", type=float, nargs=4, default=None, help="Bounding box: min_lon min_lat max_lon max_lat")
    parser.add_argument("--force-sample", action="store_true", help="Force fallback to local sample dataset")
    parser.add_argument("--sync-db", action="store_true", help="Persist fetched hotspots to SQLite database")

    args = parser.parse_args()

    print("==========================================================")
    print("           ThermalIntel FIRMS Ingestion Utility           ")
    print("==========================================================")
    print(f"FIRMS API Key configured: {'YES' if config.has_firms_key else 'NO (operating in fallback mode)'}")
    print(f"Target Source: {args.source or config.default_source}")
    print(f"Days: {args.days}")
    if args.bbox:
        print(f"Bounding Box: {args.bbox}")

    if args.sync_db:
        print("\n[*] Synchronizing with database...")
        res = data_service.sync(
            force_sample=args.force_sample,
            bbox=args.bbox,
            days=args.days,
            source=args.source,
            area=args.area,
        )
        print(f"[✓] Status: {res.status}")
        print(f"[✓] Mode: {res.data_mode.value}")
        print(f"[✓] Ingested Count: {res.ingested_count}")
        print(f"[✓] Execution Time: {res.execution_time_seconds}s")
        print(f"[✓] Message: {res.message}")
    else:
        print("\n[*] Fetching and normalizing hotspots (dry-run)...")
        hotspots, mode, message = data_service.fetch_recent_hotspots(
            source=args.source,
            days=args.days,
            bbox=args.bbox,
            area=args.area,
            force_sample=args.force_sample,
        )
        print(f"[✓] Mode: {mode.value}")
        print(f"[✓] Total Hotspots: {len(hotspots)}")
        print(f"[✓] Message: {message}")

        if hotspots:
            print(f"\nTop 3 Sample Hotspots:")
            for h in hotspots[:3]:
                print(f"  - [{h.id}] Lat: {h.latitude:.4f}, Lon: {h.longitude:.4f}, FRP: {h.frp} MW, Risk: {h.risk_score} ({h.risk_level.value})")


if __name__ == "__main__":
    main()
