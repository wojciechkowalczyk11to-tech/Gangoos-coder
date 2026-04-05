"""
Jules AI Tool — Google's async coding agent.
Supports 2 API keys with rotation. Creates sessions, sends tasks to GitHub repos.
Jules can: fix bugs, implement features, review code, refactor, write tests.
"""
import os, json, urllib.request, threading
from mcp.server.fastmcp import FastMCP

JULES_BASE = "https://jules.googleapis.com/v1alpha"

_keys = []
for i in range(1, 3):
    k = os.getenv(f"JULES_KEY_{i}", "")
    if k:
        _keys.append({"key": k, "label": f"jules_key_{i}", "fails": 0})

_key_idx = 0
_lock = threading.Lock()


def _next_key():
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


def _jules_request(method, path, body=None, api_key_obj=None):
    if not api_key_obj:
        api_key_obj = _next_key()
    if not api_key_obj:
        return {"error": "No Jules API keys configured. Set JULES_KEY_1, JULES_KEY_2"}
    headers = {"X-Goog-Api-Key": api_key_obj["key"], "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(f"{JULES_BASE}{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read())
            api_key_obj["fails"] = 0
            return result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:500]
        if e.code in (401, 403, 429):
            api_key_obj["fails"] += 1
        return {"error": f"HTTP {e.code}: {err_body}", "key_used": api_key_obj["label"]}
    except Exception as e:
        api_key_obj["fails"] += 1
        return {"error": str(e), "key_used": api_key_obj["label"]}


