"""
TOTP Authentication Gate — per-category time-based OTP unlock.

RFC 6238 compliant, 6-digit codes, ±1 window tolerance.
Failed attempts trigger lockout (3 fails → 15min).
Category TTLs: CAT-2/CAT-6 = 5min, others = 30min.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

import pyotp


# TTL w sekundach per kategoria
_CATEGORY_TTLS: dict[str, int] = {
    "cat2_control": 300,     # 5 min — niebezpieczne operacje
    "cat6_security": 300,    # 5 min — narzędzia bezpieczeństwa
}
_DEFAULT_TTL: int = 1800     # 30 min dla reszty

_MAX_FAILED_ATTEMPTS: int = 3
_LOCKOUT_DURATION: int = 900  # 15 min


@dataclass
class _UnlockState:
    """Tracks unlock state for a single category."""
    unlocked_at: float = 0.0
    ttl: int = _DEFAULT_TTL
    failed_attempts: int = 0
    locked_until: float = 0.0

    @property
    def is_unlocked(self) -> bool:
        now = time.time()
        if now < self.locked_until:
            return False
        if self.unlocked_at == 0.0:
            return False
        return (now - self.unlocked_at) < self.ttl

    @property
    def is_locked_out(self) -> bool:
        return time.time() < self.locked_until

    @property
    def remaining_seconds(self) -> float:
        if not self.is_unlocked:
            return 0.0
        elapsed = time.time() - self.unlocked_at
        return max(0.0, self.ttl - elapsed)

    @property
    def lockout_remaining(self) -> float:
        if not self.is_locked_out:
            return 0.0
        return max(0.0, self.locked_until - time.time())


def _encode_base32_from_bytes(data: bytes) -> str:
    """Encode raw bytes to base32 for pyotp (no padding)."""
    return base64.b32encode(data).decode("ascii").rstrip("=")


class CategoryTOTP:
    """
    TOTP authentication gate for tool categories.

    Each category has its own TOTP secret derived from TOTP_SECRET_BASE.
    Unlock grants temporary access (TTL varies by category risk level).
    3 failed attempts triggers 15-minute lockout.
    """

    def __init__(self, secret_base: Optional[str] = None):
        self._secret_base = secret_base or os.getenv("TOTP_SECRET_BASE", "")
        if not self._secret_base:
            raise ValueError(
                "TOTP_SECRET_BASE env var required for TOTP authentication. "
                "Generate with: python -c \"import pyotp; print(pyotp.random_base32())\""
            )
        self._states: dict[str, _UnlockState] = {}
        self._totp_instances: dict[str, pyotp.TOTP] = {}
        self._lock = Lock()

    def _get_totp(self, category: str) -> pyotp.TOTP:
        """Get or create TOTP instance for a category."""
        if category not in self._totp_instances:
            derived = hmac.new(
                self._secret_base.encode("utf-8"),
                category.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            secret = _encode_base32_from_bytes(derived[:20])
            self._totp_instances[category] = pyotp.TOTP(secret)
        return self._totp_instances[category]

    def _get_state(self, category: str) -> _UnlockState:
        """Get or create unlock state for a category."""
        if category not in self._states:
            ttl = _CATEGORY_TTLS.get(category, _DEFAULT_TTL)
            self._states[category] = _UnlockState(ttl=ttl)
        return self._states[category]

    def get_provisioning_uri(self, category: str, issuer: str = "Gangoos-MCP") -> str:
        """Get provisioning URI for adding to authenticator app."""
        totp = self._get_totp(category)
        return totp.provisioning_uri(name=category, issuer_name=issuer)

    def get_current_code(self, category: str) -> str:
        """Get current TOTP code (for testing/admin use only)."""
        totp = self._get_totp(category)
        return totp.now()

    def unlock(self, category: str, code: str) -> dict:
        """
        Attempt to unlock a category with a TOTP code.

        Returns dict with:
            - success: bool
            - message: str
            - remaining_seconds: float (if unlocked)
            - lockout_remaining: float (if locked out)
        """
        with self._lock:
            state = self._get_state(category)

            if state.is_locked_out:
                return {
                    "success": False,
                    "message": f"Category {category} locked out due to failed attempts",
                    "lockout_remaining": round(state.lockout_remaining, 1),
                    "category": category,
                }

            totp = self._get_totp(category)

            # Weryfikuj z oknem ±1 (valid_window=1 = current + ±1 step)
            if totp.verify(code, valid_window=1):
                state.unlocked_at = time.time()
                state.failed_attempts = 0
                state.locked_until = 0.0
                return {
                    "success": True,
                    "message": f"Category {category} unlocked",
                    "remaining_seconds": round(state.remaining_seconds, 1),
                    "category": category,
                    "ttl": state.ttl,
                }

            # Nieprawidłowy kod
            state.failed_attempts += 1
            remaining_attempts = _MAX_FAILED_ATTEMPTS - state.failed_attempts

            if state.failed_attempts >= _MAX_FAILED_ATTEMPTS:
                state.locked_until = time.time() + _LOCKOUT_DURATION
                state.failed_attempts = 0
                return {
                    "success": False,
                    "message": f"Category {category} LOCKED OUT — too many failed attempts",
                    "lockout_remaining": float(_LOCKOUT_DURATION),
                    "category": category,
                }

            return {
                "success": False,
                "message": f"Invalid TOTP code for {category}",
                "remaining_attempts": remaining_attempts,
                "category": category,
            }

    def is_unlocked(self, category: str) -> bool:
        """Check if a category is currently unlocked."""
        with self._lock:
            state = self._get_state(category)
            return state.is_unlocked

    def get_status(self, category: str) -> dict:
        """Get detailed status for a category."""
        with self._lock:
            state = self._get_state(category)
            return {
                "category": category,
                "unlocked": state.is_unlocked,
                "locked_out": state.is_locked_out,
                "remaining_seconds": round(state.remaining_seconds, 1),
                "lockout_remaining": round(state.lockout_remaining, 1),
                "ttl": state.ttl,
            }

    def get_all_status(self) -> dict[str, dict]:
        """Get status for all known categories."""
        with self._lock:
            return {
                cat: {
                    "unlocked": state.is_unlocked,
                    "locked_out": state.is_locked_out,
                    "remaining_seconds": round(state.remaining_seconds, 1),
                    "lockout_remaining": round(state.lockout_remaining, 1),
                    "ttl": state.ttl,
                }
                for cat, state in self._states.items()
            }

    def revoke(self, category: str) -> dict:
        """Immediately revoke unlock for a category."""
        with self._lock:
            state = self._get_state(category)
            state.unlocked_at = 0.0
            return {
                "success": True,
                "message": f"Category {category} access revoked",
                "category": category,
            }

    def revoke_all(self) -> dict:
        """Revoke all unlocks."""
        with self._lock:
            for state in self._states.values():
                state.unlocked_at = 0.0
            return {
                "success": True,
                "message": "All category unlocks revoked",
                "categories_revoked": list(self._states.keys()),
            }
