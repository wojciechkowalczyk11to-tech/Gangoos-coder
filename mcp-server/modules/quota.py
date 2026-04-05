"""
NEXUS MCP — Usage Quota, Rate Limiting & Stats Module

In-memory rate limiter + tool usage tracking.
No external deps (no Redis, no Prometheus — e2-micro friendly).
Resets on server restart (acceptable for current scale).

Tools:
  - usage_stats:         Current tool usage counters + rate limit info
  - usage_reset:         Reset counters for a specific key or all
  - quota_check:         Check remaining quota for a key

Middleware (used by rest_gateway.py):
  - check_rate_limit()   → called before every tool invocation
  - record_usage()       → called after successful tool invocation
"""

import time
import logging
from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.quota")

# ── In-Memory Storage ───────────────────────────────────────────────────────

@dataclass
class RateBucket:
    """Sliding window rate limiter per key."""
    tokens: int = 0
    window_start: float = 0.0

@dataclass
class UsageRecord:
    """Cumulative usage stats per key."""
    total_calls: int = 0
    total_errors: int = 0
    tool_counts: dict = field(default_factory=lambda: defaultdict(int))
    first_seen: float = field(default_factory=time.time)
    last_seen: float = 0.0

# Global stores
_rate_buckets: dict[str, RateBucket] = {}
_usage_records: dict[str, UsageRecord] = defaultdict(UsageRecord)
_global_stats: dict[str, int] = defaultdict(int)  # tool_name → call count
_server_start: float = time.time()

# ── Configuration ───────────────────────────────────────────────────────────

# Default limits (override via env or future config)
DEFAULT_RATE_LIMIT = 120       # requests per window
DEFAULT_WINDOW_SECONDS = 60    # 1 minute window
DEFAULT_DAILY_QUOTA = 10_000   # calls per day per key
BURST_LIMIT = 30               # max calls in 5 seconds

# ── Rate Limiting Functions (called by middleware) ──────────────────────────

def check_rate_limit(auth_key: str) -> tuple[bool, str, dict]:
    """
    Check if request is within rate limits.
    Returns: (allowed: bool, reason: str, headers: dict)
    """
    now = time.time()
    bucket_key = auth_key[-8:] if auth_key else "anon"  # last 8 chars as identifier

    # Get or create bucket
    if bucket_key not in _rate_buckets:
        _rate_buckets[bucket_key] = RateBucket(tokens=0, window_start=now)

    bucket = _rate_buckets[bucket_key]

    # Reset window if expired
    if now - bucket.window_start > DEFAULT_WINDOW_SECONDS:
        bucket.tokens = 0
        bucket.window_start = now

    # Check limit
    bucket.tokens += 1
    remaining = max(0, DEFAULT_RATE_LIMIT - bucket.tokens)
    reset_at = int(bucket.window_start + DEFAULT_WINDOW_SECONDS)

    headers = {
        "X-RateLimit-Limit": str(DEFAULT_RATE_LIMIT),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset_at),
    }

    if bucket.tokens > DEFAULT_RATE_LIMIT:
        return False, f"Rate limit exceeded: {DEFAULT_RATE_LIMIT}/min", headers

    # Check daily quota
    usage = _usage_records[bucket_key]
    day_start = now - (now % 86400)
    if usage.first_seen < day_start:
        # New day — reset daily counter
        usage.total_calls = 0
        usage.total_errors = 0
        usage.first_seen = now

    if usage.total_calls >= DEFAULT_DAILY_QUOTA:
        return False, f"Daily quota exceeded: {DEFAULT_DAILY_QUOTA}/day", headers

    return True, "ok", headers


def record_usage(auth_key: str, tool_name: str, success: bool = True):
    """Record a tool invocation for stats."""
    now = time.time()
    bucket_key = auth_key[-8:] if auth_key else "anon"

    # Per-key stats
    usage = _usage_records[bucket_key]
    usage.total_calls += 1
    usage.last_seen = now
    usage.tool_counts[tool_name] += 1
    if not success:
        usage.total_errors += 1

    # Global stats
    _global_stats[tool_name] += 1


