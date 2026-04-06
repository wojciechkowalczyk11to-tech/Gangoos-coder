"""
Rate Limiter - Token bucket algorithm with per-domain limits.
In-memory implementation suitable for single-server deployments.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class TokenBucket:
    """Token bucket for rate limiting with sliding window semantics."""
    capacity: int          # Max tokens in bucket
    refill_rate: float     # Tokens per second
    tokens: float = field(default_factory=float)  # Current tokens
    last_refill: float = field(default_factory=time.time)
    lock: Lock = field(default_factory=Lock)

    def __post_init__(self):
        self.tokens = float(self.capacity)

    def try_consume(self, amount: int = 1) -> bool:
        """
        Try to consume tokens. Returns True if successful, False if rate-limited.
        Thread-safe.
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill

            # Refill tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + (elapsed * self.refill_rate)
            )
            self.last_refill = now

            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    def get_reset_after(self) -> float:
        """Get seconds until next token is available."""
        with self.lock:
            if self.tokens >= 1:
                return 0.0
            # Time needed to generate 1 token
            return (1 - self.tokens) / self.refill_rate if self.refill_rate > 0 else 0.0


class RateLimiter:
    """Rate limiter managing per-domain limits with per-token granularity."""

    def __init__(self, config: dict[str, int] | None = None):
        """
        Initialize rate limiter with per-domain limits (requests per minute).

        Args:
            config: dict mapping domain -> requests_per_minute
                   Default: {control: 10, llm: 30, research: 60, knowledge: 120}
        """
        self._config = config or {
            "control": 10,
            "llm": 30,
            "research": 60,
            "knowledge": 120,
            "default": 30,
        }
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = Lock()

    def _get_bucket(self, token: str) -> TokenBucket:
        """Get or create token bucket for a given token."""
        if token not in self._buckets:
            with self._lock:
                if token not in self._buckets:
                    # Convert requests/minute to tokens/second
                    rpm = self._config.get("default", 30)
                    rps = rpm / 60.0
                    self._buckets[token] = TokenBucket(
                        capacity=int(rpm // 5) or 1,  # Burst capacity
                        refill_rate=rps,
                    )
        return self._buckets[token]

    def _get_bucket_for_domain(self, domain: str, token: str) -> TokenBucket:
        """Get or create token bucket for a token/domain pair."""
        bucket_key = f"{token}:{domain}"
        if bucket_key not in self._buckets:
            with self._lock:
                if bucket_key not in self._buckets:
                    rpm = self._config.get(domain, self._config.get("default", 30))
                    rps = rpm / 60.0
                    self._buckets[bucket_key] = TokenBucket(
                        capacity=rpm,
                        refill_rate=rps,
                    )
        return self._buckets[bucket_key]

    def check_limit(self, token: str, domain: str, amount: int = 1) -> tuple[bool, float]:
        """
        Check if request is within rate limit.

        Args:
            token: Bearer token or identifier
            domain: Tool domain (control, llm, research, knowledge, etc.)
            amount: Number of tokens to consume (default 1)

        Returns:
            (allowed: bool, reset_after_seconds: float)
        """
        bucket = self._get_bucket_for_domain(domain, token)
        allowed = bucket.try_consume(amount)
        reset_after = bucket.get_reset_after()
        return allowed, reset_after

    def get_stats(self, token: str | None = None) -> dict:
        """Get rate limiter statistics."""
        stats = {
            "config": self._config,
            "buckets": {},
        }

        if token:
            # Stats for specific token
            for domain in self._config:
                bucket_key = f"{token}:{domain}"
                if bucket_key in self._buckets:
                    bucket = self._buckets[bucket_key]
                    with bucket.lock:
                        stats["buckets"][domain] = {
                            "capacity": bucket.capacity,
                            "current": bucket.tokens,
                            "refill_rate": bucket.refill_rate,
                        }
        else:
            # Overall stats (don't expose individual tokens)
            stats["total_buckets"] = len(self._buckets)

        return stats

    def reset(self, token: str | None = None):
        """Reset rate limits. For testing/admin use."""
        if token:
            with self._lock:
                keys_to_remove = [k for k in self._buckets if k.startswith(f"{token}:")]
                for key in keys_to_remove:
                    del self._buckets[key]
        else:
            with self._lock:
                self._buckets.clear()
