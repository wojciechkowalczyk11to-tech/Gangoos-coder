"""
Fly.io Tool — manage Fly Machines (apps, VMs, volumes, secrets).
Uses Fly Machines API v1 (api.machines.dev).
"""
import os, json, urllib.request
from mcp.server.fastmcp import FastMCP

FLY_TOKEN = os.getenv("FLY_API_TOKEN", "")
FLY_BASE = "https://api.machines.dev/v1"


def _fly(method, path, body=None):
    if not FLY_TOKEN:
        return {"error": "FLY_API_TOKEN not set"}
    headers = {"Authorization": FLY_TOKEN, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(f"{FLY_BASE}{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {"status": "ok"}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def register(mcp: FastMCP):
    @mcp.tool(name="fly_list_apps", annotations={"title": "List Fly.io apps", "destructiveHint": False})
    async def fly_list_apps(params: dict) -> str:
        """
        List all apps on Fly.io account.
        params: org_slug (str, optional, default: personal)
        """
        org = params.get("org_slug", "personal")
        result = _fly("GET", f"/apps?org_slug={org}")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        apps = result.get("apps", []) if isinstance(result, dict) else result
        summary = []
        for a in (apps if isinstance(apps, list) else []):
            summary.append({
                "name": a.get("name", ""),
                "status": a.get("status", ""),
                "org": a.get("organization", {}).get("slug", ""),
                "network": a.get("network", ""),
            })
        return json.dumps({"count": result.get("total_apps", len(summary)), "apps": summary})

    @mcp.tool(name="fly_create_app", annotations={"title": "Create Fly.io app", "destructiveHint": True})
    async def fly_create_app(params: dict) -> str:
        """
        Create a new Fly.io app.
        params: app_name (str, required), org_slug (str, optional, default: personal)
        """
        name = params.get("app_name", "")
        if not name:
            return "Error: 'app_name' is required"
        body = {
            "app_name": name,
            "org_slug": params.get("org_slug", "personal"),
        }
        result = _fly("POST", "/apps", body)
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        return json.dumps({"status": "created", "app": name})

    @mcp.tool(name="fly_list_machines", annotations={"title": "List Fly.io machines", "destructiveHint": False})
    async def fly_list_machines(params: dict) -> str:
        """
        List all machines (VMs) for a Fly app.
        params: app_name (str, required)
        """
        app = params.get("app_name", "")
        if not app:
            return "Error: 'app_name' is required"
        result = _fly("GET", f"/apps/{app}/machines")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        machines = result if isinstance(result, list) else []
        summary = []
        for m in machines:
            summary.append({
                "id": m.get("id", ""),
                "name": m.get("name", ""),
                "state": m.get("state", ""),
                "region": m.get("region", ""),
                "image": m.get("config", {}).get("image", ""),
                "cpu_kind": m.get("config", {}).get("guest", {}).get("cpu_kind", ""),
                "cpus": m.get("config", {}).get("guest", {}).get("cpus", 0),
                "memory_mb": m.get("config", {}).get("guest", {}).get("memory_mb", 0),
            })
        return json.dumps({"count": len(summary), "machines": summary})

    @mcp.tool(name="fly_create_machine", annotations={"title": "Create Fly.io machine", "destructiveHint": True})
    async def fly_create_machine(params: dict) -> str:
        """
        Create a new machine (VM) in a Fly app.
        params:
          app_name (str, required)
          image (str, required): Docker image
          name (str, optional)
          region (str, optional: ams|cdg|fra|iad|lax|lhr|nrt|ord|sjc|sin|syd)
          cpus (int, optional, default 1)
          memory_mb (int, optional, default 256)
          env (dict, optional): environment variables
          cmd (list, optional): command override
        """
        app = params.get("app_name", "")
        image = params.get("image", "")
        if not app or not image:
            return "Error: 'app_name' and 'image' are required"
        config = {
            "image": image,
            "guest": {
                "cpu_kind": "shared",
                "cpus": int(params.get("cpus", 1)),
                "memory_mb": int(params.get("memory_mb", 256)),
            },
        }
        if params.get("env"):
            config["env"] = params["env"]
        if params.get("cmd"):
            config["cmd"] = params["cmd"]
        body = {"config": config}
        if params.get("name"):
            body["name"] = params["name"]
        if params.get("region"):
            body["region"] = params["region"]
        result = _fly("POST", f"/apps/{app}/machines", body)
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        return json.dumps({
            "id": result.get("id", ""),
            "name": result.get("name", ""),
            "state": result.get("state", ""),
            "region": result.get("region", ""),
        })

    @mcp.tool(name="fly_machine_action", annotations={"title": "Control Fly.io machine", "destructiveHint": True})
    async def fly_machine_action(params: dict) -> str:
        """
        Start, stop, or destroy a Fly machine.
        params: app_name (str, required), machine_id (str, required),
                action (str, required: start|stop|destroy)
        """
        app = params.get("app_name", "")
        mid = params.get("machine_id", "")
        action = params.get("action", "")
        if not app or not mid or action not in ("start", "stop", "destroy"):
            return "Error: app_name, machine_id, action (start|stop|destroy) required"
        if action == "destroy":
            result = _fly("DELETE", f"/apps/{app}/machines/{mid}?force=true")
        else:
            result = _fly("POST", f"/apps/{app}/machines/{mid}/{action}")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        return json.dumps({"status": f"{action}ed", "machine_id": mid})

    @mcp.tool(name="fly_list_volumes", annotations={"title": "List Fly.io volumes", "destructiveHint": False})
    async def fly_list_volumes(params: dict) -> str:
        """
        List persistent volumes for a Fly app.
        params: app_name (str, required)
        """
        app = params.get("app_name", "")
        if not app:
            return "Error: 'app_name' is required"
        result = _fly("GET", f"/apps/{app}/volumes")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        vols = result if isinstance(result, list) else []
        summary = []
        for v in vols:
            summary.append({
                "id": v.get("id", ""),
                "name": v.get("name", ""),
                "size_gb": v.get("size_gb", 0),
                "region": v.get("region", ""),
                "state": v.get("state", ""),
                "attached_machine": v.get("attached_machine_id", ""),
            })
        return json.dumps({"count": len(summary), "volumes": summary})

    @mcp.tool(name="fly_app_delete", annotations={"title": "Delete Fly.io app", "destructiveHint": True})
    async def fly_app_delete(params: dict) -> str:
        """
        Delete a Fly.io app and all its machines.
        params: app_name (str, required)
        """
        app = params.get("app_name", "")
        if not app:
            return "Error: 'app_name' is required"
        result = _fly("DELETE", f"/apps/{app}")
        if isinstance(result, dict) and "error" in result:
            return json.dumps(result)
        return json.dumps({"status": "deleted", "app": app})
