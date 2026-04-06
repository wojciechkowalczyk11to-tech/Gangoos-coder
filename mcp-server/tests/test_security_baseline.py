"""
Phase 1C+1D — security hardening and config contract tests.

Eight mandatory test classes:
  S1  non-root container — Dockerfile privilege baseline
  S2  docker-compose security — no silent docker socket in default
  S3  missing/empty auth token contract
  S4  invalid auth token contract
  S5  protected endpoint unauthenticated-access behavior
  S6  valid-config happy-path
  S7  malformed critical config rejection
  S8  regression — no insecure defaults or config drift reintroduced
"""
import os
import re
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).parent.parent.parent
MCP_SERVER_DIR = REPO_ROOT / "mcp-server"


# ─────────────────────────────────────────────────────────────────────────────
# S1. Non-root container — Dockerfile privilege baseline
# ─────────────────────────────────────────────────────────────────────────────

class TestDockerfilePrivilegeBaseline:
    """
    The MCP server Dockerfile must define a non-root USER.
    This test FAILS if the USER directive is removed (container reverts to running as root).
    """

    def _read_dockerfile(self) -> str:
        dfile = MCP_SERVER_DIR / "Dockerfile"
        assert dfile.exists(), "mcp-server/Dockerfile not found"
        return dfile.read_text()

    def test_dockerfile_has_user_directive(self):
        content = self._read_dockerfile()
        user_lines = [
            line.strip() for line in content.splitlines()
            if line.strip().startswith("USER ") and not line.strip().startswith("#")
        ]
        assert user_lines, (
            "mcp-server/Dockerfile has no USER directive — container runs as root. "
            "Add 'USER nexus' (or equivalent non-root user) before CMD."
        )

    def test_dockerfile_user_is_not_root(self):
        content = self._read_dockerfile()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("USER ") and not stripped.startswith("#"):
                user_value = stripped.split("USER", 1)[1].strip().lower()
                assert user_value not in ("root", "0", "0:0"), (
                    f"Dockerfile USER is '{user_value}' — must be a non-root user. "
                    "The default USER must not be root."
                )

    def test_dockerfile_user_comes_after_copy(self):
        """USER must appear after COPY . . to ensure app files are owned correctly."""
        content = self._read_dockerfile()
        lines = content.splitlines()
        user_idx = None
        copy_all_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("USER ") and not stripped.startswith("#"):
                if user_idx is None:
                    user_idx = i
            if stripped == "COPY . .":
                copy_all_idx = i
        assert user_idx is not None, "No USER directive found"
        if copy_all_idx is not None:
            assert user_idx > copy_all_idx, (
                f"USER (line {user_idx+1}) must come after 'COPY . .' (line {copy_all_idx+1}) "
                "so that app files are owned before privilege drop."
            )

    def test_dockerfile_no_docker_socket_baked_in(self):
        """Docker socket must not be referenced inside the Dockerfile itself."""
        content = self._read_dockerfile()
        for line in content.splitlines():
            if line.strip().startswith("#"):
                continue
            assert "/var/run/docker.sock" not in line, (
                "Dockerfile must not reference /var/run/docker.sock — "
                "socket access is an opt-in via docker-compose.privileged.yml."
            )


# ─────────────────────────────────────────────────────────────────────────────
# S2. Docker-compose security — no silent docker socket in default
# ─────────────────────────────────────────────────────────────────────────────

class TestDockerComposeSecurityBaseline:
    """
    Default docker-compose.yml must not silently mount /var/run/docker.sock.
    docker-compose.privileged.yml exists as the explicit opt-in path.
    This test FAILS if someone adds the socket back to the default compose.
    """

    def _read_compose(self, name: str) -> str:
        fpath = REPO_ROOT / name
        assert fpath.exists(), f"{name} not found"
        return fpath.read_text()

    def test_default_compose_no_docker_socket(self):
        """
        /var/run/docker.sock must NOT be in docker-compose.yml.
        Host Docker control must not be the default baseline.
        """
        content = self._read_compose("docker-compose.yml")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "/var/run/docker.sock" not in stripped, (
                "docker-compose.yml mounts /var/run/docker.sock by default. "
                "This grants host-level Docker control silently. "
                "Move it to docker-compose.privileged.yml (explicit opt-in)."
            )

    def test_privileged_compose_exists_as_opt_in(self):
        """
        docker-compose.privileged.yml must exist as the explicit privileged path.
        """
        fpath = REPO_ROOT / "docker-compose.privileged.yml"
        assert fpath.exists(), (
            "docker-compose.privileged.yml not found. "
            "It must exist as the explicit opt-in for privileged (docker socket) deployments."
        )

    def test_privileged_compose_has_docker_socket(self):
        """
        Privileged compose must define the docker socket — it's its sole purpose.
        """
        content = self._read_compose("docker-compose.privileged.yml")
        assert "/var/run/docker.sock" in content, (
            "docker-compose.privileged.yml must define the docker socket mount — "
            "that is its only purpose."
        )

    def test_privileged_compose_documents_warning(self):
        """
        Privileged compose must contain a WARNING comment about the security risk.
        """
        content = self._read_compose("docker-compose.privileged.yml")
        assert "WARNING" in content, (
            "docker-compose.privileged.yml must contain a WARNING about the security risk "
            "of mounting the docker socket."
        )

    def test_default_compose_uses_ollama_model_not_ollama_default_model(self):
        """
        OLLAMA_MODEL is the canonical env var. OLLAMA_DEFAULT_MODEL is the old drift name.
        This test FAILS if the drift name is reintroduced.
        """
        content = self._read_compose("docker-compose.yml")
        assert "OLLAMA_DEFAULT_MODEL:" not in content, (
            "docker-compose.yml uses OLLAMA_DEFAULT_MODEL — this is the old drift name. "
            "Use OLLAMA_MODEL consistently."
        )


