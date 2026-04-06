"""
Tool Registry - Metadata registry for all MCP tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ToolMeta:
    """Metadata for a single tool."""
    name: str
    domain: str              # control, llm, research, knowledge, etc.
    risk_level: str         # low, medium, high, critical
    enabled_by_default: bool = True
    requires_confirmation: bool = False
    required_env: tuple[str, ...] = ()
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass
class ToolRegistry:
    """Registry of all available tools with metadata."""
    _tools: dict[str, ToolMeta] = field(default_factory=dict)

    def register(self, meta: ToolMeta) -> None:
        """Register a new tool."""
        if meta.name in self._tools:
            raise ValueError(f"Tool already registered: {meta.name}")
        self._tools[meta.name] = meta

    def get(self, name: str) -> ToolMeta | None:
        """Get tool metadata by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolMeta]:
        """List all registered tools, sorted by name."""
        return [self._tools[name] for name in sorted(self._tools)]

    def list_by_domain(self, domain: str) -> list[ToolMeta]:
        """List all tools in a specific domain."""
        return [meta for meta in self._tools.values() if meta.domain == domain]

    def as_serializable(self) -> list[dict]:
        """Convert to JSON-serializable format."""
        return [asdict(meta) for meta in self.list_tools()]
