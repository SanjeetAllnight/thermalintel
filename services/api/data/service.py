"""Unified Thermal Data Engine Service for ThermalIntel V2.

Orchestrates NASA FIRMS satellite ingestion, raw payload content-addressed storage,
quarantine of malformed rows, observation persistence, telemetry auditing,
cache management, and backward-compatible V1 demo fallback.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union
from uuid import uuid4

from services.api.ingestion.config import config, IngestionConfig
from services.api.ingestion.cache import DataCache, cache
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.firms import FirmsClient, firms_client
from services.api.ingestion.payload_store import RawPayloadStore, payload_store as default_payload_store
from services.api.ingestion.quarantine import QuarantineManager, quarantine_manager as default_quarantine_mgr
from services.api.repositories.hotspot_repository import HotspotRepository, hotspot_repo
from services.api.repositories.observation_repository import ObservationRepository, observation_repo
from services.api.repositories.provider_run_repository import ProviderRunRepository, provider_run_repo
from services.api.repositories.raw_payload_repository import RawPayloadRepository, raw_payload_repo
from services.api.schemas import (
    Hotspot,
    HotspotsResponse,
    RefreshResponse,
    DataMode,
    RiskLevel,
    SourceType,
)
from services.api.schemas.v2.common import ProviderStatus, FreshnessState, now_utc_iso
from services.api.schemas.v2.converters import observation_from_hotspot
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.provider import ProviderRun

logger = logging.getLogger(__name__)


class HotspotDataService:
    """Core data engine coordinating FIRMS ingestion, cache, fallback, and persistence."""

    def __init__(
        self,
        repo: Optional[HotspotRepository] = None,
        client: Optional[FirmsClient] = None,
        data_cache: Optional[DataCache] = None,
        cfg: Optional[IngestionConfig] = None,
        obs_repo: Optional[ObservationRepository] = None,
        run_repo: Optional[ProviderRunRepository] = None,
        payload_repo: Optional[RawPayloadRepository] = None,
        payload_store: Optional[RawPayloadStore] = None,
        quarantine_mgr: Optional[QuarantineManager] = None,
    ):
        self.repo = repo or hotspot_repo
        self.client = client or firms_client
        self.cache = data_cache or cache
        self.config = cfg or config
        self.obs_repo = obs_repo or observation_repo
        self.run_repo = run_repo or provider_run_repo
        self.payload_repo = payload_repo or raw_payload_repo
        self.payload_store = payload_store or default_payload_store
        self.quarantine_mgr = quarantine_mgr or default_quarantine_mgr

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
        run_id = f"RUN-FIRMS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"

        # 1. Attempt Live NASA FIRMS API
        if not force_sample and self.config.has_firms_key:
            logger.info("Attempting live ingestion from NASA FIRMS API...")
            raw_csv = self.client.fetch_recent_csv(
                source=src, days=d, bbox=bbox, area=area
            )

            # Check if fetch was successful or valid empty
            fetch_res = self.client._last_result

            if raw_csv is not None:
                # Store raw payload immutably
                try:
                    payload_meta = self.payload_store.store_payload(
                        content=raw_csv,
                        provider="NASA_FIRMS",
                        product=src,
                    )
                    self.payload_repo.save_payload_metadata(payload_meta)
                    payload_id = payload_meta.payload_id
                except Exception as e:
                    logger.warning(f"Failed storing raw payload: {e}")
                    payload_id = None

                # Normalize records with quarantine of bad rows
                observations, hotspots, quarantined_count = HotspotNormalizer.normalize_csv_with_quarantine(
                    csv_text=raw_csv,
                    provider="NASA_FIRMS",
                    product=src,
                    run_id=run_id,
                    quarantine_mgr=self.quarantine_mgr,
                    raw_payload_id=payload_id,
                )

                # Persist observations to database
                if observations:
                    self.obs_repo.save_observations(observations)

                # Save raw response to cache
                self.cache.set(cache_key, raw_csv)

                # Check empty feed vs populated feed
                if fetch_res and fetch_res.is_empty:
                    # Valid empty response from FIRMS
                    run = self.client.to_provider_run(fetch_res, run_id=run_id, payload_id=payload_id)
                    self.run_repo.save_run(run)
                    msg = f"NASA FIRMS returned 0 active thermal anomalies ({src})."
                    logger.info(msg)
                    return [], DataMode.LIVE, msg

                if hotspots:
                    if fetch_res:
                        run = self.client.to_provider_run(fetch_res, run_id=run_id, payload_id=payload_id)
                    else:
                        run = ProviderRun(
                            run_id=run_id,
                            provider="NASA_FIRMS",
                            product=src,
                            status=ProviderStatus.SUCCESS,
                            rows_received=len(observations),
                            payload_id=payload_id,
                            request_metadata={"source": src, "days": d},
                        )
                    self.run_repo.save_run(run)
                    msg = f"Successfully ingested {len(hotspots)} live thermal anomalies from NASA FIRMS ({src})."
                    if quarantined_count > 0:
                        msg += f" ({quarantined_count} invalid records quarantined)"
                    logger.info(msg)
                    return hotspots, DataMode.LIVE, msg

            else:
                # Live fetch failed: record failed ProviderRun telemetry
                if fetch_res:
                    failed_run = self.client.to_provider_run(fetch_res, run_id=run_id)
                    self.run_repo.save_run(failed_run)

        # 2. Attempt Local Ephemeral Cache (check fresh or intentional stale fallback)
        if not force_sample:
            # First check fresh cache
            cached_csv = self.cache.get(cache_key, allow_stale=False)
            is_stale_fallback = False
            if not cached_csv:
                # If fresh cache missing, check if stale cache is available
                cached_csv = self.cache.get(cache_key, allow_stale=True)
                is_stale_fallback = cached_csv is not None

            if cached_csv:
                meta = self.cache.get_metadata(cache_key)
                age_str = f"{meta.age_seconds:.0f}s" if meta else "unknown"
                observations, hotspots, _ = HotspotNormalizer.normalize_csv_with_quarantine(
                    csv_text=cached_csv,
                    provider="NASA_FIRMS",
                    product=src,
                    run_id=run_id,
                    quarantine_mgr=self.quarantine_mgr,
                )
                if observations:
                    self.obs_repo.save_observations(observations)

                if hotspots:
                    if is_stale_fallback:
                        msg = f"Retrieved {len(hotspots)} thermal anomalies from stale cached FIRMS response (age: {age_str}) due to provider unavailability."
                    else:
                        msg = f"Retrieved {len(hotspots)} thermal anomalies from local cached FIRMS response."
                    logger.info(msg)
                    return hotspots, DataMode.LIVE, msg

        # 3. Resilient Fallback to Demo Dataset
        logger.info("Loading bundled fallback sample thermal dataset...")
        demo_hotspots = self.load_demo_hotspots()
        # Persist demo observations
        demo_obs = [observation_from_hotspot(h) for h in demo_hotspots]
        if demo_obs:
            self.obs_repo.save_observations(demo_obs)

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
            now_str = now_utc_iso()
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
            demo_obs = [observation_from_hotspot(h) for h in demo_hotspots]
            if demo_obs:
                self.obs_repo.save_observations(demo_obs)

            now_str = now_utc_iso()
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
            demo_obs = [observation_from_hotspot(h) for h in demo_hotspots]
            if demo_obs:
                self.obs_repo.save_observations(demo_obs)
            self.repo.set_data_mode(DataMode.DEMO)
            self.repo.set_last_sync(now_utc_iso())

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
            generated_at=now_utc_iso(),
        )

    def get_hotspot_by_id(self, hotspot_id: str) -> Optional[Hotspot]:
        """Retrieve a specific hotspot by its unique ID."""
        return self.repo.get_by_id(hotspot_id)


# Default singleton instance
data_service = HotspotDataService()