def get_stats_snapshot() -> dict:
    """Return current stats as a dict (for /api/v1/stats endpoint)."""
    now = time.time()
    uptime_sec = now - _server_start
    uptime_h = uptime_sec / 3600

    total_calls = sum(_global_stats.values())
    top_tools = sorted(_global_stats.items(), key=lambda x: x[1], reverse=True)[:20]

    return {
        "uptime_hours": round(uptime_h, 2),
        "total_calls": total_calls,
        "unique_keys": len(_usage_records),
        "calls_per_hour": round(total_calls / max(uptime_h, 0.01), 1),
        "rate_limit": f"{DEFAULT_RATE_LIMIT}/min",
        "daily_quota": DEFAULT_DAILY_QUOTA,
        "top_tools": {name: count for name, count in top_tools},
        "active_buckets": len(_rate_buckets),
    }


# ── MCP Tools ───────────────────────────────────────────────────────────────

def register(mcp: FastMCP):

    class UsageStatsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        key_filter: Optional[str] = Field(
            None,
            description="Filter stats by key suffix (last 8 chars). Omit for global stats.",
        )

    @mcp.tool(name="usage_stats", annotations={"readOnlyHint": True})
    async def usage_stats(params: UsageStatsInput, ctx: Context) -> str:
        """Get tool usage statistics: call counts, top tools, rate limit status.
        Returns global stats by default, or per-key stats if key_filter provided.
        """
        stats = get_stats_snapshot()

        output = (
            f"# NEXUS MCP Usage Stats\n\n"
            f"**Uptime:** {stats['uptime_hours']}h\n"
            f"**Total calls:** {stats['total_calls']}\n"
            f"**Unique keys:** {stats['unique_keys']}\n"
            f"**Calls/hour:** {stats['calls_per_hour']}\n"
            f"**Rate limit:** {stats['rate_limit']}\n"
            f"**Daily quota:** {stats['daily_quota']}\n\n"
            f"## Top Tools\n\n"
        )

        for name, count in stats["top_tools"].items():
            output += f"- `{name}`: {count} calls\n"

        if params.key_filter:
            usage = _usage_records.get(params.key_filter)
            if usage:
                output += (
                    f"\n## Key: ...{params.key_filter}\n"
                    f"**Total:** {usage.total_calls} | "
                    f"**Errors:** {usage.total_errors} | "
                    f"**Last seen:** {time.strftime('%H:%M:%S', time.localtime(usage.last_seen))}\n"
                )
            else:
                output += f"\nNo data for key suffix `{params.key_filter}`"

        return output

    class UsageResetInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        key_filter: Optional[str] = Field(
            None,
            description="Reset stats for specific key suffix. Omit to reset ALL stats.",
        )
        confirm: bool = Field(
            False,
            description="Must be true to actually reset. Safety check.",
        )

    @mcp.tool(name="usage_reset", annotations={"destructiveHint": True})
    async def usage_reset(params: UsageResetInput, ctx: Context) -> str:
        """Reset usage counters. Requires confirm=true as safety check."""
        if not params.confirm:
            return "⚠️ Set confirm=true to actually reset counters. This cannot be undone."

        if params.key_filter:
            if params.key_filter in _usage_records:
                del _usage_records[params.key_filter]
                if params.key_filter in _rate_buckets:
                    del _rate_buckets[params.key_filter]
                return f"✅ Reset stats for key ...{params.key_filter}"
            return f"No data for key suffix `{params.key_filter}`"
        else:
            _usage_records.clear()
            _rate_buckets.clear()
            _global_stats.clear()
            return "✅ All usage stats reset"

    class QuotaCheckInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="quota_check", annotations={"readOnlyHint": True})
    async def quota_check(params: QuotaCheckInput, ctx: Context) -> str:
        """Check remaining quota and rate limit status for the current request."""
        stats = get_stats_snapshot()
        return (
            f"**Rate limit:** {stats['rate_limit']} "
            f"({stats['active_buckets']} active windows)\n"
            f"**Daily quota:** {stats['daily_quota']} per key\n"
            f"**Server load:** {stats['calls_per_hour']} calls/hour\n"
            f"**Total served:** {stats['total_calls']}"
        )

    log.info("Quota module registered: usage_stats, usage_reset, quota_check")
