"""
Research Domain - Web research and document fetching tools.
Risk level: MEDIUM (open web access)
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from registry import ToolMeta, ToolRegistry


def normalize_https_url(url: str) -> str:
    """Validate and normalize URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported")
    return url.strip()


async def fetch_preview(url: str, timeout: int = 10) -> dict:
    """Fetch a URL preview."""
    import httpx

    normalized = normalize_https_url(url)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(normalized)
            text = response.text[:1200]
            return {
                "url": str(response.url),
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "preview": text,
            }
    except httpx.TimeoutException:
        return {
            "error": "Request timeout",
            "url": url,
            "status_code": 408,
        }
    except httpx.RequestError as e:
        return {
            "error": str(e),
            "url": url,
            "status_code": 500,
        }


async def register(mcp: Any, registry: ToolRegistry) -> None:
    """Register research domain tools."""
    from pydantic import BaseModel, ConfigDict, Field

    registry.register(
        ToolMeta(
            name="web_fetch_preview",
            domain="research",
            risk_level="medium",
            description="Fetch a remote URL and return a short preview.",
            tags=("research", "web", "fetch"),
        )
    )

    class WebFetchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., min_length=8, max_length=2000)
        timeout: int = Field(10, ge=1, le=30)

    @mcp.tool(
        name="web_fetch_preview",
        annotations={"title": "Fetch URL Preview", "readOnlyHint": True, "openWorldHint": True},
    )
    async def web_fetch_preview(params: WebFetchInput, ctx: Any) -> dict:
        """Fetch URL preview."""
        return await fetch_preview(params.url, params.timeout)
