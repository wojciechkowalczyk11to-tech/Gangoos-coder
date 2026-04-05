class PathRouter:
    """Route /mcp* to MCP, everything else to REST."""
    def __init__(self, mcp_app, rest_app):
        self.mcp = mcp_app
        self.rest = rest_app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.mcp(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith("/mcp"):
            await self.mcp(scope, receive, send)
        else:
            await self.rest(scope, receive, send)
