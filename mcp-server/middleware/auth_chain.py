"""
Auth Chain Middleware — full authentication pipeline.

Pipeline: Bearer Token → TOTP Check → Rate Limit → Audit Log

Each stage can reject the request. All stages log to audit.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from auth import validate_bearer_header, AuthResult
from audit import AuditLogger
from rate_limiter import RateLimiter
from categories import CategoryRegistry, UnlockManager
from middleware.category_guard import CategoryGuard

log = logging.getLogger("gangoos.auth_chain")


@dataclass
class AuthChainResult:
    """Result of the full auth chain evaluation."""
    allowed: bool
    stage_failed: Optional[str] = None
    message: str = ""
    caller: str = ""
    status_code: int = 200
    rate_limit_reset: float = 0.0


class AuthChain:
    """
    Full authentication pipeline for MCP tool calls.

    Stages (in order):
    1. Bearer token validation
    2. Category TOTP unlock check
    3. Rate limit check
    4. Audit logging (always, even on failure)
    """

    def __init__(
        self,
        rate_limiter: RateLimiter,
        audit_logger: AuditLogger,
        category_guard: CategoryGuard,
        cat_registry: CategoryRegistry,
    ):
        self._rate_limiter = rate_limiter
        self._audit_logger = audit_logger
        self._category_guard = category_guard
        self._cat_registry = cat_registry

    def evaluate(
        self,
        tool_name: str,
        auth_header: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> AuthChainResult:
        """
        Run the full auth chain for a tool call.

        Returns AuthChainResult with allowed=True if all checks pass.
        """
        started = time.perf_counter()

        # Stage 1: Bearer token
        auth_result = validate_bearer_header(auth_header)
        if not auth_result.ok:
            self._log_event(
                tool_name=tool_name,
                caller="unknown",
                status="auth_failed",
                started=started,
                params=params,
                error=auth_result.message,
            )
            return AuthChainResult(
                allowed=False,
                stage_failed="bearer_token",
                message=auth_result.message,
                status_code=auth_result.status_code,
            )

        caller = auth_result.token_suffix

        # Stage 2: Category TOTP check
        try:
            self._category_guard.check_access(tool_name)
        except PermissionError as e:
            self._log_event(
                tool_name=tool_name,
                caller=caller,
                status="totp_denied",
                started=started,
                params=params,
                error=str(e),
            )
            return AuthChainResult(
                allowed=False,
                stage_failed="totp_unlock",
                message=str(e),
                caller=caller,
                status_code=403,
            )

        # Stage 3: Rate limit
        mapping = self._cat_registry.get(tool_name)
        domain = mapping.category.value if mapping else "default"
        allowed, reset_after = self._rate_limiter.check_limit(caller, domain)

        if not allowed:
            self._log_event(
                tool_name=tool_name,
                caller=caller,
                status="rate_limited",
                started=started,
                params=params,
                error=f"Rate limited, retry after {reset_after:.1f}s",
            )
            return AuthChainResult(
                allowed=False,
                stage_failed="rate_limit",
                message=f"Rate limited. Retry after {reset_after:.1f}s",
                caller=caller,
                status_code=429,
                rate_limit_reset=reset_after,
            )

        # All checks passed
        self._log_event(
            tool_name=tool_name,
            caller=caller,
            status="authorized",
            started=started,
            params=params,
        )

        return AuthChainResult(
            allowed=True,
            message="Authorized",
            caller=caller,
            status_code=200,
        )

    def log_completion(
        self,
        tool_name: str,
        caller: str,
        started: float,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Log tool execution completion."""
        self._log_event(
            tool_name=tool_name,
            caller=caller,
            status="success" if success else "error",
            started=started,
            error=error,
        )

    def _log_event(
        self,
        tool_name: str,
        caller: str,
        status: str,
        started: float,
        params: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Write audit log entry."""
        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            self._audit_logger.log_event(
                tool_name=tool_name,
                caller=caller,
                status=status,
                duration_ms=duration_ms,
                params=params,
                error=error,
            )
        except Exception as e:
            log.error("Audit log failed: %s", e)


def build_auth_chain(
    rate_limiter: RateLimiter,
    audit_logger: AuditLogger,
    category_guard: CategoryGuard,
    cat_registry: CategoryRegistry,
) -> AuthChain:
    """Factory function for AuthChain."""
    return AuthChain(
        rate_limiter=rate_limiter,
        audit_logger=audit_logger,
        category_guard=category_guard,
        cat_registry=cat_registry,
    )
