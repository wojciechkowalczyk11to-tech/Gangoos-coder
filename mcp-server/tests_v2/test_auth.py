"""Tests for authentication module."""

import pytest
from auth import extract_bearer_token, validate_bearer_header, AuthResult


class TestExtractBearerToken:
    """Test Bearer token extraction."""

    def test_valid_token(self):
        """Extract valid Bearer token."""
        result = extract_bearer_token("Bearer mytoken123")
        assert result == "mytoken123"

    def test_token_with_spaces(self):
        """Extract token with extra spaces."""
        result = extract_bearer_token("Bearer   spaced_token")
        assert result == "spaced_token"

    def test_case_insensitive(self):
        """Bearer is case-insensitive."""
        assert extract_bearer_token("bearer token") == "token"
        assert extract_bearer_token("BEARER token") == "token"

    def test_missing_bearer(self):
        """Missing Bearer prefix returns None."""
        assert extract_bearer_token("Basic token") is None

    def test_no_space(self):
        """No space in header returns None."""
        assert extract_bearer_token("Bearertoken") is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert extract_bearer_token("") is None

    def test_none_input(self):
        """None input returns None."""
        assert extract_bearer_token(None) is None


class TestValidateBearerHeader:
    """Test Bearer header validation."""

    def test_valid_token(self):
        """Valid token passes validation."""
        result = validate_bearer_header("Bearer mytoken", expected_token="mytoken")
        assert result.ok is True
        assert result.status_code == 200

    def test_invalid_token(self):
        """Invalid token fails validation."""
        result = validate_bearer_header("Bearer wrong", expected_token="correct")
        assert result.ok is False
        assert result.status_code == 403

    def test_missing_header(self):
        """Missing header fails validation."""
        result = validate_bearer_header(None, expected_token="token")
        assert result.ok is False
        assert result.status_code == 401

    def test_no_expected_token(self):
        """Server misconfiguration when no expected token."""
        result = validate_bearer_header("Bearer token", expected_token="")
        assert result.ok is False
        assert result.status_code == 500

    def test_token_suffix(self):
        """Token suffix is included for logging."""
        result = validate_bearer_header(
            "Bearer verylongtoken123456",
            expected_token="verylongtoken123456"
        )
        assert result.token_suffix == "123456"  # Last 6 chars

    def test_short_token_suffix(self):
        """Short tokens don't get padding."""
        result = validate_bearer_header(
            "Bearer abc",
            expected_token="abc"
        )
        assert result.token_suffix == "abc"
