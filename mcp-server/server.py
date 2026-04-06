#!/usr/bin/env python3
"""
NEXUS MCP Server — Unified AI Infrastructure Control Plane

Endpoints:
  /mcp          → MCP Streamable HTTP (Claude.ai, Cursor, Claude CLI, etc.)
  /api/v1/*     → REST Gateway (ChatGPT Actions, curl, Gemini)
  /api/v1/stats → Usage statistics (JSON)
  /openapi.json → OpenAPI 3.1 spec
  /health       → Health check
  /docs         → Swagger UI
"""

# ── Load .env FIRST — before any module import reads os.environ ──────────────
from dotenv import load_dotenv
load_dotenv(override=True)  # override empty Docker env vars with .env values
# ───────────────────────────────────────────────────────────────────────────────

import os
import sys
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("nexus-mcp")


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    import httpx
    clients = {
        "gcp": httpx.AsyncClient(base_url="https://compute.googleapis.com", timeout=60.0),
        "cloudflare": httpx.AsyncClient(
            base_url="https://api.cloudflare.com/client/v4",
            headers={"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}"},
            timeout=30.0,
        ),
        "github": httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        ),
        "vercel": httpx.AsyncClient(
            base_url="https://api.vercel.com",
            headers={"Authorization": f"Bearer {settings.VERCEL_TOKEN}"},
            timeout=30.0,
        ),
        "general": httpx.AsyncClient(timeout=120.0),
    }
    log.info("NEXUS MCP Server starting")
    yield {"clients": clients, "settings": settings}
    for c in clients.values():
        await c.aclose()
    log.info("NEXUS MCP Server shutting down")


allowed_hosts = [
    h.strip()
    for h in os.getenv(
        "MCP_ALLOWED_HOSTS",
        "localhost,localhost:8080,127.0.0.1,127.0.0.1:8080,mcp-server,gangus-agent",
    ).split(",")
    if h.strip()
]

mcp = FastMCP(
    "nexus_mcp",
    lifespan=server_lifespan,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    ),
)

# ── Core modules ──────────────────────────────────────────────────────────────
from modules.ai_proxy import register as register_ai
from modules.ai_sdk_tools import register as register_ai_sdk
from modules.gcp import register as register_gcp
from modules.cloudflare import register as register_cloudflare
from modules.github import register as register_github
from modules.vercel import register as register_vercel
from modules.gdrive import register as register_gdrive
from modules.shell import register as register_shell
from modules.manus_tool import register as register_manus
from modules.xai_collections import register as register_xai_collections
from modules.knowledge_engine import register as register_knowledge

register_ai(mcp)
register_ai_sdk(mcp)
register_gcp(mcp)
register_cloudflare(mcp)
register_github(mcp)
register_vercel(mcp)
register_gdrive(mcp)
register_shell(mcp)
register_manus(mcp)
register_xai_collections(mcp)
register_knowledge(mcp)

# ── Restored modules (were in v1) ─────────────────────────────────────────────
from modules.aws_extended import register as register_aws
from modules.database import register as register_database
from modules.files_advanced import register as register_files
from modules.http_client import register as register_http
from modules.ml_ops import register as register_ml
from modules.multi_cloud import register as register_multi_cloud
from modules.notifications import register as register_notifications
from modules.python_repl import register as register_python

register_aws(mcp)
register_database(mcp)
register_files(mcp)
register_http(mcp)
register_ml(mcp)
register_multi_cloud(mcp)
register_notifications(mcp)
register_python(mcp)

# ── Code verification (DeepSeek) ──────────────────────────────────────────────
try:
    from modules.code_verify_tool import register as register_code_verify
    register_code_verify(mcp)
    log.info("Code verification module loaded")
except Exception as e:
    log.info(f"Code verification module skipped: {e}")

# Jules AI (Google coding agent)
try:
    from modules.jules_tool import register as register_jules
    register_jules(mcp)
    log.info("Jules module loaded")
except Exception as e:
    log.info(f"Jules module skipped: {e}")

# VirusTotal (malware/threat scanning)
try:
    from modules.virustotal_tool import register as register_vt
    register_vt(mcp)
    log.info("VirusTotal module loaded")
