"""
NEXUS MCP - Multi-cloud and external provider tools.
Adds Azure, GitLab, RunPod, DigitalOcean and OCI CLI helpers.
"""

import json
import logging
import shutil
from typing import Optional
from urllib.parse import quote_plus

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.multi-cloud")


def _cfg():
    return __import__("config").settings


async def _request_json(client, method: str, url: str, headers: dict, body=None, params=None) -> dict:
    resp = await client.request(method, url, headers=headers, json=body, params=params)
    resp.raise_for_status()
    if resp.status_code == 204:
        return {"status": "success"}
    return resp.json()


async def _run_cli(cmd: list[str]) -> tuple[int, str, str]:
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


def register(mcp: FastMCP):
    class AzureRGListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        subscription_id: Optional[str] = Field(
            None, description="Azure subscription id. Uses AZURE_SUBSCRIPTION_ID if omitted."
        )

    @mcp.tool(name="azure_resource_group_list", annotations={"readOnlyHint": True})
    async def azure_resource_group_list(params: AzureRGListInput, ctx: Context) -> str:
        """List Azure Resource Groups via ARM REST API."""
        cfg = _cfg()
        token = cfg.AZURE_ACCESS_TOKEN
        subscription_id = params.subscription_id or cfg.AZURE_SUBSCRIPTION_ID
        if not token:
            return "Error: AZURE_ACCESS_TOKEN is not set."
        if not subscription_id:
            return "Error: AZURE_SUBSCRIPTION_ID is not set."

        client = get_clients()["general"]
        url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client, "GET", url, headers=headers, params={"api-version": "2021-04-01"}
            )
            groups = data.get("value", [])
            output = f"# Azure Resource Groups ({len(groups)})\n\n"
            for rg in groups:
                output += f"- **{rg.get('name', 'unknown')}** | Location: {rg.get('location', 'n/a')}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class AzureVMListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        subscription_id: Optional[str] = Field(
            None, description="Azure subscription id. Uses AZURE_SUBSCRIPTION_ID if omitted."
        )

    @mcp.tool(name="azure_vm_list", annotations={"readOnlyHint": True})
    async def azure_vm_list(params: AzureVMListInput, ctx: Context) -> str:
        """List Azure Virtual Machines in a subscription."""
        cfg = _cfg()
        token = cfg.AZURE_ACCESS_TOKEN
        subscription_id = params.subscription_id or cfg.AZURE_SUBSCRIPTION_ID
        if not token:
            return "Error: AZURE_ACCESS_TOKEN is not set."
        if not subscription_id:
            return "Error: AZURE_SUBSCRIPTION_ID is not set."

        client = get_clients()["general"]
        url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Compute/virtualMachines"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client, "GET", url, headers=headers, params={"api-version": "2023-07-01"}
            )
            vms = data.get("value", [])
            output = f"# Azure VMs ({len(vms)})\n\n"
            for vm in vms:
                name = vm.get("name", "unknown")
                loc = vm.get("location", "n/a")
                rg = vm.get("id", "").split("/resourceGroups/")
                rg_name = rg[1].split("/")[0] if len(rg) > 1 else "n/a"
                output += f"- **{name}** | RG: `{rg_name}` | Location: {loc}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class GitLabProjectListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        membership: bool = Field(True, description="Show only projects where the token user is a member.")
        per_page: int = Field(30, ge=1, le=100)

    @mcp.tool(name="gitlab_project_list", annotations={"readOnlyHint": True})
    async def gitlab_project_list(params: GitLabProjectListInput, ctx: Context) -> str:
        """List GitLab projects for the authenticated token."""
        cfg = _cfg()
        token = cfg.GITLAB_TOKEN
        if not token:
            return "Error: GITLAB_TOKEN is not set."

        base = cfg.GITLAB_BASE_URL.rstrip("/")
        client = get_clients()["general"]
        headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client,
                "GET",
                f"{base}/projects",
                headers=headers,
                params={"membership": str(params.membership).lower(), "per_page": params.per_page},
            )
            output = f"# GitLab Projects ({len(data)})\n\n"
            for p in data:
                vis = p.get("visibility", "unknown")
                output += f"- **{p.get('path_with_namespace', p.get('name', 'unknown'))}** | {vis}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class GitLabPipelineListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        project_id: str = Field(..., description="Project numeric id or URL-encoded path.")
        per_page: int = Field(10, ge=1, le=50)

    @mcp.tool(name="gitlab_pipeline_list", annotations={"readOnlyHint": True})
    async def gitlab_pipeline_list(params: GitLabPipelineListInput, ctx: Context) -> str:
        """List recent pipelines for a GitLab project."""
        cfg = _cfg()
        token = cfg.GITLAB_TOKEN
        if not token:
            return "Error: GITLAB_TOKEN is not set."

        base = cfg.GITLAB_BASE_URL.rstrip("/")
        client = get_clients()["general"]
        headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client,
                "GET",
                f"{base}/projects/{params.project_id}/pipelines",
                headers=headers,
                params={"per_page": params.per_page},
            )
            output = f"# GitLab Pipelines - {params.project_id}\n\n"
            for p in data:
                output += (
                    f"- **#{p.get('id')}** | {p.get('status', 'unknown')} | "
                    f"ref: `{p.get('ref', 'n/a')}` | {p.get('updated_at', 'n/a')}\n"
                )
            return output
        except Exception as e:
            return f"Error: {e}"

    class RunPodPodListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="runpod_pod_list", annotations={"readOnlyHint": True})
    async def runpod_pod_list(params: RunPodPodListInput, ctx: Context) -> str:
        """List RunPod pods via GraphQL API."""
        cfg = _cfg()
        key = cfg.RUNPOD_API_KEY
        if not key:
            return "Error: RUNPOD_API_KEY is not set."

        client = get_clients()["general"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        query = {"query": "query { myself { pods { id name desiredStatus imageName costPerHr } } }"}
        try:
            data = await _request_json(client, "POST", "https://api.runpod.io/graphql", headers=headers, body=query)
            pods = data.get("data", {}).get("myself", {}).get("pods", [])
            output = f"# RunPod Pods ({len(pods)})\n\n"
            for pod in pods:
                output += (
                    f"- **{pod.get('name', 'unnamed')}** | id: `{pod.get('id')}` | "
                    f"status: {pod.get('desiredStatus', 'n/a')} | ${pod.get('costPerHr', 'n/a')}/h\n"
                )
            return output
        except Exception as e:
            return f"Error: {e}"

    class DODropletListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        per_page: int = Field(50, ge=1, le=200)

    @mcp.tool(name="do_droplet_list", annotations={"readOnlyHint": True})
    async def do_droplet_list(params: DODropletListInput, ctx: Context) -> str:
        """List DigitalOcean droplets."""
        cfg = _cfg()
        token = cfg.DIGITALOCEAN_TOKEN
        if not token:
            return "Error: DIGITALOCEAN_TOKEN is not set."

        client = get_clients()["general"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client,
                "GET",
                "https://api.digitalocean.com/v2/droplets",
                headers=headers,
                params={"per_page": params.per_page},
            )
            droplets = data.get("droplets", [])
            output = f"# DigitalOcean Droplets ({len(droplets)})\n\n"
            for d in droplets:
                mem_mb = d.get("memory", "n/a")
                vcpus = d.get("vcpus", "n/a")
                reg = d.get("region", {}).get("slug", "n/a")
                status = d.get("status", "n/a")
                output += f"- **{d.get('name', 'unnamed')}** | {vcpus} vCPU / {mem_mb}MB | {reg} | {status}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class OciInstanceListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        compartment_id: str = Field(..., description="OCI compartment OCID.")
        region: Optional[str] = Field(None, description="OCI region, e.g. eu-frankfurt-1.")

    @mcp.tool(name="oci_instance_list", annotations={"readOnlyHint": True})
    async def oci_instance_list(params: OciInstanceListInput, ctx: Context) -> str:
        """List OCI compute instances using local OCI CLI configuration."""
        cfg = _cfg()
        cli = cfg.OCI_CLI_PATH or "oci"
        if shutil.which(cli) is None:
            return f"Error: OCI CLI not found in PATH (`{cli}`)."

        cmd = [
            cli,
            "--profile",
            cfg.OCI_PROFILE,
            "compute",
            "instance",
            "list",
            "--compartment-id",
            params.compartment_id,
            "--all",
            "--output",
            "json",
        ]
        if params.region:
            cmd.extend(["--region", params.region])

        try:
            code, out, err = await _run_cli(cmd)
            if code != 0:
                return f"Error: OCI CLI failed ({code}): {err[:1000]}"
            payload = json.loads(out or "{}")
            items = payload.get("data", [])
            output = f"# OCI Instances ({len(items)})\n\n"
            for vm in items:
                output += (
                    f"- **{vm.get('display-name', 'unnamed')}** | "
                    f"{vm.get('shape', 'n/a')} | {vm.get('lifecycle-state', 'n/a')}\n"
                )
            return output
        except Exception as e:
            return f"Error: {e}"

    class AWSIdentityInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        profile: Optional[str] = Field(None, description="AWS CLI profile. Uses AWS_PROFILE if omitted.")
        region: Optional[str] = Field(None, description="AWS region. Uses AWS_REGION if omitted.")

    @mcp.tool(name="aws_sts_identity", annotations={"readOnlyHint": True})
    async def aws_sts_identity(params: AWSIdentityInput, ctx: Context) -> str:
        """Show AWS caller identity using AWS CLI."""
        cfg = _cfg()
        cli = cfg.AWS_CLI_PATH or "aws"
        if shutil.which(cli) is None:
            return f"Error: AWS CLI not found in PATH (`{cli}`)."

        cmd = [cli]
        profile = params.profile or cfg.AWS_PROFILE
        region = params.region or cfg.AWS_REGION
        if profile:
            cmd.extend(["--profile", profile])
        if region:
            cmd.extend(["--region", region])
        cmd.extend(["sts", "get-caller-identity", "--output", "json"])

        code, out, err = await _run_cli(cmd)
        if code != 0:
            return f"Error: AWS CLI failed ({code}): {err[:1000]}"
        try:
            payload = json.loads(out or "{}")
        except Exception:
            return f"Error: could not parse AWS response: {out[:1000]}"

        return (
            "# AWS STS Identity\n\n"
            f"- Account: `{payload.get('Account', 'n/a')}`\n"
            f"- Arn: `{payload.get('Arn', 'n/a')}`\n"
            f"- UserId: `{payload.get('UserId', 'n/a')}`\n"
        )

    class AWSEC2ListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        profile: Optional[str] = Field(None, description="AWS CLI profile. Uses AWS_PROFILE if omitted.")
        region: Optional[str] = Field(None, description="AWS region. Uses AWS_REGION if omitted.")

    @mcp.tool(name="aws_ec2_instance_list", annotations={"readOnlyHint": True})
    async def aws_ec2_instance_list(params: AWSEC2ListInput, ctx: Context) -> str:
        """List EC2 instances using AWS CLI."""
        cfg = _cfg()
        cli = cfg.AWS_CLI_PATH or "aws"
        if shutil.which(cli) is None:
            return f"Error: AWS CLI not found in PATH (`{cli}`)."

        cmd = [cli]
        profile = params.profile or cfg.AWS_PROFILE
        region = params.region or cfg.AWS_REGION
        if profile:
            cmd.extend(["--profile", profile])
        if region:
            cmd.extend(["--region", region])
        cmd.extend(["ec2", "describe-instances", "--output", "json"])

        code, out, err = await _run_cli(cmd)
        if code != 0:
            return f"Error: AWS CLI failed ({code}): {err[:1000]}"
        try:
            payload = json.loads(out or "{}")
        except Exception:
            return f"Error: could not parse AWS response: {out[:1000]}"

        instances = []
        for res in payload.get("Reservations", []):
            for ins in res.get("Instances", []):
                name = "unnamed"
                for t in ins.get("Tags", []):
                    if t.get("Key") == "Name":
                        name = t.get("Value", "unnamed")
                        break
                instances.append(
                    {
                        "name": name,
                        "id": ins.get("InstanceId", "n/a"),
                        "state": ins.get("State", {}).get("Name", "n/a"),
                        "type": ins.get("InstanceType", "n/a"),
                    }
                )

        output = f"# AWS EC2 Instances ({len(instances)})\n\n"
        for ins in instances:
            output += (
                f"- **{ins['name']}** | `{ins['id']}` | {ins['type']} | {ins['state']}\n"
            )
        return output

    class MistralModelListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="mistral_model_list", annotations={"readOnlyHint": True})
    async def mistral_model_list(params: MistralModelListInput, ctx: Context) -> str:
        """List models available to the current Mistral API key."""
        cfg = _cfg()
        key = cfg.MISTRAL_API_KEY
        if not key:
            return "Error: MISTRAL_API_KEY is not set."

        client = get_clients()["general"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client, "GET", "https://api.mistral.ai/v1/models", headers=headers
            )
            models = data.get("data", [])
            output = f"# Mistral Models ({len(models)})\n\n"
            for m in models:
                output += f"- **{m.get('id', 'unknown')}** | created: {m.get('created', 'n/a')}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class MistralAdminGuideInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        workspace_id: Optional[str] = Field(
            None, description="Optional Mistral workspace id to build direct admin links."
        )

    @mcp.tool(name="mistral_admin_guide", annotations={"readOnlyHint": True})
    async def mistral_admin_guide(params: MistralAdminGuideInput, ctx: Context) -> str:
        """Return an actionable admin.mistral.ai checklist and deep links."""
        ws = params.workspace_id
        ws_q = quote_plus(ws) if ws else None
        lines = [
            "# Mistral Admin Guide",
            "",
            "Panel: https://admin.mistral.ai",
            "Docs: https://docs.mistral.ai",
            "",
            "Recommended setup order:",
            "1. Workspace and members (roles, least privilege).",
            "2. API keys rotation policy and secret manager sync.",
            "3. Usage and budget alerts.",
            "4. Model policy by environment (dev/stage/prod).",
            "5. Audit cadence and key revocation drill.",
            "",
            "Direct links:",
            "- API keys: https://admin.mistral.ai/api-keys",
            "- Billing/usage: https://admin.mistral.ai/billing",
            "- Docs API reference: https://docs.mistral.ai/api/",
        ]
        if ws_q:
            lines.extend(
                [
                    "",
                    f"Workspace-specific quick links (`{ws}`):",
                    f"- Keys: https://admin.mistral.ai/workspaces/{ws_q}/api-keys",
                    f"- Members: https://admin.mistral.ai/workspaces/{ws_q}/members",
                    f"- Usage: https://admin.mistral.ai/workspaces/{ws_q}/billing",
                ]
            )
        lines.extend(
            [
                "",
                "Note: admin.mistral.ai is UI-driven; this tool provides operational guidance and links.",
            ]
        )
        return "\n".join(lines)

    class MultiCloudStatusInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="multi_cloud_status", annotations={"readOnlyHint": True})
    async def multi_cloud_status(params: MultiCloudStatusInput, ctx: Context) -> str:
        """Show which external cloud/dev providers are configured."""
        cfg = _cfg()
        status = {
            "azure": bool(cfg.AZURE_ACCESS_TOKEN and cfg.AZURE_SUBSCRIPTION_ID),
            "gitlab": bool(cfg.GITLAB_TOKEN),
            "runpod": bool(cfg.RUNPOD_API_KEY),
            "digitalocean": bool(cfg.DIGITALOCEAN_TOKEN),
            "aws_env": bool(cfg.AWS_ACCESS_KEY_ID and cfg.AWS_SECRET_ACCESS_KEY),
            "mistral_key": bool(cfg.MISTRAL_API_KEY),
            "oci_cli": bool(shutil.which(cfg.OCI_CLI_PATH or "oci")),
        }
        lines = ["# Multi Cloud Status\n"]
        for key, ok in status.items():
            lines.append(f"- {key}: {'OK' if ok else 'MISSING'}")
        lines.append("\nMissing env keys summary:")
        if not status["azure"]:
            lines.append("- Azure: AZURE_ACCESS_TOKEN, AZURE_SUBSCRIPTION_ID")
        if not status["gitlab"]:
            lines.append("- GitLab: GITLAB_TOKEN")
        if not status["runpod"]:
            lines.append("- RunPod: RUNPOD_API_KEY")
        if not status["digitalocean"]:
            lines.append("- DigitalOcean: DIGITALOCEAN_TOKEN")
        if not status["aws_env"]:
            lines.append("- AWS: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        if not status["mistral_key"]:
            lines.append("- Mistral: MISTRAL_API_KEY")
        if not status["oci_cli"]:
            lines.append("- OCI: install `oci` CLI and configure profile (OCI_PROFILE)")
        return "\n".join(lines)
