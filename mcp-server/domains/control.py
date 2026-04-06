"""
Control Domain - High-risk shell execution and filesystem operations.
DISABLED by default. Requires explicit ENABLE_CONTROL_DOMAIN=true and confirmation.
Risk level: CRITICAL
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from registry import ToolMeta, ToolRegistry


def is_control_enabled() -> bool:
    """Check if control domain is enabled."""
    return os.getenv("ENABLE_CONTROL_DOMAIN", "false").lower() in {"1", "true", "yes"}


async def shell_execute(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
) -> dict:
    """
    Execute shell command with isolation and safety limits.

    Safety measures:
    - Timeout to prevent hanging
    - Output truncation to prevent memory issues
    - Working directory restriction
    """
    if not is_control_enabled():
        return {
            "error": "Control domain not enabled",
            "status_code": 403,
        }

    # Validate timeout
    if timeout > 300:
        return {
            "error": "Timeout too long (max 300s)",
            "status_code": 400,
        }

    # Validate working directory
    if cwd:
        try:
            cwd_path = Path(cwd).resolve()
            # Don't allow escaping home directory (simple check)
            if not str(cwd_path).startswith(os.path.expanduser("~")):
                return {
                    "error": "Working directory outside allowed paths",
                    "status_code": 403,
                }
        except (ValueError, OSError):
            return {
                "error": "Invalid working directory",
                "status_code": 400,
            }
    else:
        cwd = os.path.expanduser("~")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
        )

        # Truncate output to prevent memory issues
        stdout = result.stdout[:10000]
        stderr = result.stderr[:10000]

        return {
            "command": command,
            "cwd": cwd,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": len(result.stdout) > 10000 or len(result.stderr) > 10000,
        }

    except subprocess.TimeoutExpired:
        return {
            "error": f"Command timeout after {timeout}s",
            "command": command,
            "status_code": 408,
        }
    except Exception as e:
        return {
            "error": str(e),
            "command": command,
            "status_code": 500,
        }


async def filesystem_write(
    path: str,
    content: str,
    mode: str = "w",
) -> dict:
    """
    Write to filesystem with allowlisted roots.

    Allowed roots:
    - User home directory (~)
    - /tmp
    - Current working directory

    Mode: 'w' (write), 'a' (append)
    """
    if not is_control_enabled():
        return {
            "error": "Control domain not enabled",
            "status_code": 403,
        }

    if mode not in {"w", "a"}:
        return {
            "error": "Invalid mode (must be 'w' or 'a')",
            "status_code": 400,
        }

    try:
        file_path = Path(path).resolve()

        # Check if path is in allowed roots
        allowed_roots = [
            Path(os.path.expanduser("~")).resolve(),
            Path("/tmp").resolve(),
            Path.cwd().resolve(),
        ]

        is_allowed = any(
            str(file_path).startswith(str(root)) for root in allowed_roots
        )

        if not is_allowed:
            return {
                "error": f"Path {path} not in allowed roots",
                "status_code": 403,
            }

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with file_path.open(mode, encoding="utf-8") as f:
            f.write(content)

        return {
            "path": str(file_path),
            "mode": mode,
            "size": len(content),
            "status": "success",
        }

    except (ValueError, OSError) as e:
        return {
            "error": str(e),
            "path": path,
            "status_code": 500,
        }


async def register(mcp: Any, registry: ToolRegistry) -> None:
    """Register control domain tools."""
    from pydantic import BaseModel, ConfigDict, Field

    # Control domain is disabled by default
    if not is_control_enabled():
        # Register tools but mark as disabled
        registry.register(
            ToolMeta(
                name="shell_execute",
                domain="control",
                risk_level="critical",
                enabled_by_default=False,
                requires_confirmation=True,
                description="Execute shell command (DISABLED - requires ENABLE_CONTROL_DOMAIN=true)",
                tags=("control", "shell", "dangerous"),
            )
        )

        registry.register(
            ToolMeta(
                name="filesystem_write",
                domain="control",
                risk_level="critical",
                enabled_by_default=False,
                requires_confirmation=True,
                description="Write to filesystem (DISABLED - requires ENABLE_CONTROL_DOMAIN=true)",
                tags=("control", "filesystem", "dangerous"),
            )
        )

        return

    # Register enabled tools
    registry.register(
        ToolMeta(
            name="shell_execute",
            domain="control",
            risk_level="critical",
            enabled_by_default=False,
            requires_confirmation=True,
            description="Execute shell command with timeout and output truncation.",
            tags=("control", "shell", "dangerous"),
        )
    )

    registry.register(
        ToolMeta(
            name="filesystem_write",
            domain="control",
            risk_level="critical",
            enabled_by_default=False,
            requires_confirmation=True,
            description="Write to filesystem (allowed roots: ~, /tmp, cwd)",
            tags=("control", "filesystem", "dangerous"),
        )
    )

    class ShellExecuteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        command: str = Field(..., min_length=1, max_length=1000)
        timeout: int = Field(30, ge=1, le=300)
        cwd: Optional[str] = Field(None, description="Working directory")

    class FilesystemWriteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        path: str = Field(..., min_length=1, max_length=500)
        content: str = Field(..., max_length=100000)
        mode: str = Field("w", pattern="^[wa]$")

    @mcp.tool(
        name="shell_execute",
        annotations={"title": "Execute Shell Command", "readOnlyHint": False},
    )
    async def shell_execute_tool(params: ShellExecuteInput, ctx: Any) -> dict:
        """Execute shell command."""
        return await shell_execute(params.command, params.timeout, params.cwd)

    @mcp.tool(
        name="filesystem_write",
        annotations={"title": "Write to Filesystem", "readOnlyHint": False},
    )
    async def filesystem_write_tool(params: FilesystemWriteInput, ctx: Any) -> dict:
        """Write to filesystem."""
        return await filesystem_write(params.path, params.content, params.mode)
