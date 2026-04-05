"""
NEXUS MCP — Singleton HTTP Clients
Module-level clients initialized once, reused across all tool calls.
Replaces FastMCP lifespan_state pattern (broken in FastMCP 3.1+).
"""
import httpx
from config import settings

# Initialized lazily on first use
_clients: dict | None = None


def get_clients() -> dict:
    """Return shared httpx clients. Created once, reused."""
    global _clients
    if _clients is None:
        _clients = {
            "gcp": httpx.AsyncClient(
                base_url="https://compute.googleapis.com",
                timeout=60.0,
            ),
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
    return _clients
