"""
Tests for TOTP Gate — unlock, lockout, TTL expiration.
"""

import time
from unittest.mock import patch

import pytest

from security.totp_gate import CategoryTOTP, _LOCKOUT_DURATION


@pytest.fixture
def totp():
    """Create CategoryTOTP with test secret."""
    return CategoryTOTP(secret_base="TESTSECRETBASE32CHARLONG")


class TestCategoryTOTP:
    """TOTP gate unit tests."""

    def test_init_requires_secret(self):
        """Should raise ValueError without secret base."""
        with patch.dict("os.environ", {"TOTP_SECRET_BASE": ""}, clear=False):
            with pytest.raises(ValueError, match="TOTP_SECRET_BASE"):
                CategoryTOTP(secret_base="")

    def test_init_from_env(self):
        """Should read secret from env var."""
        with patch.dict("os.environ", {"TOTP_SECRET_BASE": "ENVTESTSECRET12345678"}):
            gate = CategoryTOTP()
            assert gate._secret_base == "ENVTESTSECRET12345678"

    def test_get_current_code(self, totp):
        """Should return 6-digit code."""
        code = totp.get_current_code("cat2_control")
        assert len(code) == 6
        assert code.isdigit()

    def test_unlock_valid_code(self, totp):
        """Should unlock with valid TOTP code."""
        code = totp.get_current_code("cat1_llm")
        result = totp.unlock("cat1_llm", code)
        assert result["success"] is True
        assert result["category"] == "cat1_llm"
        assert result["remaining_seconds"] > 0

    def test_unlock_invalid_code(self, totp):
        """Should reject invalid code."""
        result = totp.unlock("cat1_llm", "000000")
        assert result["success"] is False
        assert "remaining_attempts" in result or "LOCKED OUT" in result["message"]

    def test_is_unlocked(self, totp):
        """Should track unlock state."""
        assert totp.is_unlocked("cat1_llm") is False
        code = totp.get_current_code("cat1_llm")
        totp.unlock("cat1_llm", code)
        assert totp.is_unlocked("cat1_llm") is True

    def test_ttl_control_category(self, totp):
        """CAT-2 (control) should have 5min TTL."""
        code = totp.get_current_code("cat2_control")
        result = totp.unlock("cat2_control", code)
        assert result["success"] is True
        assert result["ttl"] == 300  # 5 min

    def test_ttl_security_category(self, totp):
        """CAT-6 (security) should have 5min TTL."""
        code = totp.get_current_code("cat6_security")
        result = totp.unlock("cat6_security", code)
        assert result["success"] is True
        assert result["ttl"] == 300  # 5 min

    def test_ttl_default_category(self, totp):
        """Default categories should have 30min TTL."""
        code = totp.get_current_code("cat1_llm")
        result = totp.unlock("cat1_llm", code)
        assert result["success"] is True
        assert result["ttl"] == 1800  # 30 min

    def test_ttl_expiration(self, totp):
        """Unlock should expire after TTL."""
        code = totp.get_current_code("cat2_control")
        totp.unlock("cat2_control", code)
        assert totp.is_unlocked("cat2_control") is True

        # Symuluj upływ czasu
        state = totp._get_state("cat2_control")
        state.unlocked_at = time.time() - 301  # 5min + 1s ago
        assert totp.is_unlocked("cat2_control") is False

    def test_lockout_after_3_failures(self, totp):
        """Should lock out after 3 failed attempts."""
        for i in range(3):
            result = totp.unlock("cat1_llm", "000000")

        # Na trzeciej próbie — lockout
        assert "LOCKED OUT" in result["message"]
        assert result["lockout_remaining"] > 0

        # Kolejna próba — nadal zablokowana
        code = totp.get_current_code("cat1_llm")
        result = totp.unlock("cat1_llm", code)
        assert result["success"] is False
        assert "locked out" in result["message"]

    def test_lockout_expires(self, totp):
        """Lockout should expire after duration."""
        for _ in range(3):
            totp.unlock("cat1_llm", "000000")

        # Symuluj upływ lockout
        state = totp._get_state("cat1_llm")
        state.locked_until = time.time() - 1

        code = totp.get_current_code("cat1_llm")
        result = totp.unlock("cat1_llm", code)
        assert result["success"] is True

    def test_revoke(self, totp):
        """Should revoke unlock immediately."""
        code = totp.get_current_code("cat1_llm")
        totp.unlock("cat1_llm", code)
        assert totp.is_unlocked("cat1_llm") is True

        result = totp.revoke("cat1_llm")
        assert result["success"] is True
        assert totp.is_unlocked("cat1_llm") is False

    def test_revoke_all(self, totp):
        """Should revoke all unlocks."""
        for cat in ["cat1_llm", "cat4_research"]:
            code = totp.get_current_code(cat)
            totp.unlock(cat, code)

        result = totp.revoke_all()
        assert result["success"] is True
        assert totp.is_unlocked("cat1_llm") is False
        assert totp.is_unlocked("cat4_research") is False

    def test_get_status(self, totp):
        """Should return detailed status."""
        status = totp.get_status("cat2_control")
        assert status["category"] == "cat2_control"
        assert status["unlocked"] is False
        assert status["locked_out"] is False
        assert status["ttl"] == 300

    def test_get_all_status(self, totp):
        """Should return status for all known categories."""
        totp.get_current_code("cat1_llm")  # forces state creation
        totp.get_current_code("cat2_control")  # forces state creation
        # Access states to ensure they exist
        totp._get_state("cat1_llm")
        totp._get_state("cat2_control")

        all_status = totp.get_all_status()
        assert "cat1_llm" in all_status
        assert "cat2_control" in all_status

    def test_provisioning_uri(self, totp):
        """Should return valid provisioning URI."""
        uri = totp.get_provisioning_uri("cat1_llm")
        assert uri.startswith("otpauth://totp/")
        assert "Gangoos-MCP" in uri

    def test_per_category_secrets_differ(self, totp):
        """Different categories should have different TOTP secrets."""
        code1 = totp.get_current_code("cat1_llm")
        code2 = totp.get_current_code("cat2_control")
        # Codes *may* coincidentally match, but secrets should differ
        totp1 = totp._get_totp("cat1_llm")
        totp2 = totp._get_totp("cat2_control")
        assert totp1.secret != totp2.secret

    def test_window_tolerance(self, totp):
        """Should accept codes from ±1 time window."""
        totp_instance = totp._get_totp("cat1_llm")
        # Generuj kod z przeszłego okna (-30s)
        import pyotp
        past_code = totp_instance.at(time.time() - 30)
        result = totp.unlock("cat1_llm", past_code)
        # Powinno zaakceptować z valid_window=1
        assert result["success"] is True
