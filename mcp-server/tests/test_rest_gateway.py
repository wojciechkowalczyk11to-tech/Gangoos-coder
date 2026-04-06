"""
Tests for REST Gateway endpoints.
Uses Starlette TestClient with real app (no mocks for routing).
"""
import os
import pytest
from starlette.testclient import TestClient

# ── Helpers ──────────────────────────────────────────────────────────────────

TEST_TOKEN = "test-gateway-token"


def _build_app():
    """Build a REST app with tool discovery, isolated from other test modules."""
    os.environ["NEXUS_AUTH_TOKEN"] = TEST_TOKEN

    import rest_gateway
    import server

    rest_gateway.discover_tools_from_mcp(server.mcp)

    # Register a lightweight echo tool for contract testing
    async def _echo(params, ctx=None):
        return f"echo:{params.get('msg', '') if isinstance(params, dict) else params}"

    rest_gateway._TOOL_REGISTRY["_test_echo"] = (_echo, None)
    rest_gateway._TOOL_DEFS["_test_echo"] = rest_gateway.ToolDefinition(
        name="_test_echo",
        title="Test Echo",
        description="Echo tool for testing",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        annotations={},
    )

    return rest_gateway.create_rest_app(), rest_gateway._TOOL_REGISTRY


@pytest.fixture(scope="module")
def app_and_registry():
    return _build_app()


@pytest.fixture(scope="module")
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


# ═════════════════════════════════════════════════════════════════════════════
# Health endpoint
# ═════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:

    def test_health_endpoint_returns_200(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_endpoint_returns_json_with_status(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert "tools_registered" in body
        assert isinstance(body["tools_registered"], int)
        assert body["tools_registered"] > 0


# ═════════════════════════════════════════════════════════════════════════════
# Tools list endpoint
# ═════════════════════════════════════════════════════════════════════════════

class TestToolsList:

    def test_tools_list_returns_200_with_auth(self, app_and_registry, auth_headers):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tools", headers=auth_headers)
        assert resp.status_code == 200

    def test_tools_list_requires_auth(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tools")
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {resp.status_code}"
        )

    def test_tools_list_returns_list(self, app_and_registry, auth_headers):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tools", headers=auth_headers)
        body = resp.json()
        assert "tools" in body
        assert isinstance(body["tools"], list)
        assert body["count"] == len(body["tools"])


# ═════════════════════════════════════════════════════════════════════════════
# Tools call endpoint
# ═════════════════════════════════════════════════════════════════════════════

class TestToolsCall:

    def test_tools_call_valid_tool_returns_200(self, app_and_registry, auth_headers):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                json={"name": "_test_echo", "arguments": {"msg": "hi"}},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["tool"] == "_test_echo"

    def test_tools_call_unknown_tool_returns_404(self, app_and_registry, auth_headers):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                json={"name": "nonexistent_tool_xyz", "arguments": {}},
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_tools_call_without_auth_returns_401_or_403(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                json={"name": "_test_echo", "arguments": {}},
            )
        assert resp.status_code in (401, 403)

    def test_tools_call_with_invalid_json_returns_4xx(self, app_and_registry, auth_headers):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                content=b"this is not json!!!",
                headers={**auth_headers, "Content-Type": "application/json"},
            )
        assert resp.status_code in (400, 422)

    def test_tools_call_missing_name_returns_422(self, app_and_registry, auth_headers):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/tools/call",
                json={"arguments": {}},  # missing 'name'
                headers=auth_headers,
            )
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# OpenAPI endpoint
# ═════════════════════════════════════════════════════════════════════════════

class TestOpenAPI:

    def test_openapi_endpoint_exists(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_openapi_returns_json(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/openapi.json")
        body = resp.json()
        assert "openapi" in body
        assert "paths" in body
        assert "info" in body


# ═════════════════════════════════════════════════════════════════════════════
# CORS
# ═════════════════════════════════════════════════════════════════════════════

class TestCORS:

    def test_cors_headers_present(self, app_and_registry):
        app, _ = app_and_registry
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/health",
                headers={
                    "Origin": "http://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


# ═════════════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════════════

class TestToolsRegistry:

    def test_tools_registry_populated(self, app_and_registry):
        _, registry = app_and_registry
        assert len(registry) > 0, "Tool registry must have at least one tool"

    def test_tools_registry_has_mojo_exec(self, app_and_registry):
        _, registry = app_and_registry
        assert "mojo_exec" in registry, "mojo_exec must be in REST tool registry"
