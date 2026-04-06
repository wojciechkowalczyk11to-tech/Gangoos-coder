"""
NEXUS MCP Server - Configuration
All secrets from environment variables. Never hardcode credentials or identifiers.
"""

import logging
import os
import sys
from dataclasses import dataclass, field

log = logging.getLogger("nexus-mcp.config")


# ── Strict parsers ────────────────────────────────────────────────────────────

def _parse_port(raw: str) -> int:
    """Parse PORT env var strictly. Raises ValueError on invalid input."""
    try:
        port = int(raw)
    except (ValueError, TypeError):
        raise ValueError(f"PORT must be an integer, got {raw!r}")
    if not (1 <= port <= 65535):
        raise ValueError(f"PORT must be 1–65535, got {port}")
    return port


def _parse_url(value: str, field_name: str) -> str:
    """Validate that a URL starts with http:// or https://. Empty string is allowed (disabled)."""
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(
            f"{field_name} must start with 'http://' or 'https://', got {value!r}"
        )
    return value


def _parse_allowed_hosts(value: str) -> str:
    """Validate ALLOWED_SSH_HOSTS: must not be empty, must not be a wildcard."""
    if not value.strip():
        raise ValueError("ALLOWED_SSH_HOSTS must not be empty")
    hosts = [h.strip() for h in value.split(",") if h.strip()]
    if "*" in hosts:
        raise ValueError("ALLOWED_SSH_HOSTS must not contain wildcard '*'")
    return value


# ── Settings dataclass ────────────────────────────────────────────────────────

