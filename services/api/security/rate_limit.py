"""In-process thread-safe rate limiter for mutating and expensive operations."""

import time
import threading
from typing import Dict, List, Optional, Tuple
from fastapi import Request, HTTPException, status

from services.api.config import get_api_config


class InProcessRateLimiter:
    """Sliding-window in-process rate limiter."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int]:
        """Check whether a request under `key` is allowed.
        
        Returns:
            (is_allowed, retry_after_seconds)
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Clean old entries
            timestamps = self._history.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= self.max_requests:
                earliest = valid_timestamps[0]
                retry_after = max(1, int(earliest + self.window_seconds - now))
                self._history[key] = valid_timestamps
                return False, retry_after

            valid_timestamps.append(now)
            self._history[key] = valid_timestamps
            return True, 0

    def reset(self) -> None:
        """Clear all rate limit state (primarily for tests)."""
        with self._lock:
            self._history.clear()


# Default singleton instance for refresh endpoint
_refresh_rate_limiter: Optional[InProcessRateLimiter] = None


def get_refresh_rate_limiter() -> InProcessRateLimiter:
    global _refresh_rate_limiter
    if _refresh_rate_limiter is None:
        cfg = get_api_config().security
        _refresh_rate_limiter = InProcessRateLimiter(
            max_requests=cfg.refresh_rate_limit_calls,
            window_seconds=cfg.refresh_rate_limit_window_seconds,
        )
    return _refresh_rate_limiter


def set_refresh_rate_limiter(limiter: Optional[InProcessRateLimiter]) -> None:
    global _refresh_rate_limiter
    _refresh_rate_limiter = limiter


def verify_refresh_rate_limit(request: Request) -> None:
    """FastAPI dependency to rate-limit refresh requests."""
    limiter = get_refresh_rate_limiter()
    # Resolve client identifier: X-Forwarded-For or client host
    client_ip = request.headers.get("X-Forwarded-For")
    if client_ip:
        client_key = client_ip.split(",")[0].strip()
    elif request.client and request.client.host:
        client_key = request.client.host
    else:
        client_key = "anonymous"

    allowed, retry_after = limiter.check(client_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for data refresh. Please retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
