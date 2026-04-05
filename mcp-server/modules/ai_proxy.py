"""
NEXUS MCP — AI Proxy Module
Route queries to: OpenAI, Gemini, Grok (xAI), DeepSeek, Anthropic, Mistral.
Lets Claude delegate research/bulk tasks to cheaper models.
"""

import json
import logging
from enum import Enum
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.ai")


class AIProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    GROK = "grok"
    DEEPSEEK = "deepseek"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"


PROVIDER_MAP = {
    AIProvider.OPENAI: {
        "url": "https://api.openai.com/v1/chat/completions",
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3-mini"],
    },
    AIProvider.GEMINI: {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    },
    AIProvider.GROK: {
        "url": "https://api.x.ai/v1/chat/completions",
        "key_env": "XAI_API_KEY",
        "default_model": "grok-4-1-fast-reasoning",
        "models": [
            "grok-3", "grok-3-mini",
            "grok-4-0709",
            "grok-4-1-fast-non-reasoning", "grok-4-1-fast-reasoning",
            "grok-4-fast-non-reasoning", "grok-4-fast-reasoning",
            "grok-4.20-beta-0309-non-reasoning", "grok-4.20-beta-0309-reasoning",
            "grok-4.20-multi-agent-beta-0309",
            "grok-code-fast-1",
        ],
    },
    AIProvider.DEEPSEEK: {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    AIProvider.ANTHROPIC: {
        "url": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
    },
    AIProvider.MISTRAL: {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key_env": "MISTRAL_API_KEY",
        "default_model": "devstral-latest",
        "models": ["devstral-latest", "mistral-large-latest", "mistral-small-latest", "codestral-latest", "open-mistral-nemo"],
    },
}


async def _call_openai_compatible(client, url: str, api_key: str, model: str,
                                   messages: list, max_tokens: int, temperature: float,
                                   system: Optional[str] = None) -> str:
    """Call OpenAI-compatible API (OpenAI, Grok, DeepSeek, Mistral)."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]

    resp = await client.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _call_gemini(client, api_key: str, model: str,
                       messages: list, max_tokens: int, temperature: float,
                       system: Optional[str] = None) -> str:
    """Call Gemini API with robust response parsing."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": f"[System instruction]: {system}"}]})
        contents.append({"role": "model", "parts": [{"text": "Understood."}]})

    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                text = parts[0].get("text")
                if text:
                    return text
    except (KeyError, IndexError, TypeError, AttributeError):
        pass

    log.warning(f"Gemini unexpected response structure: {json.dumps(data)[:500]}")
    return f"[Gemini response parse error] Raw: {json.dumps(data)[:1000]}"


