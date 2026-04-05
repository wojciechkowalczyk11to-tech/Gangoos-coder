"""
NEXUS MCP — Cloudflare Module
Full DNS management (CNAME, A, AAAA, TXT), Workers, KV, D1, Tunnels.
Goes beyond the built-in Cloudflare MCP (which lacks DNS/Tunnels).
"""

import json
import logging
from typing import Optional
from enum import Enum

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.cloudflare")


async def _cf_request(client, method: str, path: str, json_data=None, params=None) -> dict:
    """Make Cloudflare API request using pre-configured client."""
    resp = await client.request(method, path, json=json_data, params=params)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success", True):
        errors = data.get("errors", [])
        return {"error": f"CF API errors: {errors}"}
    return data


def register(mcp: FastMCP):
    """Register Cloudflare management tools."""

    # ── DNS Records ─────────────────────────────────────

    class DNSListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone_id: Optional[str] = Field(None, description="Zone ID. Uses default CLOUDFLARE_ZONE_ID if omitted.")
        record_type: Optional[str] = Field(None, description="Filter by type: A, AAAA, CNAME, TXT, MX, etc.")
        name: Optional[str] = Field(None, description="Filter by record name (e.g. sub.nexus-oc.pl)")

    @mcp.tool(
        name="cf_dns_list",
        annotations={"title": "List DNS Records", "readOnlyHint": True},
    )
    async def cf_dns_list(params: DNSListInput, ctx: Context) -> str:
        """List all DNS records for a zone. Filter by type or name."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        zone_id = params.zone_id or cfg.CLOUDFLARE_ZONE_ID

        if not zone_id:
            return "Error: No zone_id provided and CLOUDFLARE_ZONE_ID not set."

        query_params = {"per_page": 100}
        if params.record_type:
            query_params["type"] = params.record_type
        if params.name:
            query_params["name"] = params.name

        try:
            data = await _cf_request(client, "GET", f"/zones/{zone_id}/dns_records", params=query_params)
            records = data.get("result", [])

            if not records:
                return "No DNS records found matching criteria."

            output = "# DNS Records\n\n"
            output += "| Type | Name | Content | Proxied | TTL |\n|------|------|---------|---------|-----|\n"
            for r in records:
                proxied = "🟠 yes" if r.get("proxied") else "⚪ no"
                ttl = "Auto" if r.get("ttl") == 1 else str(r.get("ttl", ""))
                output += f"| {r['type']} | `{r['name']}` | `{r['content'][:50]}` | {proxied} | {ttl} |\n"

            return output
        except Exception as e:
            return f"Error: {e}"

    class DNSCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone_id: Optional[str] = Field(None, description="Zone ID")
        record_type: str = Field(..., description="Record type: A, AAAA, CNAME, TXT, MX, etc.")
        name: str = Field(..., description="Record name (e.g. 'sub' for sub.nexus-oc.pl, or '@' for root)")
        content: str = Field(..., description="Record content (IP for A/AAAA, hostname for CNAME, text for TXT)")
        proxied: bool = Field(True, description="Enable Cloudflare proxy (orange cloud)")
        ttl: int = Field(1, description="TTL in seconds (1 = auto)", ge=1)
        priority: Optional[int] = Field(None, description="Priority (required for MX records)")

    @mcp.tool(
        name="cf_dns_create",
        annotations={"title": "Create DNS Record", "destructiveHint": True},
    )
    async def cf_dns_create(params: DNSCreateInput, ctx: Context) -> str:
        """Create a new DNS record. Supports A, AAAA, CNAME, TXT, MX, and more."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        zone_id = params.zone_id or cfg.CLOUDFLARE_ZONE_ID

        body = {
            "type": params.record_type.upper(),
            "name": params.name,
            "content": params.content,
            "proxied": params.proxied if params.record_type.upper() in ("A", "AAAA", "CNAME") else False,
            "ttl": params.ttl,
        }
        if params.priority is not None:
            body["priority"] = params.priority

        try:
            data = await _cf_request(client, "POST", f"/zones/{zone_id}/dns_records", body)
            r = data.get("result", {})
            return f"✅ DNS record created:\n- Type: {r.get('type')}\n- Name: `{r.get('name')}`\n- Content: `{r.get('content')}`\n- ID: `{r.get('id')}`"
        except Exception as e:
            return f"Error: {e}"

    class DNSUpdateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone_id: Optional[str] = Field(None, description="Zone ID")
        record_id: str = Field(..., description="DNS record ID to update")
        record_type: str = Field(..., description="Record type")
        name: str = Field(..., description="Record name")
        content: str = Field(..., description="New content")
        proxied: bool = Field(True, description="Enable Cloudflare proxy")
        ttl: int = Field(1, description="TTL", ge=1)

    @mcp.tool(
        name="cf_dns_update",
        annotations={"title": "Update DNS Record", "destructiveHint": True},
    )
    async def cf_dns_update(params: DNSUpdateInput, ctx: Context) -> str:
        """Update an existing DNS record by ID."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        zone_id = params.zone_id or cfg.CLOUDFLARE_ZONE_ID

        body = {
            "type": params.record_type.upper(),
            "name": params.name,
            "content": params.content,
            "proxied": params.proxied,
            "ttl": params.ttl,
        }
        try:
            data = await _cf_request(client, "PUT", f"/zones/{zone_id}/dns_records/{params.record_id}", body)
            return f"✅ DNS record `{params.record_id}` updated → `{params.content}`"
        except Exception as e:
            return f"Error: {e}"

    class DNSDeleteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone_id: Optional[str] = Field(None, description="Zone ID")
        record_id: str = Field(..., description="DNS record ID to delete")

    @mcp.tool(
        name="cf_dns_delete",
        annotations={"title": "Delete DNS Record", "destructiveHint": True},
    )
    async def cf_dns_delete(params: DNSDeleteInput, ctx: Context) -> str:
        """Delete a DNS record by ID. This is irreversible."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        zone_id = params.zone_id or cfg.CLOUDFLARE_ZONE_ID
        try:
            await _cf_request(client, "DELETE", f"/zones/{zone_id}/dns_records/{params.record_id}")
            return f"✅ DNS record `{params.record_id}` deleted."
        except Exception as e:
            return f"Error: {e}"

    # ── Zones ───────────────────────────────────────────

    class ZoneListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(
        name="cf_zone_list",
        annotations={"title": "List Cloudflare Zones", "readOnlyHint": True},
    )
    async def cf_zone_list(params: ZoneListInput, ctx: Context) -> str:
        """List all Cloudflare zones (domains) in the account."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]

        try:
            data = await _cf_request(client, "GET", "/zones", params={"account.id": cfg.CLOUDFLARE_ACCOUNT_ID})
            zones = data.get("result", [])
            output = "# Cloudflare Zones\n\n"
            for z in zones:
                status = "🟢 active" if z["status"] == "active" else f"🔴 {z['status']}"
                output += f"- **{z['name']}** | ID: `{z['id']}` | {status}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    # ── Tunnels ─────────────────────────────────────────

    class TunnelListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(
        name="cf_tunnel_list",
        annotations={"title": "List Cloudflare Tunnels", "readOnlyHint": True},
    )
    async def cf_tunnel_list(params: TunnelListInput, ctx: Context) -> str:
        """List all Cloudflare Tunnels in the account."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        try:
            data = await _cf_request(
                client, "GET",
                f"/accounts/{cfg.CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel",
                params={"is_deleted": "false"},
            )
            tunnels = data.get("result", [])
            if not tunnels:
                return "No tunnels found."

            output = "# Cloudflare Tunnels\n\n"
            for t in tunnels:
                status = t.get("status", "unknown")
                emoji = "🟢" if status == "healthy" else "🔴"
                output += f"{emoji} **{t['name']}** | ID: `{t['id']}` | Status: {status}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class TunnelConfigInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        tunnel_id: str = Field(..., description="Tunnel ID")

    @mcp.tool(
        name="cf_tunnel_get_config",
        annotations={"title": "Get Tunnel Config", "readOnlyHint": True},
    )
    async def cf_tunnel_get_config(params: TunnelConfigInput, ctx: Context) -> str:
        """Get the configuration of a Cloudflare Tunnel (ingress rules)."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        try:
            data = await _cf_request(
                client, "GET",
                f"/accounts/{cfg.CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/{params.tunnel_id}/configurations",
            )
            config = data.get("result", {}).get("config", {})
            return f"# Tunnel Config\n\n```json\n{json.dumps(config, indent=2)}\n```"
        except Exception as e:
            return f"Error: {e}"

    class TunnelUpdateConfigInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        tunnel_id: str = Field(..., description="Tunnel ID")
        config_json: str = Field(..., description="Full tunnel config JSON (ingress rules etc.)")

    @mcp.tool(
        name="cf_tunnel_update_config",
        annotations={"title": "Update Tunnel Config", "destructiveHint": True},
    )
    async def cf_tunnel_update_config(params: TunnelUpdateConfigInput, ctx: Context) -> str:
        """Update a Cloudflare Tunnel's configuration (ingress rules).
        Use cf_tunnel_get_config first to see current config, then modify and submit.
        """
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        try:
            config = json.loads(params.config_json)
            data = await _cf_request(
                client, "PUT",
                f"/accounts/{cfg.CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/{params.tunnel_id}/configurations",
                {"config": config},
            )
            return f"✅ Tunnel `{params.tunnel_id}` config updated."
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON — {e}"
        except Exception as e:
            return f"Error: {e}"

    # ── SSL Certificates ────────────────────────────────

    class SSLListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone_id: Optional[str] = Field(None, description="Zone ID")

    @mcp.tool(
        name="cf_ssl_list",
        annotations={"title": "List SSL Certificates", "readOnlyHint": True},
    )
    async def cf_ssl_list(params: SSLListInput, ctx: Context) -> str:
        """List SSL/TLS certificates for a zone."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        zone_id = params.zone_id or cfg.CLOUDFLARE_ZONE_ID
        try:
            data = await _cf_request(client, "GET", f"/zones/{zone_id}/ssl/certificate_packs")
            packs = data.get("result", [])
            output = "# SSL Certificate Packs\n\n"
            for p in packs:
                output += f"- **{p.get('type', 'unknown')}** | Status: {p.get('status')} | Hosts: {', '.join(p.get('hosts', []))}\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    # ── Purge Cache ─────────────────────────────────────

    class PurgeCacheInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        zone_id: Optional[str] = Field(None, description="Zone ID")
        purge_everything: bool = Field(False, description="Purge ALL cached content")
        urls: Optional[list[str]] = Field(None, description="Specific URLs to purge")

    @mcp.tool(
        name="cf_cache_purge",
        annotations={"title": "Purge Cloudflare Cache", "destructiveHint": True},
    )
    async def cf_cache_purge(params: PurgeCacheInput, ctx: Context) -> str:
        """Purge Cloudflare cache. Either purge everything or specific URLs."""
        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["cloudflare"]
        cfg = state["settings"]
        zone_id = params.zone_id or cfg.CLOUDFLARE_ZONE_ID

        body = {}
        if params.purge_everything:
            body["purge_everything"] = True
        elif params.urls:
            body["files"] = params.urls
        else:
            return "Error: Specify purge_everything=true or provide urls list."

        try:
            await _cf_request(client, "POST", f"/zones/{zone_id}/purge_cache", body)
            return "✅ Cache purge initiated."
        except Exception as e:
            return f"Error: {e}"
