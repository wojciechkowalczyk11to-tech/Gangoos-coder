#!/usr/bin/env python3
"""
Gangoos MCP Server — ARMORED v2 entrypoint.

Unified AI infrastructure with category-based access control,
TOTP authentication gates, and full audit chain.

Categories:
  CAT-1: LLM Workers (9 connectors)
  CAT-2: Control Shell (TOTP required, 5min TTL)
  CAT-3: Docs & Knowledge
  CAT-4: Research (web scraping, AI search)
  CAT-5: Media (reserved)
  CAT-6: Security Tools (TOTP required, 5min TTL)
  CAT-7: Cloud (TOTP required, DO/RunPod/CF/Render)
"""

from dotenv import load_dotenv
load_dotenv(override=True)

import os
import sys
import logging
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from categories import Category, CategoryRegistry, UnlockManager
from security.totp_gate import CategoryTOTP
from audit import build_audit_logger
from auth import validate_bearer_header
from rate_limiter import RateLimiter
from middleware.category_guard import CategoryGuard
from middleware.auth_chain import AuthChain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("gangoos-mcp")

# Singletons — zainicjowane poniżej
cat_registry = CategoryRegistry()
audit_logger = build_audit_logger()
rate_limiter = RateLimiter({
    "cat1_llm": int(os.getenv("RATE_LIMIT_LLM", "30")),
    "cat2_control": int(os.getenv("RATE_LIMIT_CONTROL", "10")),
    "cat3_docs": int(os.getenv("RATE_LIMIT_KNOWLEDGE", "120")),
    "cat4_research": int(os.getenv("RATE_LIMIT_RESEARCH", "60")),
    "cat7_cloud": int(os.getenv("RATE_LIMIT_CLOUD", "20")),
    "default": 30,
})

# TOTP gate — opcjonalny (gdy nie ma klucza, kategorie TOTP są zablokowane)
totp_gate: Optional[CategoryTOTP] = None
try:
    totp_gate = CategoryTOTP()
    log.info("TOTP gate initialized")
