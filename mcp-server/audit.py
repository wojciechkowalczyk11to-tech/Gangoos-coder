"""
Audit Logger - Structured audit logging with redaction.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def redact_value(value: Any) -> Any:
    """Redact sensitive values in audit logs."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(secret in lowered for secret in ("token", "secret", "password", "key", "authorization", "api")):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


def hash_payload(payload: Any) -> str:
    """Hash payload for integrity verification."""
    raw = json.dumps(redact_value(payload), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class AuditLogger:
    """Structured audit logger to JSONL file."""
    path: Path

    def log_event(
        self,
        *,
        tool_name: str,
        caller: str,
        status: str,
        duration_ms: int,
        params: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """
        Log an audit event.

        Args:
            tool_name: Name of tool invoked
            caller: Caller identifier (token suffix, etc.)
            status: Event status (success, failure, rate_limited, etc.)
            duration_ms: Request duration in milliseconds
            params: Tool parameters (will be redacted)
            error: Error message if applicable

        Returns:
            Audit event dict that was logged
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "caller": caller,
            "status": status,
            "duration_ms": duration_ms,
            "params_hash": hash_payload(params or {}),
            "params_preview": redact_value(params or {}),
        }

        if error:
            event["error"] = error

        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=True) + "\n")
        except OSError as e:
            # Log to stderr if audit file can't be written
            import sys
            print(f"[AUDIT ERROR] Failed to write to {self.path}: {e}", file=sys.stderr)

        return event


def build_audit_logger() -> AuditLogger:
    """Build audit logger from config."""
    log_path = os.getenv("AUDIT_LOG_PATH", "./logs/nexus_v2_audit.jsonl")
    return AuditLogger(Path(log_path))
