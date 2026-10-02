"""NASA FIRMS (Fire Information for Resource Management System) Ingestion Client.

Supports near-real-time (NRT) satellite thermal detection feeds from VIIRS and MODIS instruments.
Includes robust bounded retry behavior with exponential backoff and jitter for transient errors,
defensive redaction of credentials, granular execution telemetry, and empty feed discrimination.
CRITICAL: Never exposes MAP_KEY in logs, URLs, exceptions, or provider telemetry.
"""

import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import httpx

from services.api.ingestion.config import config, IngestionConfig
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.schemas import Hotspot
from services.api.schemas.v2.common import ProviderStatus, now_utc_iso
from services.api.schemas.v2.provider import ProviderRun

logger = logging.getLogger(__name__)


@dataclass
class FirmsFetchResult:
    """Detailed execution telemetry for a NASA FIRMS API query."""
    status: str  # "success", "empty", "rate_limited", "auth_failed", "timeout", "failed"
    status_code: Optional[int]
    raw_csv: Optional[str]
    rows_received: int
    duration_ms: int
    error_type: Optional[str]
    error_message: Optional[str]
    request_metadata: Dict[str, Any]
    started_at_utc: str
    finished_at_utc: str
    attempts: int = 1
    is_empty: bool = False


def parse_retry_after(header_val: Optional[str], default_delay: float, max_delay: float) -> float:
    """Parse HTTP Retry-After header value (in integer seconds or HTTP date)."""
    if not header_val:
        return default_delay
    try:
        val = float(header_val.strip())
        return max(0.0, min(val, max_delay))
    except ValueError:
        pass

    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(header_val)
        delay = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(delay, max_delay))
    except Exception:
        return default_delay


def compute_backoff(attempt: int, base_backoff: float, max_backoff: float) -> float:
    """Calculate bounded exponential backoff with random jitter."""
    exp_delay = min(max_backoff, base_backoff * (2 ** attempt))
    jitter = random.uniform(0.0, min(1.0, 0.2 * exp_delay))
    return min(max_backoff, exp_delay + jitter)


