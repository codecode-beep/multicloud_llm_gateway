import math
import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from fastapi import Depends, HTTPException, status

from app.auth import require_api_key
from app.config import rate_limit_burst, rate_limit_per_minute


@dataclass
class Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    def __init__(self, rate_per_sec: float, burst: int):
        self.rate = rate_per_sec
        self.burst = burst
        self._buckets: Dict[str, Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> Tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = Bucket(tokens=self.burst, updated=now)
                self._buckets[key] = bucket

            # Refill based on time passed since the last request
            elapsed = now - bucket.updated
            bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
            bucket.updated = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True, 0.0

            retry_after = (1 - bucket.tokens) / self.rate
            return False, retry_after


limiter = TokenBucketLimiter(
    rate_per_sec=rate_limit_per_minute() / 60,
    burst=rate_limit_burst(),
)


def enforce_rate_limit(api_key: str = Depends(require_api_key)) -> str:
    allowed, retry_after = limiter.allow(api_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
    return api_key