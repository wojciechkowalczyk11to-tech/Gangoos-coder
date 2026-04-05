![CI](https://github.com/wojciechkowalczyk11to-tech/gangus-coder/actions/workflows/ci.yml/badge.svg)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# gangus-coder

`gangus-coder` is a Rust-based coding agent forked from [block/goose](https://github.com/block/goose), extended with a Mojo-oriented CodeAct flow and a bundled Python MCP server.

The repository is being prepared as a single monorepo for:

- the Rust agent and server
- the Mojo-oriented CodeAct extension
- the bundled `mcp-server/` service
- training and knowledge assets used by the agent runtime

---

## Monorepo layout

```
gangus-coder/
  crates/           Rust agent, CLI, MCP and HTTP server
  mcp-server/       Bundled Python MCP server
  training/         Knowledge and dataset assets
  ui/               Frontend
  documentation/    Docs site sources
```

## Runtime model strategy

- Current default provider for local development: `xai`
- Current default model for local development: `grok-4-1-fast-reasoning`
- Planned later runtime: Qwen-based CodeAct worker on a dedicated VM
- Verification helpers: Gemini and DeepSeek

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

- `GOOSE_PROVIDER`
- `GOOSE_MODEL`
- `XAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GITHUB_TOKEN`
- `DIGITALOCEAN_TOKEN`
- `NEXUS_AUTH_TOKEN`

## Contributing

We welcome contributions. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

For an overview of project governance and maintainer responsibilities, see [GOVERNANCE.md](GOVERNANCE.md) and [MAINTAINERS.md](MAINTAINERS.md).

## Attribution

gangus-coder is a fork of [block/goose](https://github.com/block/goose), an open-source AI coding agent by Block, Inc. We gratefully acknowledge the goose team's foundational work. The original project is licensed under Apache 2.0.

## License

Apache License 2.0 -- see [LICENSE](LICENSE) for details.