except ValueError as e:
    log.warning("TOTP gate disabled: %s", e)


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Lifecycle: init registries, yield context, cleanup."""
    import httpx

    clients = {
        "general": httpx.AsyncClient(timeout=120.0),
    }

    log.info("Gangoos MCP ARMORED v2 starting")
    log.info("Categories registered: %d tools", len(cat_registry.list_tools()))

    yield {
        "clients": clients,
        "cat_registry": cat_registry,
        "audit_logger": audit_logger,
        "rate_limiter": rate_limiter,
        "totp_gate": totp_gate,
    }

    for c in clients.values():
        await c.aclose()
    log.info("Gangoos MCP ARMORED v2 shutting down")


allowed_hosts = [
    h.strip()
    for h in os.getenv(
        "MCP_ALLOWED_HOSTS",
        "localhost,localhost:8080,127.0.0.1,127.0.0.1:8080,mcp-server,gangus-agent",
    ).split(",")
    if h.strip()
]

mcp = FastMCP(
    "gangoos_mcp_armored",
    lifespan=server_lifespan,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    ),
)

# ── Mount categories ──────────────────────────────────────────────────────────

from categories.llm_workers import register_llm_tools
from categories.control_shell import register_control_tools
from categories.research import register_research_tools
from categories.cloud import register_cloud_tools

register_llm_tools(mcp, cat_registry)
register_control_tools(mcp, cat_registry)
register_research_tools(mcp, cat_registry)
register_cloud_tools(mcp, cat_registry)

log.info("Mounted %d tools across %d categories",
         len(cat_registry.list_tools()),
         len(cat_registry.list_categories()))

# ── TOTP unlock/status tools ─────────────────────────────────────────────────

from pydantic import BaseModel, Field


class CategoryUnlockInput(BaseModel):
    category: str = Field(..., description="Category ID (e.g. cat2_control, cat7_cloud)")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class CategoryStatusInput(BaseModel):
    category: Optional[str] = Field(None, description="Category ID or None for all")


@mcp.tool(name="category_unlock", annotations={"title": "Unlock Category", "readOnlyHint": False})
async def category_unlock_tool(params: CategoryUnlockInput) -> dict:
    """Unlock a tool category with TOTP code (required for CAT-2, CAT-6, CAT-7)."""
    if totp_gate is None:
        return {"error": "TOTP gate not configured. Set TOTP_SECRET_BASE env var."}
    return totp_gate.unlock(params.category, params.code)


@mcp.tool(name="category_status", annotations={"title": "Category Status", "readOnlyHint": True})
async def category_status_tool(params: CategoryStatusInput) -> dict:
    """Check unlock status for tool categories."""
    if totp_gate is None:
        return {"error": "TOTP gate not configured", "all_locked": True}
    if params.category:
        return totp_gate.get_status(params.category)
    return {
        "categories": totp_gate.get_all_status(),
        "registry": cat_registry.list_categories(),
    }


class CategoryRevokeInput(BaseModel):
    category: Optional[str] = Field(None, description="Category to revoke, or None for all")


@mcp.tool(name="category_revoke", annotations={"title": "Revoke Category", "readOnlyHint": False})
async def category_revoke_tool(params: CategoryRevokeInput) -> dict:
    """Revoke unlock for a category (or all categories)."""
    if totp_gate is None:
        return {"error": "TOTP gate not configured"}
    if params.category:
        return totp_gate.revoke(params.category)
    return totp_gate.revoke_all()


# ── Legacy modules (from v1 server.py) ───────────────────────────────────────

from modules.ai_proxy import register as register_ai
from modules.ai_sdk_tools import register as register_ai_sdk
from modules.shell import register as register_shell
from modules.knowledge_engine import register as register_knowledge

register_ai(mcp)
register_ai_sdk(mcp)
register_shell(mcp)
register_knowledge(mcp)

# Opcjonalne moduły — ładuj bez krytycznych błędów
_optional_modules = [
    ("modules.gcp", "GCP"),
    ("modules.cloudflare", "Cloudflare (legacy)"),
    ("modules.github", "GitHub"),
    ("modules.vercel", "Vercel"),
    ("modules.gdrive", "Google Drive"),
    ("modules.manus_tool", "Manus (legacy)"),
    ("modules.xai_collections", "xAI Collections"),
    ("modules.aws_extended", "AWS"),
    ("modules.database", "Database"),
    ("modules.files_advanced", "Files Advanced"),
    ("modules.http_client", "HTTP Client"),
    ("modules.ml_ops", "ML Ops"),
    ("modules.multi_cloud", "Multi Cloud"),
    ("modules.notifications", "Notifications"),
    ("modules.python_repl", "Python REPL"),
    ("modules.code_verify_tool", "Code Verify"),
    ("modules.jules_tool", "Jules"),
    ("modules.virustotal_tool", "VirusTotal"),
    ("modules.render_tool", "Render (legacy)"),
    ("modules.flyio_tool", "Fly.io"),
    ("modules.quota", "Quota"),
    ("modules.browser", "Browser"),
    ("modules.runpod_suite", "RunPod (legacy)"),
    ("modules.mojo_exec", "Mojo Exec"),
    ("modules.plan_verifier", "Plan Verifier"),
    ("modules.streaming", "Streaming"),
    ("modules.session_store", "Session Store"),
    ("modules.dataset_filter", "Dataset Filter"),
]

for module_path, label in _optional_modules:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        if hasattr(mod, "register"):
            mod.register(mcp)
            log.info("Loaded: %s", label)
    except Exception as e:
        log.debug("Skipped %s: %s", label, e)


# ── REST + Combined app ──────────────────────────────────────────────────────

def build_combined_app():
    """Build combined ASGI app: MCP + REST gateway."""
    from rest_gateway import create_rest_app, discover_tools_from_mcp
    from asgi_router import PathRouter

    rest_app = create_rest_app()
    discover_tools_from_mcp(mcp)

    from modules.quota import get_stats_snapshot
    from fastapi.responses import JSONResponse

    @rest_app.get("/api/v1/stats", tags=["monitoring"])
    async def stats_endpoint():
        return JSONResponse(get_stats_snapshot())

    @rest_app.get("/api/v1/categories", tags=["categories"])
    async def categories_endpoint():
        return JSONResponse({
            "categories": cat_registry.list_categories(),
            "tools": cat_registry.as_serializable(),
        })

    mcp_asgi = mcp.streamable_http_app()
    return PathRouter(mcp_asgi, rest_app)


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Gangoos MCP ARMORED v2")
    parser.add_argument("--transport", choices=["http", "stdio", "rest-only"], default="http")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "http":
        log.info(
            f"Starting Gangoos MCP ARMORED v2 on {args.host}:{args.port}\n"
            f"  MCP:        http://{args.host}:{args.port}/mcp\n"
            f"  REST:       http://{args.host}:{args.port}/api/v1/tools\n"
            f"  Categories: http://{args.host}:{args.port}/api/v1/categories\n"
            f"  Docs:       http://{args.host}:{args.port}/docs"
        )
        app = build_combined_app()
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.transport == "rest-only":
        from rest_gateway import create_rest_app, discover_tools_from_mcp
        rest_app = create_rest_app()
        discover_tools_from_mcp(mcp)
        uvicorn.run(rest_app, host=args.host, port=args.port)

    else:
        log.info("Starting Gangoos MCP ARMORED v2 (stdio)")
        mcp.run(transport="stdio")
