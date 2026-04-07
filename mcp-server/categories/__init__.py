"""
Category Registry — maps tools to security categories.

Categories define access tiers with different risk levels and TOTP requirements.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Category(str, Enum):
    """Tool security categories."""
    LLM_WORKERS = "cat1_llm"
    CONTROL_SHELL = "cat2_control"
    DOCS_KNOWLEDGE = "cat3_docs"
    RESEARCH = "cat4_research"
    MEDIA = "cat5_media"
    SECURITY_TOOLS = "cat6_security"
    CLOUD = "cat7_cloud"


# Kategorie wymagające TOTP do odblokowania
TOTP_REQUIRED_CATEGORIES: set[Category] = {
    Category.CONTROL_SHELL,
    Category.SECURITY_TOOLS,
    Category.CLOUD,
}

# Kategorie otwarte (nie wymagają TOTP)
OPEN_CATEGORIES: set[Category] = {
    Category.LLM_WORKERS,
    Category.DOCS_KNOWLEDGE,
    Category.RESEARCH,
    Category.MEDIA,
}


@dataclass(frozen=True)
class ToolCategoryMapping:
    """Maps a tool name to its category and risk metadata."""
    tool_name: str
    category: Category
    risk_level: str  # low, medium, high, critical
    requires_totp: bool = False
    description: str = ""


@dataclass
class CategoryRegistry:
    """Registry mapping tools to categories with risk metadata."""
    _mappings: dict[str, ToolCategoryMapping] = field(default_factory=dict)

    def register(self, mapping: ToolCategoryMapping) -> None:
        """Register a tool-to-category mapping."""
        self._mappings[mapping.tool_name] = mapping

    def register_tool(
        self,
        tool_name: str,
        category: Category,
        risk_level: str = "medium",
        description: str = "",
    ) -> None:
        """Convenience: register a tool with auto-detected TOTP requirement."""
        requires_totp = category in TOTP_REQUIRED_CATEGORIES
        self._mappings[tool_name] = ToolCategoryMapping(
            tool_name=tool_name,
            category=category,
            risk_level=risk_level,
            requires_totp=requires_totp,
            description=description,
        )

    def get(self, tool_name: str) -> Optional[ToolCategoryMapping]:
        """Get mapping for a tool."""
        return self._mappings.get(tool_name)

    def get_category(self, tool_name: str) -> Optional[Category]:
        """Get category for a tool."""
        mapping = self._mappings.get(tool_name)
        return mapping.category if mapping else None

    def requires_totp(self, tool_name: str) -> bool:
        """Check if a tool requires TOTP unlock."""
        mapping = self._mappings.get(tool_name)
        if mapping is None:
            return True  # unknown tools require TOTP by default
        return mapping.requires_totp

    def list_tools(self, category: Optional[Category] = None) -> list[ToolCategoryMapping]:
        """List all tools, optionally filtered by category."""
        if category is None:
            return list(self._mappings.values())
        return [m for m in self._mappings.values() if m.category == category]

    def list_categories(self) -> dict[str, list[str]]:
        """List all categories with their tools."""
        result: dict[str, list[str]] = {}
        for mapping in self._mappings.values():
            cat_name = mapping.category.value
            if cat_name not in result:
                result[cat_name] = []
            result[cat_name].append(mapping.tool_name)
        return result

    def as_serializable(self) -> list[dict]:
        """Convert to JSON-serializable format."""
        return [
            {
                "tool_name": m.tool_name,
                "category": m.category.value,
                "risk_level": m.risk_level,
                "requires_totp": m.requires_totp,
                "description": m.description,
            }
            for m in sorted(self._mappings.values(), key=lambda x: (x.category.value, x.tool_name))
        ]


class UnlockManager:
    """Manages category unlock state (delegates to CategoryTOTP)."""

    def __init__(self, totp_gate):
        self._totp_gate = totp_gate

    def is_accessible(self, tool_name: str, registry: CategoryRegistry) -> tuple[bool, str]:
        """
        Check if a tool is accessible.
        Open categories are always accessible.
        TOTP-required categories need active unlock.
        """
        mapping = registry.get(tool_name)
        if mapping is None:
            return False, f"Unknown tool: {tool_name}"

        if mapping.category in OPEN_CATEGORIES:
            return True, "Open category"

        if not mapping.requires_totp:
            return True, "TOTP not required for this tool"

        category_key = mapping.category.value
        if self._totp_gate.is_unlocked(category_key):
            status = self._totp_gate.get_status(category_key)
            return True, f"Unlocked ({status['remaining_seconds']}s remaining)"

        status = self._totp_gate.get_status(category_key)
        if status["locked_out"]:
            return False, f"Category LOCKED OUT ({status['lockout_remaining']}s remaining)"

        return False, f"Category {category_key} requires TOTP unlock"

    def unlock(self, category: Category, code: str) -> dict:
        """Unlock a category with TOTP code."""
        return self._totp_gate.unlock(category.value, code)

    def revoke(self, category: Category) -> dict:
        """Revoke unlock for a category."""
        return self._totp_gate.revoke(category.value)

    def get_status(self) -> dict:
        """Get status for all categories."""
        return self._totp_gate.get_all_status()