@dataclass
class Settings:
    """All config from env vars with safe defaults. No credentials or identifiers hardcoded."""

    # Auth — REQUIRED for protected endpoints.
    # Empty means all protected routes return 503 (safe failure, not open access).
    AUTH_TOKEN: str = field(default_factory=lambda: os.getenv("NEXUS_AUTH_TOKEN", ""))

    # AI Providers
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    ANTHROPIC_API_KEY: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    XAI_API_KEY: str = field(default_factory=lambda: os.getenv("XAI_API_KEY", ""))
    XAI_MANAGEMENT_KEY: str = field(default_factory=lambda: os.getenv("XAI_MANAGEMENT_KEY", ""))
    DEEPSEEK_API_KEY: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    MISTRAL_API_KEY: str = field(default_factory=lambda: os.getenv("MISTRAL_API_KEY", ""))

    # GCP
    GCP_PROJECT_ID: str = field(default_factory=lambda: os.getenv("GCP_PROJECT_ID", ""))
    GCP_ZONE: str = field(default_factory=lambda: os.getenv("GCP_ZONE", "europe-central2-a"))

    # Cloudflare — no hardcoded account IDs; must be set explicitly in .env
    CLOUDFLARE_API_TOKEN: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_API_TOKEN", ""))
    CLOUDFLARE_ACCOUNT_ID: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_ACCOUNT_ID", ""))
    CLOUDFLARE_ZONE_ID: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_ZONE_ID", ""))

    # GitHub — no hardcoded owner; must be set explicitly in .env
    GITHUB_TOKEN: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    GITHUB_OWNER: str = field(default_factory=lambda: os.getenv("GITHUB_OWNER", ""))

    # Vercel
    VERCEL_TOKEN: str = field(default_factory=lambda: os.getenv("VERCEL_TOKEN", ""))

    # Azure
    AZURE_ACCESS_TOKEN: str = field(default_factory=lambda: os.getenv("AZURE_ACCESS_TOKEN", ""))
    AZURE_SUBSCRIPTION_ID: str = field(default_factory=lambda: os.getenv("AZURE_SUBSCRIPTION_ID", ""))

    # GitLab
    GITLAB_TOKEN: str = field(default_factory=lambda: os.getenv("GITLAB_TOKEN", ""))
    GITLAB_BASE_URL: str = field(default_factory=lambda: os.getenv("GITLAB_BASE_URL", "https://gitlab.com/api/v4"))

    # Local LLM — Ollama
    # Canonical env var: OLLAMA_HOST (URL to Ollama endpoint)
    # Canonical env var: OLLAMA_MODEL (model name, e.g. qwen3:8b)
    OLLAMA_HOST: str = field(default_factory=lambda: _parse_url(
        os.getenv("OLLAMA_HOST", "http://localhost:11434"), "OLLAMA_HOST"
    ))
    OLLAMA_MODEL: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:8b"))

    # Groq (fast inference fallback)
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))

    # RunPod
    RUNPOD_API_KEY: str = field(default_factory=lambda: os.getenv("RUNPOD_API_KEY", ""))
    RUNPOD_TEMPLATE_ID: str = field(default_factory=lambda: os.getenv("RUNPOD_TEMPLATE_ID", ""))

    # DigitalOcean
    DIGITALOCEAN_TOKEN: str = field(default_factory=lambda: os.getenv("DIGITALOCEAN_TOKEN", ""))

    # AWS (CLI and SDK compatible env set)
    AWS_ACCESS_KEY_ID: str = field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", ""))
    AWS_SECRET_ACCESS_KEY: str = field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", ""))
    AWS_SESSION_TOKEN: str = field(default_factory=lambda: os.getenv("AWS_SESSION_TOKEN", ""))
    AWS_REGION: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    AWS_PROFILE: str = field(default_factory=lambda: os.getenv("AWS_PROFILE", "default"))
    AWS_CLI_PATH: str = field(default_factory=lambda: os.getenv("AWS_CLI_PATH", "aws"))

    # Oracle Cloud (OCI CLI based)
    OCI_CLI_PATH: str = field(default_factory=lambda: os.getenv("OCI_CLI_PATH", "oci"))
    OCI_PROFILE: str = field(default_factory=lambda: os.getenv("OCI_PROFILE", "DEFAULT"))

    # Hugging Face / Firecrawl
    HUGGINGFACE_TOKEN: str = field(default_factory=lambda: os.getenv("HUGGINGFACE_TOKEN", ""))
    FIRECRAWL_API_KEY: str = field(default_factory=lambda: os.getenv("FIRECRAWL_API_KEY", ""))

    # Google Drive / Vertex
    VERTEX_LOCATION: str = field(default_factory=lambda: os.getenv("VERTEX_LOCATION", "europe-central2"))

    # Shell access — allowlist for SSH targets
    ALLOWED_SSH_HOSTS: str = field(default_factory=lambda: _parse_allowed_hosts(
        os.getenv("ALLOWED_SSH_HOSTS", "localhost")
    ))

    # Server port — strictly validated (must be 1–65535)
    PORT: int = field(default_factory=lambda: _parse_port(os.getenv("PORT", "8080")))

    def get_allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_SSH_HOSTS.split(",") if h.strip()]

    def validate(self) -> list[str]:
        """
        Return list of configuration issues.
        Issues prefixed 'ERROR:' are critical — the server will not serve protected routes.
        Issues prefixed 'WARNING:' indicate disabled features.
        """
        issues: list[str] = []
        if not self.AUTH_TOKEN:
            issues.append(
                "ERROR: NEXUS_AUTH_TOKEN not set — all protected routes will return 503. "
                "Set NEXUS_AUTH_TOKEN in .env before accepting traffic."
            )
        if not self.CLOUDFLARE_API_TOKEN:
            issues.append("WARNING: CLOUDFLARE_API_TOKEN missing — Cloudflare tools disabled")
        if not self.GITHUB_TOKEN:
            issues.append("WARNING: GITHUB_TOKEN missing — GitHub tools disabled")
        return issues


settings = Settings()

# Report configuration issues at startup
_issues = settings.validate()
for issue in _issues:
    if issue.startswith("ERROR:"):
        log.error("[CONFIG] %s", issue)
    else:
        log.warning("[CONFIG] %s", issue)
