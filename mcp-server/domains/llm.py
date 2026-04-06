"""
LLM Domain - Language model integration with fallback chain.
Supports: Ollama/Qwen (local) → DeepSeek → GPT-4o-mini
Risk level: MEDIUM (requires API keys)
"""

from __future__ import annotations

import os
from typing import Any, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from registry import ToolMeta, ToolRegistry


async def qwen_complete(prompt: str, max_tokens: int = 1000) -> dict:
    """
    Call local Ollama with Qwen model.
    Returns dict with response and model info.
    """
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen:7b")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{ollama_host}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "provider": "ollama",
                "model": ollama_model,
                "response": data.get("response", ""),
                "done": data.get("done", False),
            }
    except Exception as e:
        return {
            "error": f"Ollama failed: {e}",
            "provider": "ollama",
        }


async def deepseek_complete(prompt: str, max_tokens: int = 1000) -> dict:
    """
    Call DeepSeek API.
    Requires DEEPSEEK_API_KEY env var.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"error": "DEEPSEEK_API_KEY not set", "provider": "deepseek"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "response": data["choices"][0]["message"]["content"],
            }
    except Exception as e:
        return {
            "error": f"DeepSeek failed: {e}",
            "provider": "deepseek",
        }


async def gpt4_complete(prompt: str, max_tokens: int = 1000) -> dict:
    """
    Call OpenAI GPT-4o-mini.
    Requires OPENAI_API_KEY env var.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set", "provider": "openai"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "response": data["choices"][0]["message"]["content"],
            }
    except Exception as e:
        return {
            "error": f"OpenAI failed: {e}",
            "provider": "openai",
        }


async def llm_complete_with_fallback(
    prompt: str,
    max_tokens: int = 1000,
    prefer_local: bool = True,
) -> dict:
    """
    Complete text with fallback chain:
    1. Ollama/Qwen (local, free) - if available and prefer_local=True
    2. DeepSeek (cheap, fast)
    3. GPT-4o-mini (expensive, most capable)
    """
    results = []

    # Try Ollama first if preferred
    if prefer_local:
        result = await qwen_complete(prompt, max_tokens)
        results.append(result)
        if "error" not in result:
            return result

    # Try DeepSeek
    result = await deepseek_complete(prompt, max_tokens)
    results.append(result)
    if "error" not in result:
        return result

    # Fall back to GPT-4o-mini
    result = await gpt4_complete(prompt, max_tokens)
    results.append(result)
    if "error" not in result:
        return result

    # All failed - return fallback info
    return {
        "error": "All LLM providers failed",
        "attempts": results,
    }


def get_provider_status() -> dict[str, bool]:
    """Check which LLM providers are available."""
    providers = {
        "ollama": bool(os.getenv("OLLAMA_HOST")),
        "deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
    }
    return providers


async def register(mcp: Any, registry: ToolRegistry) -> None:
    """Register LLM domain tools."""
    from pydantic import BaseModel, ConfigDict, Field

    # Tool 1: Provider status
    registry.register(
        ToolMeta(
            name="llm_provider_status",
            domain="llm",
            risk_level="low",
            description="Check which LLM providers are configured.",
            tags=("llm", "providers", "status"),
        )
    )

    class ProviderStatusInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        include_details: bool = Field(False, description="Include provider details")

    @mcp.tool(
        name="llm_provider_status",
        annotations={"title": "LLM Provider Status", "readOnlyHint": True},
    )
    async def llm_provider_status(params: ProviderStatusInput, ctx: Any) -> dict:
        """Get LLM provider status."""
        status = get_provider_status()
        return {
            "providers": status,
            "available": [p for p, enabled in status.items() if enabled],
        }

    # Tool 2: LLM completion with fallback
    registry.register(
        ToolMeta(
            name="llm_complete",
            domain="llm",
            risk_level="medium",
            description="Complete text with LLM (fallback chain: Qwen → DeepSeek → GPT-4o-mini)",
            tags=("llm", "completion", "text"),
        )
    )

    class LLMCompleteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        prompt: str = Field(..., min_length=1, max_length=4000)
        max_tokens: int = Field(1000, ge=10, le=4000)
        prefer_local: bool = Field(True, description="Try local Ollama first")

    @mcp.tool(
        name="llm_complete",
        annotations={"title": "LLM Text Completion", "openWorldHint": True},
    )
    async def llm_complete(params: LLMCompleteInput, ctx: Any) -> dict:
        """Complete text with LLM."""
        return await llm_complete_with_fallback(
            params.prompt,
            params.max_tokens,
            params.prefer_local,
        )
