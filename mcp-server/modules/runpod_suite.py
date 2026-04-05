"""
NEXUS MCP — RunPod Full Suite Module

Complete GPU pod management: deploy, stop, logs, templates, GPU availability.
Requires: RUNPOD_API_KEY env var

Tools:
  - runpod_pods:         List all pods with status, GPU, cost
  - runpod_deploy:       Deploy pod from template or image
  - runpod_pod_control:  Start/stop/terminate a pod
  - runpod_pod_logs:     Get stdout/stderr logs from a pod
  - runpod_gpu_types:    List available GPU types + pricing
  - runpod_templates:    List saved templates
"""

import json
import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.runpod")

RUNPOD_API_URL = "https://api.runpod.io/graphql"


def _get_api_key() -> str:
    key = os.getenv("RUNPOD_API_KEY", "")
    if not key:
        raise RuntimeError(
            "RUNPOD_API_KEY not set. Get it from: https://runpod.io/console/user/settings"
        )
    return key


async def _gql(query: str, variables: dict | None = None) -> dict:
    """Execute a RunPod GraphQL query."""
    import httpx

    api_key = _get_api_key()
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{RUNPOD_API_URL}?api_key={api_key}",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"RunPod API error: {data['errors']}")
        return data.get("data", {})


def register(mcp: FastMCP):

    class RunpodPodsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="runpod_pods", annotations={"readOnlyHint": True})
    async def runpod_pods(params: RunpodPodsInput, ctx: Context) -> str:
        """List all RunPod pods with status, GPU type, cost, and uptime."""
        try:
            data = await _gql("""
                query {
                    myself {
                        pods {
                            id
                            name
                            desiredStatus
                            runtime {
                                uptimeInSeconds
                                gpus { id gpuUtilPercent memoryUtilPercent }
                            }
                            machine {
                                gpuDisplayName
                                podHostId
                            }
                            costPerHr
                            gpuCount
                            vcpuCount
                            memoryInGb
                            volumeInGb
                            containerDiskInGb
                            imageName
                        }
                    }
                }
            """)
            pods = data.get("myself", {}).get("pods", [])
            if not pods:
                return "No RunPod pods found."

            output = "# RunPod Pods\n\n"
            for p in pods:
                runtime = p.get("runtime") or {}
                uptime_h = (runtime.get("uptimeInSeconds") or 0) / 3600
                gpus = runtime.get("gpus") or []
                gpu_util = ""
                if gpus:
                    utils = [f"{g.get('gpuUtilPercent', 0):.0f}%" for g in gpus]
                    gpu_util = f" | GPU util: {', '.join(utils)}"

                machine = p.get("machine") or {}
                output += (
                    f"## {p['name']} (`{p['id']}`)\n"
                    f"**Status:** {p['desiredStatus']} | "
                    f"**GPU:** {p['gpuCount']}x {machine.get('gpuDisplayName', '?')} | "
                    f"**Cost:** ${p.get('costPerHr', 0):.3f}/hr\n"
                    f"**Uptime:** {uptime_h:.1f}h | "
                    f"**RAM:** {p.get('memoryInGb', 0)}GB | "
                    f"**vCPU:** {p.get('vcpuCount', 0)} | "
                    f"**Disk:** {p.get('containerDiskInGb', 0)}GB + {p.get('volumeInGb', 0)}GB vol"
                    f"{gpu_util}\n"
                    f"**Image:** `{p.get('imageName', '?')}`\n\n"
                )
            return output
        except Exception as e:
            return f"Error: {e}"

    class RunpodDeployInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(..., description="Pod name")
        image_name: Optional[str] = Field(None, description="Docker image")
        template_id: Optional[str] = Field(None, description="RunPod template ID")
        gpu_type_id: str = Field("NVIDIA GeForce RTX 4090", description="GPU type")
        gpu_count: int = Field(1, ge=1, le=8)
        volume_gb: int = Field(20)
        container_disk_gb: int = Field(20)
        cloud_type: str = Field("ALL", description="COMMUNITY, SECURE, or ALL")
        env_vars: Optional[dict] = Field(None, description="Environment variables")

    @mcp.tool(name="runpod_deploy", annotations={"destructiveHint": True})
    async def runpod_deploy(params: RunpodDeployInput, ctx: Context) -> str:
        """Deploy a new GPU pod on RunPod. Specify image or template_id."""
        try:
            if params.template_id:
                data = await _gql("""
                    mutation ($input: PodFindAndDeployOnDemandInput!) {
                        podFindAndDeployOnDemand(input: $input) {
                            id name desiredStatus costPerHr
                            machine { gpuDisplayName }
                        }
                    }
                """, {"input": {
                    "name": params.name,
                    "templateId": params.template_id,
                    "gpuTypeId": params.gpu_type_id,
                    "gpuCount": params.gpu_count,
                    "volumeInGb": params.volume_gb,
                    "containerDiskInGb": params.container_disk_gb,
                    "cloudType": params.cloud_type,
                }})
            else:
                image = params.image_name or "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04"
                env_input = [{"key": k, "value": v} for k, v in (params.env_vars or {}).items()]
                data = await _gql("""
                    mutation ($input: PodFindAndDeployOnDemandInput!) {
                        podFindAndDeployOnDemand(input: $input) {
                            id name desiredStatus costPerHr
                            machine { gpuDisplayName }
                        }
                    }
                """, {"input": {
                    "name": params.name,
                    "imageName": image,
                    "gpuTypeId": params.gpu_type_id,
                    "gpuCount": params.gpu_count,
                    "volumeInGb": params.volume_gb,
                    "containerDiskInGb": params.container_disk_gb,
                    "cloudType": params.cloud_type,
                    "env": env_input,
                }})

            pod = data.get("podFindAndDeployOnDemand", {})
            machine = pod.get("machine") or {}
            return (
                f"\u2705 Pod deployed!\n"
                f"**ID:** `{pod.get('id')}`\n"
                f"**Name:** {pod.get('name')}\n"
                f"**GPU:** {machine.get('gpuDisplayName', '?')}\n"
                f"**Cost:** ${pod.get('costPerHr', 0):.3f}/hr\n"
                f"**Status:** {pod.get('desiredStatus')}"
            )
        except Exception as e:
            return f"Error deploying pod: {e}"

    class RunpodControlInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        pod_id: str = Field(..., description="Pod ID")
        action: str = Field(..., description="Action: stop, resume, terminate")

    @mcp.tool(name="runpod_pod_control", annotations={"destructiveHint": True})
    async def runpod_pod_control(params: RunpodControlInput, ctx: Context) -> str:
        """Stop, resume, or terminate a RunPod pod."""
        try:
            mutations = {
                "stop": 'mutation { podStop(input: {podId: "%s"}) { id desiredStatus } }',
                "resume": 'mutation { podResume(input: {podId: "%s", gpuCount: 1}) { id desiredStatus costPerHr } }',
                "terminate": 'mutation { podTerminate(input: {podId: "%s"}) }',
            }
            if params.action not in mutations:
                return f"Unknown action: {params.action}. Use: stop, resume, terminate"
            query = mutations[params.action] % params.pod_id
            data = await _gql(query)
            return f"\u2705 Pod `{params.pod_id}` \u2192 {params.action}\n\n```json\n{json.dumps(data, indent=2)}\n```"
        except Exception as e:
            return f"Error: {e}"

    class RunpodLogsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        pod_id: str = Field(..., description="Pod ID")

    @mcp.tool(name="runpod_pod_logs", annotations={"readOnlyHint": True})
    async def runpod_pod_logs(params: RunpodLogsInput, ctx: Context) -> str:
        """Get stdout/stderr logs from a RunPod pod."""
        import httpx
        try:
            api_key = _get_api_key()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"https://api.runpod.io/v2/{params.pod_id}/stream",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    return f"**Logs for `{params.pod_id}`:**\n\n```\n{resp.text[:15000]}\n```"
            data = await _gql("""
                query ($podId: String!) {
                    pod(input: {podId: $podId}) { runtime { container { log } } }
                }
            """, {"podId": params.pod_id})
            log_text = data.get("pod", {}).get("runtime", {}).get("container", {}).get("log", "No logs")
            return f"**Logs for `{params.pod_id}`:**\n\n```\n{log_text[:15000]}\n```"
        except Exception as e:
            return f"Error: {e}"

    class RunpodGpuTypesInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="runpod_gpu_types", annotations={"readOnlyHint": True})
    async def runpod_gpu_types(params: RunpodGpuTypesInput, ctx: Context) -> str:
        """List available GPU types with pricing and availability on RunPod."""
        try:
            data = await _gql("""
                query {
                    gpuTypes {
                        id displayName memoryInGb
                        communityPrice securePrice
                        communitySpotPrice secureSpotPrice
                        lowestPrice(input: {gpuCount: 1}) { minimumBidPrice uninterruptablePrice }
                    }
                }
            """)
            gpus = sorted(data.get("gpuTypes", []), key=lambda g: g.get("communityPrice") or 999)
            if not gpus:
                return "No GPU types available."
            output = "# RunPod GPU Types\n\n| GPU | VRAM | Community $/hr | Secure $/hr | Spot $/hr |\n|-----|------|---------------|-------------|----------|\n"
            for g in gpus:
                if not g.get("communityPrice"):
                    continue
                output += f"| {g['displayName']} | {g.get('memoryInGb', '?')}GB | ${g.get('communityPrice', 0):.2f} | ${g.get('securePrice', 0):.2f} | ${g.get('communitySpotPrice', 0):.2f} |\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class RunpodTemplatesInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="runpod_templates", annotations={"readOnlyHint": True})
    async def runpod_templates(params: RunpodTemplatesInput, ctx: Context) -> str:
        """List saved RunPod templates (for quick pod deployment)."""
        try:
            data = await _gql("""
                query { myself { podTemplates { id name imageName containerDiskInGb volumeInGb isPublic } } }
            """)
            templates = data.get("myself", {}).get("podTemplates", [])
            if not templates:
                return "No templates found."
            output = "# RunPod Templates\n\n"
            for t in templates:
                output += f"- **{t['name']}** (`{t['id']}`) | Image: `{t.get('imageName', '?')}` | Disk: {t.get('containerDiskInGb', 0)}GB + {t.get('volumeInGb', 0)}GB vol\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    log.info("RunPod suite registered: runpod_pods, runpod_deploy, runpod_pod_control, runpod_pod_logs, runpod_gpu_types, runpod_templates")
