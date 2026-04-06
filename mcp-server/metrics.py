"""
Metrics Collection - Tool usage metrics and observability.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class ToolMetrics:
    """Metrics for a single tool."""
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Average latency."""
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count

    @property
    def error_rate(self) -> float:
        """Error rate as percentage."""
        if self.call_count == 0:
            return 0.0
        return (self.error_count / self.call_count) * 100


class MetricsCollector:
    """Collects and stores tool usage metrics."""

    def __init__(self):
        self._metrics: dict[str, ToolMetrics] = {}
        self._lock = Lock()
        self._start_time = time.time()

    def record_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Record a tool call."""
        with self._lock:
            if tool_name not in self._metrics:
                self._metrics[tool_name] = ToolMetrics()

            metrics = self._metrics[tool_name]
            metrics.call_count += 1
            metrics.total_latency_ms += duration_ms
            metrics.min_latency_ms = min(metrics.min_latency_ms, duration_ms)
            metrics.max_latency_ms = max(metrics.max_latency_ms, duration_ms)

            if success:
                metrics.success_count += 1
            else:
                metrics.error_count += 1

    def get_metrics(self, tool_name: Optional[str] = None) -> dict:
        """Get metrics for a tool or all tools."""
        with self._lock:
            if tool_name:
                if tool_name not in self._metrics:
                    return {}
                metrics = self._metrics[tool_name]
                return {
                    "call_count": metrics.call_count,
                    "success_count": metrics.success_count,
                    "error_count": metrics.error_count,
                    "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                    "min_latency_ms": round(metrics.min_latency_ms, 2) if metrics.min_latency_ms != float('inf') else 0,
                    "max_latency_ms": round(metrics.max_latency_ms, 2),
                    "error_rate": round(metrics.error_rate, 2),
                }
            else:
                # All metrics
                all_metrics = {}
                for name, metrics in self._metrics.items():
                    all_metrics[name] = {
                        "call_count": metrics.call_count,
                        "success_count": metrics.success_count,
                        "error_count": metrics.error_count,
                        "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                        "min_latency_ms": round(metrics.min_latency_ms, 2) if metrics.min_latency_ms != float('inf') else 0,
                        "max_latency_ms": round(metrics.max_latency_ms, 2),
                        "error_rate": round(metrics.error_rate, 2),
                    }
                return all_metrics

    def get_summary(self) -> dict:
        """Get summary metrics."""
        with self._lock:
            total_calls = sum(m.call_count for m in self._metrics.values())
            total_errors = sum(m.error_count for m in self._metrics.values())
            total_latency = sum(m.total_latency_ms for m in self._metrics.values())

            return {
                "uptime_seconds": int(time.time() - self._start_time),
                "total_calls": total_calls,
                "total_errors": total_errors,
                "total_tools": len(self._metrics),
                "avg_latency_ms": round(total_latency / total_calls, 2) if total_calls > 0 else 0,
                "error_rate": round((total_errors / total_calls * 100), 2) if total_calls > 0 else 0,
            }

    def reset(self) -> None:
        """Reset all metrics. For testing."""
        with self._lock:
            self._metrics.clear()
            self._start_time = time.time()
