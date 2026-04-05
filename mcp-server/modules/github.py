"""
NEXUS MCP — GitHub Module
Repos, files, PRs, issues, Actions, releases.
"""

import json
import base64
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.github")


async def _gh(client, method: str, path: str, json_data=None, params=None) -> dict:
    resp = await client.request(method, path, json=json_data, params=params)
    resp.raise_for_status()
    if resp.status_code == 204:
        return {"status": "success"}
    return resp.json()


def register(mcp: FastMCP):

    class RepoListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        owner: Optional[str] = Field(None, description="GitHub user/org. Uses default GITHUB_OWNER if omitted.")
        per_page: int = Field(30, ge=1, le=100)

    @mcp.tool(name="gh_repo_list", annotations={"readOnlyHint": True})
    async def gh_repo_list(params: RepoListInput, ctx: Context) -> str:
        """List repositories for a user/org."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER
        try:
            data = await _gh(client, "GET", f"/users/{owner}/repos", params={"per_page": params.per_page, "sort": "updated"})
            output = f"# Repos for {owner}\n\n"
            for r in data:
                vis = "🔒" if r["private"] else "🌐"
                desc = (r.get("description") or "N/A")[:80]
                output += f"{vis} **{r['name']}** — {desc}\n"
                output += f"   ⭐ {r['stargazers_count']} | 🍴 {r['forks_count']} | Updated: {r['updated_at'][:10]}\n\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class FileGetInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        repo: str = Field(..., description="Repository name")
        path: str = Field(..., description="File path in repo")
        owner: Optional[str] = Field(None)
        ref: Optional[str] = Field(None, description="Branch/tag/SHA")

    @mcp.tool(name="gh_file_get", annotations={"readOnlyHint": True})
    async def gh_file_get(params: FileGetInput, ctx: Context) -> str:
        """Get file content from a GitHub repository."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER
        query = {}
        if params.ref:
            query["ref"] = params.ref
        try:
            data = await _gh(client, "GET", f"/repos/{owner}/{params.repo}/contents/{params.path}", params=query)
            if isinstance(data, list):
                output = f"# Directory: {params.path}\n\n"
                for item in data:
                    icon = "📁" if item["type"] == "dir" else "📄"
                    output += f"{icon} {item['name']}\n"
                return output
            content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
            return f"# {params.path}\n\n```\n{content[:15000]}\n```\n\nSHA: `{data.get('sha')}`"
        except Exception as e:
            return f"Error: {e}"

    class FileCreateUpdateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        repo: str = Field(..., description="Repository name")
        path: str = Field(..., description="File path")
        content: str = Field(..., description="File content")
        message: str = Field(..., description="Commit message")
        owner: Optional[str] = Field(None)
        branch: Optional[str] = Field(None, description="Target branch")
        sha: Optional[str] = Field(None, description="Current SHA (required for updates, get from gh_file_get)")

    @mcp.tool(name="gh_file_write", annotations={"destructiveHint": True})
    async def gh_file_write(params: FileCreateUpdateInput, ctx: Context) -> str:
        """Create or update a file in a GitHub repository. For updates, provide the current SHA."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER

        body = {
            "message": params.message,
            "content": base64.b64encode(params.content.encode()).decode(),
        }
        if params.branch:
            body["branch"] = params.branch
        if params.sha:
            body["sha"] = params.sha

        try:
            data = await _gh(client, "PUT", f"/repos/{owner}/{params.repo}/contents/{params.path}", body)
            commit_sha = data.get("commit", {}).get("sha", "unknown")
            return f"✅ File `{params.path}` written to `{owner}/{params.repo}`.\nCommit: `{commit_sha[:7]}`"
        except Exception as e:
            return f"Error: {e}"

    class PRCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        repo: str = Field(..., description="Repository name")
        title: str = Field(..., description="PR title")
        body: str = Field("", description="PR description")
        head: str = Field(..., description="Source branch")
        base: str = Field("main", description="Target branch")
        owner: Optional[str] = Field(None)

    @mcp.tool(name="gh_pr_create", annotations={"destructiveHint": True})
    async def gh_pr_create(params: PRCreateInput, ctx: Context) -> str:
        """Create a pull request."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER
        try:
            data = await _gh(client, "POST", f"/repos/{owner}/{params.repo}/pulls", {
                "title": params.title, "body": params.body,
                "head": params.head, "base": params.base,
            })
            return f"✅ PR #{data['number']} created: {data['html_url']}"
        except Exception as e:
            return f"Error: {e}"

    class IssueCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        repo: str = Field(..., description="Repository name")
        title: str = Field(..., description="Issue title")
        body: str = Field("", description="Issue body")
        labels: Optional[list[str]] = Field(None, description="Labels to add")
        owner: Optional[str] = Field(None)

    @mcp.tool(name="gh_issue_create", annotations={"destructiveHint": True})
    async def gh_issue_create(params: IssueCreateInput, ctx: Context) -> str:
        """Create a GitHub issue."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER
        body = {"title": params.title, "body": params.body}
        if params.labels:
            body["labels"] = params.labels
        try:
            data = await _gh(client, "POST", f"/repos/{owner}/{params.repo}/issues", body)
            return f"✅ Issue #{data['number']} created: {data['html_url']}"
        except Exception as e:
            return f"Error: {e}"

    class ActionsListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        repo: str = Field(..., description="Repository name")
        owner: Optional[str] = Field(None)

    @mcp.tool(name="gh_actions_list", annotations={"readOnlyHint": True})
    async def gh_actions_list(params: ActionsListInput, ctx: Context) -> str:
        """List recent GitHub Actions workflow runs."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER
        try:
            data = await _gh(client, "GET", f"/repos/{owner}/{params.repo}/actions/runs", params={"per_page": 10})
            runs = data.get("workflow_runs", [])
            output = f"# Actions — {owner}/{params.repo}\n\n"
            for r in runs:
                emoji = {"completed": "✅", "in_progress": "🔄", "queued": "⏳", "failure": "❌"}.get(r["status"], "❓")
                conclusion = r.get("conclusion", r["status"])
                output += f"{emoji} **{r['name']}** — {conclusion} | Branch: `{r['head_branch']}` | {r['created_at'][:10]}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class ActionsDispatchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        repo: str = Field(..., description="Repository name")
        workflow_id: str = Field(..., description="Workflow filename (e.g. deploy.yml) or ID")
        ref: str = Field("main", description="Branch/tag to run on")
        inputs: Optional[dict] = Field(None, description="Workflow dispatch inputs")
        owner: Optional[str] = Field(None)

    @mcp.tool(name="gh_actions_dispatch", annotations={"destructiveHint": True})
    async def gh_actions_dispatch(params: ActionsDispatchInput, ctx: Context) -> str:
        """Trigger a GitHub Actions workflow dispatch event."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        cfg = state["settings"]
        owner = params.owner or cfg.GITHUB_OWNER
        body = {"ref": params.ref}
        if params.inputs:
            body["inputs"] = params.inputs
        try:
            await _gh(client, "POST", f"/repos/{owner}/{params.repo}/actions/workflows/{params.workflow_id}/dispatches", body)
            return f"✅ Workflow `{params.workflow_id}` dispatched on `{params.ref}`"
        except Exception as e:
            return f"Error: {e}"

    class RepoCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(..., description="Repository name")
        description: str = Field("", description="Repository description")
        private: bool = Field(True, description="Create as private repo")
        auto_init: bool = Field(True, description="Initialize with README")

    @mcp.tool(name="gh_repo_create", annotations={"destructiveHint": True})
    async def gh_repo_create(params: RepoCreateInput, ctx: Context) -> str:
        """Create a new GitHub repository."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["github"]
        try:
            data = await _gh(client, "POST", "/user/repos", {
                "name": params.name, "description": params.description,
                "private": params.private, "auto_init": params.auto_init,
            })
            return f"✅ Repository created: {data['html_url']}"
        except Exception as e:
            return f"Error: {e}"
