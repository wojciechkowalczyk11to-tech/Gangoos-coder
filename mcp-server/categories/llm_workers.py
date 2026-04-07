"""
CAT-1: LLM Workers — 9 LLM connectors.

Each connector calls its respective API via httpx async,
returns structured dict with provider, model, response fields.
All API keys from environment variables.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from categories import Category, CategoryRegistry


async def _call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    provider: str,
    system_prompt: Optional[str] = None,
    timeout: float = 60.0,
) -> dict:
    """Shared caller for OpenAI-compatible APIs."""
    if not api_key:
        return {"error": f"{provider} API key not configured", "provider": provider}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return {
                "provider": provider,
                "model": model,
                "response": choice["message"]["content"],
                "finish_reason": choice.get("finish_reason", "unknown"),
                "usage": data.get("usage", {}),
            }
    except httpx.HTTPStatusError as e:
        return {
            "error": f"{provider} HTTP {e.response.status_code}: {e.response.text[:500]}",
            "provider": provider,
            "model": model,
        }
    except Exception as e:
        return {"error": f"{provider} failed: {e}", "provider": provider, "model": model}


async def grok_analyze(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "grok-3-latest",
) -> dict:
    """xAI Grok — analiza, długi kontekst, rozumowanie."""
    return await _call_openai_compatible(
        base_url="https://api.x.ai/v1",
        api_key=os.getenv("XAI_API_KEY", ""),
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        provider="xai_grok",
    )


async def groq_fast(
    prompt: str,
    max_tokens: int = 1500,
    model: str = "llama-3.3-70b-versatile",
) -> dict:
    """Groq — ultra-fast inference (Llama, Qwen)."""
    return await _call_openai_compatible(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY", ""),
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        provider="groq",
    )


async def claude_complete(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "claude-sonnet-4-20250514",
    system_prompt: Optional[str] = None,
) -> dict:
    """Anthropic Claude — via Messages API (not OpenAI-compatible)."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured", "provider": "anthropic"}

    messages = [{"role": "user", "content": prompt}]
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if system_prompt:
        body["system"] = system_prompt

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
            return {
                "provider": "anthropic",
                "model": model,
                "response": "\n".join(text_blocks),
                "stop_reason": data.get("stop_reason", "unknown"),
                "usage": data.get("usage", {}),
            }
    except httpx.HTTPStatusError as e:
        return {
            "error": f"Anthropic HTTP {e.response.status_code}: {e.response.text[:500]}",
            "provider": "anthropic",
            "model": model,
        }
    except Exception as e:
        return {"error": f"Anthropic failed: {e}", "provider": "anthropic", "model": model}


async def gpt_complete(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "gpt-4o-mini",
    system_prompt: Optional[str] = None,
) -> dict:
    """OpenAI GPT — completion via chat API."""
    return await _call_openai_compatible(
        base_url="https://api.openai.com/v1",
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        provider="openai",
        system_prompt=system_prompt,
    )


async def deepseek_code(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "deepseek-chat",
) -> dict:
    """DeepSeek — code generation and verification."""
    return await _call_openai_compatible(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        provider="deepseek",
        system_prompt="You are a senior software engineer. Provide clean, tested code.",
    )


