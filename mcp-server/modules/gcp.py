"""
NEXUS MCP — GCP Module
Manage VMs, deploy to Cloud Run, execute commands via SSH.
Uses Application Default Credentials (ADC).
"""

import json
import logging
from typing import Optional
from enum import Enum

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.gcp")


async def _gcp_headers(client) -> dict:
    """Get OAuth2 headers using ADC via google-auth."""
    import google.auth
    import google.auth.transport.requests

    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}


async def _gcp_request(client, method: str, url: str, json_data=None) -> dict:
    """Make authenticated GCP API request."""
    headers = await _gcp_headers(client)
    resp = await client.request(method, url, headers=headers, json=json_data)
    resp.raise_for_status()
    if resp.status_code == 204:
        return {"status": "success"}
    return resp.json()


def register(mcp: FastMCP):
    """Register GCP management tools."""

    # ── VM Management ───────────────────────────────────

    class VMListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone: Optional[str] = Field(None, description="GCP zone (e.g. europe-central2-a). Uses default if omitted.")

    @mcp.tool(
        name="gcp_vm_list",
        annotations={"title": "List GCP VMs", "readOnlyHint": True},
    )
    async def gcp_vm_list(params: VMListInput, ctx: Context) -> str:
        """List all Compute Engine VMs in a zone. Shows name, status, machine type, and IPs."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]
        zone = params.zone or cfg.GCP_ZONE
        project = cfg.GCP_PROJECT_ID

        if not project:
            return "Error: GCP_PROJECT_ID not set."

        try:
            url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances"
            data = await _gcp_request(client, "GET", url)

            if "items" not in data:
                return f"No VMs found in {zone}"

            output = f"# VMs in {zone}\n\n"
            for vm in data["items"]:
                status = vm.get("status", "UNKNOWN")
                mtype = vm.get("machineType", "").split("/")[-1]
                nics = vm.get("networkInterfaces", [])
                internal_ip = nics[0].get("networkIP", "N/A") if nics else "N/A"
                ext_ip = "N/A"
                if nics and nics[0].get("accessConfigs"):
                    ext_ip = nics[0]["accessConfigs"][0].get("natIP", "N/A")

                emoji = "🟢" if status == "RUNNING" else "🔴"
                output += f"{emoji} **{vm['name']}** — {mtype}\n"
                output += f"   Status: {status} | Internal: {internal_ip} | External: {ext_ip}\n\n"

            return output
        except Exception as e:
            return f"Error listing VMs: {e}"

    class VMActionInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        instance: str = Field(..., description="VM instance name")
        action: str = Field(..., description="Action: start, stop, reset, delete")
        zone: Optional[str] = Field(None, description="GCP zone")

    @mcp.tool(
        name="gcp_vm_action",
        annotations={"title": "Control GCP VM", "destructiveHint": True},
    )
    async def gcp_vm_action(params: VMActionInput, ctx: Context) -> str:
        """Start, stop, reset, or delete a GCP VM instance."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]
        zone = params.zone or cfg.GCP_ZONE
        project = cfg.GCP_PROJECT_ID

        valid_actions = ["start", "stop", "reset", "delete"]
        if params.action not in valid_actions:
            return f"Error: action must be one of {valid_actions}"

        try:
            if params.action == "delete":
                url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{params.instance}"
                data = await _gcp_request(client, "DELETE", url)
            else:
                url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{params.instance}/{params.action}"
                data = await _gcp_request(client, "POST", url)

            return f"✅ VM `{params.instance}` — action `{params.action}` initiated.\nOperation: {data.get('name', 'unknown')}"
        except Exception as e:
            return f"Error: {e}"

    class VMCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(..., description="VM name", min_length=1, max_length=63, pattern=r"^[a-z][a-z0-9-]*$")
        machine_type: str = Field("e2-micro", description="Machine type (e.g. e2-micro, e2-standard-2)")
        zone: Optional[str] = Field(None, description="GCP zone")
        image_family: str = Field("debian-12", description="OS image family")
        image_project: str = Field("debian-cloud", description="OS image project")
        disk_size_gb: int = Field(20, description="Boot disk size in GB", ge=10, le=1000)
        startup_script: Optional[str] = Field(None, description="Startup script content")

    @mcp.tool(
        name="gcp_vm_create",
        annotations={"title": "Create GCP VM", "destructiveHint": True},
    )
    async def gcp_vm_create(params: VMCreateInput, ctx: Context) -> str:
        """Create a new Compute Engine VM with specified configuration."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]
        zone = params.zone or cfg.GCP_ZONE
        project = cfg.GCP_PROJECT_ID

        body = {
            "name": params.name,
            "machineType": f"zones/{zone}/machineTypes/{params.machine_type}",
            "disks": [{
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": f"projects/{params.image_project}/global/images/family/{params.image_family}",
                    "diskSizeGb": str(params.disk_size_gb),
                },
            }],
            "networkInterfaces": [{
                "network": "global/networks/default",
                "accessConfigs": [{"name": "External NAT", "type": "ONE_TO_ONE_NAT"}],
            }],
        }

        if params.startup_script:
            body["metadata"] = {
                "items": [{"key": "startup-script", "value": params.startup_script}]
            }

        try:
            url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances"
            data = await _gcp_request(client, "POST", url, body)
            return f"✅ VM `{params.name}` creation initiated in {zone}.\nOperation: {data.get('name', 'unknown')}"
        except Exception as e:
            return f"Error creating VM: {e}"

    # ── Cloud Run ───────────────────────────────────────

    class CloudRunDeployInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        service_name: str = Field(..., description="Cloud Run service name")
        image: str = Field(..., description="Docker image URL (e.g. gcr.io/project/image:tag)")
        region: str = Field("europe-central2", description="Cloud Run region")
        memory: str = Field("512Mi", description="Memory limit (e.g. 256Mi, 1Gi)")
        cpu: str = Field("1", description="CPU limit")
        env_vars: Optional[dict] = Field(None, description="Environment variables as key:value dict")
        allow_unauthenticated: bool = Field(True, description="Allow public access")
        port: int = Field(8080, description="Container port", ge=1, le=65535)

    @mcp.tool(
        name="gcp_cloudrun_deploy",
        annotations={"title": "Deploy to Cloud Run", "destructiveHint": True},
    )
    async def gcp_cloudrun_deploy(params: CloudRunDeployInput, ctx: Context) -> str:
        """Deploy a container image to Cloud Run. Handles service creation and updates."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]
        project = cfg.GCP_PROJECT_ID

        env_list = []
        if params.env_vars:
            env_list = [{"name": k, "value": v} for k, v in params.env_vars.items()]

        service_body = {
            "apiVersion": "serving.knative.dev/v1",
            "kind": "Service",
            "metadata": {
                "name": params.service_name,
                "namespace": project,
                "annotations": {"run.googleapis.com/ingress": "all"},
            },
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{
                            "image": params.image,
                            "ports": [{"containerPort": params.port}],
                            "resources": {
                                "limits": {"memory": params.memory, "cpu": params.cpu}
                            },
                            "env": env_list,
                        }],
                    },
                },
            },
        }

        try:
            url = f"https://run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{project}/services/{params.service_name}"
            # Try update first, then create
            try:
                data = await _gcp_request(client, "PUT", url, service_body)
                action = "updated"
            except Exception:
                url = f"https://run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{project}/services"
                data = await _gcp_request(client, "POST", url, service_body)
                action = "created"

            return f"✅ Cloud Run service `{params.service_name}` {action} in {params.region}.\nImage: {params.image}"
        except Exception as e:
            return f"Error deploying: {e}"

    class CloudRunListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        region: str = Field("europe-central2", description="Cloud Run region")

    @mcp.tool(
        name="gcp_cloudrun_list",
        annotations={"title": "List Cloud Run Services", "readOnlyHint": True},
    )
    async def gcp_cloudrun_list(params: CloudRunListInput, ctx: Context) -> str:
        """List all Cloud Run services in a region."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]
        project = cfg.GCP_PROJECT_ID

        try:
            url = f"https://run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{project}/services"
            data = await _gcp_request(client, "GET", url)

            items = data.get("items", [])
            if not items:
                return "No Cloud Run services found."

            output = "# Cloud Run Services\n\n"
            for svc in items:
                name = svc["metadata"]["name"]
                url_svc = svc.get("status", {}).get("url", "N/A")
                conditions = svc.get("status", {}).get("conditions", [])
                ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
                emoji = "🟢" if ready else "🔴"
                output += f"{emoji} **{name}** — {url_svc}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    # ── SSH / Remote Command Execution ──────────────────

    class VMSSHInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        instance: str = Field(..., description="VM instance name or IP address")
        command: str = Field(..., description="Shell command to execute", min_length=1, max_length=10000)
        user: str = Field("ryjek", description="SSH username")
        zone: Optional[str] = Field(None, description="GCP zone (for gcloud ssh)")
        use_gcloud: bool = Field(True, description="Use gcloud compute ssh (true) or direct ssh (false)")

    @mcp.tool(
        name="gcp_vm_ssh",
        annotations={"title": "Execute Command on VM via SSH", "destructiveHint": True},
    )
    async def gcp_vm_ssh(params: VMSSHInput, ctx: Context) -> str:
        """Execute a command on a GCP VM via SSH. Uses gcloud compute ssh by default.
        For direct SSH, set use_gcloud=false and provide IP as instance.

        WARNING: This executes real commands on real machines. Be careful.
        """
        import asyncio

        state = {"clients": get_clients(), "settings": __import__("config").settings}
        cfg = state["settings"]
        zone = params.zone or cfg.GCP_ZONE

        try:
            if params.use_gcloud:
                cmd = [
                    "gcloud", "compute", "ssh",
                    f"{params.user}@{params.instance}",
                    f"--zone={zone}",
                    f"--project={cfg.GCP_PROJECT_ID}",
                    "--command", params.command,
                    "--quiet",
                ]
            else:
                cmd = [
                    "ssh", "-o", "StrictHostKeyChecking=no",
                    "-o", "ConnectTimeout=10",
                    f"{params.user}@{params.instance}",
                    params.command,
                ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            output = f"**Exit code:** {proc.returncode}\n\n"
            if stdout:
                output += f"**stdout:**\n```\n{stdout.decode(errors='replace')[:8000]}\n```\n\n"
            if stderr:
                output += f"**stderr:**\n```\n{stderr.decode(errors='replace')[:4000]}\n```\n"
            return output
        except asyncio.TimeoutError:
            return "Error: Command timed out after 120 seconds."
        except Exception as e:
            return f"Error executing SSH command: {e}"
