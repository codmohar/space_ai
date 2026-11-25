"""Sliding-window rate limiting helper returning structured 429 errors."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from app.core.errors import ApiError


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            q = self._buckets[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                retry_after = max(1, int(window_seconds - (now - q[0])))
                raise ApiError(
                    "RATE_LIMIT_EXCEEDED",
                    f"Rate limit exceeded ({limit} requests/{window_seconds}s). Retry after {retry_after}s.",
                    status_code=429,
                    details={"retry_after_seconds": retry_after, "limit": limit},
                )
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = SlidingWindowRateLimiter()


def client_rate_key(request: Request, bucket: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{bucket}:{ip}"