class FirmsClient:
    """Hardened HTTP Client for querying NASA FIRMS NRT CSV APIs with retry and telemetry."""

    def __init__(self, cfg: Optional[IngestionConfig] = None):
        self.config = cfg or config
        self._last_result: Optional[FirmsFetchResult] = None

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
            bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            return f"{base}/area/csv/{key}/{source}/{bbox_str}/{days}"

        target_area = area or self.config.default_area
        return f"{base}/country/csv/{key}/{source}/{target_area}/{days}"

    def _mask_key(self, text: str) -> str:
        """Sanitize text by defensively redacting any FIRMS API key."""
        if not text:
            return ""
        result = str(text)
        if self.config.firms_map_key:
            result = result.replace(self.config.firms_map_key, "***KEY***")
        # Mask URL patterns matching /csv/<key>/
        result = re.sub(r"(/csv/)[^/]+(/)", r"\1***KEY***\2", result)
        return result

    def fetch_raw(
        self,
        source: Optional[str] = None,
        days: Optional[int] = None,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
        max_retries: int = 3,
        base_backoff: float = 0.5,
        max_backoff: float = 10.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> FirmsFetchResult:
        """Fetch raw CSV from NASA FIRMS API with bounded retry and execution telemetry.
        
        Returns:
            FirmsFetchResult with status, data, and telemetry metadata.
        """
        src = source or self.config.default_source
        d = days or self.config.default_days
        started_at = now_utc_iso()
        start_mono = time.time()

        # Build sanitized request metadata (strictly credential-free)
        safe_metadata: Dict[str, Any] = {
            "source": src,
            "days": d,
        }
        if bbox:
            safe_metadata["bbox"] = bbox
        if area:
            safe_metadata["area"] = area

        if not self.config.has_firms_key:
            return FirmsFetchResult(
                status="auth_failed",
                status_code=None,
                raw_csv=None,
                rows_received=0,
                duration_ms=0,
                error_type="MissingApiKey",
                error_message="FIRMS_MAP_KEY is missing or empty; live ingestion disabled",
                request_metadata=safe_metadata,
                started_at_utc=started_at,
                finished_at_utc=now_utc_iso(),
                attempts=0,
                is_empty=False,
            )

        url = self._build_url(source=src, days=d, bbox=bbox, area=area)
        if not url:
            return FirmsFetchResult(
                status="auth_failed",
                status_code=None,
                raw_csv=None,
                rows_received=0,
                duration_ms=0,
                error_type="UrlBuildError",
                error_message="Failed to build FIRMS URL",
                request_metadata=safe_metadata,
                started_at_utc=started_at,
                finished_at_utc=now_utc_iso(),
                attempts=0,
                is_empty=False,
            )

        masked_url = self._mask_key(url)
        logger.info(f"Querying NASA FIRMS API: {masked_url}")

        attempts_made = 0
        final_status = "failed"
        final_status_code: Optional[int] = None
        final_csv: Optional[str] = None
        final_error_type: Optional[str] = None
        final_error_message: Optional[str] = None
        rows_count = 0
        is_empty_feed = False

        for attempt in range(max_retries + 1):
            attempts_made += 1
            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    response = client.get(url)
                    final_status_code = response.status_code

                    # 1. Successful HTTP 200 Response
                    if response.status_code == 200:
                        text = response.text or ""
                        lower_text = text.lower()

                        # Detect body-level API errors returned with 200 OK
                        if "invalid map key" in lower_text or "invalid key" in lower_text or "invalid or expired map_key" in lower_text:
                            final_status = "auth_failed"
                            final_error_type = "AuthFailed"
                            final_error_message = self._mask_key(text.strip().splitlines()[0] if text else "Invalid map key")
                            logger.warning(f"NASA FIRMS authentication rejected: {final_error_message}")
                            break  # Permanent error: do not retry

                        if "rate limit" in lower_text or "too many requests" in lower_text:
                            final_status = "rate_limited"
                            final_error_type = "RateLimit"
                            final_error_message = "NASA FIRMS rate limit message returned in body"
                            logger.warning(final_error_message)
                            if attempt < max_retries:
                                delay = compute_backoff(attempt, base_backoff, max_backoff)
                                sleep_fn(delay)
                                continue
                            break

                        first_line = text.strip().splitlines()[0].lower() if text.strip() else ""
                        if "error" in first_line or "invalid" in first_line or "html" in first_line:
                            final_status = "failed"
                            final_error_type = "ApiError"
                            final_error_message = self._mask_key(first_line)
                            logger.warning(f"NASA FIRMS returned API error message: {final_error_message}")
                            break  # Permanent malformed error: do not retry

                        # Distinguish empty valid feed from populated feed
                        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
                        if len(lines) <= 1:
                            # Header only or blank body: valid empty detection set
                            final_status = "empty"
                            final_csv = text
                            rows_count = 0
                            is_empty_feed = True
                            final_error_type = None
                            logger.info("NASA FIRMS returned empty feed (0 thermal observations detected).")
                            break
                        else:
                            final_status = "success"
                            final_csv = text
                            rows_count = len(lines) - 1
                            is_empty_feed = False
                            final_error_type = None
                            logger.info(f"NASA FIRMS fetch succeeded with {rows_count} raw observations.")
                            break

                    # 2. HTTP 429 Too Many Requests (Rate Limited)
                    elif response.status_code == 429:
                        final_status = "rate_limited"
                        final_error_type = "RateLimit"
                        final_error_message = f"HTTP 429 Too Many Requests: {self._mask_key(response.text[:200])}"
                        logger.warning(final_error_message)
                        if attempt < max_retries:
                            retry_hdr = response.headers.get("Retry-After")
                            delay = parse_retry_after(retry_hdr, compute_backoff(attempt, base_backoff, max_backoff), max_backoff)
                            logger.info(f"Retrying after {delay:.2f}s due to HTTP 429 (attempt {attempt + 1}/{max_retries})...")
                            sleep_fn(delay)
                            continue
                        break

                    # 3. HTTP 401 / 403 Permanent Authentication Failures
                    elif response.status_code in (401, 403):
                        final_status = "auth_failed"
                        final_error_type = f"Http{response.status_code}"
                        final_error_message = f"NASA FIRMS HTTP {response.status_code}: {self._mask_key(response.text[:200])}"
                        logger.warning(final_error_message)
                        break  # Permanent: do NOT retry

                    # 4. HTTP 5xx Server Errors (Transient)
                    elif response.status_code in (500, 502, 503, 504):
                        final_status = "failed"
                        final_error_type = f"Http{response.status_code}"
                        final_error_message = f"NASA FIRMS server error HTTP {response.status_code}"
                        logger.warning(final_error_message)
                        if attempt < max_retries:
                            retry_hdr = response.headers.get("Retry-After")
                            delay = parse_retry_after(retry_hdr, compute_backoff(attempt, base_backoff, max_backoff), max_backoff)
                            logger.info(f"Retrying after {delay:.2f}s due to HTTP {response.status_code} (attempt {attempt + 1}/{max_retries})...")
                            sleep_fn(delay)
                            continue
                        break

                    # 5. Other HTTP 4xx Client Errors (Permanent)
                    else:
                        final_status = "failed"
                        final_error_type = f"Http{response.status_code}"
                        final_error_message = f"NASA FIRMS HTTP {response.status_code}: {self._mask_key(response.text[:200])}"
                        logger.warning(final_error_message)
                        break

            except httpx.TimeoutException:
                final_status = "timeout"
                final_error_type = "Timeout"
                final_error_message = f"Request timed out after {self.config.timeout_seconds}s"
                logger.warning(final_error_message)
                if attempt < max_retries:
                    delay = compute_backoff(attempt, base_backoff, max_backoff)
                    logger.info(f"Retrying after {delay:.2f}s due to Timeout (attempt {attempt + 1}/{max_retries})...")
                    sleep_fn(delay)
                    continue
                break

            except (httpx.NetworkError, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                final_status = "failed"
                final_error_type = "NetworkError"
                final_error_message = f"Network connection error: {self._mask_key(str(e))}"
                logger.warning(final_error_message)
                if attempt < max_retries:
                    delay = compute_backoff(attempt, base_backoff, max_backoff)
                    logger.info(f"Retrying after {delay:.2f}s due to NetworkError (attempt {attempt + 1}/{max_retries})...")
                    sleep_fn(delay)
                    continue
                break

            except Exception as e:
                final_status = "failed"
                final_error_type = "UnexpectedException"
                final_error_message = f"Unexpected error: {self._mask_key(str(e))}"
                logger.warning(final_error_message)
                break

        duration_ms = max(0, int((time.time() - start_mono) * 1000))
        finished_at = now_utc_iso()

        result = FirmsFetchResult(
            status=final_status,
            status_code=final_status_code,
            raw_csv=final_csv,
            rows_received=rows_count,
            duration_ms=duration_ms,
            error_type=final_error_type,
            error_message=final_error_message,
            request_metadata=safe_metadata,
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            attempts=attempts_made,
            is_empty=is_empty_feed,
        )

        self._last_result = result
        return result

    def fetch_recent_csv(
        self,
        source: Optional[str] = None,
        days: Optional[int] = None,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
    ) -> Optional[str]:
        """Fetch raw CSV data from NASA FIRMS API.
        
        Backward compatible method returning CSV text if successful or empty,
        or None if failed.
        """
        res = self.fetch_raw(source=source, days=days, bbox=bbox, area=area)
        self._last_result = res
        if res.status in ("success", "empty"):
            return res.raw_csv
        return None

    def fetch_and_normalize(
        self,
        source: Optional[str] = None,
        days: Optional[int] = None,
        bbox: Optional[List[float]] = None,
        area: Optional[str] = None,
    ) -> List[Hotspot]:
        """Fetch thermal anomalies from FIRMS and normalize to Hotspot models."""
        raw_csv = self.fetch_recent_csv(source=source, days=days, bbox=bbox, area=area)
        if not raw_csv:
            return []
        return HotspotNormalizer.normalize_csv(raw_csv)

    def to_provider_run(
        self,
        result: FirmsFetchResult,
        run_id: Optional[str] = None,
        payload_id: Optional[str] = None,
    ) -> ProviderRun:
        """Construct a validated canonical ProviderRun from execution telemetry."""
        # Status mapping adhering to frozen ProviderStatus enum
        if result.status in ("success", "empty"):
            run_status = ProviderStatus.SUCCESS
        else:
            run_status = ProviderStatus.FAILED

        effective_run_id = (
            run_id
            or f"RUN-FIRMS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
        )

        return ProviderRun(
            run_id=effective_run_id,
            provider="NASA_FIRMS",
            product=str(result.request_metadata.get("source", "VIIRS_SNPP_NRT")),
            started_at_utc=result.started_at_utc,
            finished_at_utc=result.finished_at_utc,
            status=run_status,
            rows_received=result.rows_received,
            duration_ms=result.duration_ms,
            error_type=result.error_type,
            error_message=result.error_message,
            request_metadata=dict(result.request_metadata),
            payload_id=payload_id,
        )


# Default singleton instance
firms_client = FirmsClient()