async def gemini_generate(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "gemini-2.0-flash",
) -> dict:
    """Google Gemini — multimodal generation."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY not configured", "provider": "gemini"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"error": "No candidates returned", "provider": "gemini", "model": model}
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "\n".join(p.get("text", "") for p in parts)
            return {
                "provider": "gemini",
                "model": model,
                "response": text,
                "finish_reason": candidates[0].get("finishReason", "unknown"),
                "usage": data.get("usageMetadata", {}),
            }
    except httpx.HTTPStatusError as e:
        return {
            "error": f"Gemini HTTP {e.response.status_code}: {e.response.text[:500]}",
            "provider": "gemini",
            "model": model,
        }
    except Exception as e:
        return {"error": f"Gemini failed: {e}", "provider": "gemini", "model": model}


async def mistral_codestral(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "codestral-latest",
) -> dict:
    """Mistral Codestral — specialized code model."""
    return await _call_openai_compatible(
        base_url="https://api.mistral.ai/v1",
        api_key=os.getenv("MISTRAL_API_KEY", ""),
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        provider="mistral",
        system_prompt="You are Codestral, a code-specialized AI. Write clean, efficient code.",
    )


async def ollama_local(
    prompt: str,
    max_tokens: int = 1500,
    model: Optional[str] = None,
) -> dict:
    """Ollama — local LLM inference (Qwen, Llama, etc.)."""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.getenv("OLLAMA_MODEL", "qwen3:8b")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "provider": "ollama",
                "model": model,
                "response": data.get("response", ""),
                "done": data.get("done", False),
                "eval_count": data.get("eval_count", 0),
                "eval_duration_ms": round(data.get("eval_duration", 0) / 1e6, 1),
            }
    except Exception as e:
        return {"error": f"Ollama failed: {e}", "provider": "ollama", "model": model}


async def jules_agent(
    task: str,
    repo_url: Optional[str] = None,
    max_wait: int = 120,
) -> dict:
    """Google Jules — autonomous coding agent (plan + execute)."""
    api_key = os.getenv("JULES_API_KEY", "")
    if not api_key:
        return {"error": "JULES_API_KEY not configured", "provider": "jules"}

    try:
        async with httpx.AsyncClient(timeout=float(max_wait)) as client:
            body: dict[str, Any] = {"task": task}
            if repo_url:
                body["repo_url"] = repo_url

            resp = await client.post(
                "https://jules.google.com/api/v1/tasks",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "provider": "jules",
                "task_id": data.get("task_id", ""),
                "status": data.get("status", "submitted"),
                "response": data.get("result", "Task submitted"),
                "plan": data.get("plan", []),
            }
    except Exception as e:
        return {"error": f"Jules failed: {e}", "provider": "jules"}


def register_llm_tools(mcp: Any, cat_registry: CategoryRegistry) -> None:
    """Register all CAT-1 LLM worker tools with MCP server."""
    from pydantic import BaseModel, Field

    # Rejestracja w CategoryRegistry
    tools = [
        ("grok_analyze", "xAI Grok analysis — long context, reasoning"),
        ("groq_fast", "Groq ultra-fast inference (Llama/Qwen)"),
        ("claude_complete", "Anthropic Claude completion"),
        ("gpt_complete", "OpenAI GPT completion"),
        ("deepseek_code", "DeepSeek code generation/verification"),
        ("gemini_generate", "Google Gemini multimodal generation"),
        ("mistral_codestral", "Mistral Codestral code model"),
        ("ollama_local", "Ollama local LLM inference"),
        ("jules_agent", "Google Jules autonomous coding agent"),
    ]
    for name, desc in tools:
        cat_registry.register_tool(name, Category.LLM_WORKERS, risk_level="medium", description=desc)

    # --- Tool schemas & registration ---

    class GrokInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=8000)
        max_tokens: int = Field(2000, ge=10, le=8000)
        model: str = Field("grok-3-latest")

    @mcp.tool(name="grok_analyze", annotations={"title": "Grok Analyze", "openWorldHint": True})
    async def _grok(params: GrokInput) -> dict:
        """xAI Grok: analysis, long context reasoning."""
        return await grok_analyze(params.prompt, params.max_tokens, params.model)

    class GroqInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=8000)
        max_tokens: int = Field(1500, ge=10, le=8000)
        model: str = Field("llama-3.3-70b-versatile")

    @mcp.tool(name="groq_fast", annotations={"title": "Groq Fast", "openWorldHint": True})
    async def _groq(params: GroqInput) -> dict:
        """Groq: ultra-fast inference."""
        return await groq_fast(params.prompt, params.max_tokens, params.model)

    class ClaudeInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=16000)
        max_tokens: int = Field(2000, ge=10, le=8000)
        model: str = Field("claude-sonnet-4-20250514")
        system_prompt: Optional[str] = Field(None)

    @mcp.tool(name="claude_complete", annotations={"title": "Claude Complete", "openWorldHint": True})
    async def _claude(params: ClaudeInput) -> dict:
        """Anthropic Claude completion."""
        return await claude_complete(params.prompt, params.max_tokens, params.model, params.system_prompt)

    class GPTInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=16000)
        max_tokens: int = Field(2000, ge=10, le=8000)
        model: str = Field("gpt-4o-mini")
        system_prompt: Optional[str] = Field(None)

    @mcp.tool(name="gpt_complete", annotations={"title": "GPT Complete", "openWorldHint": True})
    async def _gpt(params: GPTInput) -> dict:
        """OpenAI GPT completion."""
        return await gpt_complete(params.prompt, params.max_tokens, params.model, params.system_prompt)

    class DeepSeekInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=16000)
        max_tokens: int = Field(2000, ge=10, le=8000)
        model: str = Field("deepseek-chat")

    @mcp.tool(name="deepseek_code", annotations={"title": "DeepSeek Code", "openWorldHint": True})
    async def _deepseek(params: DeepSeekInput) -> dict:
        """DeepSeek code generation and verification."""
        return await deepseek_code(params.prompt, params.max_tokens, params.model)

    class GeminiInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=16000)
        max_tokens: int = Field(2000, ge=10, le=8000)
        model: str = Field("gemini-2.0-flash")

    @mcp.tool(name="gemini_generate", annotations={"title": "Gemini Generate", "openWorldHint": True})
    async def _gemini(params: GeminiInput) -> dict:
        """Google Gemini multimodal generation."""
        return await gemini_generate(params.prompt, params.max_tokens, params.model)

    class MistralInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=16000)
        max_tokens: int = Field(2000, ge=10, le=8000)
        model: str = Field("codestral-latest")

    @mcp.tool(name="mistral_codestral", annotations={"title": "Mistral Codestral", "openWorldHint": True})
    async def _mistral(params: MistralInput) -> dict:
        """Mistral Codestral code model."""
        return await mistral_codestral(params.prompt, params.max_tokens, params.model)

    class OllamaInput(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=16000)
        max_tokens: int = Field(1500, ge=10, le=4000)
        model: Optional[str] = Field(None)

    @mcp.tool(name="ollama_local", annotations={"title": "Ollama Local", "openWorldHint": False})
    async def _ollama(params: OllamaInput) -> dict:
        """Ollama local LLM inference."""
        return await ollama_local(params.prompt, params.max_tokens, params.model)

    class JulesInput(BaseModel):
        task: str = Field(..., min_length=1, max_length=4000)
        repo_url: Optional[str] = Field(None)
        max_wait: int = Field(120, ge=10, le=600)

    @mcp.tool(name="jules_agent", annotations={"title": "Jules Agent", "openWorldHint": True})
    async def _jules(params: JulesInput) -> dict:
        """Google Jules autonomous coding agent."""
        return await jules_agent(params.task, params.repo_url, params.max_wait)
