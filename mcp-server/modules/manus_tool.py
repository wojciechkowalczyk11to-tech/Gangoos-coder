"""
Manus AI Tool — delegate complex browser/research tasks to Manus.
Supports 6 API keys with round-robin rotation (300 credits/day each).
Use when: frontend building, web scraping, multi-step research, form filling.
"""
import os, json, urllib.request, threading, time
from mcp.server.fastmcp import FastMCP

MANUS_BASE = "https://api.manus.ai/v1"

# Load all keys: MANUS_KEY_1..MANUS_KEY_6_PRO + legacy MANUS_API_KEY
_keys = []
for i in range(1, 7):
    suffix = f"_{i}_PRO" if i == 6 else f"_{i}"
    k = os.getenv(f"MANUS_KEY{suffix}", "")
    if k:
        _keys.append({"key": k, "label": f"key{i}" + (" (Pro)" if i == 6 else " (Lite)"), "fails": 0})
legacy = os.getenv("MANUS_API_KEY", "")
if legacy and not any(m["key"] == legacy for m in _keys):
    _keys.append({"key": legacy, "label": "legacy", "fails": 0})

_key_idx = 0
_lock = threading.Lock()


def _next_key():
    """Round-robin key selection, skip keys with recent failures."""
    global _key_idx
    if not _keys:
        return None
    with _lock:
        for _ in range(len(_keys)):
            k = _keys[_key_idx % len(_keys)]
            _key_idx += 1
            if k["fails"] < 3:
                return k
    return _keys[0]


def _manus_request(method, path, body=None, api_key_obj=None):
    """Make authenticated request to Manus API."""
    if not api_key_obj:
        api_key_obj = _next_key()
    if not api_key_obj:
        return {"error": "No Manus API keys configured. Set MANUS_KEY_1..MANUS_KEY_6_PRO in .env"}
    headers = {"API_KEY": api_key_obj["key"], "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(f"{MANUS_BASE}{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=300) as r:
            result = json.loads(r.read())
            api_key_obj["fails"] = 0
            return result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:300]
        if e.code in (401, 403, 429):
            api_key_obj["fails"] += 1
        return {"error": f"HTTP {e.code}: {err_body}", "key_used": api_key_obj["label"]}
    except Exception as e:
        api_key_obj["fails"] += 1
        return {"error": str(e), "key_used": api_key_obj["label"]}


def register(mcp: FastMCP):
    @mcp.tool(name="manus_delegate", annotations={"title": "Delegate task to Manus AI", "destructiveHint": False})
    async def manus_delegate(params: dict) -> str:
        """
        Delegate a complex task to Manus AI agent.
        Manus can: browse web, build websites, fill forms, automate workflows.
        Use for: frontend building, research, UI generation, web automation.

        params: task (str, required), key_index (int, optional 1-6 to force specific key)
        """
        task = params.get("task", "")
        if not task:
            return "Error: 'task' param is required"
        if not _keys:
            return "Error: No Manus API keys. Set MANUS_KEY_1..MANUS_KEY_6_PRO"

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _manus_request("POST", "/tasks", {"input": task}, forced_key)
        if "error" in result:
            return json.dumps(result)

        task_id = result.get("data", result).get("id", "unknown")
        status = result.get("data", result).get("status", "unknown")
        key_label = (forced_key or _next_key() or {}).get("label", "?")
        return json.dumps({
            "task_id": task_id,
            "status": status,
            "key_used": key_label,
            "url": f"https://manus.im/app/{task_id}",
            "hint": "Use manus_task_status to poll for completion"
        })

    @mcp.tool(name="manus_task_status", annotations={"title": "Check Manus task status", "destructiveHint": False})
    async def manus_task_status(params: dict) -> str:
        """
        Check status of a Manus task by ID.
        params: task_id (str, required), key_index (int, optional)
        """
        task_id = params.get("task_id", "")
        if not task_id:
            return "Error: 'task_id' param is required"

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _manus_request("GET", f"/tasks/{task_id}", api_key_obj=forced_key)
        if "error" in result:
            return json.dumps(result)

        data = result.get("data", result)
        outputs = data.get("output", [])
        last_output = ""
        for o in reversed(outputs):
            for c in o.get("content", []):
                if c.get("text"):
                    last_output = c["text"][:500]
                    break
            if last_output:
                break

        return json.dumps({
            "task_id": task_id,
            "status": data.get("status", "unknown"),
            "model": data.get("model", ""),
            "output_count": len(outputs),
            "last_output": last_output,
            "url": f"https://manus.im/app/{task_id}"
        })

    @mcp.tool(name="manus_list_tasks", annotations={"title": "List Manus tasks", "destructiveHint": False})
    async def manus_list_tasks(params: dict) -> str:
        """
        List all Manus tasks for a key.
        params: key_index (int, optional 1-6), limit (int, optional)
        """
        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _manus_request("GET", "/tasks", api_key_obj=forced_key)
        if "error" in result:
            return json.dumps(result)

        tasks = result.get("data", [])
        limit = int(params.get("limit", 20))
        summary = []
        for t in tasks[:limit]:
            summary.append({
                "id": t.get("id"),
                "status": t.get("status"),
                "title": t.get("metadata", {}).get("task_title", "")[:80],
                "model": t.get("model", ""),
                "outputs": len(t.get("output", []))
            })
        return json.dumps({"count": len(tasks), "tasks": summary})

    @mcp.tool(name="manus_keys_status", annotations={"title": "Show Manus API keys status", "destructiveHint": False})
    async def manus_keys_status(params: dict) -> str:
        """Show status of all configured Manus API keys (count, labels, fail counts)."""
        return json.dumps({
            "total_keys": len(_keys),
            "keys": [{"index": i+1, "label": k["label"], "fails": k["fails"],
                       "key_preview": k["key"][:8] + "..."} for i, k in enumerate(_keys)],
            "daily_budget": f"{len(_keys) * 300} credits ({len(_keys)} keys x 300)"
        })
