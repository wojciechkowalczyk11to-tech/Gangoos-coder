"""Tests for rate limiting module."""

import time
import pytest
from rate_limiter import TokenBucket, RateLimiter


class TestTokenBucket:
    """Test token bucket algorithm."""

    def test_basic_consumption(self):
        """Tokens are consumed successfully."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.try_consume(1) is True
        assert bucket.try_consume(1) is True

    def test_capacity_limit(self):
        """Cannot consume more than capacity."""
        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        assert bucket.try_consume(2) is True
        assert bucket.try_consume(1) is False

    def test_multi_token_consumption(self):
        """Can consume multiple tokens at once."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.try_consume(5) is True
        assert bucket.try_consume(5) is True
        assert bucket.try_consume(1) is False

    def test_refill_over_time(self):
        """Tokens refill over time."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)  # 10 tokens/sec
        bucket.tokens = 0  # Start empty

        # Wait a bit and check refill
        time.sleep(0.15)
        allowed = bucket.try_consume(1)
        assert allowed is True

    def test_thread_safety(self):
        """Token bucket is thread-safe."""
        import threading

        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        consumed = 0
        lock = threading.Lock()

        def consumer():
            nonlocal consumed
            for _ in range(10):
                if bucket.try_consume(1):
                    with lock:
                        consumed += 1

        threads = [threading.Thread(target=consumer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least some should have succeeded
        assert consumed > 0

    def test_reset_after(self):
        """Get seconds until next token available."""
        bucket = TokenBucket(capacity=1, refill_rate=1.0)
        bucket.tokens = 0

        reset = bucket.get_reset_after()
        assert reset > 0
        assert reset <= 1.0


class TestRateLimiter:
    """Test rate limiter with per-domain limits."""

    def test_basic_limit(self):
        """Respects basic rate limit."""
        limiter = RateLimiter({"default": 10})
        token = "token123"

        # Should allow up to limit
        for i in range(10):
            allowed, _ = limiter.check_limit(token, "llm")
            assert allowed is True

        # Should reject after limit
        allowed, _ = limiter.check_limit(token, "llm")
        assert allowed is False

    def test_per_domain_limits(self):
        """Different domains have different limits."""
        limiter = RateLimiter({
            "control": 5,
            "llm": 10,
            "default": 10,
        })

        token = "token123"

        # Control: 5 limit
        for i in range(5):
            allowed, _ = limiter.check_limit(token, "control")
            assert allowed is True

        allowed, _ = limiter.check_limit(token, "control")
        assert allowed is False

        # LLM: 10 limit (separate bucket)
        for i in range(10):
            allowed, _ = limiter.check_limit(token, "llm")
            assert allowed is True

    def test_per_token_isolation(self):
        """Different tokens have separate buckets."""
        limiter = RateLimiter({"default": 3})

        # Token 1: use 3
        for i in range(3):
            allowed, _ = limiter.check_limit("token1", "llm")
            assert allowed is True

        allowed, _ = limiter.check_limit("token1", "llm")
        assert allowed is False

        # Token 2: still has 3 available
        for i in range(3):
            allowed, _ = limiter.check_limit("token2", "llm")
            assert allowed is True

    def test_multi_token_consumption(self):
        """Can consume multiple tokens at once."""
        limiter = RateLimiter({"default": 10})

        allowed, _ = limiter.check_limit("token1", "llm", amount=5)
        assert allowed is True

        allowed, _ = limiter.check_limit("token1", "llm", amount=5)
        assert allowed is True

        allowed, _ = limiter.check_limit("token1", "llm", amount=1)
        assert allowed is False

    def test_reset_after_seconds(self):
        """Returns reset_after time."""
        limiter = RateLimiter({"default": 1})
        token = "token123"

        # Use the one token
        limiter.check_limit(token, "llm")

        # Next should be rate limited with reset time
        allowed, reset_after = limiter.check_limit(token, "llm")
        assert allowed is False
        assert reset_after > 0

    def test_get_stats(self):
        """Get rate limiter stats."""
        limiter = RateLimiter({"llm": 30, "control": 10})
        limiter.check_limit("token1", "llm")

        stats = limiter.get_stats("token1")
        assert "config" in stats
        assert "llm" in stats["config"]
        assert stats["config"]["llm"] == 30

    def test_reset(self):
        """Reset rate limits."""
        limiter = RateLimiter({"default": 2})
        limiter.check_limit("token1", "llm")
        limiter.check_limit("token1", "llm")

        # Should be rate limited
        allowed, _ = limiter.check_limit("token1", "llm")
        assert allowed is False

        # Reset and try again
        limiter.reset("token1")
        allowed, _ = limiter.check_limit("token1", "llm")
        assert allowed is True
