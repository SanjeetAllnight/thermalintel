"""Rate limiting, concurrency protection, and bounded retries for Overpass API.

Prevents request storms and protects external OpenStreetMap Overpass servers:
- Configurable concurrency semaphore (default max 2 concurrent network queries)
- Token spacing / minimum interval enforcement between requests
- Bounded retries with exponential backoff for 429 (rate limited) and 5xx errors
- Respects HTTP Retry-After header
- Circuit-breaker style temporary cooldown on repeated provider failure
"""

from contextlib import contextmanager
import logging
import os
import threading
import time
from typing import Callable, Optional, Tuple, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_MIN_SPACING_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_FACTOR = 1.5
DEFAULT_COOLDOWN_SECONDS = 30.0


class OverpassRateLimiter:
    """Thread-safe rate limiter and concurrency guard for Overpass queries."""

    def __init__(
        self,
        max_concurrency: Optional[int] = None,
        min_spacing_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None
    ):
        concurrency = max_concurrency or int(os.getenv("OVERPASS_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY))
        self.min_spacing = min_spacing_seconds or float(os.getenv("OVERPASS_MIN_SPACING_SECONDS", DEFAULT_MIN_SPACING_SECONDS))
        self.max_retries = max_retries or int(os.getenv("OVERPASS_MAX_RETRIES", DEFAULT_MAX_RETRIES))
        self.backoff_factor = backoff_factor or DEFAULT_BACKOFF_FACTOR

        self._semaphore = threading.Semaphore(max(1, concurrency))
        self._lock = threading.Lock()
        self._last_request_time: float = 0.0
        self._consecutive_failures: int = 0
        self._cooldown_until: float = 0.0

    @property
    def is_in_cooldown(self) -> bool:
        """True if rate limiter is in temporary cooldown after provider failure."""
        return time.time() < self._cooldown_until

    def record_success(self) -> None:
        """Reset consecutive failure counter on successful response."""
        with self._lock:
            self._consecutive_failures = 0
            self._cooldown_until = 0.0

    def record_failure(self, is_rate_limited: bool = False) -> None:
        """Record provider failure and trigger cooldown if threshold exceeded."""
        with self._lock:
            self._consecutive_failures += 1
            if is_rate_limited or self._consecutive_failures >= 3:
                cooldown_dur = DEFAULT_COOLDOWN_SECONDS if not is_rate_limited else 60.0
                self._cooldown_until = time.time() + cooldown_dur
                logger.warning(
                    "Overpass entering temporary cooldown for %.1fs after %d consecutive failures (rate_limited=%s)",
                    cooldown_dur, self._consecutive_failures, is_rate_limited
                )

    @contextmanager
    def guard(self):
        """Context manager acquiring concurrency slot and enforcing minimum inter-call spacing."""
        self._semaphore.acquire()
        try:
            # Enforce minimum spacing
            with self._lock:
                now = time.time()
                elapsed = now - self._last_request_time
                if elapsed < self.min_spacing:
                    sleep_time = self.min_spacing - elapsed
                    time.sleep(sleep_time)
                self._last_request_time = time.time()

            yield

        finally:
            self._semaphore.release()

    def execute_with_retry(
        self,
        func: Callable[[], httpx.Response]
    ) -> Tuple[Optional[httpx.Response], Optional[str]]:
        """Execute HTTP query with concurrency guard, spacing, and bounded retries.
        
        Returns:
            Tuple of (response_or_None, error_message_or_None).
        """
        if self.is_in_cooldown:
            remaining = int(self._cooldown_until - time.time())
            return None, f"Overpass in temporary cooldown ({remaining}s remaining after provider failure)"

        last_error: Optional[str] = None

        for attempt in range(self.max_retries + 1):
            try:
                with self.guard():
                    resp = func()

                # Success
                if resp.status_code == 200:
                    self.record_success()
                    return resp, None

                # Rate limited (429)
                if resp.status_code == 429:
                    retry_after_hdr = resp.headers.get("Retry-After")
                    delay = float(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else (self.backoff_factor ** (attempt + 1))
                    delay = min(delay, 10.0)  # Bound delay
                    last_error = f"Overpass HTTP 429 Too Many Requests (attempt {attempt + 1}/{self.max_retries + 1})"
                    logger.warning("%s. Backing off for %.1fs", last_error, delay)
                    self.record_failure(is_rate_limited=True)
                    if attempt < self.max_retries:
                        time.sleep(delay)
                        continue
                    return None, last_error

                # Server error (502, 503, 504)
                if resp.status_code in (502, 503, 504):
                    delay = min(5.0, self.backoff_factor ** (attempt + 1))
                    last_error = f"Overpass HTTP {resp.status_code} Server Error"
                    logger.warning("%s. Retrying in %.1fs", last_error, delay)
                    self.record_failure(is_rate_limited=False)
                    if attempt < self.max_retries:
                        time.sleep(delay)
                        continue
                    return None, last_error

                # Other HTTP failure (e.g. 400 Bad Request)
                last_error = f"Overpass HTTP {resp.status_code}: {resp.text[:120]}"
                self.record_failure(is_rate_limited=False)
                return None, last_error

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                delay = min(4.0, self.backoff_factor ** (attempt + 1))
                last_error = f"Overpass network error: {type(e).__name__} - {e}"
                logger.warning("%s (attempt %d/%d). Retrying in %.1fs", last_error, attempt + 1, self.max_retries + 1, delay)
                self.record_failure(is_rate_limited=False)
                if attempt < self.max_retries:
                    time.sleep(delay)
                    continue
                return None, last_error
            except Exception as e:
                last_error = f"Unexpected Overpass execution exception: {e}"
                logger.error(last_error)
                self.record_failure(is_rate_limited=False)
                return None, last_error

        return None, last_error
