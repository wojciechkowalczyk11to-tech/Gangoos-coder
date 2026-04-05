"""
NEXUS MCP — Knowledge Engine Module
Tools for managing and querying structured knowledge from tools.jsonl.
Pure Python — no external dependencies beyond the standard library.
"""

import json
import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.knowledge")

# Default knowledge base path — can be overridden via env
DEFAULT_KB_PATH = os.getenv(
    "NEXUS_KB_PATH",
    "/workspace/knowledge-base-output/tools.jsonl",
)


def _load_knowledge_base(path: str) -> list[dict]:
    """Load tools.jsonl from disk. Returns list of tool records."""
    if not os.path.exists(path):
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log.warning(f"Failed to load knowledge base from {path}: {e}")
    return records


def _fuzzy_score(record: dict, query: str) -> float:
    """
    Compute a simple relevance score for a knowledge record against a query.
    Checks: tool_name, category, tags, description, ai_routing_hint.
    Returns a float score (higher = more relevant).
    """
    query_lower = query.lower()
    query_tokens = set(query_lower.split())
    score = 0.0

    # Exact substring matches (weighted by field importance)
    fields = {
        "tool_name": 3.0,
        "category": 2.0,
        "tags": 2.0,
        "description": 1.5,
        "ai_routing_hint": 2.5,
        "summary": 1.0,
    }

    for field, weight in fields.items():
        value = record.get(field, "")
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        elif not isinstance(value, str):
            value = str(value)
        value_lower = value.lower()

        # Substring match
        if query_lower in value_lower:
            score += weight * 2.0

        # Token-level overlap
        value_tokens = set(value_lower.split())
        overlap = query_tokens & value_tokens
        if overlap:
            score += weight * len(overlap) * 0.5

    return score


