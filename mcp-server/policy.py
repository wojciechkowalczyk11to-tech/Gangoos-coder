"""
Policy Engine - Comprehensive tool access policy evaluation.
Full evaluation chain: auth → registered → enabled → domain_enabled → confirmation → env_vars → rate_limit
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping, Optional

from registry import ToolMeta

log = logging.getLogger("nexus-v2.policy")


@dataclass(frozen=True)
class PolicyDecision:
    """Result of policy evaluation."""
    allowed: bool
    reason: str
    status_code: int = 200  # HTTP status if denied


def domain_env_flag(domain: str) -> str:
    """Get env var name to enable/disable a domain."""
    return f"NEXUS_V2_ENABLE_{domain.upper()}"


def is_domain_enabled(domain: str, env: Mapping[str, str] | None = None) -> bool:
    """Check if a domain is enabled."""
    source = env if env is not None else os.environ
    value = source.get(domain_env_flag(domain), "true")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def evaluate_tool_access(
    meta: ToolMeta,
    *,
    confirmation_requested: bool = False,
    rate_limit_ok: bool = True,
    env: Mapping[str, str] | None = None,
) -> PolicyDecision:
    """
    Comprehensive policy evaluation for tool access.

    Evaluation chain:
    1. Tool exists and is registered (meta must not be None)
    2. Domain is enabled
    3. Tool is enabled by default OR explicitly enabled
    4. Confirmation required? Check if provided
    5. All required env vars are set
    6. Rate limit not exceeded

    Args:
        meta: Tool metadata
        confirmation_requested: Whether user confirmed high-risk operation
        rate_limit_ok: Whether rate limit check passed
        env: Custom environment dict (for testing)

    Returns:
        PolicyDecision with allowed flag and reason
    """
    if meta is None:
        return PolicyDecision(False, "Unknown tool", status_code=404)

    source = env if env is not None else os.environ

    # Chain 1: Domain enabled?
    if not is_domain_enabled(meta.domain, source):
        log.info(f"Tool {meta.name}: domain {meta.domain} disabled")
        return PolicyDecision(False, f"Domain disabled: {meta.domain}", status_code=403)

    # Chain 2: Tool enabled by default?
    if not meta.enabled_by_default:
        log.info(f"Tool {meta.name}: disabled by default, requires explicit enable")
        return PolicyDecision(False, f"Tool disabled by default: {meta.name}", status_code=403)

    # Chain 3: Confirmation required?
    if meta.requires_confirmation and not confirmation_requested:
        log.warning(f"Tool {meta.name}: confirmation required but not provided")
        return PolicyDecision(False, f"Confirmation required: {meta.name}", status_code=403)

    # Chain 4: Required env vars?
    missing = [key for key in meta.required_env if not source.get(key)]
    if missing:
        log.warning(f"Tool {meta.name}: missing env vars {missing}")
        return PolicyDecision(False, f"Missing env: {', '.join(missing)}", status_code=503)

    # Chain 5: Rate limit?
    if not rate_limit_ok:
        log.warning(f"Tool {meta.name}: rate limit exceeded")
        return PolicyDecision(False, "Rate limit exceeded", status_code=429)

    log.info(f"Tool {meta.name}: allowed")
    return PolicyDecision(True, "Allowed", status_code=200)
