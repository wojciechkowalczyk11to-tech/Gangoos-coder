"""
mojo_exec — Mojo code execution tool.
Called by Rust CodeAct via POST /tools/call {"name": "mojo_exec", ...}.

Current runtime state:
- If MOJO_EXEC_BACKEND=subprocess: runs `mojo` binary in a sandboxed subprocess.
- If MOJO_EXEC_BACKEND=disabled (default): returns a clear error — Mojo SDK not present.
  This is the honest state when the VM does not have Mojo installed.

Backends must not be faked. If Mojo is unavailable, mojo_exec reports it correctly.
CodeAct self-healing: on mojo_exec error, agent inspects stderr and retries with fix.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.mojo-exec")

MOJO_EXEC_BACKEND = os.getenv("MOJO_EXEC_BACKEND", "disabled")
MOJO_BINARY = os.getenv("MOJO_BINARY", "mojo")
MOJO_TIMEOUT = int(os.getenv("MOJO_EXEC_TIMEOUT", "30"))
MAX_CODE_SIZE = 64 * 1024  # 64KB


class MojoExecInput(BaseModel):
    """Input model for mojo_exec tool — exported at module level for test access."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    code: str = Field(..., description="Mojo source code to execute", min_length=1)
    timeout: int = Field(MOJO_TIMEOUT, description="Execution timeout in seconds", ge=1, le=120)


async def _exec_mojo_subprocess(code: str, timeout: int) -> dict:
    """Run Mojo code in a temp file via subprocess. Returns {stdout, stderr, exit_code}."""
    with tempfile.NamedTemporaryFile(suffix=".mojo", mode="w", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            MOJO_BINARY, "run", tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "stdout": "",
                "stderr": f"mojo_exec: execution timed out after {timeout}s",
                "exit_code": -1,
            }
        return {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "exit_code": proc.returncode,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def register(mcp: FastMCP):

    @mcp.tool(
        name="mojo_exec",
        annotations={
            "title": "Execute Mojo Code",
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": False,
        },
    )
    async def mojo_exec(params: MojoExecInput, ctx: Context) -> str:
        """Execute Mojo source code.

        Called by CodeAct via /tools/call {"name": "mojo_exec", "arguments": {"code": "..."}}.
        Returns stdout/stderr/exit_code.

        Set MOJO_EXEC_BACKEND=subprocess and ensure `mojo` binary is in PATH.
        Default backend is 'disabled' — returns error when Mojo SDK is not installed.
        """
        if not params.code.strip():
            return "ERROR: mojo_exec received empty code"

        if len(params.code) > MAX_CODE_SIZE:
            return f"ERROR: code exceeds max size ({len(params.code)}B > {MAX_CODE_SIZE}B)"

        if MOJO_EXEC_BACKEND == "disabled":
            return (
                "mojo_exec: Mojo SDK not available on this host.\n"
                "To enable: set MOJO_EXEC_BACKEND=subprocess, install Mojo SDK, "
                "ensure `mojo` binary is in PATH.\n"
                "Alternatively, use python_repl or shell for non-Mojo code execution."
            )

        if MOJO_EXEC_BACKEND == "subprocess":
            # Verify binary is available before attempting
            which = subprocess.run(
                ["which", MOJO_BINARY], capture_output=True, timeout=5
            )
            if which.returncode != 0:
                return (
                    f"mojo_exec: binary '{MOJO_BINARY}' not found in PATH.\n"
                    "Set MOJO_BINARY env var or install Mojo SDK."
                )

            started = time.monotonic()
            log.info(f"mojo_exec: running {len(params.code)}B, timeout={params.timeout}s")
            result = await _exec_mojo_subprocess(params.code, params.timeout)
            elapsed = time.monotonic() - started

            output_parts = []
            if result["stdout"]:
                output_parts.append(f"stdout:\n{result['stdout']}")
            if result["stderr"]:
                output_parts.append(f"stderr:\n{result['stderr']}")
            output_parts.append(f"exit_code: {result['exit_code']} ({elapsed:.2f}s)")
            return "\n".join(output_parts)

        return f"mojo_exec: unknown backend '{MOJO_EXEC_BACKEND}' (expected: disabled|subprocess)"