async def _call_anthropic(client, api_key: str, model: str,
                          messages: list, max_tokens: int, temperature: float,
                          system: Optional[str] = None) -> str:
    """Call Anthropic API."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        payload["system"] = system

    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def register(mcp: FastMCP):
    """Register AI proxy tools."""

    class AIQueryInput(BaseModel):
        """Input for querying an AI model."""
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        provider: AIProvider = Field(..., description="AI provider: openai, gemini, grok, deepseek, anthropic, mistral")
        prompt: str = Field(..., description="User prompt / query to send", min_length=1, max_length=100000)
        system: Optional[str] = Field(None, description="Optional system prompt")
        model: Optional[str] = Field(None, description="Specific model name. If omitted, uses provider default.")
        max_tokens: int = Field(4096, description="Max response tokens", ge=1, le=128000)
        temperature: float = Field(0.7, description="Temperature (0.0-2.0)", ge=0.0, le=2.0)

    @mcp.tool(
        name="ai_query",
        annotations={
            "title": "Query AI Model",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def ai_query(params: AIQueryInput, ctx: Context) -> str:
        """Send a query to any AI provider. Use for research delegation, bulk processing,
        or getting a second opinion from another model. Returns the model's response text.

        Providers & default models:
        - openai: gpt-4o (also: gpt-4o-mini, gpt-4.1, gpt-4.1-mini, gpt-4.1-nano, o3-mini)
        - gemini: gemini-2.5-flash (also: gemini-2.5-pro, gemini-2.0-flash)
        - grok: grok-4-fast-reasoning (also: grok-4-1-fast-reasoning, grok-4.20-beta-0309-reasoning, grok-3, grok-code-fast-1)
        - deepseek: deepseek-chat (also: deepseek-reasoner)
        - anthropic: claude-sonnet-4 (also: claude-haiku-4.5)
        - mistral: devstral-latest (also: mistral-large-latest, codestral-latest, mistral-small-latest)
        """
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]
        provider_cfg = PROVIDER_MAP[params.provider]

        api_key = getattr(cfg, provider_cfg["key_env"], "")
        if not api_key:
            return f"Error: {provider_cfg['key_env']} not configured. Set this env var."

        model = params.model or provider_cfg["default_model"]
        messages = [{"role": "user", "content": params.prompt}]

        try:
            if params.provider in (AIProvider.OPENAI, AIProvider.GROK, AIProvider.DEEPSEEK, AIProvider.MISTRAL):
                result = await _call_openai_compatible(
                    client, provider_cfg["url"], api_key, model,
                    messages, params.max_tokens, params.temperature, params.system
                )
            elif params.provider == AIProvider.GEMINI:
                result = await _call_gemini(
                    client, api_key, model,
                    messages, params.max_tokens, params.temperature, params.system
                )
            elif params.provider == AIProvider.ANTHROPIC:
                result = await _call_anthropic(
                    client, api_key, model,
                    messages, params.max_tokens, params.temperature, params.system
                )
            else:
                return f"Error: Provider {params.provider} not implemented"

            log.info(f"AI query: {params.provider}/{model} — {len(result)} chars response")
            return f"**[{params.provider.value}/{model}]**\n\n{result}"

        except Exception as e:
            return f"Error calling {params.provider.value}/{model}: {e}"

    class AIMultiQueryInput(BaseModel):
        """Query multiple models in parallel for comparison."""
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        prompt: str = Field(..., description="Prompt to send to all providers", min_length=1)
        system: Optional[str] = Field(None, description="Optional system prompt for all")
        providers: list[AIProvider] = Field(
            default=[AIProvider.OPENAI, AIProvider.GEMINI, AIProvider.DEEPSEEK],
            description="List of providers to query",
        )
        max_tokens: int = Field(2048, ge=1, le=32000)
        temperature: float = Field(0.7, ge=0.0, le=2.0)

    @mcp.tool(
        name="ai_multi_query",
        annotations={
            "title": "Query Multiple AI Models",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def ai_multi_query(params: AIMultiQueryInput, ctx: Context) -> str:
        """Query multiple AI providers simultaneously and return all responses.
        Useful for comparing answers, getting consensus, or broad research.
        """
        import asyncio

        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]

        async def query_one(provider: AIProvider) -> tuple[str, str]:
            provider_cfg = PROVIDER_MAP[provider]
            api_key = getattr(cfg, provider_cfg["key_env"], "")
            if not api_key:
                return provider.value, f"[SKIP: {provider_cfg['key_env']} not set]"
            model = provider_cfg["default_model"]
            messages = [{"role": "user", "content": params.prompt}]
            try:
                if provider in (AIProvider.OPENAI, AIProvider.GROK, AIProvider.DEEPSEEK, AIProvider.MISTRAL):
                    result = await _call_openai_compatible(
                        client, provider_cfg["url"], api_key, model,
                        messages, params.max_tokens, params.temperature, params.system
                    )
                elif provider == AIProvider.GEMINI:
                    result = await _call_gemini(
                        client, api_key, model,
                        messages, params.max_tokens, params.temperature, params.system
                    )
                elif provider == AIProvider.ANTHROPIC:
                    result = await _call_anthropic(
                        client, api_key, model,
                        messages, params.max_tokens, params.temperature, params.system
                    )
                else:
                    result = "[not implemented]"
                return provider.value, result
            except Exception as e:
                return provider.value, f"[ERROR: {e}]"

        results = await asyncio.gather(*[query_one(p) for p in params.providers])

        output = "# Multi-Model Response\n\n"
        for provider_name, response in results:
            output += f"## {provider_name}\n{response}\n\n---\n\n"
        return output

    class AIListModelsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        provider: Optional[AIProvider] = Field(None, description="Filter by provider, or omit for all")

    @mcp.tool(
        name="ai_list_models",
        annotations={"title": "List Available AI Models", "readOnlyHint": True},
    )
    async def ai_list_models(params: AIListModelsInput, ctx: Context) -> str:
        """List all available AI models and their providers."""
        cfg = __import__("config").settings
        output = "# Available AI Models\n\n"

        for provider, pcfg in PROVIDER_MAP.items():
            if params.provider and params.provider != provider:
                continue
            api_key = getattr(cfg, pcfg["key_env"], "")
            status = "✅ configured" if api_key else "❌ no API key"
            output += f"## {provider.value} ({status})\n"
            output += f"Default: **{pcfg['default_model']}**\n"
            output += f"Models: {', '.join(pcfg['models'])}\n\n"

        return output
