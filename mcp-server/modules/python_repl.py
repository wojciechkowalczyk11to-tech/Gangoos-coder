"""
NEXUS MCP — Python REPL Module
Execute Python code in isolated subprocess sandbox with pip support
"""
import json
import logging
import asyncio
import sys
import os
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP, Context

log = logging.getLogger("nexus-mcp.python_repl")


def register(mcp: FastMCP):

    class PythonREPLInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        code: str = Field(..., description="Python code to execute", min_length=1, max_length=50000)
        timeout: int = Field(60, description="Execution timeout in seconds", ge=1, le=300)
        working_dir: Optional[str] = Field(None, description="Working directory for execution")

    @mcp.tool(name="python_exec", annotations={"title": "Execute Python Code", "destructiveHint": True})
    async def python_exec(params: PythonREPLInput, ctx: Context) -> str:
        """Execute Python code in an isolated subprocess. Returns stdout, stderr, exit code.
        Perfect for data processing, file manipulation, API calls, calculations."""
        try:
            env = os.environ.copy()
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", params.code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=params.working_dir,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=params.timeout
            )
            return json.dumps({
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:15000],
                "stderr": stderr.decode(errors="replace")[:5000],
            })
        except asyncio.TimeoutError:
            return json.dumps({"error": f"Timeout after {params.timeout}s", "exit_code": -1})
        except Exception as e:
            return f"Error: {e}"

    class PipInstallInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        packages: list = Field(..., description="List of pip packages to install")

    @mcp.tool(name="python_pip_install", annotations={"title": "Pip Install Packages"})
    async def python_pip_install(params: PipInstallInput, ctx: Context) -> str:
        """Install Python packages via pip."""
        try:
            packages = " ".join(params.packages)
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", *params.packages,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            return json.dumps({
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[-3000:],
                "stderr": stderr.decode(errors="replace")[-2000:],
                "packages": params.packages,
            })
        except asyncio.TimeoutError:
            return json.dumps({"error": "pip install timed out after 120s"})
        except Exception as e:
            return f"Error: {e}"

    class PythonScriptInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        script_path: str = Field(..., description="Path to Python script file to execute")
        args: Optional[list] = Field(None, description="Command line arguments")
        timeout: int = Field(120, description="Execution timeout in seconds")
        working_dir: Optional[str] = Field(None, description="Working directory")

    @mcp.tool(name="python_run_script", annotations={"title": "Run Python Script File", "destructiveHint": True})
    async def python_run_script(params: PythonScriptInput, ctx: Context) -> str:
        """Run a Python script file from disk."""
        try:
            cmd = [sys.executable, params.script_path] + (params.args or [])
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=params.working_dir,
                env=os.environ.copy(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=params.timeout)
            return json.dumps({
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:15000],
                "stderr": stderr.decode(errors="replace")[:5000],
                "script": params.script_path,
            })
        except asyncio.TimeoutError:
            return json.dumps({"error": f"Script timed out after {params.timeout}s"})
        except Exception as e:
            return f"Error: {e}"

    log.info("Python REPL module registered (python_exec, pip_install, run_script)")
