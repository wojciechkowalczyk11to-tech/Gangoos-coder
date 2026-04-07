"""
CAT-7: Cloud — digitalocean_manage, runpod_gpu, cloudflare_manage, render_deploy.

Cloud infrastructure management tools.
Requires TOTP unlock (category cat7_cloud).
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

from categories import Category, CategoryRegistry


async def digitalocean_manage(
    action: str,
    resource_type: str = "droplets",
    resource_id: Optional[str] = None,
    params: Optional[dict] = None,
) -> dict:
    """
    DigitalOcean API — manage droplets, domains, databases, etc.
    """
    token = os.getenv("DIGITALOCEAN_TOKEN", "")
    if not token:
        return {"error": "DIGITALOCEAN_TOKEN not configured", "provider": "digitalocean"}

    base = "https://api.digitalocean.com/v2"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if action == "list":
                resp = await client.get(f"{base}/{resource_type}", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                items = data.get(resource_type, [])
                return {
                    "action": "list",
                    "resource_type": resource_type,
                    "count": len(items),
                    "items": items[:20],
                }

            elif action == "get" and resource_id:
                resp = await client.get(f"{base}/{resource_type}/{resource_id}", headers=headers)
                resp.raise_for_status()
                return {"action": "get", "resource_type": resource_type, "data": resp.json()}

            elif action == "create":
                resp = await client.post(
                    f"{base}/{resource_type}", headers=headers, json=params or {},
                )
                resp.raise_for_status()
                return {"action": "create", "resource_type": resource_type, "data": resp.json()}

            elif action == "delete" and resource_id:
                resp = await client.delete(f"{base}/{resource_type}/{resource_id}", headers=headers)
                resp.raise_for_status()
                return {"action": "delete", "resource_type": resource_type, "resource_id": resource_id}

            else:
                return {"error": f"Invalid action/params: action={action}", "status_code": 400}
    except httpx.HTTPStatusError as e:
        return {"error": f"DO API {e.response.status_code}: {e.response.text[:500]}", "provider": "digitalocean"}
    except Exception as e:
        return {"error": f"DigitalOcean failed: {e}", "provider": "digitalocean"}


async def runpod_gpu(
    action: str,
    gpu_type: str = "NVIDIA A40",
    template_id: Optional[str] = None,
    pod_id: Optional[str] = None,
) -> dict:
    """
    RunPod GPU — serverless GPU inference and pod management.
    """
    api_key = os.getenv("RUNPOD_API_KEY", "")
    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured", "provider": "runpod"}

    base = "https://api.runpod.io/v2"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if action == "list_pods":
                resp = await client.get(
                    "https://api.runpod.io/graphql",
                    headers=headers,
                    params={"query": "{ myself { pods { id name runtime { uptimeInSeconds gpus { id gpuUtilPercent } } } } }"},
                )
                resp.raise_for_status()
                return {"action": "list_pods", "data": resp.json()}

            elif action == "create_pod":
                query = """
                mutation {
                    podFindAndDeployOnDemand(input: {
                        name: "gangoos-gpu-%d",
                        gpuTypeId: "%s",
                        imageName: "runpod/pytorch:2.1.0-py3.10-cuda12.1",
                        volumeInGb: 20,
                        containerDiskInGb: 10,
                    }) { id name }
                }
                """ % (int(time.time()), gpu_type)
                resp = await client.post(
                    "https://api.runpod.io/graphql",
                    headers=headers,
                    json={"query": query},
                )
                resp.raise_for_status()
                return {"action": "create_pod", "data": resp.json()}

            elif action == "stop_pod" and pod_id:
                query = f'mutation {{ podStop(input: {{ podId: "{pod_id}" }}) {{ id }} }}'
                resp = await client.post(
                    "https://api.runpod.io/graphql",
                    headers=headers,
                    json={"query": query},
                )
                resp.raise_for_status()
                return {"action": "stop_pod", "pod_id": pod_id, "data": resp.json()}

            elif action == "list_gpus":
                query = "{ gpuTypes { id displayName memoryInGb } }"
                resp = await client.post(
                    "https://api.runpod.io/graphql",
                    headers=headers,
                    json={"query": query},
                )
                resp.raise_for_status()
                return {"action": "list_gpus", "data": resp.json()}

            else:
                return {"error": f"Invalid action: {action}", "status_code": 400}
    except httpx.HTTPStatusError as e:
        return {"error": f"RunPod HTTP {e.response.status_code}: {e.response.text[:500]}", "provider": "runpod"}
    except Exception as e:
        return {"error": f"RunPod failed: {e}", "provider": "runpod"}


async def cloudflare_manage(
    action: str,
    zone_id: Optional[str] = None,
    record_data: Optional[dict] = None,
) -> dict:
    """
    Cloudflare — DNS, Workers, zones management.
    """
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not token:
        return {"error": "CLOUDFLARE_API_TOKEN not configured", "provider": "cloudflare"}

    base = "https://api.cloudflare.com/client/v4"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if action == "list_zones":
                resp = await client.get(f"{base}/zones", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                zones = data.get("result", [])
                return {
                    "action": "list_zones",
                    "count": len(zones),
                    "zones": [
                        {"id": z["id"], "name": z["name"], "status": z["status"]}
                        for z in zones
                    ],
                }

            elif action == "list_dns" and zone_id:
                resp = await client.get(f"{base}/zones/{zone_id}/dns_records", headers=headers)
                resp.raise_for_status()
                records = resp.json().get("result", [])
                return {
                    "action": "list_dns",
                    "zone_id": zone_id,
                    "count": len(records),
                    "records": [
                        {"id": r["id"], "type": r["type"], "name": r["name"], "content": r["content"]}
                        for r in records
                    ],
                }

            elif action == "create_dns" and zone_id and record_data:
                resp = await client.post(
                    f"{base}/zones/{zone_id}/dns_records",
                    headers=headers,
                    json=record_data,
                )
                resp.raise_for_status()
                return {"action": "create_dns", "zone_id": zone_id, "record": resp.json().get("result", {})}

            elif action == "list_workers":
                account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
                if not account_id:
                    return {"error": "CLOUDFLARE_ACCOUNT_ID not configured"}
                resp = await client.get(
                    f"{base}/accounts/{account_id}/workers/scripts",
                    headers=headers,
                )
                resp.raise_for_status()
                return {"action": "list_workers", "data": resp.json().get("result", [])}

            else:
                return {"error": f"Invalid action: {action}", "status_code": 400}
    except httpx.HTTPStatusError as e:
        return {"error": f"Cloudflare HTTP {e.response.status_code}: {e.response.text[:500]}", "provider": "cloudflare"}
    except Exception as e:
        return {"error": f"Cloudflare failed: {e}", "provider": "cloudflare"}


async def render_deploy(
    action: str,
    service_id: Optional[str] = None,
    service_data: Optional[dict] = None,
) -> dict:
    """
    Render.com — web service deployment and management.
    """
    api_key = os.getenv("RENDER_API_KEY", "")
    if not api_key:
        return {"error": "RENDER_API_KEY not configured", "provider": "render"}

    base = "https://api.render.com/v1"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if action == "list_services":
                resp = await client.get(f"{base}/services", headers=headers)
                resp.raise_for_status()
                services = resp.json()
                return {
                    "action": "list_services",
                    "count": len(services),
                    "services": [
                        {
                            "id": s.get("service", {}).get("id", ""),
                            "name": s.get("service", {}).get("name", ""),
                            "type": s.get("service", {}).get("type", ""),
                            "status": s.get("service", {}).get("suspended", "unknown"),
                        }
                        for s in services[:20]
                    ],
                }

            elif action == "deploy" and service_id:
                resp = await client.post(
                    f"{base}/services/{service_id}/deploys",
                    headers={**headers, "Content-Type": "application/json"},
                    json={},
                )
                resp.raise_for_status()
                return {"action": "deploy", "service_id": service_id, "deploy": resp.json()}

            elif action == "get_service" and service_id:
                resp = await client.get(f"{base}/services/{service_id}", headers=headers)
                resp.raise_for_status()
                return {"action": "get_service", "service": resp.json()}

            elif action == "create_service" and service_data:
                resp = await client.post(
                    f"{base}/services",
                    headers={**headers, "Content-Type": "application/json"},
                    json=service_data,
                )
                resp.raise_for_status()
                return {"action": "create_service", "service": resp.json()}

            else:
                return {"error": f"Invalid action: {action}", "status_code": 400}
    except httpx.HTTPStatusError as e:
        return {"error": f"Render HTTP {e.response.status_code}: {e.response.text[:500]}", "provider": "render"}
    except Exception as e:
        return {"error": f"Render failed: {e}", "provider": "render"}


def register_cloud_tools(mcp: Any, cat_registry: CategoryRegistry) -> None:
    """Register CAT-7 cloud tools."""
    from pydantic import BaseModel, Field

    cat_registry.register_tool(
        "digitalocean_manage", Category.CLOUD, risk_level="high",
        description="DigitalOcean API: droplets, domains, databases",
    )
    cat_registry.register_tool(
        "runpod_gpu", Category.CLOUD, risk_level="high",
        description="RunPod GPU: serverless inference and pod management",
    )
    cat_registry.register_tool(
        "cloudflare_manage", Category.CLOUD, risk_level="high",
        description="Cloudflare: DNS, Workers, zones",
    )
    cat_registry.register_tool(
        "render_deploy", Category.CLOUD, risk_level="medium",
        description="Render.com: web service deployment",
    )

    class DOInput(BaseModel):
        action: str = Field(..., description="list | get | create | delete")
        resource_type: str = Field("droplets")
        resource_id: Optional[str] = Field(None)
        params: Optional[dict] = Field(None)

    @mcp.tool(name="digitalocean_manage", annotations={"title": "DigitalOcean Manage", "readOnlyHint": False})
    async def _do(params: DOInput) -> dict:
        """DigitalOcean cloud management (CAT-7: requires TOTP)."""
        return await digitalocean_manage(params.action, params.resource_type, params.resource_id, params.params)

    class RunPodInput(BaseModel):
        action: str = Field(..., description="list_pods | create_pod | stop_pod | list_gpus")
        gpu_type: str = Field("NVIDIA A40")
        template_id: Optional[str] = Field(None)
        pod_id: Optional[str] = Field(None)

    @mcp.tool(name="runpod_gpu", annotations={"title": "RunPod GPU", "readOnlyHint": False})
    async def _runpod(params: RunPodInput) -> dict:
        """RunPod GPU management (CAT-7: requires TOTP)."""
        return await runpod_gpu(params.action, params.gpu_type, params.template_id, params.pod_id)

    class CFInput(BaseModel):
        action: str = Field(..., description="list_zones | list_dns | create_dns | list_workers")
        zone_id: Optional[str] = Field(None)
        record_data: Optional[dict] = Field(None)

    @mcp.tool(name="cloudflare_manage", annotations={"title": "Cloudflare Manage", "readOnlyHint": False})
    async def _cf(params: CFInput) -> dict:
        """Cloudflare management (CAT-7: requires TOTP)."""
        return await cloudflare_manage(params.action, params.zone_id, params.record_data)

    class RenderInput(BaseModel):
        action: str = Field(..., description="list_services | deploy | get_service | create_service")
        service_id: Optional[str] = Field(None)
        service_data: Optional[dict] = Field(None)

    @mcp.tool(name="render_deploy", annotations={"title": "Render Deploy", "readOnlyHint": False})
    async def _render(params: RenderInput) -> dict:
        """Render.com deployment (CAT-7: requires TOTP)."""
        return await render_deploy(params.action, params.service_id, params.service_data)
