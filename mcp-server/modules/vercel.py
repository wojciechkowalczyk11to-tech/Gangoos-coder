"""
NEXUS MCP — Vercel Module
List/manage deployments, projects, domains, environment variables.
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.vercel")


async def _vc(client, method: str, path: str, json_data=None, params=None) -> dict:
    resp = await client.request(method, path, json=json_data, params=params)
    resp.raise_for_status()
    return resp.json()


def register(mcp: FastMCP):

    class ProjectListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="vercel_project_list", annotations={"readOnlyHint": True})
    async def vercel_project_list(params: ProjectListInput, ctx: Context) -> str:
        """List all Vercel projects."""
        client = get_clients()["vercel"]
        try:
            data = await _vc(client, "GET", "/v9/projects")
            projects = data.get("projects", [])
            output = "# Vercel Projects\n\n"
            for p in projects:
                fw = p.get("framework", "none")
                output += f"- **{p['name']}** | Framework: {fw} | Created: {p.get('createdAt', 'N/A')}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class DeploymentListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        project_name: Optional[str] = Field(None, description="Filter by project name")
        limit: int = Field(10, ge=1, le=50)

    @mcp.tool(name="vercel_deployment_list", annotations={"readOnlyHint": True})
    async def vercel_deployment_list(params: DeploymentListInput, ctx: Context) -> str:
        """List recent Vercel deployments."""
        client = get_clients()["vercel"]
        query = {"limit": params.limit}
        if params.project_name:
            query["projectId"] = params.project_name
        try:
            data = await _vc(client, "GET", "/v6/deployments", params=query)
            deps = data.get("deployments", [])
            output = "# Vercel Deployments\n\n"
            for d in deps:
                state = d.get("state", d.get("readyState", "UNKNOWN"))
                emoji = {"READY": "🟢", "ERROR": "🔴", "BUILDING": "🔄", "QUEUED": "⏳"}.get(state, "❓")
                url = d.get("url", "N/A")
                output += f"{emoji} **{d.get('name', 'unnamed')}** — {state}\n   URL: `{url}`\n\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class DeployInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        project_name: str = Field(..., description="Vercel project name")
        git_source: Optional[str] = Field(None, description="Git repo URL to deploy from")
        target: str = Field("production", description="Deploy target: production or preview")

    @mcp.tool(name="vercel_deploy", annotations={"destructiveHint": True})
    async def vercel_deploy(params: DeployInput, ctx: Context) -> str:
        """Trigger a new Vercel deployment."""
        client = get_clients()["vercel"]
        body = {"name": params.project_name, "target": params.target}
        if params.git_source:
            body["gitSource"] = {"type": "github", "repoId": params.git_source}
        try:
            data = await _vc(client, "POST", "/v13/deployments", body)
            return f"✅ Deployment triggered: `{data.get('url', 'pending')}`\nID: `{data.get('id')}`"
        except Exception as e:
            return f"Error: {e}"

    class DomainListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="vercel_domain_list", annotations={"readOnlyHint": True})
    async def vercel_domain_list(params: DomainListInput, ctx: Context) -> str:
        """List all domains in Vercel account."""
        client = get_clients()["vercel"]
        try:
            data = await _vc(client, "GET", "/v5/domains")
            domains = data.get("domains", [])
            output = "# Vercel Domains\n\n"
            for d in domains:
                output += f"- **{d['name']}** | Verified: {'✅' if d.get('verified') else '❌'}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class EnvVarInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        project_name: str = Field(..., description="Project name")
        key: str = Field(..., description="Environment variable key")
        value: str = Field(..., description="Environment variable value")
        target: list[str] = Field(["production", "preview"], description="Targets: production, preview, development")

    @mcp.tool(name="vercel_env_set", annotations={"destructiveHint": True})
    async def vercel_env_set(params: EnvVarInput, ctx: Context) -> str:
        """Set an environment variable for a Vercel project."""
        client = get_clients()["vercel"]
        try:
            data = await _vc(client, "POST", f"/v10/projects/{params.project_name}/env", {
                "key": params.key, "value": params.value,
                "target": params.target, "type": "encrypted",
            })
            return f"✅ Env var `{params.key}` set for `{params.project_name}`"
        except Exception as e:
            return f"Error: {e}"
