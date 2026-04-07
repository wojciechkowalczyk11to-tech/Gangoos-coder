"""
CAT-4: Research — firecrawl_scrape, web_fetch, perplexity_ask, manus_agent_task.

Web research tools for information gathering and scraping.
"""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from categories import Category, CategoryRegistry


def _validate_url(url: str) -> str:
    """Validate and normalize URL."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs supported")
    return url


async def firecrawl_scrape(
    url: str,
    formats: Optional[list[str]] = None,
    timeout: int = 30,
) -> dict:
    """
    Firecrawl — intelligent web scraping with content extraction.
    Returns clean markdown/text from web pages.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_key:
        return {"error": "FIRECRAWL_API_KEY not configured", "provider": "firecrawl"}

    try:
        normalized = _validate_url(url)
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "url": normalized,
                    "formats": formats or ["markdown", "links"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("data", {})
            return {
                "provider": "firecrawl",
                "url": normalized,
                "markdown": result.get("markdown", "")[:8000],
                "links": result.get("links", [])[:50],
                "metadata": result.get("metadata", {}),
                "success": data.get("success", False),
            }
    except ValueError as e:
        return {"error": str(e), "provider": "firecrawl"}
    except httpx.HTTPStatusError as e:
        return {
            "error": f"Firecrawl HTTP {e.response.status_code}: {e.response.text[:500]}",
            "provider": "firecrawl",
        }
    except Exception as e:
        return {"error": f"Firecrawl failed: {e}", "provider": "firecrawl"}


async def web_fetch(
    url: str,
    timeout: int = 15,
    max_length: int = 5000,
) -> dict:
    """
    Simple HTTP fetch — raw or text content from URLs.
    No JS rendering, lightweight.
    """
    try:
        normalized = _validate_url(url)
        async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True) as client:
            resp = await client.get(normalized)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            text = resp.text[:max_length]
            return {
                "provider": "web_fetch",
                "url": str(resp.url),
                "status_code": resp.status_code,
                "content_type": content_type,
                "content": text,
                "truncated": len(resp.text) > max_length,
                "headers": dict(list(resp.headers.items())[:10]),
            }
    except ValueError as e:
        return {"error": str(e), "provider": "web_fetch"}
    except httpx.TimeoutException:
        return {"error": f"Timeout after {timeout}s", "url": url, "provider": "web_fetch"}
    except Exception as e:
        return {"error": f"Fetch failed: {e}", "url": url, "provider": "web_fetch"}


async def perplexity_ask(
    question: str,
    max_tokens: int = 2000,
    model: str = "sonar",
) -> dict:
    """
    Perplexity AI — research-grade web search + synthesis.
    Returns answer with citations.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"error": "PERPLEXITY_API_KEY not configured", "provider": "perplexity"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": question}],
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return {
                "provider": "perplexity",
                "model": model,
                "answer": choice["message"]["content"],
                "citations": data.get("citations", []),
                "usage": data.get("usage", {}),
            }
    except httpx.HTTPStatusError as e:
        return {
            "error": f"Perplexity HTTP {e.response.status_code}: {e.response.text[:500]}",
            "provider": "perplexity",
        }
    except Exception as e:
        return {"error": f"Perplexity failed: {e}", "provider": "perplexity"}


async def manus_agent_task(
    task: str,
    context: Optional[str] = None,
    max_wait: int = 120,
) -> dict:
    """
    Manus AI — autonomous agent for complex multi-step tasks.
    Uses one of the available API keys (round-robin).
    """
    # Próbuj klucze po kolei
    keys = []
    for i in range(1, 7):
        key = os.getenv(f"MANUS_API_KEY_{i}", "")
        if key:
            keys.append(key)
    main_key = os.getenv("MANUS_API_KEY", "")
    if main_key:
        keys.insert(0, main_key)

    if not keys:
        return {"error": "No MANUS_API_KEY configured", "provider": "manus"}

    body: dict[str, Any] = {"task": task}
    if context:
        body["context"] = context

    for idx, api_key in enumerate(keys):
        try:
            async with httpx.AsyncClient(timeout=float(max_wait)) as client:
                resp = await client.post(
                    "https://api.manus.ai/v1/tasks",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "provider": "manus",
                    "task_id": data.get("task_id", ""),
                    "status": data.get("status", "submitted"),
                    "result": data.get("result", ""),
                    "key_index": idx,
                }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and idx < len(keys) - 1:
                continue  # try next key
            return {
                "error": f"Manus HTTP {e.response.status_code}: {e.response.text[:500]}",
                "provider": "manus",
                "key_index": idx,
            }
        except Exception as e:
            if idx < len(keys) - 1:
                continue
            return {"error": f"Manus failed: {e}", "provider": "manus"}

    return {"error": "All Manus API keys exhausted", "provider": "manus"}


def register_research_tools(mcp: Any, cat_registry: CategoryRegistry) -> None:
    """Register CAT-4 research tools."""
    from pydantic import BaseModel, Field

    cat_registry.register_tool(
        "firecrawl_scrape", Category.RESEARCH, risk_level="medium",
        description="Firecrawl intelligent web scraping",
    )
    cat_registry.register_tool(
        "web_fetch", Category.RESEARCH, risk_level="low",
        description="Simple HTTP fetch (no JS rendering)",
    )
    cat_registry.register_tool(
        "perplexity_ask", Category.RESEARCH, risk_level="medium",
        description="Perplexity AI research search with citations",
    )
    cat_registry.register_tool(
        "manus_agent_task", Category.RESEARCH, risk_level="medium",
        description="Manus AI autonomous agent for complex tasks",
    )

    class FirecrawlInput(BaseModel):
        url: str = Field(..., min_length=8, max_length=2000)
        formats: Optional[list[str]] = Field(None)
        timeout: int = Field(30, ge=5, le=120)

    @mcp.tool(name="firecrawl_scrape", annotations={"title": "Firecrawl Scrape", "openWorldHint": True})
    async def _firecrawl(params: FirecrawlInput) -> dict:
        """Firecrawl: intelligent web scraping with clean extraction."""
        return await firecrawl_scrape(params.url, params.formats, params.timeout)

    class WebFetchInput(BaseModel):
        url: str = Field(..., min_length=8, max_length=2000)
        timeout: int = Field(15, ge=1, le=60)
        max_length: int = Field(5000, ge=100, le=50000)

    @mcp.tool(name="web_fetch", annotations={"title": "Web Fetch", "openWorldHint": True, "readOnlyHint": True})
    async def _web_fetch(params: WebFetchInput) -> dict:
        """Simple HTTP fetch — raw content from URLs."""
        return await web_fetch(params.url, params.timeout, params.max_length)

    class PerplexityInput(BaseModel):
        question: str = Field(..., min_length=3, max_length=4000)
        max_tokens: int = Field(2000, ge=100, le=4000)
        model: str = Field("sonar")

    @mcp.tool(name="perplexity_ask", annotations={"title": "Perplexity Ask", "openWorldHint": True})
    async def _perplexity(params: PerplexityInput) -> dict:
        """Perplexity AI: research search with citations."""
        return await perplexity_ask(params.question, params.max_tokens, params.model)

    class ManusInput(BaseModel):
        task: str = Field(..., min_length=5, max_length=4000)
        context: Optional[str] = Field(None)
        max_wait: int = Field(120, ge=10, le=600)

    @mcp.tool(name="manus_agent_task", annotations={"title": "Manus Agent", "openWorldHint": True})
    async def _manus(params: ManusInput) -> dict:
        """Manus AI: autonomous agent for complex multi-step tasks."""
        return await manus_agent_task(params.task, params.context, params.max_wait)
