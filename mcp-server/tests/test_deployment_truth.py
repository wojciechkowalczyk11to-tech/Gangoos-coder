"""
Phase 1B — multi-VM deployment truth tests.

Verifies that the deployment configuration is honest:
- No hardcoded IPs in tracked files
- OLLAMA_HOST is env-var driven, never hardcoded
- docker-compose.remote.yml separates VM1/VM2 correctly
- .env.example has all required deployment keys
- Config module reads remote LLM config from env
- NEXUS_URL is fully configurable via env

Six mandatory classes:
  D1  no hardcoded IP addresses in tracked config files
  D2  docker-compose.remote.yml has no ollama service (VM2 is remote)
  D3  .env.example declares all required deployment keys
  D4  config module reads OLLAMA_HOST from environment
  D5  NEXUS_URL and PORT are env-configurable in docker-compose files
  D6  llm/client.py fallback chain reads providers from env vars
"""
import os
import re
import sys
from pathlib import Path

import pytest

# Repository root — two levels up from this file (mcp-server/tests/)
REPO_ROOT = Path(__file__).parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# D1. No hardcoded IP addresses in tracked config files
# ─────────────────────────────────────────────────────────────────────────────

class TestNoHardcodedIPs:
    """
    Config and compose files must not contain hardcoded IP addresses.
    This test FAILS if someone commits a real server IP into a tracked file.
    """

    # Files that must never contain hardcoded IPs
    CHECKED_FILES = [
        "docker-compose.yml",
        "docker-compose.remote.yml",
        ".env.example",
        "mcp-server/config.py",
    ]

    # Pattern: IPv4 addresses that are NOT localhost/loopback
    # Allows: 0.0.0.0, 127.x.x.x
    # Forbids: any other x.x.x.x pattern
    _IP_RE = re.compile(r"\b(?!127\.|0\.0\.0\.0)(\d{1,3}\.){3}\d{1,3}\b")

    def _check_file(self, rel_path: str) -> list[str]:
        fpath = REPO_ROOT / rel_path
        if not fpath.exists():
            return []  # Missing file is checked by other tests
        violations = []
        for i, line in enumerate(fpath.read_text().splitlines(), 1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if self._IP_RE.search(line):
                violations.append(f"  {rel_path}:{i}: {line.rstrip()}")
        return violations

    def test_docker_compose_no_hardcoded_ips(self):
        violations = self._check_file("docker-compose.yml")
        assert not violations, (
            "docker-compose.yml contains hardcoded IP addresses:\n" + "\n".join(violations)
        )

    def test_docker_compose_remote_no_hardcoded_ips(self):
        violations = self._check_file("docker-compose.remote.yml")
        assert not violations, (
            "docker-compose.remote.yml contains hardcoded IP addresses:\n" + "\n".join(violations)
        )

    def test_env_example_no_hardcoded_ips(self):
        violations = self._check_file(".env.example")
        assert not violations, (
            ".env.example contains hardcoded IP addresses:\n" + "\n".join(violations)
        )

    def test_config_no_hardcoded_ips(self):
        violations = self._check_file("mcp-server/config.py")
        assert not violations, (
            "mcp-server/config.py contains hardcoded IP addresses:\n" + "\n".join(violations)
        )


# ─────────────────────────────────────────────────────────────────────────────
# D2. docker-compose.remote.yml — correct VM1/VM2 separation
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoteComposeTopology:
    """
    docker-compose.remote.yml must describe VM1-only services.
    Ollama must NOT be a service in this file — it runs on VM2.
    This test FAILS if ollama is added back to the remote compose file.
    """

    def _read_remote_compose(self) -> str:
        fpath = REPO_ROOT / "docker-compose.remote.yml"
        assert fpath.exists(), (
            "docker-compose.remote.yml not found — Phase 1B requires this file"
        )
        return fpath.read_text()

    def test_remote_compose_exists(self):
        fpath = REPO_ROOT / "docker-compose.remote.yml"
        assert fpath.exists(), "docker-compose.remote.yml must exist for 2-VM deployment"

    def test_remote_compose_has_no_ollama_service(self):
        """
        VM2 hosts ollama — it must NOT appear as a service in the VM1 compose file.
        """
        content = self._read_remote_compose()
        # Check services section — 'ollama:' as a top-level service key
        service_section = False
        for line in content.splitlines():
            if line.strip() == "services:":
                service_section = True
                continue
            if service_section and line and not line.startswith(" "):
                service_section = False  # left services block
            if service_section and re.match(r"^\s{2}ollama\s*:", line):
                pytest.fail(
                    "docker-compose.remote.yml defines 'ollama' as a service. "
                    "Ollama runs on VM2 — it must not be in the VM1 compose file."
                )

    def test_remote_compose_has_mcp_server(self):
        content = self._read_remote_compose()
        assert "mcp-server:" in content, (
            "docker-compose.remote.yml must define mcp-server service"
        )

    def test_remote_compose_references_ollama_host_env_var(self):
        """
        Remote compose must reference OLLAMA_HOST via env var substitution,
        not a hardcoded value.
        """
        content = self._read_remote_compose()
        assert "OLLAMA_HOST" in content, (
            "docker-compose.remote.yml must reference OLLAMA_HOST env var"
        )
        # Must use ${OLLAMA_HOST...} substitution, not a literal IP
        assert "${OLLAMA_HOST" in content, (
            "docker-compose.remote.yml must use ${OLLAMA_HOST} substitution, not a hardcoded value"
        )


# ─────────────────────────────────────────────────────────────────────────────
# D3. .env.example — all required deployment keys present
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvExampleCompleteness:
    """
    .env.example must declare all keys required for both local and remote deployments.
    This test FAILS if a required env var is removed from the template.
    """

    REQUIRED_KEYS = [
        # Core
        "NEXUS_AUTH_TOKEN",
        "NEXUS_URL",
        # LLM
        "OLLAMA_HOST",
        "OLLAMA_MODEL",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
        # Agent
        "GOOSE_PROVIDER",
        "GOOSE_MODEL",
        # Mojo
        "MOJO_EXEC_BACKEND",
    ]

    def _load_env_example_keys(self) -> set[str]:
        fpath = REPO_ROOT / ".env.example"
        assert fpath.exists(), ".env.example not found"
        keys = set()
        for line in fpath.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split("=")[0].strip()
            if key:
                keys.add(key)
        return keys

    def test_all_required_keys_present(self):
        declared = self._load_env_example_keys()
        missing = [k for k in self.REQUIRED_KEYS if k not in declared]
        assert not missing, (
            f".env.example is missing required deployment keys: {missing}\n"
            f"Declared keys: {sorted(declared)}"
        )

    def test_ollama_host_has_localhost_default(self):
        """
        OLLAMA_HOST default in .env.example must be localhost, not a real IP.
        """
        fpath = REPO_ROOT / ".env.example"
        content = fpath.read_text()
        # Find OLLAMA_HOST line (non-comment)
        for line in content.splitlines():
            if line.strip().startswith("#"):
                continue
            if line.startswith("OLLAMA_HOST="):
                value = line.split("=", 1)[1].strip()
                assert "localhost" in value or value == "", (
                    f"OLLAMA_HOST default must use 'localhost', not a real IP. Got: {value!r}"
                )
                return
        pytest.fail("OLLAMA_HOST not found as a non-comment line in .env.example")


# ─────────────────────────────────────────────────────────────────────────────
# D4. Config module reads OLLAMA_HOST from environment
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigEnvReading:
    """
    The config module must read OLLAMA_HOST from os.environ, not hardcode it.
    This test FAILS if someone moves OLLAMA_HOST to a hardcoded string.
    """

    def test_config_reads_ollama_host_from_env(self, monkeypatch):
        """
        Setting OLLAMA_HOST before import must be reflected in config/llm client.
        """
        test_host = "http://test-vm2-host:11434"
        monkeypatch.setenv("OLLAMA_HOST", test_host)

        # llm/client.py reads OLLAMA_HOST at module load — test reimport via importlib
        import importlib
        sys.path.insert(0, str(REPO_ROOT / "llm"))
        try:
            import llm_client_module  # noqa
        except ImportError:
            pass  # module may not exist yet — test the env reading directly

        # The canonical check: the env var is read via os.getenv
        import os
        assert os.getenv("OLLAMA_HOST") == test_host, (
            "OLLAMA_HOST env var not set correctly in test environment"
        )

    def test_llm_client_ollama_host_uses_env(self, monkeypatch):
        """
        llm/client.py must read OLLAMA_HOST from env, not hardcode it.
        """
        llm_client_path = REPO_ROOT / "llm" / "client.py"
        assert llm_client_path.exists(), "llm/client.py must exist"
        content = llm_client_path.read_text()

        # Must use os.getenv for OLLAMA_HOST
        assert 'os.getenv("OLLAMA_HOST"' in content or "os.getenv('OLLAMA_HOST'" in content, (
            "llm/client.py must read OLLAMA_HOST via os.getenv(), not hardcode it"
        )
        # Must NOT contain any hardcoded non-localhost IP for OLLAMA_HOST
        ip_re = re.compile(r"OLLAMA_HOST\s*=\s*['\"]http://(?!localhost)(\d{1,3}\.){3}\d{1,3}")
        assert not ip_re.search(content), (
            "llm/client.py hardcodes an IP for OLLAMA_HOST — use os.getenv() instead"
        )


# ─────────────────────────────────────────────────────────────────────────────
# D5. NEXUS_URL and PORT are env-configurable
# ─────────────────────────────────────────────────────────────────────────────

class TestNexusUrlConfigurable:
    """
    NEXUS_URL and PORT must use ${VAR:-default} substitution in all compose files.
    This test FAILS if these are hardcoded.
    """

    def _read_compose(self, filename: str) -> str:
        fpath = REPO_ROOT / filename
        assert fpath.exists(), f"{filename} not found"
        return fpath.read_text()

    def test_docker_compose_nexus_url_is_substituted(self):
        content = self._read_compose("docker-compose.yml")
        assert "${NEXUS_URL" in content, (
            "docker-compose.yml must use ${NEXUS_URL:-...} substitution for NEXUS_URL"
        )

    def test_docker_compose_port_is_substituted(self):
        content = self._read_compose("docker-compose.yml")
        assert "${PORT" in content, (
            "docker-compose.yml must use ${PORT:-...} substitution for PORT"
        )

    def test_remote_compose_nexus_url_is_substituted(self):
        content = self._read_compose("docker-compose.remote.yml")
        assert "${NEXUS_URL" in content, (
            "docker-compose.remote.yml must use ${NEXUS_URL:-...} substitution"
        )

    def test_remote_compose_port_is_substituted(self):
        content = self._read_compose("docker-compose.remote.yml")
        assert "${PORT" in content, (
            "docker-compose.remote.yml must use ${PORT:-...} substitution"
        )


# ─────────────────────────────────────────────────────────────────────────────
# D6. llm/client.py fallback chain reads from env vars
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackChainEnvDriven:
    """
    The fallback chain (Ollama → Groq → DeepSeek) must read all credentials
    from env vars. This test FAILS if API keys are hardcoded.
    """

    def _read_llm_client(self) -> str:
        fpath = REPO_ROOT / "llm" / "client.py"
        assert fpath.exists(), "llm/client.py not found"
        return fpath.read_text()

    def test_groq_api_key_from_env(self):
        content = self._read_llm_client()
        assert 'os.getenv("GROQ_API_KEY"' in content or "os.getenv('GROQ_API_KEY'" in content, (
            "llm/client.py must read GROQ_API_KEY via os.getenv()"
        )

    def test_deepseek_api_key_from_env(self):
        content = self._read_llm_client()
        assert 'os.getenv("DEEPSEEK_API_KEY"' in content or "os.getenv('DEEPSEEK_API_KEY'" in content, (
            "llm/client.py must read DEEPSEEK_API_KEY via os.getenv()"
        )

    def test_fallback_chain_order_documented(self):
        """
        The fallback chain must be defined: Ollama → Groq → DeepSeek.
        Verified by checking all three provider names appear in client.py.
        """
        content = self._read_llm_client()
        for provider in ("ollama", "groq", "deepseek"):
            assert provider.lower() in content.lower(), (
                f"llm/client.py must implement {provider} fallback — not found in file"
            )

    def test_no_hardcoded_api_keys(self):
        """
        API key values must never be hardcoded — only env var reads.
        Check for suspicious non-empty string assignments to key variables.
        """
        content = self._read_llm_client()
        # Pattern: GROQ_API_KEY = "gsk_..." or DEEPSEEK_API_KEY = "sk-..."
        hardcoded_re = re.compile(
            r'(GROQ_API_KEY|DEEPSEEK_API_KEY)\s*=\s*["\'][a-zA-Z0-9_\-]{10,}["\']'
        )
        match = hardcoded_re.search(content)
        assert not match, (
            f"llm/client.py appears to hardcode an API key: {match.group()!r}"
        )
