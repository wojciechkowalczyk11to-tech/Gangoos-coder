"""
NEXUS MCP — Shell & Utility Module
Local command execution, web page fetching, file operations.
This is the "power tool" — use responsibly.
"""

import json
import asyncio
import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.shell")


def register(mcp: FastMCP):

    # ── Shell Execution ─────────────────────────────────

    class ShellExecInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        command: str = Field(..., description="Shell command to execute locally", min_length=1, max_length=10000)
        working_dir: Optional[str] = Field(None, description="Working directory")
        timeout: int = Field(120, description="Timeout in seconds", ge=1, le=600)

    @mcp.tool(
        name="shell_exec",
        annotations={"title": "Execute Local Shell Command", "destructiveHint": True},
    )
    async def shell_exec(params: ShellExecInput, ctx: Context) -> str:
        """Execute a shell command on the server (ThinkPad or Cloud Run container).
        Returns stdout, stderr, and exit code. Use for: git, docker, systemctl, etc.

        WARNING: This runs real commands. Be careful with destructive operations.
        """
        try:
            proc = await asyncio.create_subprocess_shell(
                params.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=params.working_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=params.timeout
            )

            output = f"**Exit code:** {proc.returncode}\n\n"
            if stdout:
                text = stdout.decode(errors="replace")[:12000]
                output += f"**stdout:**\n```\n{text}\n```\n\n"
            if stderr:
                text = stderr.decode(errors="replace")[:6000]
                output += f"**stderr:**\n```\n{text}\n```"
            return output
        except asyncio.TimeoutError:
            return f"Error: Command timed out after {params.timeout}s"
        except Exception as e:
            return f"Error: {e}"

    # ── Web Fetch (Browser-like) ────────────────────────

    class WebFetchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="URL to fetch")
        method: str = Field("GET", description="HTTP method: GET, POST, PUT, DELETE")
        headers: Optional[dict] = Field(None, description="Custom headers")
        body: Optional[str] = Field(None, description="Request body (for POST/PUT)")
        extract_text: bool = Field(True, description="Extract text content from HTML (removes tags)")
        max_length: int = Field(15000, description="Max response length in chars", ge=100, le=100000)

    @mcp.tool(
        name="web_fetch",
        annotations={"title": "Fetch Web Page", "readOnlyHint": True, "openWorldHint": True},
    )
    async def web_fetch(params: WebFetchInput, ctx: Context) -> str:
        """Fetch a web page or API endpoint. Can extract text from HTML.
        Use for: reading docs, checking service status, API calls.
        """
        client = get_clients()["general"]
        try:
            kwargs = {"headers": params.headers or {}}
            if params.body:
                kwargs["content"] = params.body.encode()

            resp = await client.request(params.method, params.url, **kwargs)

            content_type = resp.headers.get("content-type", "")
            status = resp.status_code

            if params.extract_text and "html" in content_type:
                # Simple HTML to text extraction
                import re
                text = resp.text
                text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                content = text[:params.max_length]
            else:
                content = resp.text[:params.max_length]

            return f"**Status:** {status}\n**URL:** {params.url}\n**Content-Type:** {content_type}\n\n---\n\n{content}"
        except Exception as e:
            return f"Error fetching {params.url}: {e}"

    # ── File Operations ─────────────────────────────────

    class FileReadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        path: str = Field(..., description="File path to read")
        max_lines: int = Field(500, ge=1, le=5000)

    @mcp.tool(name="file_read", annotations={"readOnlyHint": True})
    async def file_read(params: FileReadInput, ctx: Context) -> str:
        """Read a local file. Returns content with line numbers."""
        try:
            if not os.path.exists(params.path):
                return f"Error: File not found: {params.path}"
            with open(params.path, "r", errors="replace") as f:
                lines = f.readlines()[:params.max_lines]
            numbered = "".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
            total = len(lines)
            return f"**{params.path}** ({total} lines shown)\n\n```\n{numbered}\n```"
        except Exception as e:
            return f"Error: {e}"

    class FileWriteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        path: str = Field(..., description="File path to write")
        content: str = Field(..., description="File content")
        append: bool = Field(False, description="Append instead of overwrite")

    @mcp.tool(name="file_write", annotations={"destructiveHint": True})
    async def file_write(params: FileWriteInput, ctx: Context) -> str:
        """Write content to a local file. Creates parent directories if needed."""
        try:
            os.makedirs(os.path.dirname(params.path) or ".", exist_ok=True)
            mode = "a" if params.append else "w"
            with open(params.path, mode) as f:
                f.write(params.content)
            size = os.path.getsize(params.path)
            return f"✅ Written {len(params.content)} chars to `{params.path}` ({size} bytes)"
        except Exception as e:
            return f"Error: {e}"

    class DirListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        path: str = Field(".", description="Directory path")
        recursive: bool = Field(False, description="List recursively")
        max_depth: int = Field(2, ge=1, le=5)

    @mcp.tool(name="dir_list", annotations={"readOnlyHint": True})
    async def dir_list(params: DirListInput, ctx: Context) -> str:
        """List directory contents."""
        try:
            if not os.path.isdir(params.path):
                return f"Error: Not a directory: {params.path}"

            output = f"# {params.path}\n\n"
            if params.recursive:
                for root, dirs, files in os.walk(params.path):
                    depth = root.replace(params.path, "").count(os.sep)
                    if depth >= params.max_depth:
                        dirs.clear()
                        continue
                    indent = "  " * depth
                    output += f"{indent}📁 {os.path.basename(root)}/\n"
                    for f in sorted(files)[:50]:
                        output += f"{indent}  📄 {f}\n"
            else:
                entries = sorted(os.listdir(params.path))
                for e in entries[:100]:
                    full = os.path.join(params.path, e)
                    icon = "📁" if os.path.isdir(full) else "📄"
                    size = ""
                    if os.path.isfile(full):
                        s = os.path.getsize(full)
                        size = f" ({s / 1024:.1f} KB)" if s > 1024 else f" ({s} B)"
                    output += f"{icon} {e}{size}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    # ── Docker Management ───────────────────────────────

    class DockerInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        action: str = Field(..., description="Docker command: ps, images, logs, build, run, stop, rm, compose-up, compose-down")
        args: Optional[str] = Field(None, description="Additional arguments (e.g. container name, image, compose file path)")
        working_dir: Optional[str] = Field(None, description="Working directory for build/compose")

    @mcp.tool(name="docker_manage", annotations={"destructiveHint": True})
    async def docker_manage(params: DockerInput, ctx: Context) -> str:
        """Manage Docker containers and images. Supports common docker and docker-compose commands."""
        cmd_map = {
            "ps": "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}'",
            "images": "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'",
            "logs": f"docker logs --tail 100 {params.args or ''}",
            "build": f"docker build {params.args or '.'}",
            "run": f"docker run {params.args or ''}",
            "stop": f"docker stop {params.args or ''}",
            "rm": f"docker rm {params.args or ''}",
            "compose-up": f"docker compose {'-f ' + params.args if params.args else ''} up -d",
            "compose-down": f"docker compose {'-f ' + params.args if params.args else ''} down",
        }

        cmd = cmd_map.get(params.action)
        if not cmd:
            return f"Error: Unknown action '{params.action}'. Valid: {list(cmd_map.keys())}"

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=params.working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            output = f"**Command:** `{cmd}`\n**Exit:** {proc.returncode}\n\n"
            if stdout:
                output += f"```\n{stdout.decode(errors='replace')[:8000]}\n```\n"
            if stderr:
                output += f"\n**stderr:**\n```\n{stderr.decode(errors='replace')[:4000]}\n```"
            return output
        except Exception as e:
            return f"Error: {e}"

    # ── System Info ─────────────────────────────────────

    class SysInfoInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="sys_info", annotations={"readOnlyHint": True})
    async def sys_info(params: SysInfoInput, ctx: Context) -> str:
        """Get system information: CPU, RAM, disk, network, uptime."""
        try:
            commands = {
                "hostname": "hostname",
                "uptime": "uptime -p 2>/dev/null || uptime",
                "cpu": "nproc",
                "memory": "free -h | head -2",
                "disk": "df -h / | tail -1",
                "ip": "hostname -I 2>/dev/null || echo 'N/A'",
                "os": "cat /etc/os-release 2>/dev/null | head -3 || echo 'unknown'",
            }
            results = {}
            for name, cmd in commands.items():
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                results[name] = stdout.decode(errors="replace").strip()

            output = "# System Info\n\n"
            for k, v in results.items():
                output += f"**{k}:** {v}\n"
            return output
        except Exception as e:
            return f"Error: {e}"
