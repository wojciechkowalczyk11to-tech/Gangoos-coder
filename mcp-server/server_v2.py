#!/usr/bin/env python3
"""
NEXUS MCP Server v2 - Improved production-ready implementation.

Features:
  - Bearer token authentication
  - Rate limiting (sliding window, per-domain)
  - Comprehensive policy engine
  - Domain-based tool organization
  - Audit logging with redaction
  - Health & metrics endpoints
  - Control domain with safety guards
  - LLM fallback chain (Ollama → DeepSeek → GPT-4o-mini)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from audit import build_audit_logger
from auth import validate_bearer_header
from config import settings
from domains import register_all
from metrics import MetricsCollector
from policy import evaluate_tool_access
from rate_limiter import RateLimiter
from registry import ToolRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("nexus-v2")

# Global singletons
registry = ToolRegistry()
audit_logger = build_audit_logger()
metrics = MetricsCollector()
rate_limiter = RateLimiter(
    {
        "control": settings.RATE_LIMIT_CONTROL,
        "llm": settings.RATE_LIMIT_LLM,
        "research": settings.RATE_LIMIT_RESEARCH,
        "knowledge": settings.RATE_LIMIT_KNOWLEDGE,
        "default": 30,
    }
)


def _load_env() -> None:
    """Load environment variables from .env file."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=True)


def _allowed_hosts() -> list[str]:
    """Get allowed hosts for CORS."""
    raw = os.getenv(
        "MCP_ALLOWED_HOSTS",
        "localhost,127.0.0.1,localhost:8080,127.0.0.1:8080",
    )
    return [host.strip() for host in raw.split(",") if host.strip()]


def build_mcp_server():
    """Build FastMCP server with all tools registered."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    @asynccontextmanager
    async def server_lifespan(server: FastMCP):
        log.info("NEXUS MCP v2 starting")
        log.info("Rate limits: control=%d, llm=%d, research=%d, knowledge=%d",
                 settings.RATE_LIMIT_CONTROL,
                 settings.RATE_LIMIT_LLM,
                 settings.RATE_LIMIT_RESEARCH,
                 settings.RATE_LIMIT_KNOWLEDGE)

        # Report configuration issues
        for warning in settings.validate():
            log.warning("[CONFIG] %s", warning)

        yield {
            "registry": registry,
            "audit_logger": audit_logger,
            "metrics": metrics,
            "rate_limiter": rate_limiter,
        }

        log.info("NEXUS MCP v2 shutting down")

    mcp = FastMCP(
        "nexus_mcp_v2",
        lifespan=server_lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_allowed_hosts(),
        ),
    )

    # Register all domain tools
    import asyncio
    asyncio.run(register_all(mcp, registry))

    log.info("Registered %d tools", len(registry.list_tools()))
    return mcp


class ProtectedASGIApp:
    """ASGI middleware that enforces authentication on protected paths."""

    def __init__(
        self,
        app,
        protected_prefixes: tuple[str, ...] = ("/mcp", "/api/v2"),
        open_prefixes: tuple[str, ...] = ("/health", "/metrics"),
    ):
        self.app = app
        self.protected_prefixes = protected_prefixes
        self.open_prefixes = open_prefixes

    async def __call__(self, scope, receive, send):
        """ASGI interface."""
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Open paths bypass auth
        if any(path.startswith(prefix) for prefix in self.open_prefixes):
            await self.app(scope, receive, send)
            return

        # Unprotected paths bypass auth
        if not any(path.startswith(prefix) for prefix in self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        # Protected path - check auth
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        auth_result = validate_bearer_header(headers.get("authorization"))

        if auth_result.ok:
            await self.app(scope, receive, send)
            return

        # Auth failed - return error
        body = json.dumps({
            "detail": auth_result.message,
            "status_code": auth_result.status_code,
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": auth_result.status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def create_rest_app():
    """Create FastAPI REST app with health, metrics, and policy endpoints."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(
        title="NEXUS MCP v2",
        version="2.0.0",
        description="Model Context Protocol server with rate limiting and policy engine",
    )

    @app.get("/health")
    async def health() -> JSONResponse:
        """Health check endpoint."""
        component_status = {
            "registry": len(registry.list_tools()) > 0,
            "audit_logger": True,
            "rate_limiter": True,
            "metrics": True,
        }

        return JSONResponse({
            "status": "ok" if all(component_status.values()) else "degraded",
            "server": "nexus-v2",
            "version": "2.0.0",
            "components": component_status,
            "tool_count": len(registry.list_tools()),
            "timestamp": time.time(),
        })

    @app.get("/metrics")
    async def metrics_endpoint() -> JSONResponse:
        """Metrics endpoint with tool usage statistics."""
        return JSONResponse({
            "summary": metrics.get_summary(),
            "tools": metrics.get_metrics(),
            "timestamp": time.time(),
        })

    @app.get("/api/v2/tools")
    async def list_tools() -> JSONResponse:
        """List all registered tools."""
        return JSONResponse({
            "tools": registry.as_serializable(),
            "count": len(registry.list_tools()),
        })

    @app.post("/api/v2/policy/{tool_name}")
    async def check_tool_policy(tool_name: str, request: Request) -> JSONResponse:
        """Check tool access policy."""
        meta = registry.get(tool_name)
        if meta is None:
            return JSONResponse(
                {"allowed": False, "reason": "Unknown tool"},
                status_code=404,
            )

        # Check rate limit (use authorization header suffix as token)
        headers = dict(request.headers)
        auth_header = headers.get("authorization", "")
        token = auth_header.split()[-1][:6] if auth_header else "unknown"

        allowed, reset_after = rate_limiter.check_limit(token, meta.domain)

        # Get body if present
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        decision = evaluate_tool_access(
            meta,
            confirmation_requested=body.get("confirmation", False),
            rate_limit_ok=allowed,
        )

        response = {
            "tool": tool_name,
            "allowed": decision.allowed,
            "reason": decision.reason,
        }

        if not allowed:
            response["retry_after"] = reset_after

        return JSONResponse(response, status_code=decision.status_code)

    @app.post("/api/v2/audit/sample/{tool_name}")
    async def audit_sample(tool_name: str) -> JSONResponse:
        """Sample audit logging endpoint."""
        started = time.perf_counter()
        event = audit_logger.log_event(
            tool_name=tool_name,
            caller="api-sample",
            status="sample",
            duration_ms=int((time.perf_counter() - started) * 1000),
            params={"tool_name": tool_name},
        )
        return JSONResponse(event)

    return app


def build_app():
    """Build combined ASGI app (MCP + REST)."""
    _load_env()

    from asgi_router import PathRouter

    rest_app = create_rest_app()
    mcp_app = build_mcp_server().streamable_http_app()
    combined = PathRouter(mcp_app, rest_app)
    return ProtectedASGIApp(combined, protected_prefixes=("/mcp", "/api/v2"))


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="NEXUS MCP v2 Server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--port", type=int, default=settings.PORT)
    parser.add_argument("--host", default=settings.HOST)
    args = parser.parse_args()

    _load_env()

    if args.transport == "http":
        log.info(
            f"Starting NEXUS MCP v2 on {args.host}:{args.port}\n"
            f"  MCP:     http://{args.host}:{args.port}/mcp\n"
            f"  Health:  http://{args.host}:{args.port}/health\n"
            f"  Metrics: http://{args.host}:{args.port}/metrics\n"
            f"  Tools:   http://{args.host}:{args.port}/api/v2/tools"
        )
        app = build_app()
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        log.info("Starting NEXUS MCP v2 (stdio)")
        mcp = build_mcp_server()
        mcp.run(transport="stdio")