def register(mcp: FastMCP):
    """Register knowledge engine tools."""

    # ── Knowledge Search ─────────────────────────────────

    class KnowledgeSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(
            ...,
            description="Search query — tool name, category, tags, or description keywords",
            min_length=1,
            max_length=2000,
        )
        top_n: int = Field(
            10,
            ge=1,
            le=50,
            description="Number of top results to return",
        )
        kb_path: Optional[str] = Field(
            None,
            description=f"Path to tools.jsonl file. Defaults to {DEFAULT_KB_PATH}",
        )

    @mcp.tool(
        name="knowledge_search",
        annotations={
            "title": "Search Knowledge Base",
            "readOnlyHint": True,
        },
    )
    async def knowledge_search(params: KnowledgeSearchInput, ctx: Context) -> str:
        """Search the NEXUS knowledge base (tools.jsonl) by tool name, category,
        tags, or description. Uses fuzzy matching — no external dependencies.
        Returns top N matches ranked by relevance score.
        """
        path = params.kb_path or DEFAULT_KB_PATH
        records = _load_knowledge_base(path)

        if not records:
            return (
                f"Knowledge base not found or empty at: `{path}`\n\n"
                "To populate it, run the knowledge base generation script or "
                "set NEXUS_KB_PATH to the correct path."
            )

        # Score all records
        scored = []
        for record in records:
            score = _fuzzy_score(record, params.query)
            if score > 0:
                scored.append((score, record))

        if not scored:
            return f"No results found for query: `{params.query}`\n\nKnowledge base has {len(records)} entries."

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: params.top_n]

        output = f"# Knowledge Search: `{params.query}`\n\n"
        output += f"Found {len(scored)} matches, showing top {len(top)}:\n\n"

        for rank, (score, record) in enumerate(top, 1):
            tool_name = record.get("tool_name", record.get("name", "unknown"))
            category = record.get("category", "")
            description = record.get("description", record.get("summary", ""))
            tags = record.get("tags", [])
            routing_hint = record.get("ai_routing_hint", "")

            if isinstance(tags, list):
                tags_str = ", ".join(str(t) for t in tags)
            else:
                tags_str = str(tags)

            output += f"### {rank}. `{tool_name}` (score: {score:.1f})\n"
            if category:
                output += f"**Category**: {category}\n"
            if tags_str:
                output += f"**Tags**: {tags_str}\n"
            if description:
                output += f"**Description**: {description[:300]}\n"
            if routing_hint:
                output += f"**Routing hint**: {routing_hint[:200]}\n"
            output += "\n"

        return output

    # ── Knowledge Recommend ──────────────────────────────

    class KnowledgeRecommendInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        task: str = Field(
            ...,
            description="Describe what you want to accomplish — the system will recommend the best tools",
            min_length=5,
            max_length=5000,
        )
        top_n: int = Field(
            5,
            ge=1,
            le=20,
            description="Number of tool recommendations to return",
        )
        use_ai: bool = Field(
            False,
            description="Use Grok for semantic matching (slower but more accurate for complex tasks)",
        )
        kb_path: Optional[str] = Field(
            None,
            description=f"Path to tools.jsonl. Defaults to {DEFAULT_KB_PATH}",
        )

    @mcp.tool(
        name="knowledge_recommend",
        annotations={
            "title": "Recommend Tools for Task",
            "readOnlyHint": True,
            "openWorldHint": False,
        },
    )
    async def knowledge_recommend(params: KnowledgeRecommendInput, ctx: Context) -> str:
        """Given a task description, recommend the best NEXUS tools to use.
        Matches against tool descriptions, categories, and ai_routing_hint fields.
        Optionally delegates to Grok for semantic matching (use_ai=true).
        """
        path = params.kb_path or DEFAULT_KB_PATH
        records = _load_knowledge_base(path)

        if not records:
            return (
                f"Knowledge base not found or empty at: `{path}`\n\n"
                "Cannot provide recommendations without a populated knowledge base."
            )

        # Score all records against the task
        scored = []
        for record in records:
            score = _fuzzy_score(record, params.task)
            scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: params.top_n]

        output = f"# Tool Recommendations for Task\n\n**Task**: {params.task[:200]}\n\n"

        if params.use_ai:
            # Delegate to Grok for semantic re-ranking
            try:
                from clients import get_clients
                import os as _os

                client = get_clients()["general"]
                api_key = _os.getenv("XAI_API_KEY", "")
                if not api_key:
                    output += "_Note: XAI_API_KEY not set — using keyword matching only._\n\n"
                else:
                    # Build context from top candidates
                    candidates_text = "\n".join(
                        f"- {r.get('tool_name', 'unknown')}: {r.get('description', '')[:100]}"
                        for _, r in scored[:20]
                    )
                    prompt = (
                        f"Task: {params.task}\n\n"
                        f"Available tools:\n{candidates_text}\n\n"
                        f"Which {params.top_n} tools are most relevant? "
                        f"Rank them and explain briefly why each is useful."
                    )
                    resp = await client.post(
                        "https://api.x.ai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "grok-4-1-fast-reasoning",
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 1024,
                        },
                        timeout=60.0,
                    )
                    resp.raise_for_status()
                    ai_ranking = resp.json()["choices"][0]["message"]["content"]
                    output += f"## AI-Powered Recommendations (Grok)\n\n{ai_ranking}\n\n---\n\n"
            except Exception as e:
                output += f"_AI ranking failed ({e}) — falling back to keyword matching._\n\n"

        output += f"## Keyword-Matched Recommendations (top {len(top)})\n\n"

        for rank, (score, record) in enumerate(top, 1):
            tool_name = record.get("tool_name", record.get("name", "unknown"))
            category = record.get("category", "")
            description = record.get("description", record.get("summary", ""))
            routing_hint = record.get("ai_routing_hint", "")

            output += f"### {rank}. `{tool_name}`"
            if score > 0:
                output += f" (relevance: {score:.1f})"
            output += "\n"
            if category:
                output += f"**Category**: {category}\n"
            if description:
                output += f"{description[:250]}\n"
            if routing_hint:
                output += f"_When to use_: {routing_hint[:200]}\n"
            output += "\n"

        return output

    # ── Knowledge Stats ──────────────────────────────────

    class KnowledgeStatsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        kb_path: Optional[str] = Field(
            None,
            description=f"Path to tools.jsonl. Defaults to {DEFAULT_KB_PATH}",
        )

    @mcp.tool(
        name="knowledge_stats",
        annotations={
            "title": "Knowledge Base Statistics",
            "readOnlyHint": True,
        },
    )
    async def knowledge_stats(params: KnowledgeStatsInput, ctx: Context) -> str:
        """Return statistics about the NEXUS knowledge base:
        total tools, category breakdown, average score, top 10 by score.
        """
        path = params.kb_path or DEFAULT_KB_PATH
        records = _load_knowledge_base(path)

        if not records:
            return (
                f"Knowledge base not found or empty at: `{path}`\n\n"
                "Run the knowledge base generation script to populate it."
            )

        total = len(records)

        # Category breakdown
        categories: dict[str, int] = {}
        scores = []
        for record in records:
            cat = record.get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1

            score = record.get("score", record.get("quality_score", None))
            if score is not None:
                try:
                    scores.append(float(score))
                except (ValueError, TypeError):
                    pass

        avg_score = sum(scores) / len(scores) if scores else None

        # Top 10 by score
        scored_records = []
        for record in records:
            score = record.get("score", record.get("quality_score", 0))
            try:
                scored_records.append((float(score), record))
            except (ValueError, TypeError):
                scored_records.append((0.0, record))

        scored_records.sort(key=lambda x: x[0], reverse=True)
        top10 = scored_records[:10]

        output = f"# Knowledge Base Statistics\n\n"
        output += f"**Path**: `{path}`\n"
        output += f"**Total tools**: {total}\n"
        if avg_score is not None:
            output += f"**Average score**: {avg_score:.2f}\n"
        output += "\n"

        output += "## Categories\n\n"
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        for cat, count in sorted_cats:
            pct = count / total * 100
            output += f"- **{cat}**: {count} tools ({pct:.1f}%)\n"
        output += "\n"

        if top10:
            output += "## Top 10 Tools by Score\n\n"
            for rank, (score, record) in enumerate(top10, 1):
                tool_name = record.get("tool_name", record.get("name", "unknown"))
                description = record.get("description", record.get("summary", ""))[:100]
                output += f"{rank}. **`{tool_name}`** (score: {score:.1f}) — {description}\n"

        return output
