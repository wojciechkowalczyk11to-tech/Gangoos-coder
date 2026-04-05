"""
NEXUS MCP — HTTP Client Module
Full HTTP: GET, POST, PUT, PATCH, DELETE with custom headers, body, auth
"""
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP, Context

log = logging.getLogger("nexus-mcp.http_client")


def register(mcp: FastMCP):

    class HTTPRequestInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        method: str = Field(..., description="HTTP method: GET, POST, PUT, PATCH, DELETE")
        url: str = Field(..., description="Target URL")
        headers: Optional[dict] = Field(None, description="HTTP headers dict")
        body: Optional[str] = Field(None, description="Request body (JSON string or plain text)")
        json_body: Optional[dict] = Field(None, description="Request body as JSON object (auto-sets Content-Type)")
        params: Optional[dict] = Field(None, description="URL query parameters")
        timeout: int = Field(30, description="Timeout in seconds")
        auth_bearer: Optional[str] = Field(None, description="Bearer token for Authorization header")

    @mcp.tool(name="http_request", annotations={"title": "HTTP Request (GET/POST/PUT/PATCH/DELETE)"})
    async def http_request(params: HTTPRequestInput, ctx: Context) -> str:
        """Make any HTTP request with full control over method, headers, body, auth."""
        import httpx
        method = params.method.upper()
        headers = dict(params.headers or {})
        if params.auth_bearer:
            headers["Authorization"] = f"Bearer {params.auth_bearer}"

        kwargs = {
            "method": method,
            "url": params.url,
            "headers": headers,
            "timeout": params.timeout,
        }
        if params.params:
            kwargs["params"] = params.params
        if params.json_body is not None:
            kwargs["json"] = params.json_body
        elif params.body:
            kwargs["content"] = params.body.encode()

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.request(**kwargs)
                body = r.text[:10000]
                try:
                    parsed = json.loads(body)
                    body_repr = parsed
                except Exception:
                    body_repr = body
                return json.dumps({
                    "status_code": r.status_code,
                    "headers": dict(r.headers),
                    "body": body_repr,
                })
        except Exception as e:
            return f"Error: {e}"

    class WebhookInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="Webhook URL")
        payload: dict = Field(..., description="JSON payload to POST")
        secret_header: Optional[str] = Field(None, description="Header name for secret")
        secret_value: Optional[str] = Field(None, description="Secret value for header")

    @mcp.tool(name="http_webhook", annotations={"title": "Send Webhook"})
    async def http_webhook(params: WebhookInput, ctx: Context) -> str:
        """POST JSON payload to a webhook URL."""
        import httpx
        headers = {"Content-Type": "application/json"}
        if params.secret_header and params.secret_value:
            headers[params.secret_header] = params.secret_value
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(params.url, json=params.payload, headers=headers, timeout=15)
                return json.dumps({"status_code": r.status_code, "response": r.text[:2000]})
        except Exception as e:
            return f"Error: {e}"

    log.info("HTTP Client module registered (GET/POST/PUT/PATCH/DELETE, webhooks)")
