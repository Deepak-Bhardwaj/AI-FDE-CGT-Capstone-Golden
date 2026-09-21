"""Rate limiting.

Every advisory tool in this service already declared a rate limit in its contract. Nothing
enforced it, which made the limit a description of intent rather than a control - the shape of
gap this codebase exists to find.

The limiter is a sliding window rather than a fixed one. A fixed window lets a caller spend its
whole allowance at the end of one minute and again at the start of the next, which is twice the
declared rate at the moment it matters least to be wrong about.

Refusal carries the time to wait. A limit that says "no" without saying "how long" turns a
well-behaved client into a polling one.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

WINDOWS: dict[str, int] = {
    "sec": 1, "second": 1, "s": 1,
    "min": 60, "minute": 60, "m": 60,
    "hour": 3600, "hr": 3600, "h": 3600,
    "day": 86_400, "d": 86_400,
}

_SPEC = re.compile(r"^\s*(\d+)\s*/\s*([a-z]+)\s*$", re.IGNORECASE)


class RateLimitExceeded(RuntimeError):
    """Raised when a caller has spent its declared allowance."""

    def __init__(self, message: str, retry_after: int, limit: str) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.limit = limit


@dataclass(frozen=True)
class Limit:
    count: int
    window_seconds: int
    spec: str

    def as_dict(self) -> dict:
        return {"limit": self.spec, "count": self.count, "window_seconds": self.window_seconds}


def parse(spec: str) -> Limit | None:
    """'120/min' -> Limit(120, 60). An unparseable or unlimited spec limits nothing."""
    match = _SPEC.match(spec or "")
    if not match:
        return None
    count, unit = int(match.group(1)), match.group(2).lower()
    window = WINDOWS.get(unit)
    if window is None or count <= 0:
        return None
    return Limit(count, window, spec.strip())


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: Limit | None, now: float | None = None) -> None:
        """Record one use, or refuse and say how long to wait."""
        if limit is None:
            return
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]
        cutoff = moment - limit.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit.count:
            retry_after = max(1, int(hits[0] + limit.window_seconds - moment) + 1)
            raise RateLimitExceeded(
                f"'{key}' has used its allowance of {limit.spec}. Try again in "
                f"{retry_after} second(s).", retry_after, limit.spec)
        hits.append(moment)

    def used(self, key: str, limit: Limit | None, now: float | None = None) -> int:
        if limit is None:
            return 0
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]
        cutoff = moment - limit.window_seconds
        return sum(1 for hit in hits if hit > cutoff)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


LIMITER = SlidingWindow()
