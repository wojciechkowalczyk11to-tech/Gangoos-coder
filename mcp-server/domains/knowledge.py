"""
Knowledge Domain - Documentation and knowledge base search tools.
Risk level: LOW
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from registry import ToolMeta, ToolRegistry


ROOT = Path(__file__).resolve().parent.parent.parent
DOC_EXTENSIONS = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}


def _candidate_files() -> list[Path]:
    """Find all documentation files."""
    try:
        return [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and "__pycache__" not in path.parts
            and path.suffix.lower() in DOC_EXTENSIONS
        ]
    except (OSError, PermissionError):
        return []


def search_docs(query: str, limit: int = 5) -> list[dict]:
    """Search documentation by query."""
    query_lower = query.lower()
    results = []

    for path in _candidate_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            continue

        score = 0
        if query_lower in path.name.lower():
            score += 3
        score += text.lower().count(query_lower)

        if score <= 0:
            continue

        # Extract snippet around match
        snippet = ""
        idx = text.lower().find(query_lower)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(text), idx + 160)
            snippet = text[start:end].replace("\n", " ").strip()

        results.append({
            "path": str(path.relative_to(ROOT)),
            "score": score,
            "snippet": snippet[:240],
        })

    results.sort(key=lambda item: (-item["score"], item["path"]))
    return results[:limit]


async def register(mcp: Any, registry: ToolRegistry) -> None:
    """Register knowledge domain tools."""
    from pydantic import BaseModel, ConfigDict, Field

    registry.register(
        ToolMeta(
            name="docs_search",
            domain="knowledge",
            risk_level="low",
            description="Search local repository documentation and source files.",
            tags=("knowledge", "docs", "search"),
        )
    )

    class DocsSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., min_length=2, max_length=200)
        limit: int = Field(5, ge=1, le=20)

    @mcp.tool(
        name="docs_search",
        annotations={"title": "Search Local Docs", "readOnlyHint": True},
    )
    async def docs_search(params: DocsSearchInput, ctx: Any) -> dict:
        """Search documentation."""
        return {
            "query": params.query,
            "results": search_docs(params.query, params.limit),
        }
