"""
E1: VerifyPlanExecutionTool — pre-execution plan validation.
Before CodeAct runs code, route plan through lightweight model (Qwen-fast / Groq).
If validation fails → return error, don't execute.
"""
import logging
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.plan-verifier")

VERIFY_SYSTEM_PROMPT = """You are a plan validator. Analyze the given plan for:
1. Coherence — does each step logically follow from the previous?
2. Completeness — are inputs/outputs clearly defined?
3. Hallucination risk — does it reference things that likely don't exist?

Respond with JSON only:
{"valid": true/false, "issues": ["issue1", ...], "confidence": 0.0-1.0}
"""


async def _call_verifier(client: httpx.AsyncClient, cfg, plan: str) -> dict:
    """Call lightweight model for plan verification. Prefers Ollama, falls back to Groq."""
    messages = [{"role": "user", "content": f"Validate this plan:\n\n{plan}"}]

    # Try Ollama first (local, fast, free)
    if cfg.OLLAMA_HOST:
        try:
            resp = await client.post(
                f"{cfg.OLLAMA_HOST}/v1/chat/completions",
                json={
                    "model": cfg.OLLAMA_MODEL,
                    "messages": [{"role": "system", "content": VERIFY_SYSTEM_PROMPT}] + messages,
                    "temperature": 0.1,
                    "max_tokens": 256,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            import json as _json
            return _json.loads(content)
        except Exception as e:
            log.warning(f"Ollama verifier failed: {e}, trying Groq")

    # Fallback: Groq
    if cfg.GROQ_API_KEY:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {cfg.GROQ_API_KEY}"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "system", "content": VERIFY_SYSTEM_PROMPT}] + messages,
                "temperature": 0.1,
                "max_tokens": 256,
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        import json as _json
        return _json.loads(content)

    raise RuntimeError("No verifier model available (OLLAMA_HOST or GROQ_API_KEY required)")


def register(mcp: FastMCP):

    class VerifyPlanInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        plan: str = Field(..., description="Plan text to validate before execution", min_length=10)
        strict: bool = Field(False, description="If True, reject plans with confidence < 0.8")

    @mcp.tool(
        name="verify_plan",
        annotations={
            "title": "Verify Execution Plan",
            "readOnlyHint": True,
            "destructiveHint": False,
        },
    )
    async def verify_plan(params: VerifyPlanInput, ctx: Context) -> str:
        """Validate a plan with a lightweight model before execution.
        Returns validation result. If invalid, do NOT proceed with execution.

        Use before running any CodeAct or destructive tool sequence.
        """
        from clients import get_clients
        import config as cfg_module

        cfg = cfg_module.settings
        client = get_clients()["general"]

        if not params.plan.strip():
            return "ERROR: empty plan — nothing to validate"

        try:
            result = await _call_verifier(client, cfg, params.plan)
        except Exception as e:
            return f"ERROR: verifier unavailable — {e}. Proceed with caution."

        valid = result.get("valid", False)
        issues = result.get("issues", [])
        confidence = result.get("confidence", 0.0)

        if not valid:
            issues_str = "\n".join(f"  - {i}" for i in issues)
            return f"PLAN REJECTED (confidence={confidence:.2f})\nIssues:\n{issues_str}\n\nDo NOT execute this plan."

        if params.strict and confidence < 0.8:
            return f"PLAN REJECTED (strict mode, confidence={confidence:.2f} < 0.8)\nIssues: {issues}"

        issues_str = f"\nMinor issues: {issues}" if issues else ""
        return f"PLAN APPROVED (confidence={confidence:.2f}){issues_str}\nSafe to proceed with execution."
