"""
Shared test fixtures for mcp-server tests.
pytest.ini sets pythonpath=mcp-server so all imports resolve from repo root.
"""
import os
import sys
from pathlib import Path

import pytest

# Ensure mcp-server is on path even if pytest.ini is absent (e.g. direct invocation)
_mcp_root = Path(__file__).parent.parent
if str(_mcp_root) not in sys.path:
    sys.path.insert(0, str(_mcp_root))

# Point dotenv at a non-existent .env so server.py dotenv load is a no-op in tests
os.environ.setdefault("NEXUS_AUTH_TOKEN", "test-token")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")


@pytest.fixture(autouse=False)
def clean_env(monkeypatch):
    """Fixture: clean sensitive env vars for isolated config tests."""
    for key in ("NEXUS_AUTH_TOKEN", "OLLAMA_HOST", "GROQ_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield
