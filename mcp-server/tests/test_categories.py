"""
Tests for category tools — each category tool returns valid structure.
Uses mocks for external APIs.
"""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from categories import Category, CategoryRegistry


@pytest.fixture
def cat_registry():
    """Fresh category registry."""
    return CategoryRegistry()


class TestCategoryRegistry:
    """CategoryRegistry unit tests."""

    def test_register_tool(self, cat_registry):
        """Should register tool with category."""
        cat_registry.register_tool("test_tool", Category.LLM_WORKERS, "low", "Test")
        mapping = cat_registry.get("test_tool")
        assert mapping is not None
        assert mapping.category == Category.LLM_WORKERS
        assert mapping.requires_totp is False  # CAT-1 = open

    def test_totp_required_for_control(self, cat_registry):
        """Control tools should require TOTP."""
        cat_registry.register_tool("shell", Category.CONTROL_SHELL, "critical")
        assert cat_registry.requires_totp("shell") is True

    def test_totp_not_required_for_llm(self, cat_registry):
        """LLM tools should NOT require TOTP."""
        cat_registry.register_tool("gpt", Category.LLM_WORKERS, "medium")
        assert cat_registry.requires_totp("gpt") is False

    def test_unknown_tool_requires_totp(self, cat_registry):
        """Unknown tools should require TOTP (safe default)."""
        assert cat_registry.requires_totp("unknown_tool") is True

    def test_list_by_category(self, cat_registry):
        """Should filter tools by category."""
        cat_registry.register_tool("grok", Category.LLM_WORKERS, "medium")
        cat_registry.register_tool("shell", Category.CONTROL_SHELL, "critical")
        cat_registry.register_tool("groq", Category.LLM_WORKERS, "medium")

        llm_tools = cat_registry.list_tools(Category.LLM_WORKERS)
        assert len(llm_tools) == 2
        assert all(t.category == Category.LLM_WORKERS for t in llm_tools)

    def test_list_categories(self, cat_registry):
        """Should return category-to-tools mapping."""
        cat_registry.register_tool("grok", Category.LLM_WORKERS, "medium")
        cat_registry.register_tool("shell", Category.CONTROL_SHELL, "critical")

        cats = cat_registry.list_categories()
        assert "cat1_llm" in cats
        assert "cat2_control" in cats
        assert "grok" in cats["cat1_llm"]

    def test_as_serializable(self, cat_registry):
        """Should return JSON-serializable list."""
        cat_registry.register_tool("grok", Category.LLM_WORKERS, "medium", "Test grok")
        result = cat_registry.as_serializable()
        assert len(result) == 1
        assert result[0]["tool_name"] == "grok"
        assert result[0]["category"] == "cat1_llm"


