"""Tests for LLM domain tools."""

from unittest.mock import patch, AsyncMock, MagicMock
import os
import pytest
from domains.llm import (
    qwen_complete,
    deepseek_complete,
    gpt4_complete,
    llm_complete_with_fallback,
    get_provider_status,
)


def make_mock_response(json_data: dict):
    """Create a mock httpx response with sync methods."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class TestProviderStatus:
    """Test LLM provider status detection."""

    def test_all_disabled(self):
        """No providers configured."""
        with patch.dict(os.environ, {}, clear=True):
            status = get_provider_status()
            assert status["ollama"] is False
            assert status["deepseek"] is False
            assert status["openai"] is False

    def test_some_enabled(self):
        """Some providers configured."""
        env = {
            "OLLAMA_HOST": "http://localhost:11434",
            "DEEPSEEK_API_KEY": "key123",
        }
        with patch.dict(os.environ, env):
            status = get_provider_status()
            assert status["ollama"] is True
            assert status["deepseek"] is True
            assert status["openai"] is False


@pytest.mark.asyncio
class TestQwenComplete:
    """Test Ollama Qwen completion."""

    async def test_ollama_unavailable(self):
        """Returns error when Ollama is unavailable."""
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://localhost:11434"}):
            with patch("domains.llm.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post.side_effect = Exception("Connection refused")

                result = await qwen_complete("test prompt")
                assert "error" in result
                assert result["provider"] == "ollama"

    async def test_qwen_success(self):
        """Successful Qwen completion."""
        with patch.dict(os.environ, {
            "OLLAMA_HOST": "http://localhost:11434",
            "OLLAMA_MODEL": "qwen:7b"
        }):
            mock_response = make_mock_response({
                "response": "This is a test response",
                "done": True,
            })

            with patch("domains.llm.httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                result = await qwen_complete("test prompt", max_tokens=500)
                assert result["provider"] == "ollama"
                assert result["response"] == "This is a test response"
                assert result["done"] is True


@pytest.mark.asyncio
class TestDeepseekComplete:
    """Test DeepSeek completion."""

    async def test_missing_api_key(self):
        """Returns error when API key missing."""
        with patch.dict(os.environ, {}, clear=True):
            result = await deepseek_complete("test prompt")
            assert "error" in result
            assert "DEEPSEEK_API_KEY" in result["error"]

    async def test_deepseek_success(self):
        """Successful DeepSeek completion."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test123"}):
            mock_response = make_mock_response({
                "choices": [
                    {"message": {"content": "DeepSeek response"}}
                ]
            })

            with patch("domains.llm.httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                result = await deepseek_complete("test prompt")
                assert result["provider"] == "deepseek"
                assert result["response"] == "DeepSeek response"


@pytest.mark.asyncio
class TestGPT4Complete:
    """Test OpenAI GPT-4o-mini completion."""

    async def test_missing_api_key(self):
        """Returns error when API key missing."""
        with patch.dict(os.environ, {}, clear=True):
            result = await gpt4_complete("test prompt")
            assert "error" in result
            assert "OPENAI_API_KEY" in result["error"]

    async def test_gpt4_success(self):
        """Successful GPT-4o-mini completion."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}):
            mock_response = make_mock_response({
                "choices": [
                    {"message": {"content": "GPT-4 response"}}
                ]
            })

            with patch("domains.llm.httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                result = await gpt4_complete("test prompt")
                assert result["provider"] == "openai"
                assert result["response"] == "GPT-4 response"


@pytest.mark.asyncio
class TestFallbackChain:
    """Test fallback chain behavior."""

    async def test_fallback_ollama_success(self):
        """Uses Ollama when available and working."""
        with patch.dict(os.environ, {
            "OLLAMA_HOST": "http://localhost:11434",
            "DEEPSEEK_API_KEY": "sk-test",
            "OPENAI_API_KEY": "sk-test",
        }):
            mock_response = make_mock_response({
                "response": "Local response",
                "done": True,
            })

            with patch("domains.llm.httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                result = await llm_complete_with_fallback(
                    "test",
                    prefer_local=True,
                )
                assert result["provider"] == "ollama"

    async def test_fallback_to_deepseek(self):
        """Falls back to DeepSeek when Ollama fails."""
        with patch.dict(os.environ, {
            "OLLAMA_HOST": "http://localhost:11434",
            "DEEPSEEK_API_KEY": "sk-test",
        }):
            with patch("domains.llm.qwen_complete", new_callable=AsyncMock) as mock_qwen:
                mock_qwen.return_value = {"error": "Connection failed"}

                with patch("domains.llm.deepseek_complete", new_callable=AsyncMock) as mock_deepseek:
                    mock_deepseek.return_value = {
                        "provider": "deepseek",
                        "response": "DeepSeek response",
                    }

                    result = await llm_complete_with_fallback("test", prefer_local=True)
                    assert result["provider"] == "deepseek"

    async def test_fallback_to_gpt4(self):
        """Falls back to GPT-4 when others fail."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            with patch("domains.llm.qwen_complete", new_callable=AsyncMock) as mock_qwen, \
                 patch("domains.llm.deepseek_complete", new_callable=AsyncMock) as mock_deepseek, \
                 patch("domains.llm.gpt4_complete", new_callable=AsyncMock) as mock_gpt4:
                mock_qwen.return_value = {"error": "Failed"}
                mock_deepseek.return_value = {"error": "Failed"}
                mock_gpt4.return_value = {
                    "provider": "openai",
                    "response": "GPT-4 response",
                }

                result = await llm_complete_with_fallback("test")
                assert result["provider"] == "openai"

    async def test_all_providers_fail(self):
        """Returns error when all providers fail."""
        with patch("domains.llm.qwen_complete", new_callable=AsyncMock) as mock_qwen, \
             patch("domains.llm.deepseek_complete", new_callable=AsyncMock) as mock_deepseek, \
             patch("domains.llm.gpt4_complete", new_callable=AsyncMock) as mock_gpt4:
            mock_qwen.return_value = {"error": "Failed"}
            mock_deepseek.return_value = {"error": "Failed"}
            mock_gpt4.return_value = {"error": "Failed"}

            result = await llm_complete_with_fallback("test")
            assert "error" in result
            assert "All LLM providers failed" in result["error"]

    async def test_prefer_local_false(self):
        """Skips local when prefer_local=False."""
        with patch("domains.llm.qwen_complete", new_callable=AsyncMock) as mock_qwen, \
             patch("domains.llm.deepseek_complete", new_callable=AsyncMock) as mock_deepseek:
            mock_deepseek.return_value = {
                "provider": "deepseek",
                "response": "Success",
            }

            result = await llm_complete_with_fallback(
                "test",
                prefer_local=False,
            )

            mock_qwen.assert_not_called()
            assert result["provider"] == "deepseek"
