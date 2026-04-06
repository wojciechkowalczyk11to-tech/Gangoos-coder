"""
Domain modules - Organized tool implementations by domain.
Domains: control, llm, research, knowledge
"""

from __future__ import annotations

from typing import Any

from registry import ToolRegistry


async def register_all(mcp: Any, registry: ToolRegistry) -> None:
    """Register all domain tools with MCP server."""
    from . import control, knowledge, llm, research

    # Order matters: knowledge first (low risk), then research, llm, control (high risk)
    await knowledge.register(mcp, registry)
    await research.register(mcp, registry)
    await llm.register(mcp, registry)
    await control.register(mcp, registry)
