# Changelog

All notable changes to gangoos-coder are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2026-04-06

### Added
- `mcp-server/` — 170-tool Python MCP server merged into monorepo
- `llm/` — Qwen3:8b via Ollama: Modelfile, config, client, setup script
- `docker-compose.yml` — unified stack: gangus-agent + mcp-server + ollama (profile)
- `.devcontainer/setup.sh` — Codespaces-native full-stack setup
- Groq and Ollama providers in `mcp-server/modules/ai_proxy.py`
- `OLLAMA_HOST` / `GROQ_API_KEY` in `mcp-server/config.py`
- GitHub Actions: secret-scan job added to CI
- `NOTICE` file — Apache 2.0 attribution to block/goose
- `FUNDING.yml`, `CODE_OF_CONDUCT.md` — org-ready metadata
- Tests: `test_ollama_config.py` — no hardcoded IPs, env-var overrides

### Changed
- `README.md` — unified docs covering agent + MCP + LLM
- `.env.example` — full variable list, values empty
- `.devcontainer/devcontainer.json` — port 11434 forwarded, setup.sh extracted
- `docker-compose.yml` — ollama service added under `llm` profile
- All hardcoded server IPs replaced with `${OLLAMA_HOST}` / `${MCP_URL}` env vars

### Removed
- `.vm-state/` — runtime node state (now gitignored)
- Hardcoded private IPs from `llm/config.yaml`, `llm/client.py`, `docker-compose.yml`
- `training/` — dataset pipeline removed (requires Mojo, tracked separately)
- `documentation/` — docs site removed from monorepo (size, tracked separately)

### Security
- No secrets, tokens, or private IPs in any committed file
- `.vm-state/` added to `.gitignore`
- `secret-scan` CI job rejects commits with credential patterns

---

## [0.1.0] — 2026-04-05

### Added
- Initial monorepo snapshot from `gangus-coder` main branch
- Clean push without git history (no leaked credentials)
