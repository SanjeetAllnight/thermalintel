"""Unified Thermal Data Engine Service.

Orchestrates NASA FIRMS satellite ingestion, fallback demo loading, caching,
data normalization, and database persistence.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

from services.api.ingestion.config import config, IngestionConfig
from services.api.ingestion.cache import DataCache, cache
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.firms import FirmsClient, firms_client
from services.api.repositories.hotspot_repository import HotspotRepository, hotspot_repo
from services.api.schemas import (
    Hotspot,
    HotspotsResponse,
    RefreshResponse,
    DataMode,
    RiskLevel,
    SourceType,
)

logger = logging.getLogger(__name__)


class HotspotDataService:
    """Core data engine coordinating FIRMS ingestion, cache, fallback, and persistence."""

    def __init__(
        self,
        repo: Optional[HotspotRepository] = None,
        client: Optional[FirmsClient] = None,
        data_cache: Optional[DataCache] = None,
        cfg: Optional[IngestionConfig] = None,
    ):
        self.repo = repo or hotspot_repo
        self.client = client or firms_client
        self.cache = data_cache or cache
        self.config = cfg or config

    def load_demo_hotspots(self) -> List[Hotspot]:
        """Load deterministic fallback thermal anomaly dataset from disk."""
        path = self.config.sample_hotspots_path
        if not path.is_file():
            logger.warning(f"Sample hotspots file not found at {path}")
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.warning(f"Sample hotspots file at {path} did not contain a JSON list.")
                return []
            return HotspotNormalizer.normalize_records(data)
        except Exception as e:
            logger.error(f"Failed to read or parse sample hotspots from {path}: {e}")
            return []

    def fetch_recent_hotspots(
        self,
        source: Optional[str] = None,
        days: Optional[int] = None,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
        force_sample: bool = False,
    ) -> Tuple[List[Hotspot], DataMode, str]:
        """Fetch thermal hotspots adhering to priority hierarchy:
        
        1. LIVE FIRMS (if key configured and not forced to sample)
        2. VALID CACHE (if live fails or is unavailable)
        3. DEMO DATASET (if cache is absent or expired)
        
        Returns:
            Tuple of (hotspots, data_mode, outcome_message)
        """
        src = source or self.config.default_source
        d = days or self.config.default_days
        cache_key = self.cache.make_key(
            "firms", source=src, days=d, bbox=bbox, area=area
        )

        # 1. Attempt Live NASA FIRMS API
        if not force_sample and self.config.has_firms_key:
            logger.info("Attempting live ingestion from NASA FIRMS API...")
            raw_csv = self.client.fetch_recent_csv(
                source=src, days=d, bbox=bbox, area=area
            )
            if raw_csv:
                hotspots = HotspotNormalizer.normalize_csv(raw_csv)
                if hotspots:
                    # Save successful raw response to cache
                    self.cache.set(cache_key, raw_csv)
                    msg = f"Successfully ingested {len(hotspots)} live thermal anomalies from NASA FIRMS ({src})."
                    logger.info(msg)
                    return hotspots, DataMode.LIVE, msg

        # 2. Attempt Local Ephemeral Cache
        if not force_sample:
            cached_csv = self.cache.get(cache_key)
            if cached_csv:
                hotspots = HotspotNormalizer.normalize_csv(cached_csv)
                if hotspots:
                    msg = f"Retrieved {len(hotspots)} thermal anomalies from local cached FIRMS response."
                    logger.info(msg)
                    return hotspots, DataMode.LIVE, msg

        # 3. Resilient Fallback to Demo Dataset
        logger.info("Loading bundled fallback sample thermal dataset...")
        demo_hotspots = self.load_demo_hotspots()
        msg = f"Operating in high-fidelity demo fallback mode with {len(demo_hotspots)} sample anomalies."
        return demo_hotspots, DataMode.DEMO, msg

    def sync(
        self,
        force_sample: bool = False,
        bbox: Optional[List[float]] = None,
        days: Optional[int] = None,
        source: Optional[str] = None,
        area: Optional[str] = None,
    ) -> RefreshResponse:
        """Execute full synchronization pipeline and persist normalized records.
        
        Guaranteed never to crash the application upon network or API failure.
        """
        start_time = time.time()

        try:
            hotspots, mode, message = self.fetch_recent_hotspots(
                source=source,
                days=days,
                bbox=bbox,
                area=area,
                force_sample=force_sample,
            )

            # Persist to SQLite
            ingested_count = self.repo.upsert_hotspots(hotspots, data_mode=mode.value)

            # Update system metadata
            now_str = datetime.now(timezone.utc).isoformat()
            self.repo.set_data_mode(mode)
            self.repo.set_last_sync(now_str)

            duration = round(time.time() - start_time, 3)
            status_str = "success" if mode == DataMode.LIVE else "fallback_sample"

            return RefreshResponse(
                status=status_str,
                message=message,
                ingested_count=ingested_count,
                data_mode=mode,
                timestamp=now_str,
                execution_time_seconds=duration,
            )
        except Exception as e:
            logger.error(f"Error during thermal data synchronization: {e}", exc_info=True)
            # Safe recovery fallback: ensure demo data is loaded
            demo_hotspots = self.load_demo_hotspots()
            self.repo.upsert_hotspots(demo_hotspots, data_mode="demo")
            now_str = datetime.now(timezone.utc).isoformat()
            self.repo.set_data_mode(DataMode.DEMO)
            self.repo.set_last_sync(now_str)

            return RefreshResponse(
                status="fallback_sample",
                message=f"Sync encountered an error; recovered with sample dataset: {e}",
                ingested_count=len(demo_hotspots),
                data_mode=DataMode.DEMO,
                timestamp=now_str,
                execution_time_seconds=round(time.time() - start_time, 3),
            )

    def get_hotspots(
        self,
        risk_level: Optional[Union[RiskLevel, str]] = None,
        source_type: Optional[Union[SourceType, str]] = None,
        min_frp: Optional[float] = None,
        min_confidence: Optional[str] = None,
        is_anomaly: Optional[bool] = None,
        cluster_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> HotspotsResponse:
        """Retrieve paginated and filtered hotspots from the repository."""
        # Ensure database is seeded if empty
        if self.repo.count_hotspots() == 0:
            demo_hotspots = self.load_demo_hotspots()
            self.repo.upsert_hotspots(demo_hotspots, data_mode="demo")
            self.repo.set_data_mode(DataMode.DEMO)
            self.repo.set_last_sync(datetime.now(timezone.utc).isoformat())

        items, total = self.repo.get_hotspots(
            risk_level=risk_level,
            source_type=source_type,
            min_frp=min_frp,
            min_confidence=min_confidence,
            is_anomaly=is_anomaly,
            cluster_id=cluster_id,
            page=page,
            page_size=page_size,
        )

        current_mode = self.repo.get_data_mode()

        return HotspotsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            data_mode=current_mode,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_hotspot_by_id(self, hotspot_id: str) -> Optional[Hotspot]:
        """Retrieve a specific hotspot by its unique ID."""
        return self.repo.get_by_id(hotspot_id)


# Default singleton instance
data_service = HotspotDataService()
