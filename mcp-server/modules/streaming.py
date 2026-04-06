"""
E2: AsyncGenerator streaming for CodeAct execution.
Yields intermediate steps as events — partial results recoverable on cancellation.
"""
import asyncio
import logging
import time
from typing import AsyncIterator, Optional

import httpx
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.streaming")


async def stream_ollama(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 4096,
) -> AsyncIterator[str]:
    """Stream tokens from Ollama OpenAI-compatible endpoint."""
    async with client.stream(
        "POST",
        f"{host}/v1/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
        },
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            import json as _json
            try:
                chunk = _json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    yield token
            except (_json.JSONDecodeError, KeyError, IndexError):
                continue


def register(mcp: FastMCP):

    class StreamExecuteInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        prompt: str = Field(..., description="CodeAct prompt to stream", min_length=1)
        system: Optional[str] = Field(None, description="System prompt override")
        max_tokens: int = Field(4096, ge=1, le=32768)
        step_prefix: str = Field(
            "```", description="String that marks the start of an execution step in the stream"
        )

    @mcp.tool(
        name="stream_execute",
        annotations={
            "title": "Stream CodeAct Execution",
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": True,
        },
    )
    async def stream_execute(params: StreamExecuteInput, ctx: Context) -> str:
        """Execute a CodeAct prompt with streaming — returns aggregated result with step markers.

        Steps are separated by the step_prefix pattern.
        Partial results are preserved if execution is cancelled.
        Use stream_execute instead of ai_query when you need intermediate steps visible.
        """
        import config as cfg_module
        from clients import get_clients

        cfg = cfg_module.settings
        client = get_clients()["general"]

        system = params.system or (
            "You are Gangus, a CodeAct agent. Execute the task step by step. "
            "Mark each step with ``` before and after the code block."
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": params.prompt},
        ]

        steps: list[str] = []
        current_step: list[str] = []
        buffer: list[str] = []
        step_count = 0
        started = time.monotonic()

        try:
            async for token in stream_ollama(
                client, cfg.OLLAMA_HOST, cfg.OLLAMA_MODEL, messages, params.max_tokens
            ):
                buffer.append(token)
                current_step.append(token)

                # Detect step boundary
                joined = "".join(current_step)
                if params.step_prefix in joined and len(joined) > len(params.step_prefix) + 5:
                    parts = joined.split(params.step_prefix)
                    for part in parts[:-1]:
                        if part.strip():
                            step_count += 1
                            steps.append(f"**Step {step_count}:**\n{part.strip()}")
                    current_step = list(parts[-1])

        except asyncio.CancelledError:
            log.warning("stream_execute cancelled — returning partial result")
            if current_step:
                steps.append(f"**Step {step_count + 1} (partial):**\n{''.join(current_step)}")

        except Exception as e:
            log.error(f"stream_execute error: {e}")
            partial = "".join(buffer)
            return f"ERROR: {e}\n\nPartial output:\n{partial}"

        elapsed = time.monotonic() - started

        # Flush remaining
        if current_step:
            remaining = "".join(current_step).strip()
            if remaining:
                step_count += 1
                steps.append(f"**Step {step_count}:**\n{remaining}")

        result = "\n\n".join(steps) if steps else "".join(buffer)
        log.info(f"stream_execute: {step_count} steps, {len(buffer)} tokens, {elapsed:.1f}s")
        return f"{result}\n\n---\n*{step_count} steps · {elapsed:.1f}s*"
