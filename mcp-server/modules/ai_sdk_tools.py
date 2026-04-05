"""
NEXUS MCP — Native AI SDK Tools
OpenAI SDK (Responses API, structured output, file_search)
xAI Responses API (web_search, x_search, collections)
These complement ai_proxy.py with SDK-native features.
"""

import os
import logging
import asyncio
import json
from typing import Optional

import httpx
from openai import AsyncOpenAI
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.ai-sdk")

XAI_BASE = "https://api.x.ai/v1"


def _openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


def _xai_headers() -> dict:
    key = os.getenv("XAI_API_KEY", "")
    if not key:
        raise ValueError("XAI_API_KEY not set")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def register(mcp: FastMCP):

    # ─── 1. OpenAI SDK — chat completions (native SDK) ───────────────────────
    class OpenAISDKInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        prompt: str = Field(..., description="User prompt", min_length=1, max_length=100000)
        system: Optional[str] = Field(None, description="System message")
        model: str = Field("gpt-4o", description="OpenAI model (gpt-4o, gpt-4.1, gpt-4.1-mini, o3-mini)")
        max_tokens: int = Field(4096, ge=1, le=128000)
        temperature: float = Field(0.7, ge=0.0, le=2.0)

    @mcp.tool(name="ai_query_openai_sdk", annotations={"title": "Query OpenAI via native SDK", "readOnlyHint": True, "openWorldHint": True})
    async def ai_query_openai_sdk(params: OpenAISDKInput, ctx: Context) -> str:
        """Query OpenAI models using the official AsyncOpenAI SDK.
        Supports: gpt-4o, gpt-4.1, gpt-4.1-mini, gpt-4.1-nano, o3-mini.
        Use for: structured output, JSON mode, fine-tuned models.
        """
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return "Error: OPENAI_API_KEY not set"
        client = AsyncOpenAI(api_key=key)
        messages = []
        if params.system:
            messages.append({"role": "system", "content": params.system})
        messages.append({"role": "user", "content": params.prompt})
        try:
            resp = await client.chat.completions.create(
                model=params.model,
                messages=messages,
                max_tokens=params.max_tokens,
                temperature=params.temperature,
            )
            result = resp.choices[0].message.content or ""
            log.info(f"openai_sdk: {params.model} — {len(result)} chars")
            return f"**[OpenAI SDK / {params.model}]**\n\n{result}"
        except Exception as e:
            log.error(f"openai_sdk error: {e}")
            return f"Error (OpenAI SDK / {params.model}): {e}"

    # ─── 2. OpenAI Responses API — with web_search tool ─────────────────────
    class OpenAIResponsesInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        prompt: str = Field(..., description="Query to send with web search enabled", min_length=1)
        model: str = Field("gpt-4o", description="OpenAI model that supports Responses API")
        max_tokens: int = Field(4096, ge=1, le=32000)

    @mcp.tool(name="ai_query_openai_responses", annotations={"title": "OpenAI Responses API (with web search)", "readOnlyHint": True, "openWorldHint": True})
    async def ai_query_openai_responses(params: OpenAIResponsesInput, ctx: Context) -> str:
        """Use OpenAI Responses API with built-in web_search tool.
        Returns grounded answer with citations.
        """
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return "Error: OPENAI_API_KEY not set"
        client = AsyncOpenAI(api_key=key)
        try:
            resp = await client.responses.create(
                model=params.model,
                input=params.prompt,
                tools=[{"type": "web_search_preview"}],
                max_output_tokens=params.max_tokens,
            )
            # Extract text from output blocks
            texts = []
            for item in (resp.output or []):
                if hasattr(item, "content"):
                    for block in (item.content or []):
                        if hasattr(block, "text") and block.text:
                            texts.append(block.text)
                elif hasattr(item, "text") and item.text:
                    texts.append(item.text)
            result = "\n\n".join(texts) if texts else str(resp)
            return f"**[OpenAI Responses / {params.model}]**\n\n{result}"
        except Exception as e:
            log.error(f"openai_responses error: {e}")
            return f"Error (OpenAI Responses): {e}"

    # ─── 3. xAI Responses API — web_search + x_search ───────────────────────
    class XAIResponsesInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Search query for Grok with web + X search", min_length=1, max_length=10000)
        model: str = Field("grok-4-1-fast-reasoning", description="Grok model to use")
        include_x_search: bool = Field(True, description="Also search X/Twitter posts")
        collection_id: Optional[str] = Field(None, description="Optional xAI collection ID to search alongside web")

    @mcp.tool(name="xai_responses", annotations={"title": "Grok Responses API (web+X+collection)", "readOnlyHint": True, "openWorldHint": True})
    async def xai_responses(params: XAIResponsesInput, ctx: Context) -> str:
        """Use xAI Responses API: web_search + x_search + optional collection search.
        Ideal for: real-time research, news, technical lookups, X/Twitter trends.
        Combined with collection_id for knowledge-grounded web search.
        """
        try:
            headers = _xai_headers()
        except ValueError as e:
            return f"Error: {e}"

        tools: list = [{"type": "web_search"}]
        if params.include_x_search:
            tools.append({"type": "x_search"})
        if params.collection_id:
            tools.append({"type": "file_search", "vector_store_ids": [params.collection_id], "max_num_results": 5})

        payload = {
            "model": params.model,
            "input": [{"role": "user", "content": params.query}],
            "tools": tools,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{XAI_BASE}/responses", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            # Parse output blocks
            texts = []
            for item in data.get("output", []):
                for block in item.get("content", []):
                    if block.get("type") == "output_text" and block.get("text"):
                        texts.append(block["text"])
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        if isinstance(c, dict) and c.get("text"):
                            texts.append(c["text"])

            result = "\n\n".join(texts) if texts else json.dumps(data, indent=2)[:2000]
            tag = "web+X" + ("+collection" if params.collection_id else "")
            return f"**[Grok Responses / {params.model} / {tag}]**\n\n{result}"
        except Exception as e:
            log.error(f"xai_responses error: {e}")
            return f"Error (xAI Responses): {e}"

    # ─── 4. OpenAI SDK — structured JSON output ──────────────────────────────
    class OpenAIStructuredInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        prompt: str = Field(..., description="Prompt requesting structured data", min_length=1)
        json_schema_desc: str = Field(..., description="Describe the JSON structure you want (e.g. 'list of objects with name, score, reason')")
        model: str = Field("gpt-4.1-mini", description="Model (gpt-4.1-mini recommended for cost)")
        max_tokens: int = Field(2048, ge=1, le=32000)

    @mcp.tool(name="ai_structured_output", annotations={"title": "OpenAI Structured JSON Output", "readOnlyHint": True})
    async def ai_structured_output(params: OpenAIStructuredInput, ctx: Context) -> str:
        """Get structured JSON output from OpenAI. Forces JSON mode.
        Use for: data extraction, classification, scoring, report generation.
        Cost-optimized: uses gpt-4.1-mini by default.
        """
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return "Error: OPENAI_API_KEY not set"
        client = AsyncOpenAI(api_key=key)
        system = f"You are a data extraction assistant. Return ONLY valid JSON matching this structure: {params.json_schema_desc}. No markdown, no explanation."
        try:
            resp = await client.chat.completions.create(
                model=params.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": params.prompt},
                ],
                max_tokens=params.max_tokens,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            result = resp.choices[0].message.content or "{}"
            log.info(f"structured_output: {params.model} — {len(result)} chars")
            return f"**[Structured Output / {params.model}]**\n\n```json\n{result}\n```"
        except Exception as e:
            log.error(f"structured_output error: {e}")
            return f"Error (structured output): {e}"
