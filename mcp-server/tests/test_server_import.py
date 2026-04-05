from server import build_combined_app, mcp


def test_server_registers_tools():
    assert mcp is not None


def test_rest_app_builds():
    app = build_combined_app()
    assert app is not None
