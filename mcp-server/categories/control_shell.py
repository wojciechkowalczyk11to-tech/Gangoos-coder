"""
CAT-2: Control Shell — shell_execute, vm_manage.

DANGEROUS — requires TOTP unlock with 5min TTL.
Extra audit logging on every invocation.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from categories import Category, CategoryRegistry


async def shell_execute(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    allowed_roots: Optional[list[str]] = None,
) -> dict:
    """
    Execute shell command with safety limits.

    - Timeout max 300s
    - Output truncation at 10KB
    - Working directory restricted to allowed roots
    """
    if timeout > 300:
        return {"error": "Timeout max 300s", "status_code": 400}

    effective_cwd = cwd or os.getcwd()
    if allowed_roots:
        resolved = str(Path(effective_cwd).resolve())
        if not any(resolved.startswith(str(Path(r).resolve())) for r in allowed_roots):
            return {"error": f"cwd {effective_cwd} outside allowed roots", "status_code": 403}

    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=effective_cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        stdout = result.stdout[:10000]
        stderr = result.stderr[:10000]

        return {
            "command": command,
            "cwd": effective_cwd,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": len(result.stdout) > 10000 or len(result.stderr) > 10000,
            "duration_ms": elapsed_ms,
        }
    except subprocess.TimeoutExpired:
        return {
            "error": f"Command timeout after {timeout}s",
            "command": command,
            "status_code": 408,
        }
    except Exception as e:
        return {"error": str(e), "command": command, "status_code": 500}


async def vm_manage(
    action: str,
    droplet_id: Optional[str] = None,
    region: str = "fra1",
    size: str = "s-1vcpu-1gb",
    image: str = "ubuntu-24-04-x64",
    name: Optional[str] = None,
) -> dict:
    """
    DigitalOcean VM management — create, list, reboot, destroy.

    Requires DIGITALOCEAN_TOKEN env var.
    """
    token = os.getenv("DIGITALOCEAN_TOKEN", "")
    if not token:
        return {"error": "DIGITALOCEAN_TOKEN not configured", "action": action}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    base = "https://api.digitalocean.com/v2"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if action == "list":
                resp = await client.get(f"{base}/droplets", headers=headers)
                resp.raise_for_status()
                droplets = resp.json().get("droplets", [])
                return {
                    "action": "list",
                    "count": len(droplets),
                    "droplets": [
                        {
                            "id": d["id"],
                            "name": d["name"],
                            "status": d["status"],
                            "region": d["region"]["slug"],
                            "size": d["size_slug"],
                            "ip": d.get("networks", {}).get("v4", [{}])[0].get("ip_address", ""),
                        }
                        for d in droplets
                    ],
                }

            elif action == "create":
                vm_name = name or f"gangoos-worker-{int(time.time())}"
                resp = await client.post(
                    f"{base}/droplets",
                    headers=headers,
                    json={
                        "name": vm_name,
                        "region": region,
                        "size": size,
                        "image": image,
                        "ssh_keys": [],
                        "tags": ["gangoos-coder"],
                    },
                )
                resp.raise_for_status()
                droplet = resp.json().get("droplet", {})
                return {
                    "action": "create",
                    "droplet_id": droplet.get("id"),
                    "name": droplet.get("name"),
                    "status": droplet.get("status"),
                }

            elif action == "reboot" and droplet_id:
                resp = await client.post(
                    f"{base}/droplets/{droplet_id}/actions",
                    headers=headers,
                    json={"type": "reboot"},
                )
                resp.raise_for_status()
                return {"action": "reboot", "droplet_id": droplet_id, "status": "initiated"}

            elif action == "destroy" and droplet_id:
                resp = await client.delete(f"{base}/droplets/{droplet_id}", headers=headers)
                resp.raise_for_status()
                return {"action": "destroy", "droplet_id": droplet_id, "status": "destroyed"}

            else:
                return {
                    "error": f"Invalid action: {action}. Use: list, create, reboot, destroy",
                    "status_code": 400,
                }
    except httpx.HTTPStatusError as e:
        return {
            "error": f"DigitalOcean API error {e.response.status_code}: {e.response.text[:500]}",
            "action": action,
        }
    except Exception as e:
        return {"error": f"VM management failed: {e}", "action": action}


def register_control_tools(mcp: Any, cat_registry: CategoryRegistry) -> None:
    """Register CAT-2 control shell tools."""
    from pydantic import BaseModel, Field

    cat_registry.register_tool(
        "shell_execute", Category.CONTROL_SHELL, risk_level="critical",
        description="Execute shell command with timeout and safety limits",
    )
    cat_registry.register_tool(
        "vm_manage", Category.CONTROL_SHELL, risk_level="critical",
        description="DigitalOcean VM management (create/list/reboot/destroy)",
    )

    class ShellInput(BaseModel):
        command: str = Field(..., min_length=1, max_length=2000)
        timeout: int = Field(30, ge=1, le=300)
        cwd: Optional[str] = Field(None)

    @mcp.tool(name="shell_execute", annotations={"title": "Shell Execute", "readOnlyHint": False})
    async def _shell(params: ShellInput) -> dict:
        """Execute shell command (CAT-2: requires TOTP unlock)."""
        return await shell_execute(params.command, params.timeout, params.cwd)

    class VMInput(BaseModel):
        action: str = Field(..., description="list | create | reboot | destroy")
        droplet_id: Optional[str] = Field(None)
        region: str = Field("fra1")
        size: str = Field("s-1vcpu-1gb")
        image: str = Field("ubuntu-24-04-x64")
        name: Optional[str] = Field(None)

    @mcp.tool(name="vm_manage", annotations={"title": "VM Manage", "readOnlyHint": False})
    async def _vm(params: VMInput) -> dict:
        """DigitalOcean VM management (CAT-2: requires TOTP unlock)."""
        return await vm_manage(
            params.action, params.droplet_id, params.region,
            params.size, params.image, params.name,
        )