class TestLLMWorkers:
    """CAT-1 LLM worker tests with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_grok_analyze_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import grok_analyze
        with patch.dict("os.environ", {"XAI_API_KEY": ""}, clear=False):
            result = await grok_analyze("test prompt")
            assert "error" in result
            assert result["provider"] == "xai_grok"

    @pytest.mark.asyncio
    async def test_groq_fast_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import groq_fast
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}, clear=False):
            result = await groq_fast("test")
            assert "error" in result
            assert result["provider"] == "groq"

    @pytest.mark.asyncio
    async def test_claude_complete_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import claude_complete
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = await claude_complete("test")
            assert "error" in result
            assert result["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_gpt_complete_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import gpt_complete
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            result = await gpt_complete("test")
            assert "error" in result
            assert result["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_deepseek_code_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import deepseek_code
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
            result = await deepseek_code("test")
            assert "error" in result
            assert result["provider"] == "deepseek"

    @pytest.mark.asyncio
    async def test_gemini_generate_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import gemini_generate
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
            result = await gemini_generate("test")
            assert "error" in result
            assert result["provider"] == "gemini"

    @pytest.mark.asyncio
    async def test_mistral_codestral_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import mistral_codestral
        with patch.dict("os.environ", {"MISTRAL_API_KEY": ""}, clear=False):
            result = await mistral_codestral("test")
            assert "error" in result
            assert result["provider"] == "mistral"

    @pytest.mark.asyncio
    async def test_ollama_local_connection_error(self):
        """Should handle connection errors gracefully."""
        from categories.llm_workers import ollama_local
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://localhost:99999"}, clear=False):
            result = await ollama_local("test")
            assert "error" in result
            assert result["provider"] == "ollama"

    @pytest.mark.asyncio
    async def test_jules_agent_no_key(self):
        """Should return error when API key missing."""
        from categories.llm_workers import jules_agent
        with patch.dict("os.environ", {"JULES_API_KEY": ""}, clear=False):
            result = await jules_agent("test task")
            assert "error" in result
            assert result["provider"] == "jules"

    @pytest.mark.asyncio
    async def test_grok_analyze_success_mock(self):
        """Should return structured response on success."""
        from categories.llm_workers import grok_analyze
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await grok_analyze("Analyze this")
                assert result["provider"] == "xai_grok"
                assert result["response"] == "Test response"
                assert "usage" in result


class TestControlShell:
    """CAT-2 control shell tests."""

    @pytest.mark.asyncio
    async def test_shell_execute_basic(self):
        """Should execute simple command."""
        from categories.control_shell import shell_execute
        result = await shell_execute("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_shell_execute_timeout_limit(self):
        """Should reject excessive timeout."""
        from categories.control_shell import shell_execute
        result = await shell_execute("echo test", timeout=999)
        assert "error" in result
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_vm_manage_no_token(self):
        """Should return error without DO token."""
        from categories.control_shell import vm_manage
        with patch.dict("os.environ", {"DIGITALOCEAN_TOKEN": ""}, clear=False):
            result = await vm_manage("list")
            assert "error" in result


class TestResearch:
    """CAT-4 research tools tests."""

    @pytest.mark.asyncio
    async def test_web_fetch_valid_url(self):
        """Should fetch valid URL (mocked)."""
        from categories.research import web_fetch
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.text = "<html>Hello</html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await web_fetch("https://example.com")
            assert result["status_code"] == 200
            assert "content" in result

    @pytest.mark.asyncio
    async def test_web_fetch_invalid_url(self):
        """Should reject non-http URL."""
        from categories.research import web_fetch
        result = await web_fetch("ftp://evil.com")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_firecrawl_no_key(self):
        """Should return error without API key."""
        from categories.research import firecrawl_scrape
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": ""}, clear=False):
            result = await firecrawl_scrape("https://example.com")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_perplexity_no_key(self):
        """Should return error without API key."""
        from categories.research import perplexity_ask
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": ""}, clear=False):
            result = await perplexity_ask("What is Python?")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_manus_no_keys(self):
        """Should return error without any Manus keys."""
        from categories.research import manus_agent_task
        env_overrides = {"MANUS_API_KEY": ""}
        for i in range(1, 7):
            env_overrides[f"MANUS_API_KEY_{i}"] = ""
        with patch.dict("os.environ", env_overrides, clear=False):
            result = await manus_agent_task("test task")
            assert "error" in result


class TestCloud:
    """CAT-7 cloud tools tests."""

    @pytest.mark.asyncio
    async def test_digitalocean_no_token(self):
        """Should return error without DO token."""
        from categories.cloud import digitalocean_manage
        with patch.dict("os.environ", {"DIGITALOCEAN_TOKEN": ""}, clear=False):
            result = await digitalocean_manage("list")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_runpod_no_key(self):
        """Should return error without RunPod key."""
        from categories.cloud import runpod_gpu
        with patch.dict("os.environ", {"RUNPOD_API_KEY": ""}, clear=False):
            result = await runpod_gpu("list_gpus")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_cloudflare_no_token(self):
        """Should return error without CF token."""
        from categories.cloud import cloudflare_manage
        with patch.dict("os.environ", {"CLOUDFLARE_API_TOKEN": ""}, clear=False):
            result = await cloudflare_manage("list_zones")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_render_no_key(self):
        """Should return error without Render key."""
        from categories.cloud import render_deploy
        with patch.dict("os.environ", {"RENDER_API_KEY": ""}, clear=False):
            result = await render_deploy("list_services")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_digitalocean_invalid_action(self):
        """Should return error for invalid action."""
        from categories.cloud import digitalocean_manage
        with patch.dict("os.environ", {"DIGITALOCEAN_TOKEN": "test-token"}, clear=False):
            result = await digitalocean_manage("invalid_action")
            assert "error" in result
