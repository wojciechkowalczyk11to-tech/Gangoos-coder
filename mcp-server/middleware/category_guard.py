"""
Category Guard Middleware — checks TOTP unlock state before tool calls.

Intercepts tool invocations and verifies the caller has unlocked
the required category. Raises PermissionError with helpful message if locked.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Awaitable

from categories import CategoryRegistry, UnlockManager, OPEN_CATEGORIES

log = logging.getLogger("gangoos.category_guard")


class CategoryGuard:
    """
    Middleware that enforces category-based access control.

    For each tool call:
    1. Look up tool's category in CategoryRegistry
    2. Check if category requires TOTP unlock
    3. If locked, raise PermissionError with unlock instructions
    4. If unlocked, proceed to tool execution
    """

    def __init__(
        self,
        cat_registry: CategoryRegistry,
        unlock_manager: UnlockManager,
    ):
        self._cat_registry = cat_registry
        self._unlock_manager = unlock_manager

    def check_access(self, tool_name: str) -> None:
        """
        Check if tool is accessible. Raises PermissionError if not.

        Raises:
            PermissionError: with detailed message about how to unlock
        """
        accessible, reason = self._unlock_manager.is_accessible(tool_name, self._cat_registry)

        if accessible:
            log.debug("Access granted: %s (%s)", tool_name, reason)
            return

        mapping = self._cat_registry.get(tool_name)
        if mapping is None:
            raise PermissionError(
                f"Unknown tool: {tool_name}. "
                "Register the tool in CategoryRegistry before use."
            )

        category = mapping.category
        raise PermissionError(
            f"🔒 Tool '{tool_name}' requires TOTP unlock for category {category.value}.\n"
            f"Reason: {reason}\n\n"
            f"To unlock, call the 'category_unlock' tool with:\n"
            f"  category: \"{category.value}\"\n"
            f"  code: <your 6-digit TOTP code>\n\n"
            f"TOTP secrets are derived from TOTP_SECRET_BASE env var.\n"
            f"Use your authenticator app or: python -c "
            f"\"from security.totp_gate import CategoryTOTP; "
            f"t = CategoryTOTP(); print(t.get_current_code('{category.value}'))\""
        )

    def wrap_tool(
        self,
        tool_name: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        """Wrap a tool handler with category guard check."""
        async def guarded(*args: Any, **kwargs: Any) -> Any:
            self.check_access(tool_name)
            return await handler(*args, **kwargs)
        guarded.__name__ = handler.__name__
        guarded.__doc__ = handler.__doc__
        return guarded


def create_category_guard(
    cat_registry: CategoryRegistry,
    unlock_manager: UnlockManager,
) -> CategoryGuard:
    """Factory function for CategoryGuard."""
    return CategoryGuard(cat_registry, unlock_manager)
