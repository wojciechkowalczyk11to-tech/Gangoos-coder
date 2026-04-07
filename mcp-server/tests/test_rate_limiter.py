"""
Tests for Rate Limiter — sliding window / token bucket tests.
"""

import time
from threading import Thread

import pytest

from rate_limiter import RateLimiter, TokenBucket


class TestTokenBucket:
    """TokenBucket unit tests."""

    def test_initial_full(self):
        """Bucket should start full."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.tokens == 10.0

    def test_consume_success(self):
        """Should consume tokens when available."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.try_consume(1) is True
        assert bucket.tokens == 9.0

    def test_consume_multiple(self):
        """Should consume multiple tokens at once."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.try_consume(5) is True
        assert bucket.tokens == 5.0

    def test_consume_empty(self):
        """Should reject when bucket is empty."""
        bucket = TokenBucket(capacity=2, refill_rate=0.1)
        assert bucket.try_consume(1) is True
        assert bucket.try_consume(1) is True
        assert bucket.try_consume(1) is False

    def test_refill_over_time(self):
        """Tokens should refill over time."""
        bucket = TokenBucket(capacity=10, refill_rate=100.0)  # 100 tokens/sec
        bucket.try_consume(10)  # drain
        assert bucket.tokens < 1.0

        time.sleep(0.05)  # ~5 tokens should refill at 100/sec
        assert bucket.try_consume(1) is True

    def test_no_over_capacity(self):
        """Should not exceed capacity after refill."""
        bucket = TokenBucket(capacity=5, refill_rate=100.0)
        time.sleep(0.1)  # wait for refill
        assert bucket.try_consume(1) is True
        # Even after long wait, should be capped at capacity
        with bucket.lock:
            assert bucket.tokens <= 5.0

    def test_reset_after(self):
        """Should report time until next token."""
        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        bucket.try_consume(2)
        reset = bucket.get_reset_after()
        assert reset > 0.0
        assert reset <= 1.0

    def test_thread_safety(self):
        """Token bucket should be thread-safe."""
        bucket = TokenBucket(capacity=100, refill_rate=0.0)  # no refill
        consumed = {"count": 0}

        def consume_many():
            for _ in range(20):
                if bucket.try_consume(1):
                    consumed["count"] += 1

        threads = [Thread(target=consume_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Dokładnie 100 tokenów, nie więcej
        assert consumed["count"] == 100


class TestRateLimiter:
    """RateLimiter integration tests."""

    def test_default_config(self):
        """Should have default rate limits."""
        rl = RateLimiter()
        stats = rl.get_stats()
        assert "control" in stats["config"]
        assert "llm" in stats["config"]

    def test_check_limit_allowed(self):
        """Should allow requests within limit."""
        rl = RateLimiter({"llm": 60, "default": 30})
        allowed, reset = rl.check_limit("token1", "llm")
        assert allowed is True
        assert reset == 0.0

    def test_check_limit_exceeded(self):
        """Should reject requests exceeding limit."""
        rl = RateLimiter({"control": 2, "default": 2})
        # Drain bucket
        for _ in range(10):
            rl.check_limit("token1", "control")

        allowed, reset = rl.check_limit("token1", "control")
        assert allowed is False
        assert reset > 0.0

    def test_different_tokens_independent(self):
        """Different tokens should have independent limits."""
        rl = RateLimiter({"test": 2, "default": 2})
        # Drain token1
        for _ in range(10):
            rl.check_limit("token1", "test")

        # token2 should still be allowed
        allowed, _ = rl.check_limit("token2", "test")
        assert allowed is True

    def test_different_domains_independent(self):
        """Different domains should have independent limits."""
        rl = RateLimiter({"llm": 2, "research": 100, "default": 2})
        # Drain llm
        for _ in range(10):
            rl.check_limit("token1", "llm")

        # research should still work
        allowed, _ = rl.check_limit("token1", "research")
        assert allowed is True

    def test_get_stats_for_token(self):
        """Should return per-token stats."""
        rl = RateLimiter({"llm": 30, "default": 30})
        rl.check_limit("token1", "llm")

        stats = rl.get_stats("token1")
        assert "buckets" in stats
        assert "llm" in stats["buckets"]

    def test_reset_token(self):
        """Should reset specific token limits."""
        rl = RateLimiter({"llm": 3, "default": 3})
        for _ in range(10):
            rl.check_limit("token1", "llm")

        rl.reset("token1")
        allowed, _ = rl.check_limit("token1", "llm")
        assert allowed is True

    def test_reset_all(self):
        """Should reset all limits."""
        rl = RateLimiter({"llm": 3, "default": 3})
        for _ in range(10):
            rl.check_limit("token1", "llm")

        rl.reset()
        allowed, _ = rl.check_limit("token1", "llm")
        assert allowed is True

    def test_overall_stats(self):
        """Should return overall stats without leaking tokens."""
        rl = RateLimiter()
        rl.check_limit("secret-token", "llm")
        stats = rl.get_stats()
        assert "total_buckets" in stats
        assert "secret-token" not in str(stats)

    def test_sliding_window_behavior(self):
        """Rate should refill over time (sliding window effect)."""
        rl = RateLimiter({"fast": 600, "default": 600})  # 10/sec
        # Consume all burst capacity
        for _ in range(200):
            rl.check_limit("token1", "fast")

        time.sleep(0.1)  # Allow some refill

        allowed, _ = rl.check_limit("token1", "fast")
        assert allowed is True