def register(mcp: FastMCP):
    @mcp.tool(name="jules_create_session", annotations={"title": "Create Jules coding session", "destructiveHint": False})
    async def jules_create_session(params: dict) -> str:
        """
        Create a new Jules coding session on a GitHub repo.
        Jules will analyze the repo and create a plan, then optionally auto-create a PR.

        params:
          prompt (str, required): Task description (e.g. "Fix the login bug in auth.py")
          repo (str, required): GitHub repo as "owner/repo"
          branch (str, optional): Starting branch (default: "main")
          title (str, optional): Session title
          auto_pr (bool, optional): Auto-create PR when done (default: true)
          key_index (int, optional): Force specific key (1 or 2)
        """
        prompt = params.get("prompt", "")
        repo = params.get("repo", "")
        if not prompt:
            return "Error: 'prompt' is required"
        if not repo:
            return "Error: 'repo' is required (format: owner/repo)"

        parts = repo.split("/")
        if len(parts) != 2:
            return "Error: repo must be 'owner/repo' format"

        branch = params.get("branch", "main")
        title = params.get("title", prompt[:60])
        auto_pr = params.get("auto_pr", True)

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        body = {
            "prompt": prompt,
            "sourceContext": {
                "source": f"sources/github/{parts[0]}/{parts[1]}",
                "githubRepoContext": {
                    "startingBranch": branch
                }
            },
            "title": title
        }
        if auto_pr:
            body["automationMode"] = "AUTO_CREATE_PR"

        result = _jules_request("POST", "/sessions", body, forced_key)
        if "error" in result:
            return json.dumps(result)

        session_name = result.get("name", "")
        return json.dumps({
            "session": session_name,
            "status": result.get("state", "unknown"),
            "title": title,
            "repo": repo,
            "url": f"https://jules.google.com/session/{session_name.split('/')[-1]}",
            "hint": "Use jules_session_status to check progress, jules_approve_plan to approve"
        })

    @mcp.tool(name="jules_session_status", annotations={"title": "Check Jules session status", "destructiveHint": False})
    async def jules_session_status(params: dict) -> str:
        """
        Get status of a Jules session.
        params: session (str, required - full name like "sessions/xxx"), key_index (int, optional)
        """
        session = params.get("session", "")
        if not session:
            return "Error: 'session' name is required"
        if not session.startswith("sessions/"):
            session = f"sessions/{session}"

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _jules_request("GET", f"/{session}", api_key_obj=forced_key)
        if "error" in result:
            return json.dumps(result)

        return json.dumps({
            "session": result.get("name", ""),
            "state": result.get("state", "unknown"),
            "title": result.get("title", ""),
            "created": result.get("createTime", ""),
            "plan_state": result.get("planState", ""),
        })

    @mcp.tool(name="jules_approve_plan", annotations={"title": "Approve Jules plan", "destructiveHint": False})
    async def jules_approve_plan(params: dict) -> str:
        """
        Approve a Jules session plan so it can start coding.
        params: session (str, required), key_index (int, optional)
        """
        session = params.get("session", "")
        if not session:
            return "Error: 'session' name is required"
        if not session.startswith("sessions/"):
            session = f"sessions/{session}"

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _jules_request("POST", f"/{session}:approvePlan", {}, forced_key)
        if "error" in result:
            return json.dumps(result)
        return json.dumps({"status": "plan_approved", "session": session})

    @mcp.tool(name="jules_send_message", annotations={"title": "Send message to Jules session", "destructiveHint": False})
    async def jules_send_message(params: dict) -> str:
        """
        Send a follow-up message to an active Jules session.
        params: session (str, required), message (str, required), key_index (int, optional)
        """
        session = params.get("session", "")
        message = params.get("message", "")
        if not session or not message:
            return "Error: 'session' and 'message' are required"
        if not session.startswith("sessions/"):
            session = f"sessions/{session}"

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _jules_request("POST", f"/{session}:sendMessage", {"message": message}, forced_key)
        if "error" in result:
            return json.dumps(result)
        return json.dumps({"status": "message_sent", "session": session})

    @mcp.tool(name="jules_list_sessions", annotations={"title": "List Jules sessions", "destructiveHint": False})
    async def jules_list_sessions(params: dict) -> str:
        """
        List all Jules sessions.
        params: key_index (int, optional), limit (int, optional)
        """
        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _jules_request("GET", "/sessions", api_key_obj=forced_key)
        if "error" in result:
            return json.dumps(result)

        sessions = result.get("sessions", [])
        limit = int(params.get("limit", 20))
        summary = []
        for s in sessions[:limit]:
            summary.append({
                "name": s.get("name", ""),
                "state": s.get("state", ""),
                "title": s.get("title", "")[:80],
                "created": s.get("createTime", ""),
            })
        return json.dumps({"count": len(sessions), "sessions": summary})

    @mcp.tool(name="jules_list_sources", annotations={"title": "List Jules GitHub sources", "destructiveHint": False})
    async def jules_list_sources(params: dict) -> str:
        """
        List all GitHub repos connected to Jules.
        params: key_index (int, optional)
        """
        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _jules_request("GET", "/sources", api_key_obj=forced_key)
        if "error" in result:
            return json.dumps(result)

        sources = result.get("sources", [])
        summary = []
        for s in sources:
            gh = s.get("githubRepo", {})
            summary.append({
                "name": s.get("name", ""),
                "repo": f"{gh.get('owner','')}/{gh.get('repo','')}",
                "private": gh.get("isPrivate", False),
                "default_branch": gh.get("defaultBranch", {}).get("displayName", "main"),
            })
        return json.dumps({"count": len(sources), "sources": summary})

    @mcp.tool(name="jules_list_activities", annotations={"title": "List Jules session activities", "destructiveHint": False})
    async def jules_list_activities(params: dict) -> str:
        """
        List activities (steps/events) in a Jules session.
        params: session (str, required), key_index (int, optional)
        """
        session = params.get("session", "")
        if not session:
            return "Error: 'session' is required"
        if not session.startswith("sessions/"):
            session = f"sessions/{session}"

        forced_key = None
        ki = params.get("key_index")
        if ki and 1 <= int(ki) <= len(_keys):
            forced_key = _keys[int(ki) - 1]

        result = _jules_request("GET", f"/{session}/activities", api_key_obj=forced_key)
        if "error" in result:
            return json.dumps(result)

        activities = result.get("activities", [])
        summary = []
        for a in activities:
            summary.append({
                "name": a.get("name", ""),
                "type": a.get("type", ""),
                "state": a.get("state", ""),
            })
        return json.dumps({"count": len(activities), "activities": summary})
