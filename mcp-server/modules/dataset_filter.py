"""
E4: Continue-metric dataset quality filter.
Detects and removes incomplete CodeAct traces before training.
Heuristics: truncated output, missing tool_result, no final answer.
Can be run standalone: python -m modules.dataset_filter <input.jsonl> <output.jsonl>
"""
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.dataset-filter")


# ── Quality heuristics ───────────────────────────────────────────────────────

def _is_complete_trace(messages: list[dict]) -> tuple[bool, str]:
    """Return (is_complete, reason_if_not)."""
    if not messages:
        return False, "empty trace"

    # Must have at least one assistant message
    roles = [m.get("role") for m in messages]
    if "assistant" not in roles:
        return False, "no assistant message"

    # Last message must be from assistant (not truncated mid-turn)
    last = messages[-1]
    if last.get("role") != "assistant":
        return False, f"trace ends with role={last.get('role')} (expected assistant)"

    # Last assistant message must have non-empty content
    last_content = last.get("content", "")
    if isinstance(last_content, list):
        # Content blocks format
        texts = [b.get("text", "") for b in last_content if isinstance(b, dict)]
        last_content = " ".join(texts)
    if not str(last_content).strip():
        return False, "last assistant message is empty"

    # If there are tool_use blocks, there must be corresponding tool_result blocks
    tool_use_ids = set()
    tool_result_ids = set()
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id", ""))
                    elif block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id", ""))

    missing = tool_use_ids - tool_result_ids
    if missing:
        return False, f"missing tool_result for tool_use ids: {missing}"

    # Check for truncation signals in last content
    truncation_signals = ["...", "[truncated]", "[cut off]", "to be continued"]
    content_lower = str(last_content).lower()
    for sig in truncation_signals:
        if content_lower.endswith(sig):
            return False, f"output appears truncated (ends with '{sig}')"

    return True, ""


def filter_dataset(input_path: Path, output_path: Path) -> dict:
    """Filter a JSONL dataset file. Returns quality metrics."""
    total = 0
    passed = 0
    filtered = 0
    reasons: dict[str, int] = {}

    with open(input_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                filtered += 1
                reasons["invalid_json"] = reasons.get("invalid_json", 0) + 1
                continue

            messages = record.get("messages", [])
            ok, reason = _is_complete_trace(messages)

            if ok:
                fout.write(json.dumps(record) + "\n")
                passed += 1
            else:
                filtered += 1
                reasons[reason] = reasons.get(reason, 0) + 1

    return {
        "total": total,
        "passed": passed,
        "filtered": filtered,
        "pass_rate": round(passed / total, 4) if total else 0,
        "filter_reasons": reasons,
    }


# ── MCP tool ─────────────────────────────────────────────────────────────────

def register(mcp: FastMCP):

    class FilterDatasetInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        input_path: str = Field(..., description="Path to input JSONL dataset")
        output_path: str = Field(..., description="Path to write filtered JSONL")

    @mcp.tool(
        name="filter_dataset",
        annotations={"title": "Filter Dataset Quality", "destructiveHint": False},
    )
    async def filter_dataset_tool(params: FilterDatasetInput, ctx: Context) -> str:
        """Remove incomplete CodeAct traces from a JSONL training dataset.
        Heuristics: no final answer, missing tool_result, truncated output, empty traces.
        Returns quality metrics including filtered count.
        """
        inp = Path(params.input_path)
        out = Path(params.output_path)
        if not inp.exists():
            return f"ERROR: input file not found: {inp}"
        try:
            metrics = filter_dataset(inp, out)
        except Exception as e:
            return f"ERROR filtering dataset: {e}"

        lines = [
            f"Dataset filter complete:",
            f"  Total:    {metrics['total']}",
            f"  Passed:   {metrics['passed']} ({metrics['pass_rate']*100:.1f}%)",
            f"  Filtered: {metrics['filtered']}",
        ]
        if metrics["filter_reasons"]:
            lines.append("  Reasons:")
            for reason, count in sorted(metrics["filter_reasons"].items(), key=lambda x: -x[1]):
                lines.append(f"    {count:4d}  {reason}")
        return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python -m modules.dataset_filter <input.jsonl> <output.jsonl>")
        sys.exit(1)
    metrics = filter_dataset(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(metrics, indent=2))
