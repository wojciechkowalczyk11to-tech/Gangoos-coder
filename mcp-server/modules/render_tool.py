"""
Render Tool — manage web services, databases, cron jobs on Render.com.
Supports: list/create/manage services, deploys, env vars, databases.
"""
import os, json, urllib.request, urllib.parse
from mcp.server.fastmcp import FastMCP

RENDER_KEY = os.getenv("RENDER_API_KEY", "")
RENDER_BASE = "https://api.render.com/v1"


def _render(method, path, body=None):
    if not RENDER_KEY:
        return {"error": "RENDER_API_KEY not set"}
    headers = {"Authorization": f"Bearer {RENDER_KEY}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(f"{RENDER_BASE}{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {"status": "ok"}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def register(mcp: FastMCP):
    @mcp.tool(name="render_list_services", annotations={"title": "List Render services", "destructiveHint": False})
    async def render_list_services(params: dict) -> str:
        """
        List all services on Render account.
        params: type (str, optional: web_service|static_site|private_service|background_worker|cron_job),
                limit (int, optional, default 20)
        """
        qs = f"?limit={params.get('limit', 20)}"
        stype = params.get("type")
        if stype:
            qs += f"&type={stype}"
        result = _render("GET", f"/services{qs}")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        services = result if isinstance(result, list) else []
        summary = []
        for item in services:
            s = item.get("service", item)
            summary.append({
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "type": s.get("type", ""),
                "status": s.get("suspended", "active") and "suspended" or "active",
                "url": s.get("serviceDetails", {}).get("url", ""),
                "region": s.get("region", ""),
                "branch": s.get("branch", ""),
                "repo": s.get("repo", ""),
            })
        return json.dumps({"count": len(summary), "services": summary})

    @mcp.tool(name="render_create_service", annotations={"title": "Create Render service", "destructiveHint": True})
    async def render_create_service(params: dict) -> str:
        """
        Create a new web service on Render.
        params:
          name (str, required)
          repo (str, required): GitHub repo URL
          type (str, optional: web_service|background_worker|cron_job, default: web_service)
          branch (str, optional, default: main)
          runtime (str, optional: python|node|docker|go|rust)
          region (str, optional: oregon|frankfurt|ohio|singapore)
          plan (str, optional: free|starter|standard|pro)
          build_command (str, optional)
          start_command (str, optional)
          env_vars (dict, optional): key-value pairs for environment
        """
        name = params.get("name", "")
        repo = params.get("repo", "")
        if not name or not repo:
            return "Error: 'name' and 'repo' are required"

        body = {
            "name": name,
            "repo": repo,
            "type": params.get("type", "web_service"),
            "autoDeploy": "yes",
            "branch": params.get("branch", "main"),
            "region": params.get("region", "oregon"),
            "plan": params.get("plan", "free"),
        }
        sd = {}
        if params.get("runtime"):
            sd["runtime"] = params["runtime"]
        if params.get("build_command"):
            sd["buildCommand"] = params["build_command"]
        if params.get("start_command"):
            sd["startCommand"] = params["start_command"]
        if sd:
            body["serviceDetails"] = sd

        envs = params.get("env_vars", {})
        if envs:
            body["envVars"] = [{"key": k, "value": v} for k, v in envs.items()]

        result = _render("POST", "/services", body)
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        s = result.get("service", result)
        return json.dumps({
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "url": s.get("serviceDetails", {}).get("url", ""),
            "status": "created",
        })

    @mcp.tool(name="render_deploy", annotations={"title": "Trigger Render deploy", "destructiveHint": False})
    async def render_deploy(params: dict) -> str:
        """
        Trigger a manual deploy for a service.
        params: service_id (str, required), clear_cache (bool, optional)
        """
        sid = params.get("service_id", "")
        if not sid:
            return "Error: 'service_id' is required"
        body = {}
        if params.get("clear_cache"):
            body["clearCache"] = "clear"
        result = _render("POST", f"/services/{sid}/deploys", body)
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        d = result.get("deploy", result)
        return json.dumps({
            "deploy_id": d.get("id", ""),
            "status": d.get("status", ""),
            "commit": d.get("commit", {}).get("message", ""),
        })

    @mcp.tool(name="render_list_deploys", annotations={"title": "List Render deploys", "destructiveHint": False})
    async def render_list_deploys(params: dict) -> str:
        """
        List recent deploys for a service.
        params: service_id (str, required), limit (int, optional)
        """
        sid = params.get("service_id", "")
        if not sid:
            return "Error: 'service_id' is required"
        limit = params.get("limit", 10)
        result = _render("GET", f"/services/{sid}/deploys?limit={limit}")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        deploys = result if isinstance(result, list) else []
        summary = []
        for item in deploys:
            d = item.get("deploy", item)
            summary.append({
                "id": d.get("id", ""),
                "status": d.get("status", ""),
                "created": d.get("createdAt", ""),
                "commit": d.get("commit", {}).get("message", "")[:60],
            })
        return json.dumps({"count": len(summary), "deploys": summary})

    @mcp.tool(name="render_env_set", annotations={"title": "Set Render env var", "destructiveHint": True})
    async def render_env_set(params: dict) -> str:
        """
        Set environment variables for a Render service.
        params: service_id (str, required), env_vars (dict, required): key-value pairs
        """
        sid = params.get("service_id", "")
        envs = params.get("env_vars", {})
        if not sid or not envs:
            return "Error: 'service_id' and 'env_vars' are required"
        body = [{"key": k, "value": v} for k, v in envs.items()]
        result = _render("PUT", f"/services/{sid}/env-vars", body)
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        return json.dumps({"status": "updated", "count": len(envs)})

    @mcp.tool(name="render_service_action", annotations={"title": "Control Render service", "destructiveHint": True})
    async def render_service_action(params: dict) -> str:
        """
        Suspend, resume, or delete a Render service.
        params: service_id (str, required), action (str, required: suspend|resume|delete)
        """
        sid = params.get("service_id", "")
        action = params.get("action", "")
        if not sid or action not in ("suspend", "resume", "delete"):
            return "Error: 'service_id' and 'action' (suspend|resume|delete) required"
        if action == "delete":
            result = _render("DELETE", f"/services/{sid}")
        elif action == "suspend":
            result = _render("POST", f"/services/{sid}/suspend")
        else:
            result = _render("POST", f"/services/{sid}/resume")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        return json.dumps({"status": action + "d", "service_id": sid})

    @mcp.tool(name="render_list_databases", annotations={"title": "List Render databases", "destructiveHint": False})
    async def render_list_databases(params: dict) -> str:
        """
        List PostgreSQL databases on Render.
        params: limit (int, optional)
        """
        limit = params.get("limit", 20)
        result = _render("GET", f"/postgres?limit={limit}")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        dbs = result if isinstance(result, list) else []
        summary = []
        for item in dbs:
            db = item.get("postgres", item)
            summary.append({
                "id": db.get("id", ""),
                "name": db.get("name", ""),
                "status": db.get("status", ""),
                "region": db.get("region", ""),
                "plan": db.get("plan", ""),
                "version": db.get("version", ""),
            })
        return json.dumps({"count": len(summary), "databases": summary})
