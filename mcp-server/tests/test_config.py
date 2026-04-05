from config import Settings


def test_allowed_hosts_parsing():
    settings = Settings(ALLOWED_SSH_HOSTS="localhost, 127.0.0.1 , mcp-server")
    assert settings.get_allowed_hosts() == ["localhost", "127.0.0.1", "mcp-server"]


def test_validate_warns_when_critical_tokens_missing():
    settings = Settings(
        AUTH_TOKEN="",
        CLOUDFLARE_API_TOKEN="",
        GITHUB_TOKEN="",
    )
    warnings = settings.validate()
    assert any("NEXUS_AUTH_TOKEN" in warning for warning in warnings)
    assert any("CLOUDFLARE_API_TOKEN" in warning for warning in warnings)
    assert any("GITHUB_TOKEN" in warning for warning in warnings)
