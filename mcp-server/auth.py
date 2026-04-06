"""
Authentication module - Bearer token validation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuthResult:
    """Result of bearer token validation."""
    ok: bool
    status_code: int
    message: str
    token_suffix: str = ""


def get_expected_token() -> str:
    """Get auth token from environment."""
    return os.getenv("NEXUS_AUTH_TOKEN", "")


def extract_bearer_token(header_value: Optional[str]) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    if not header_value:
        return None
    parts = header_value.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def validate_bearer_header(
    header_value: Optional[str],
    expected_token: Optional[str] = None,
) -> AuthResult:
    """
    Validate Authorization header with Bearer token.
    Returns AuthResult with status_code and message.
    """
    expected = expected_token if expected_token is not None else get_expected_token()

    if not expected:
        return AuthResult(
            ok=False,
            status_code=500,
            message="Server misconfiguration: NEXUS_AUTH_TOKEN is not set.",
        )

    token = extract_bearer_token(header_value)
    if not token:
        return AuthResult(
            ok=False,
            status_code=401,
            message="Missing or invalid Authorization header. Use: Bearer <token>.",
        )

    if token != expected:
        return AuthResult(
            ok=False,
            status_code=403,
            message="Invalid Bearer token.",
            token_suffix=token[-6:] if len(token) >= 6 else token,
        )

    return AuthResult(
        ok=True,
        status_code=200,
        message="Authorized",
        token_suffix=token[-6:] if len(token) >= 6 else token,
    )