except Exception as e:
    log.info(f"VirusTotal module skipped: {e}")

# Render.com (web services, databases)
try:
    from modules.render_tool import register as register_render
    register_render(mcp)
    log.info("Render module loaded")
except Exception as e:
    log.info(f"Render module skipped: {e}")

# Fly.io (Machines, apps, volumes)
try:
    from modules.flyio_tool import register as register_fly
    register_fly(mcp)
    log.info("Fly.io module loaded")
except Exception as e:
    log.info(f"Fly.io module skipped: {e}")

# ── New modules (v2 update) ───────────────────────────────────────────────────
from modules.quota import register as register_quota
register_quota(mcp)

# Browser: optional — only if playwright installed
try:
    from modules.browser import register as register_browser
    register_browser(mcp)
    log.info("Browser module loaded (playwright available)")
except ImportError:
    log.info("Browser module skipped (playwright not installed)")

# RunPod suite: optional — only if API key set
if os.getenv("RUNPOD_API_KEY"):
    from modules.runpod_suite import register as register_runpod
    register_runpod(mcp)
    log.info("RunPod suite loaded")
else:
    log.info("RunPod suite skipped (RUNPOD_API_KEY not set)")

# ── mojo_exec — CodeAct contract tool ────────────────────────────────────────
from modules.mojo_exec import register as register_mojo_exec
register_mojo_exec(mcp)
log.info("mojo_exec registered (backend=%s)", os.getenv("MOJO_EXEC_BACKEND", "disabled"))

# ── E1-E4 Enhancements ───────────────────────────────────────────────────────
try:
    from modules.plan_verifier import register as register_plan_verifier
    register_plan_verifier(mcp)
    log.info("E1: plan verifier loaded")
except Exception as e:
    log.info(f"E1: plan verifier skipped: {e}")

try:
    from modules.streaming import register as register_streaming
    register_streaming(mcp)
    log.info("E2: streaming loaded")
except Exception as e:
    log.info(f"E2: streaming skipped: {e}")

try:
    from modules.session_store import register as register_session_store
    register_session_store(mcp)
    log.info("E3: session store loaded")
except Exception as e:
    log.info(f"E3: session store skipped: {e}")

try:
    from modules.dataset_filter import register as register_dataset_filter
    register_dataset_filter(mcp)
    log.info("E4: dataset filter loaded")
except Exception as e:
    log.info(f"E4: dataset filter skipped: {e}")

log.info("All modules registered")


def build_combined_app():
    from rest_gateway import create_rest_app, discover_tools_from_mcp
    from asgi_router import PathRouter
    rest_app = create_rest_app()
    discover_tools_from_mcp(mcp)

    # ── Stats endpoint (lightweight observability) ────────
    from modules.quota import get_stats_snapshot
    from fastapi.responses import JSONResponse

    @rest_app.get("/api/v1/stats", tags=["monitoring"])
    async def stats_endpoint():
        """Tool usage statistics — lightweight observability."""
        return JSONResponse(get_stats_snapshot())

    log.info(f"REST gateway: {len(rest_app.routes)} routes")
    mcp_asgi = mcp.streamable_http_app()
    return PathRouter(mcp_asgi, rest_app)


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="NEXUS MCP + REST Server")
    parser.add_argument("--transport", choices=["http", "stdio", "rest-only"], default="http")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "http":
        log.info(
            f"Starting NEXUS on {args.host}:{args.port}\n"
            f"  MCP:   http://{args.host}:{args.port}/mcp\n"
            f"  REST:  http://{args.host}:{args.port}/api/v1/tools\n"
            f"  Stats: http://{args.host}:{args.port}/api/v1/stats\n"
            f"  Docs:  http://{args.host}:{args.port}/docs"
        )
        app = build_combined_app()
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.transport == "rest-only":
        from rest_gateway import create_rest_app, discover_tools_from_mcp
        rest_app = create_rest_app()
        discover_tools_from_mcp(mcp)
        uvicorn.run(rest_app, host=args.host, port=args.port)

    else:
        log.info("Starting NEXUS MCP (stdio)")
        mcp.run(transport="stdio")
