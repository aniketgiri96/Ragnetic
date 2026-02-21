"""In-memory request rate limiting."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - now))
                return False, retry_after
            events.append(now)
            return True, 0


limiter = RateLimiter()


DEFAULT_RULES: dict[str, RateLimitRule] = {
    "auth:register": RateLimitRule(limit=10, window_seconds=60),
    "auth:login": RateLimitRule(limit=20, window_seconds=60),
    "upload": RateLimitRule(limit=30, window_seconds=60),
    "search": RateLimitRule(limit=120, window_seconds=60),
    "chat": RateLimitRule(limit=90, window_seconds=60),
}


def enforce_rate_limit(scope: str, key: str, rule: RateLimitRule | None = None) -> None:
    active_rule = rule or DEFAULT_RULES[scope]
    allowed, retry_after = limiter.hit(key=f"{scope}:{key}", limit=active_rule.limit, window_seconds=active_rule.window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
