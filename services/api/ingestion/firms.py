"""NASA FIRMS (Fire Information for Resource Management System) Ingestion Client.

Supports near-real-time (NRT) satellite thermal detection feeds from VIIRS and MODIS instruments.
Includes graceful fallback handling for missing API keys, rate limits, timeouts, and network errors.
"""

import logging
from typing import List, Optional, Tuple, Union
import httpx

from services.api.ingestion.config import config, IngestionConfig
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.schemas import Hotspot

logger = logging.getLogger(__name__)


class FirmsClient:
    """HTTP Client for querying NASA FIRMS NRT CSV APIs."""

    def __init__(self, cfg: Optional[IngestionConfig] = None):
        self.config = cfg or config

    def _build_url(
        self,
        source: str,
        days: int,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
    ) -> Optional[str]:
        """Construct FIRMS API URL according to specification.
        
        BBox format: min_lon,min_lat,max_lon,max_lat (West, South, East, North)
        """
        if not self.config.has_firms_key:
            logger.info("FIRMS_MAP_KEY is missing or invalid; skipping live API call.")
            return None

        key = self.config.firms_map_key
        base = self.config.firms_base_url

        if bbox and len(bbox) == 4:
            # Format: min_lon,min_lat,max_lon,max_lat
            bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            return f"{base}/area/csv/{key}/{source}/{bbox_str}/{days}"
        
        target_area = area or self.config.default_area
        return f"{base}/country/csv/{key}/{source}/{target_area}/{days}"

    def fetch_recent_csv(
        self,
        source: Optional[str] = None,
        days: Optional[int] = None,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
    ) -> Optional[str]:
        """Fetch raw CSV data from NASA FIRMS API.
        
        Returns:
            Raw CSV text if successful, or None if failed/offline/no key.
        """
        src = source or self.config.default_source
        d = days or self.config.default_days
        url = self._build_url(source=src, days=d, bbox=bbox, area=area)

        if not url:
            return None

        # Mask key in logs for security
        masked_url = url.replace(self.config.firms_map_key, "***KEY***")
        logger.info(f"Querying NASA FIRMS API: {masked_url}")

        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.get(url)
                if response.status_code != 200:
                    logger.warning(
                        f"NASA FIRMS returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                    return None

                text = response.text
                if not text or not text.strip():
                    logger.warning("NASA FIRMS returned an empty response.")
                    return None

                # Check if FIRMS returned an error string in body instead of CSV
                first_line = text.strip().splitlines()[0].lower()
                if "error" in first_line or "invalid" in first_line or "html" in first_line:
                    logger.warning(f"NASA FIRMS returned API error message: {first_line}")
                    return None

                return text

        except httpx.TimeoutException:
            logger.warning(f"NASA FIRMS API request timed out after {self.config.timeout_seconds}s.")
            return None
        except httpx.RequestError as e:
            logger.warning(f"NASA FIRMS API network request error: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error querying NASA FIRMS API: {e}")
            return None

    def fetch_and_normalize(
        self,
        source: Optional[str] = None,
        days: Optional[int] = None,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
    ) -> List[Hotspot]:
        """Fetch thermal anomalies from FIRMS and normalize to Hotspot models.
        
        Returns:
            List of Hotspot models, or empty list on failure.
        """
        raw_csv = self.fetch_recent_csv(source=source, days=days, bbox=bbox, area=area)
        if not raw_csv:
            return []
        return HotspotNormalizer.normalize_csv(raw_csv)


# Default singleton instance
firms_client = FirmsClient()