# ─────────────────────────────────────────────────────────────────────────────
# S3. Missing/empty auth token — contract test
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingAuthTokenContract:
    """
    When NEXUS_AUTH_TOKEN is not configured, protected routes must return
    503 (not 200, not 500). This test FAILS if missing auth is treated as normal.
    """

    def _make_app_no_token(self):
        import os
        old = os.environ.pop("NEXUS_AUTH_TOKEN", None)
        os.environ["NEXUS_AUTH_TOKEN"] = ""
        try:
            import rest_gateway
            import server
            rest_gateway.discover_tools_from_mcp(server.mcp)
            app = rest_gateway.create_rest_app()
        finally:
            if old is not None:
                os.environ["NEXUS_AUTH_TOKEN"] = old
            else:
                os.environ.pop("NEXUS_AUTH_TOKEN", None)
        return app

    def test_missing_token_returns_503_not_200(self):
        """Protected route with missing token must return 503, not succeed."""
        os.environ["NEXUS_AUTH_TOKEN"] = ""
        try:
            import rest_gateway
            import server
            rest_gateway.discover_tools_from_mcp(server.mcp)
            app = rest_gateway.create_rest_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/tools/call",
                    json={"name": "mojo_exec", "arguments": {"code": "x = 1"}},
                    headers={"Authorization": "Bearer anything"},
                )
        finally:
            os.environ["NEXUS_AUTH_TOKEN"] = "test-token"

        assert resp.status_code == 503, (
            f"Missing NEXUS_AUTH_TOKEN must return 503, got {resp.status_code}. "
            "Empty token must not grant access."
        )

    def test_missing_token_does_not_return_500(self):
        """Missing token must return 503, not 500 (500 leaks misconfiguration info)."""
        os.environ["NEXUS_AUTH_TOKEN"] = ""
        try:
            import rest_gateway
            app = rest_gateway.create_rest_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/tools/call",
                    json={"name": "_any", "arguments": {}},
                    headers={"Authorization": "Bearer anything"},
                )
        finally:
            os.environ["NEXUS_AUTH_TOKEN"] = "test-token"

        assert resp.status_code != 500, (
            "Missing auth token returns 500 — this leaks misconfiguration information. "
            "Must return 503 instead."
        )

    def test_validate_returns_error_for_missing_token(self):
        """Config.validate() must flag missing token as an ERROR, not just a warning."""
        from config import Settings
        s = Settings(AUTH_TOKEN="")
        issues = s.validate()
        error_issues = [i for i in issues if i.startswith("ERROR:")]
        assert error_issues, (
            f"Settings.validate() must include at least one 'ERROR:' issue when AUTH_TOKEN is empty. "
            f"Got: {issues}"
        )
        assert any("NEXUS_AUTH_TOKEN" in i for i in error_issues), (
            f"ERROR issue must name NEXUS_AUTH_TOKEN. Got: {error_issues}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# S4. Invalid auth token contract
# ─────────────────────────────────────────────────────────────────────────────

class TestInvalidAuthTokenContract:
    """
    Invalid Bearer token must return 403, not 200.
    This test FAILS if auth validation is loosened.
    """

    def _make_app(self):
        import os
        os.environ["NEXUS_AUTH_TOKEN"] = "correct-token-abc123"
        import rest_gateway
        import server
        rest_gateway.discover_tools_from_mcp(server.mcp)
        return rest_gateway.create_rest_app()

    def test_wrong_token_returns_403(self):
        app = self._make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                json={"name": "_test", "arguments": {}},
                headers={"Authorization": "Bearer wrong-token-xyz"},
            )
        assert resp.status_code == 403, (
            f"Wrong token must return 403, got {resp.status_code}: {resp.text}"
        )

    def test_empty_bearer_returns_403(self):
        app = self._make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                json={"name": "_test", "arguments": {}},
                headers={"Authorization": "Bearer "},
            )
        assert resp.status_code in (401, 403), (
            f"Empty Bearer value must return 401 or 403, got {resp.status_code}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# S5. Protected endpoint unauthenticated-access behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestUnauthenticatedAccessBehavior:
    """
    Requests without any Authorization header must be rejected with 401.
    This test FAILS if any protected endpoint becomes accessible without auth.
    """

    @pytest.fixture(scope="class")
    def app(self):
        import os
        os.environ["NEXUS_AUTH_TOKEN"] = "test-unauthenticated-check"
        import rest_gateway
        import server
        rest_gateway.discover_tools_from_mcp(server.mcp)
        return rest_gateway.create_rest_app()

    def test_tools_call_no_auth_returns_401(self, app):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/tools/call", json={"name": "mojo_exec", "arguments": {}})
        assert resp.status_code == 401, (
            f"/tools/call without auth must return 401, got {resp.status_code}"
        )

    def test_list_tools_no_auth_returns_401(self, app):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tools")
        assert resp.status_code == 401, (
            f"GET /api/v1/tools without auth must return 401, got {resp.status_code}"
        )

    def test_health_endpoint_accessible_without_auth(self, app):
        """Health check must remain public — it reveals no sensitive data."""
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200, (
            f"/health must be publicly accessible without auth, got {resp.status_code}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# S6. Valid-config happy-path
# ─────────────────────────────────────────────────────────────────────────────

class TestValidConfigHappyPath:
    """
    Valid, complete configuration must produce zero errors from validate().
    This test FAILS if validate() starts returning spurious errors on valid config.
    """

    def test_valid_config_produces_no_errors(self):
        from config import Settings
        s = Settings(
            AUTH_TOKEN="test-token-abc123",
            CLOUDFLARE_API_TOKEN="cf-token",
            GITHUB_TOKEN="gh-token",
        )
        issues = s.validate()
        errors = [i for i in issues if i.startswith("ERROR:")]
        assert not errors, (
            f"Valid config must produce zero ERROR issues, got: {errors}"
        )

    def test_settings_creates_successfully_with_defaults(self):
        """Default Settings() must not raise when all env vars are sane."""
        import os
        os.environ.setdefault("NEXUS_AUTH_TOKEN", "test-token")
        from config import Settings
        try:
            s = Settings()
        except Exception as e:
            pytest.fail(f"Settings() with valid defaults must not raise: {e}")
        assert isinstance(s.PORT, int)
        assert 1 <= s.PORT <= 65535

    def test_valid_ollama_host_accepted(self):
        from config import Settings
        s = Settings(OLLAMA_HOST="http://vm2-host:11434")
        assert s.OLLAMA_HOST == "http://vm2-host:11434"

    def test_valid_https_ollama_host_accepted(self):
        from config import Settings
        s = Settings(OLLAMA_HOST="https://secure-ollama.example.com")
        assert "https://" in s.OLLAMA_HOST


# ─────────────────────────────────────────────────────────────────────────────
# S7. Malformed critical config rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestMalformedConfigRejection:
    """
    Malformed critical config values must raise ValueError, not silently degrade.
    This test FAILS if strict validation is removed from config.py.
    """

    def test_port_zero_rejected(self):
        from config import Settings, _parse_port
        with pytest.raises(ValueError, match="PORT must be"):
            _parse_port("0")

    def test_port_out_of_range_rejected(self):
        from config import Settings, _parse_port
        with pytest.raises(ValueError, match="PORT must be"):
            _parse_port("99999")

    def test_port_string_rejected(self):
        from config import Settings, _parse_port
        with pytest.raises(ValueError, match="PORT must be an integer"):
            _parse_port("not-a-number")

    def test_invalid_ollama_host_url_rejected(self):
        from config import Settings, _parse_url
        with pytest.raises(ValueError, match="OLLAMA_HOST must start with"):
            _parse_url("not-a-url:11434", "OLLAMA_HOST")

    def test_bare_hostname_ollama_host_rejected(self):
        from config import Settings, _parse_url
        with pytest.raises(ValueError, match="OLLAMA_HOST must start with"):
            _parse_url("vm2-host:11434", "OLLAMA_HOST")

    def test_wildcard_ssh_hosts_rejected(self):
        from config import _parse_allowed_hosts
        with pytest.raises(ValueError, match="must not contain wildcard"):
            _parse_allowed_hosts("*")

    def test_empty_ssh_hosts_rejected(self):
        from config import _parse_allowed_hosts
        with pytest.raises(ValueError, match="must not be empty"):
            _parse_allowed_hosts("")

    def test_empty_ollama_host_is_allowed(self):
        """
        Empty OLLAMA_HOST is allowed (means 'no local LLM configured').
        Only invalid URL format is rejected.
        """
        from config import _parse_url
        result = _parse_url("", "OLLAMA_HOST")
        assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# S8. Regression — no insecure defaults or config drift reintroduced
# ─────────────────────────────────────────────────────────────────────────────

class TestNoInsecureDefaultsRegression:
    """
    Regression tests that fire loudly if removed security improvements are reintroduced.
    """

    def test_config_no_hardcoded_cloudflare_account_id(self):
        """
        CLOUDFLARE_ACCOUNT_ID must have no hardcoded default (real account IDs were removed).
        This test FAILS if someone adds a real account ID back as a default.
        """
        config_path = MCP_SERVER_DIR / "config.py"
        content = config_path.read_text()
        # Match CLOUDFLARE_ACCOUNT_ID default that looks like a real 32-char hex ID
        bad_default = re.compile(
            r'CLOUDFLARE_ACCOUNT_ID.*os\.getenv\("CLOUDFLARE_ACCOUNT_ID".*"[a-f0-9]{20,}"'
        )
        assert not bad_default.search(content), (
            "config.py has a hardcoded Cloudflare account ID as a default value. "
            "Account identifiers must come from env vars only."
        )

    def test_config_no_hardcoded_github_owner(self):
        """
        GITHUB_OWNER must have no hardcoded default (personal identifiers were removed).
        """
        config_path = MCP_SERVER_DIR / "config.py"
        content = config_path.read_text()
        # Match GITHUB_OWNER default that looks like a real username (non-empty string after comma)
        bad_default = re.compile(
            r'GITHUB_OWNER.*os\.getenv\("GITHUB_OWNER".*"[a-zA-Z][a-zA-Z0-9_-]{2,}"'
        )
        assert not bad_default.search(content), (
            "config.py has a hardcoded GitHub owner as a default value. "
            "User identifiers must come from env vars only."
        )

    def test_config_ollama_model_not_default_model(self):
        """
        OLLAMA_MODEL must be the canonical field name in config.py (not OLLAMA_DEFAULT_MODEL).
        This test FAILS if the drift name is reintroduced.
        """
        config_path = MCP_SERVER_DIR / "config.py"
        content = config_path.read_text()
        assert "OLLAMA_DEFAULT_MODEL" not in content, (
            "config.py uses OLLAMA_DEFAULT_MODEL — this is the old drift name. "
            "Use OLLAMA_MODEL consistently."
        )

    def test_rest_gateway_missing_token_returns_503_not_500(self):
        """
        Missing auth token must return 503, not 500.
        500 leaks misconfiguration info. This was fixed and must not regress.
        """
        gw_path = MCP_SERVER_DIR / "rest_gateway.py"
        content = gw_path.read_text()
        # Find the block where empty token is handled
        # Must not use HTTP_500_INTERNAL_SERVER_ERROR
        lines = content.splitlines()
        in_empty_token_block = False
        for i, line in enumerate(lines):
            if "not expected" in line or "not _get_auth_token" in line:
                in_empty_token_block = True
            if in_empty_token_block:
                assert "HTTP_500_INTERNAL_SERVER_ERROR" not in line, (
                    f"rest_gateway.py line {i+1}: missing auth token returns 500. "
                    "Must return 503 to avoid leaking misconfiguration info."
                )
                if "raise HTTPException" in line or "HTTP_503" in line:
                    break

    def test_env_example_has_security_notes(self):
        """
        .env.example must contain security notes about NEXUS_AUTH_TOKEN.
        """
        env_path = REPO_ROOT / ".env.example"
        content = env_path.read_text()
        assert "NEXUS_AUTH_TOKEN" in content, ".env.example must mention NEXUS_AUTH_TOKEN"
        # Should warn that empty token causes 503
        assert "503" in content or "protected" in content.lower(), (
            ".env.example must document that empty NEXUS_AUTH_TOKEN causes protected routes to fail"
        )

    def test_settings_validate_returns_error_prefix_for_critical(self):
        """
        Settings.validate() must use 'ERROR:' prefix for critical issues.
        This separates errors from warnings and is testable.
        """
        from config import Settings
        s = Settings(AUTH_TOKEN="")
        issues = s.validate()
        assert any(i.startswith("ERROR:") for i in issues), (
            "Settings.validate() must use 'ERROR:' prefix for critical issues. "
            "Warnings-only for missing auth is insufficient."
        )
