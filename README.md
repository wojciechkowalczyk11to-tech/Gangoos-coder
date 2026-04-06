![CI](https://github.com/wojciechkowalczyk11to-tech/Gangoos-coder/actions/workflows/ci.yml/badge.svg)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# gangoos-coder

`gangoos-coder` is a Rust-based coding agent forked from [block/goose](https://github.com/block/goose), extended with a Mojo-oriented CodeAct flow, a bundled 170-tool Python MCP server, and a local Qwen3:8b LLM integration.

---

## Monorepo layout

```
gangoos-coder/
  crates/           Rust agent, CLI, MCP and HTTP server
  mcp-server/       Bundled Python MCP server (170+ tools)
  llm/              Local LLM config — Qwen3:8b via Ollama
  ui/               Frontend
```

## Runtime model strategy

| Mode | Provider | Model |
|------|----------|-------|
| Default (cloud) | xAI | grok-4-1-fast-reasoning |
| Local LLM | Ollama | qwen3:8b |
| Fast inference | Groq | qwen-qwq-32b |
| Verification | DeepSeek | deepseek-chat |

Set `OLLAMA_HOST` in `.env` to point at a machine running `llm/setup.sh`.

## Architecture

```
user / client
  -> gangus-coder Rust agent
  -> platform extensions (`planner`, `context7`, `codeact`, `git_aware`, `watcher`, `gangus_memory`, `hooks`)
  -> bundled `mcp-server/`
  -> external services such as GitHub, DigitalOcean, xAI, Gemini, DeepSeek
```

## Platform Extensions

gangus-coder ships with built-in platform extensions that inject context and capabilities into the agent loop:

| Extension | Role |
|---|---|
| **codeact** | Code execution flow for Mojo-oriented tasks via the bundled MCP stack |
| **context7** | Documentation and context injection |
| **watcher** | File-system change tracking |
| **git_aware** | Repository awareness and diff context |
| **gangus_memory** | Persistent project memory |
| **hooks** | Validation and side-effect hooks |
| **planner** | Structured planning support |

Extensions are defined in `crates/goose/src/agents/platform_extensions/` and implement the `McpClientTrait` interface.

## Local development

### Prerequisites

- Rust toolchain
- Python 3.12
- Node 22
- Docker with Compose

### Codespaces

The repository includes a `.devcontainer` setup that installs Rust, Python, Node, Docker tooling and the Python dependencies for `mcp-server/`.

### Start the stack

```bash
cp .env.example .env
docker compose up --build
```

Services:

- `gangus-agent` on `http://localhost:3000`
- `mcp-server` on `http://localhost:8080`

The compose defaults route the agent through xAI Grok:

```env
GOOSE_PROVIDER=xai
GOOSE_MODEL=grok-4-1-fast-reasoning
NEXUS_URL=http://mcp-server:8080
```

## Configuration

The shared root `.env.example` contains variable names only. Populate values locally in `.env`.

Key variables:

| Variable | Purpose |
|----------|---------|
| `GOOSE_PROVIDER` | Agent LLM provider (`xai`, `groq`, `deepseek`) |
| `GOOSE_MODEL` | Model name |
| `NEXUS_AUTH_TOKEN` | MCP server bearer token |
| `OLLAMA_HOST` | Ollama endpoint, e.g. `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name (default: `qwen3:8b`) |
| `XAI_API_KEY` | xAI / Grok |
| `GROQ_API_KEY` | Groq (fast inference) |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `GEMINI_API_KEY` | Google Gemini |
| `GITHUB_TOKEN` | GitHub API |
| `DIGITALOCEAN_TOKEN` | DigitalOcean API |

## Contributing

We welcome contributions. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

For an overview of project governance and maintainer responsibilities, see [GOVERNANCE.md](GOVERNANCE.md) and [MAINTAINERS.md](MAINTAINERS.md).

## Attribution

gangus-coder is a fork of [block/goose](https://github.com/block/goose), an open-source AI coding agent by Block, Inc. We gratefully acknowledge the goose team's foundational work. The original project is licensed under Apache 2.0.

## License

Apache License 2.0 -- see [LICENSE](LICENSE) for details.
