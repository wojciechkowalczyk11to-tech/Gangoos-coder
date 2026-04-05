"""
NEXUS MCP Server - Configuration
All secrets from environment variables. Never hardcode.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """All config from env vars with sensible defaults."""

    # Auth
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

    # Cloudflare
    CLOUDFLARE_API_TOKEN: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_API_TOKEN", ""))
    CLOUDFLARE_ACCOUNT_ID: str = field(
        default_factory=lambda: os.getenv("CLOUDFLARE_ACCOUNT_ID", "c263403c94461a2bb3c5564fce8762a5")
    )
    CLOUDFLARE_ZONE_ID: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_ZONE_ID", ""))

    # GitHub
    GITHUB_TOKEN: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    GITHUB_OWNER: str = field(
        default_factory=lambda: os.getenv("GITHUB_OWNER", "wojciechkowalczyk11to-tech")
    )

    # Vercel
    VERCEL_TOKEN: str = field(default_factory=lambda: os.getenv("VERCEL_TOKEN", ""))

    # Azure
    AZURE_ACCESS_TOKEN: str = field(default_factory=lambda: os.getenv("AZURE_ACCESS_TOKEN", ""))
    AZURE_SUBSCRIPTION_ID: str = field(default_factory=lambda: os.getenv("AZURE_SUBSCRIPTION_ID", ""))

    # GitLab
    GITLAB_TOKEN: str = field(default_factory=lambda: os.getenv("GITLAB_TOKEN", ""))
    GITLAB_BASE_URL: str = field(default_factory=lambda: os.getenv("GITLAB_BASE_URL", "https://gitlab.com/api/v4"))

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

    # Shell access
    ALLOWED_SSH_HOSTS: str = field(
        default_factory=lambda: os.getenv("ALLOWED_SSH_HOSTS", "localhost")
    )

    # Server
    PORT: int = field(default_factory=lambda: int(os.getenv("PORT", "8080")))

    def get_allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_SSH_HOSTS.split(",") if h.strip()]

    def validate(self) -> list[str]:
        """Return list of missing critical configs."""
        warnings = []
        if not self.AUTH_TOKEN:
            warnings.append("NEXUS_AUTH_TOKEN not set - server has NO auth!")
        if not self.CLOUDFLARE_API_TOKEN:
            warnings.append("CLOUDFLARE_API_TOKEN missing - CF tools disabled")
        if not self.GITHUB_TOKEN:
            warnings.append("GITHUB_TOKEN missing - GitHub tools disabled")
        return warnings


settings = Settings()

# Validate on import
for w in settings.validate():
    import sys

    print(f"[CONFIG WARNING] {w}", file=sys.stderr)
