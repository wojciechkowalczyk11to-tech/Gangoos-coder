"""
NEXUS MCP Server v2 - Configuration
All secrets from environment variables. Never hardcode.
"""

import os
from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class RateLimitConfig:
    """Rate limiting configuration per domain."""
    control: int = 10         # control domain: 10 requests per minute
    llm: int = 30            # llm domain: 30 requests per minute
    research: int = 60       # research domain: 60 requests per minute
    knowledge: int = 120     # knowledge domain: 120 requests per minute
    default: int = 30        # default: 30 requests per minute


@dataclass
class Settings:
    """All config from env vars with sensible defaults."""

    # Auth
    AUTH_TOKEN: str = field(default_factory=lambda: os.getenv("NEXUS_AUTH_TOKEN", ""))

    # AI Providers
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    ANTHROPIC_API_KEY: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    DEEPSEEK_API_KEY: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))

    # Local LLM - Ollama
    OLLAMA_HOST: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    OLLAMA_MODEL: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen:7b"))

    # Rate limiting (configurable per domain)
    RATE_LIMIT_CONTROL: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_CONTROL", "10"))
    )
    RATE_LIMIT_LLM: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_LLM", "30"))
    )
    RATE_LIMIT_RESEARCH: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_RESEARCH", "60"))
    )
    RATE_LIMIT_KNOWLEDGE: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_KNOWLEDGE", "120"))
    )

    # Control domain safety (disabled by default)
    ENABLE_CONTROL_DOMAIN: bool = field(
        default_factory=lambda: os.getenv("ENABLE_CONTROL_DOMAIN", "false").lower() in {"1", "true", "yes"}
    )

    # Audit logging
    AUDIT_LOG_PATH: str = field(default_factory=lambda: os.getenv("AUDIT_LOG_PATH", "./logs/nexus_v2_audit.jsonl"))

    # Server
    PORT: int = field(default_factory=lambda: int(os.getenv("PORT", "8080")))
    HOST: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))

    def get_rate_limit_config(self) -> RateLimitConfig:
        """Return rate limit configuration object."""
        return RateLimitConfig(
            control=self.RATE_LIMIT_CONTROL,
            llm=self.RATE_LIMIT_LLM,
            research=self.RATE_LIMIT_RESEARCH,
            knowledge=self.RATE_LIMIT_KNOWLEDGE,
        )

    def validate(self) -> list[str]:
        """Return list of configuration issues."""
        warnings = []
        if not self.AUTH_TOKEN:
            warnings.append("WARNING: NEXUS_AUTH_TOKEN not set - server has NO authentication!")
        if not self.OPENAI_API_KEY and not self.DEEPSEEK_API_KEY and not self.GROQ_API_KEY:
            warnings.append("WARNING: No LLM API keys configured - LLM tools disabled")
        if self.ENABLE_CONTROL_DOMAIN:
            warnings.append("WARNING: Control domain ENABLED - high-risk shell/filesystem operations available")
        return warnings


settings = Settings()
