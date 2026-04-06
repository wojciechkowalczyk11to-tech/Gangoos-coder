# Gangoos-coder — Copilot Agent Instructions

> Model: claude-opus-4-5 | Mode: extended thinking | Env: GitHub Codespaces

## Co budujesz

**Gangoos-coder** — Rust AI coding agent (fork goose) + 170-tool Python MCP server + Qwen3:8b LLM.
Cel: 300+ testów passing, zero red, dużo commitów → potem transfer do czystej org repo.

## Struktura monorepo

```
Gangoos-coder/
├── crates/
│   ├── goose/            ← core agent (Rust)
│   ├── goose-cli/        ← binary: goose
│   ├── goose-server/     ← binary: goosed (HTTP API)
│   ├── goose-mcp/        ← MCP extensions
│   ├── goose-acp/        ← Agent Client Protocol
│   ├── goose-acp-macros/ ← proc macros
│   ├── goose-test/       ← test utilities
│   └── goose-test-support/
├── mcp-server/           ← 170+ tools, Python FastMCP
│   ├── server.py
│   ├── rest_gateway.py   ← /tools/call + /mojo_exec
│   ├── config.py
│   ├── modules/          ← jeden plik per tool group
│   └── tests/            ← pytest (cel: 130+ testów)
├── llm/                  ← Qwen3:8b via Ollama
│   ├── Modelfile
│   ├── config.yaml
│   └── client.py
├── knowledge/            ← hacker-laws KB + context7
│   └── tests/
├── training/             ← fine-tune pipeline Mojo/RunPod
│   ├── pipeline/
│   ├── data/
│   └── scripts/
├── docker-compose.yml
└── pytest.ini
```

## Infrastruktura (zawsze przez env vars, nigdy hardcode)

| VM | Env var | Co robi |
|----|---------|---------|
| VM1 | `GANGOOS_VM1_HOST` | MCP server :8080, agent :3000 |
| VM2 | `OLLAMA_HOST` | Qwen3:8b Ollama :11434 |

## Aktualny stan CI

| Check | Stan |
|-------|------|
| cargo fmt | ✅ |
| cargo check | ✅ |
| cargo clippy -D warnings | ✅ |
| cargo test -p goose | ✅ (mało testów) |
| pytest (39 testów) | ✅ |
| docker compose config | ✅ |
| secret-scan | ✅ |

## Plan: 300+ testów, zero red

### Rust — cel 150 testów

Gdzie pisać: `crates/*/tests/` i `#[cfg(test)]` moduły inline

Priorytety:
1. `crates/goose/src/agents/` — state machine, tool routing, context mgmt
2. `crates/goose/src/providers/` — Provider trait, parsowanie odpowiedzi
3. `crates/goose-mcp/` — rejestracja narzędzi, dispatch
4. `crates/goose-server/src/routes/` — każdy endpoint (axum::test)
5. `crates/goose-acp/` — serializacja ACP schema
6. `crates/goose/src/context_mgmt/` — token budget, pruning

Zasady:
- `#[tokio::test]` dla async
- mockall lub ręczne test doubles — zero real API calls
- proptest dla parserów i serializerów
- Każda publiczna funkcja = min 1 test

### Python — cel 130 testów

Gdzie pisać: `mcp-server/tests/`, `knowledge/tests/`

Priorytety:
1. Każdy tool w `mcp-server/modules/` — 3 testy (happy, bad input, edge)
2. `rest_gateway.py` — wszystkie route'y + /tools/call + /mojo_exec
3. `server.py` lifespan — startup, shutdown, config injection
4. `config.py` — env parsing, defaults, missing required
5. `llm/client.py` — timeout, retry, fallback
6. `knowledge/` — KB lookup, hacker-laws, context7 detection

Zasady:
- pytest + pytest-asyncio + httpx.AsyncClient
- Mockuj zewnętrzny HTTP z respx lub unittest.mock
- @pytest.mark.parametrize — min 50 sparametryzowanych cases
- Fixtures w conftest.py

### UI — cel 20 testów

`ui/desktop/` — pnpm test (Vitest)

## Kolejność roboty

1. Rozszerz testy Rust — dodaj 100+ w crates/goose/tests/
2. Rozszerz testy Python — pokryj wszystkie 170+ MCP tools
3. Napraw każdy czerwony test — zero red to warunek konieczny
4. Dodaj testy UI — Vitest components
5. Ulepsz CI — coverage report, matrix builds
6. Security — cargo deny check + pip-audit
7. Training pipeline — dokoncz training/pipeline/ dla Qwen fine-tune
8. README — screenshoty, badge CI, architektura diagram
9. Release prep — tag v1.0.0, CHANGELOG

## Zasady kodu (z AGENTS.md)

- Samodokumentujący kod — dobre nazwy > komentarze
- Komentarze tylko dla nieoczywistej logiki biznesowej
- `anyhow::Result` dla błędów Rust
- Ufaj systemowi typów Rust — nie bądź defensywny
- Nie dodawaj logów — chyba że error lub security event
- Nigdy nie edytuj `ui/desktop/openapi.json` ręcznie
- Zawsze `cargo add` zamiast ręcznej edycji Cargo.toml
- Zawsze `cargo fmt` przed commitem

## Commit discipline

```
type(scope): message
```
- feat / fix / test / refactor / ci / docs
- DCO: `git commit -s`
- Nigdy: .env, prywatne IPs, tokeny API
- Jeden commit per logiczna jednostka pracy

## Czego NIE robić

- Nie hardcoduj IP, tokenów, haseł
- Nie zostawiaj TODO/FIXME — napraw od razu
- Nie dodawaj ficzerów spoza planu
- Nie skipuj czerwonych testów
- Nie amenduj publicznych commitów
