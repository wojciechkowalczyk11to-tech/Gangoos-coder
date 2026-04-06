"""
Comprehensive configuration tests.
Tests all validators, edge cases, defaults, and error conditions.
"""
import os
import pytest
from config import Settings, _parse_port, _parse_url, _parse_allowed_hosts


# ═════════════════════════════════════════════════════════════════════════════
# _parse_port tests
# ═════════════════════════════════════════════════════════════════════════════

class TestParsePort:

    def test_parse_port_valid_8080(self):
        assert _parse_port("8080") == 8080

    def test_parse_port_valid_1(self):
        assert _parse_port("1") == 1

    def test_parse_port_valid_65535(self):
        assert _parse_port("65535") == 65535

    def test_parse_port_valid_443(self):
        assert _parse_port("443") == 443

    def test_parse_port_rejects_zero(self):
        with pytest.raises(ValueError, match="1–65535"):
            _parse_port("0")

    def test_parse_port_rejects_negative(self):
        with pytest.raises(ValueError, match="1–65535"):
            _parse_port("-1")

    def test_parse_port_rejects_too_high(self):
        with pytest.raises(ValueError, match="1–65535"):
            _parse_port("65536")

    def test_parse_port_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="integer"):
            _parse_port("abc")

    def test_parse_port_rejects_float_string(self):
        with pytest.raises(ValueError, match="integer"):
            _parse_port("80.5")

    def test_parse_port_rejects_empty_string(self):
        with pytest.raises(ValueError, match="integer"):
            _parse_port("")


# ═════════════════════════════════════════════════════════════════════════════
# _parse_url tests
# ═════════════════════════════════════════════════════════════════════════════

class TestParseUrl:

    def test_parse_url_accepts_http(self):
        result = _parse_url("http://localhost:11434", "TEST_URL")
        assert result == "http://localhost:11434"

    def test_parse_url_accepts_https(self):
        result = _parse_url("https://api.example.com", "TEST_URL")
        assert result == "https://api.example.com"

    def test_parse_url_accepts_empty(self):
        result = _parse_url("", "TEST_URL")
        assert result == ""

    def test_parse_url_rejects_ftp(self):
        with pytest.raises(ValueError, match="http://.*https://"):
            _parse_url("ftp://example.com", "TEST_URL")

    def test_parse_url_rejects_no_scheme(self):
        with pytest.raises(ValueError, match="http://.*https://"):
            _parse_url("example.com:8080", "TEST_URL")


# ═════════════════════════════════════════════════════════════════════════════
# _parse_allowed_hosts tests
# ═════════════════════════════════════════════════════════════════════════════

class TestParseAllowedHosts:

    def test_parse_allowed_hosts_single(self):
        result = _parse_allowed_hosts("localhost")
        assert result == "localhost"

    def test_parse_allowed_hosts_multiple(self):
        result = _parse_allowed_hosts("localhost,192.168.1.1,mcp-server")
        assert "localhost" in result
        assert "192.168.1.1" in result

    def test_parse_allowed_hosts_with_whitespace(self):
        result = _parse_allowed_hosts("  localhost , 127.0.0.1 ")
        assert "localhost" in result
        assert "127.0.0.1" in result

    def test_parse_allowed_hosts_rejects_empty(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _parse_allowed_hosts("")

    def test_parse_allowed_hosts_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _parse_allowed_hosts("   ")

    def test_parse_allowed_hosts_rejects_wildcard(self):
        with pytest.raises(ValueError, match="wildcard"):
            _parse_allowed_hosts("*")

    def test_parse_allowed_hosts_rejects_wildcard_in_list(self):
        with pytest.raises(ValueError, match="wildcard"):
            _parse_allowed_hosts("localhost, *")


# ═════════════════════════════════════════════════════════════════════════════
# Settings dataclass tests
# ═════════════════════════════════════════════════════════════════════════════

class TestSettingsDefaults:

    def test_settings_default_port_is_8080(self, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        s = Settings()
        assert s.PORT == 8080

    def test_settings_default_ollama_model_is_qwen3(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        s = Settings()
        assert s.OLLAMA_MODEL == "qwen3:8b"

    def test_settings_default_aws_region(self, monkeypatch):
        monkeypatch.delenv("AWS_REGION", raising=False)
        s = Settings()
        assert s.AWS_REGION == "us-east-1"

    def test_settings_default_ollama_host(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        s = Settings()
        assert s.OLLAMA_HOST == "http://localhost:11434"

    def test_settings_default_gitlab_base_url(self, monkeypatch):
        monkeypatch.delenv("GITLAB_BASE_URL", raising=False)
        s = Settings()
        assert s.GITLAB_BASE_URL == "https://gitlab.com/api/v4"

    def test_settings_default_allowed_ssh_hosts(self, monkeypatch):
        monkeypatch.delenv("ALLOWED_SSH_HOSTS", raising=False)
        s = Settings()
        assert s.ALLOWED_SSH_HOSTS == "localhost"


class TestSettingsValidation:

    def test_settings_validate_no_token_reports_error(self, monkeypatch):
        monkeypatch.setenv("NEXUS_AUTH_TOKEN", "")
        s = Settings(AUTH_TOKEN="")
        issues = s.validate()
        error_issues = [i for i in issues if i.startswith("ERROR:")]
        assert len(error_issues) > 0
        assert any("NEXUS_AUTH_TOKEN" in i for i in error_issues)

    def test_settings_validate_missing_cloudflare_warns(self):
        s = Settings(AUTH_TOKEN="valid", CLOUDFLARE_API_TOKEN="", GITHUB_TOKEN="ok")
        issues = s.validate()
        assert any("CLOUDFLARE_API_TOKEN" in i for i in issues)

    def test_settings_validate_missing_github_warns(self):
        s = Settings(AUTH_TOKEN="valid", GITHUB_TOKEN="")
        issues = s.validate()
        assert any("GITHUB_TOKEN" in i for i in issues)

    def test_settings_validate_all_present_no_errors(self):
        s = Settings(
            AUTH_TOKEN="tok",
            CLOUDFLARE_API_TOKEN="cf",
            GITHUB_TOKEN="gh",
        )
        issues = s.validate()
        error_issues = [i for i in issues if i.startswith("ERROR:")]
        assert len(error_issues) == 0

    def test_settings_get_allowed_hosts_returns_list(self):
        s = Settings(ALLOWED_SSH_HOSTS="a, b, c")
        hosts = s.get_allowed_hosts()
        assert isinstance(hosts, list)
        assert hosts == ["a", "b", "c"]

    def test_settings_custom_port_from_env(self, monkeypatch):
        monkeypatch.setenv("PORT", "9090")
        s = Settings(PORT=_parse_port("9090"))
        assert s.PORT == 9090
