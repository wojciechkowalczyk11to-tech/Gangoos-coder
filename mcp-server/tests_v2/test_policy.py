"""Tests for policy engine module."""

import pytest
from policy import evaluate_tool_access, is_domain_enabled, domain_env_flag
from registry import ToolMeta


class TestDomainFlags:
    """Test domain enable/disable logic."""

    def test_domain_env_flag(self):
        """Correct env flag name."""
        assert domain_env_flag("llm") == "NEXUS_V2_ENABLE_LLM"
        assert domain_env_flag("control") == "NEXUS_V2_ENABLE_CONTROL"

    def test_is_domain_enabled_default(self):
        """Domains are enabled by default."""
        assert is_domain_enabled("llm", env={}) is True

    def test_is_domain_enabled_explicit(self):
        """Explicit enable."""
        env = {"NEXUS_V2_ENABLE_LLM": "true"}
        assert is_domain_enabled("llm", env=env) is True

    def test_is_domain_disabled(self):
        """Can explicitly disable domain."""
        env = {"NEXUS_V2_ENABLE_LLM": "false"}
        assert is_domain_enabled("llm", env=env) is False

    def test_is_domain_disabled_variants(self):
        """Various disable values."""
        for value in ["0", "false", "no", "off", "False", "NO"]:
            env = {"NEXUS_V2_ENABLE_LLM": value}
            assert is_domain_enabled("llm", env=env) is False


class TestPolicyEvaluation:
    """Test policy evaluation chain."""

    def test_tool_exists(self):
        """Unknown tool rejected."""
        decision = evaluate_tool_access(None)
        assert decision.allowed is False
        assert decision.status_code == 404

    def test_domain_disabled(self):
        """Disabled domain rejected."""
        meta = ToolMeta(
            name="test_tool",
            domain="llm",
            risk_level="low",
            enabled_by_default=True,
        )
        env = {"NEXUS_V2_ENABLE_LLM": "false"}
        decision = evaluate_tool_access(meta, env=env)
        assert decision.allowed is False
        assert "domain" in decision.reason.lower()

    def test_tool_disabled_by_default(self):
        """Disabled-by-default tool rejected."""
        meta = ToolMeta(
            name="dangerous_tool",
            domain="control",
            risk_level="critical",
            enabled_by_default=False,
        )
        decision = evaluate_tool_access(meta)
        assert decision.allowed is False
        assert "disabled by default" in decision.reason.lower()

    def test_confirmation_required(self):
        """Confirmation required and not provided."""
        meta = ToolMeta(
            name="risky_tool",
            domain="control",
            risk_level="critical",
            requires_confirmation=True,
        )
        decision = evaluate_tool_access(meta, confirmation_requested=False)
        assert decision.allowed is False
        assert "confirmation" in decision.reason.lower()

    def test_confirmation_provided(self):
        """Confirmation required and provided."""
        meta = ToolMeta(
            name="risky_tool",
            domain="control",
            risk_level="critical",
            requires_confirmation=True,
        )
        decision = evaluate_tool_access(meta, confirmation_requested=True)
        assert decision.allowed is True

    def test_missing_env_var(self):
        """Missing required env var."""
        meta = ToolMeta(
            name="api_tool",
            domain="llm",
            risk_level="medium",
            required_env=("OPENAI_API_KEY",),
        )
        env = {}  # Missing OPENAI_API_KEY
        decision = evaluate_tool_access(meta, env=env)
        assert decision.allowed is False
        assert "env" in decision.reason.lower()

    def test_env_var_present(self):
        """All required env vars present."""
        meta = ToolMeta(
            name="api_tool",
            domain="llm",
            risk_level="medium",
            required_env=("OPENAI_API_KEY",),
        )
        env = {"OPENAI_API_KEY": "sk-1234"}
        decision = evaluate_tool_access(meta, env=env)
        assert decision.allowed is True

    def test_rate_limit_exceeded(self):
        """Rate limit exceeded."""
        meta = ToolMeta(
            name="test_tool",
            domain="llm",
            risk_level="low",
        )
        decision = evaluate_tool_access(meta, rate_limit_ok=False)
        assert decision.allowed is False
        assert decision.status_code == 429

    def test_allowed_basic(self):
        """Basic allowed case."""
        meta = ToolMeta(
            name="test_tool",
            domain="llm",
            risk_level="low",
        )
        decision = evaluate_tool_access(meta)
        assert decision.allowed is True
        assert decision.reason == "Allowed"

    def test_full_chain(self):
        """Full evaluation chain with multiple requirements."""
        meta = ToolMeta(
            name="complex_tool",
            domain="llm",
            risk_level="medium",
            enabled_by_default=True,
            requires_confirmation=True,
            required_env=("API_KEY",),
        )

        # Missing confirmation
        decision = evaluate_tool_access(meta, env={"API_KEY": "key"})
        assert decision.allowed is False

        # Has confirmation but missing env
        decision = evaluate_tool_access(
            meta,
            confirmation_requested=True,
            env={},
        )
        assert decision.allowed is False

        # All conditions met
        decision = evaluate_tool_access(
            meta,
            confirmation_requested=True,
            env={"API_KEY": "key"},
            rate_limit_ok=True,
        )
        assert decision.allowed is True
