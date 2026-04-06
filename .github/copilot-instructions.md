# Gangoos-coder — Copilot Agent Instructions

> Model: claude-opus-4-5 | extended thinking ON | Env: GitHub Codespaces

## MISJA (czytaj najpierw)

Gangoos-coder to fork goose (Block Inc) z dodanym:
- 161-tool Python MCP server (REST + FastMCP)
- Qwen3:8b backend (Ollama) — tanie, lokalne LLM
- CodeAct agent — Rust, autonomiczny coding agent

**Cel #1 — działający CLI agent (zrób to PIERWSZE):**
```
goose run   ← działa, używa Qwen3:8b przez Ollama, ma dostęp do MCP tools
```

**Cel #2 — 300+ testów, zero czerwonych, dużo commitów**

---

## Infrastruktura (LIVE, dostępna przez cały czas)

| Serwis | URL | Co to |
|--------|-----|--------|
| MCP REST API | `http://46.101.108.96:8080` | 161 tools, REST gateway |
| Qwen3:8b | `http://164.90.217.149:11434` | Ollama, darmowe LLM |
| MCP health | `http://46.101.108.96:8080/health` | {"status":"ok","tools_registered":161} |
| MCP tools list | `GET /api/v1/tools` + Bearer token | lista wszystkich tools |
| MCP tool call | `POST /api/v1/tools/{name}` + Bearer token | wywołanie narzędzia |

**NEXUS_AUTH_TOKEN:** pobierz z `.env` (plik `NEXUS_AUTH_TOKEN=...`).
Nigdy nie hardcoduj tokenu — zawsze `os.getenv("NEXUS_AUTH_TOKEN")`.

---

## PLAN WYKONANIA — kolejność bezwzględna

### KROK 0: Zbuduj i uruchom goose CLI (PRIORYTET #1)

```bash
# W Codespaces (Rust zainstalowany przez devcontainer feature)
source bin/activate-hermit  # lub cargo bezpośrednio

# Build CLI
cargo build --release -p goose-cli

# Skonfiguruj dla Qwen3:8b (tanie!)
export GOOSE_PROVIDER=ollama
export GOOSE_MODEL=qwen3:8b
export OLLAMA_HOST=http://164.90.217.149:11434

# Skonfiguruj MCP server
export NEXUS_MCP_URL=http://46.101.108.96:8080
export NEXUS_AUTH_TOKEN=<z .env>

# Test
./target/release/goose run --text "hello, list your tools"
```

**Jeśli goose nie obsługuje Ollama natywnie** — dodaj provider w:
`crates/goose/src/providers/` (wzoruj się na `openai.rs`, zmień URL na `OLLAMA_HOST/api/chat`)

**MCP integracja w goose:**
```toml
# ~/.config/goose/config.toml  lub przez env
[extensions.gangoos-mcp]
type = "sse"  # lub "streamable_http"
url = "http://46.101.108.96:8080/mcp"
```

Alternatywnie przez REST gateway — dodaj HTTP extension client w `crates/goose-mcp/`.

### KROK 1: Ollama provider w goose

Sprawdź `crates/goose/src/providers/` — czy jest `ollama.rs`.
Jeśli nie: utwórz go wzorując się na `openai.rs`:
- Base URL: `OLLAMA_HOST/api/chat`  
- Format: Ollama chat API (messages array, model name)
- Streaming: SSE lub non-streaming (Qwen3:8b obsługuje oba)
- Zarejestruj w `crates/goose/src/providers/mod.rs`

### KROK 2: Podłącz MCP tools do goose

MCP server ma REST gateway (`/api/v1/tools/{name}`).
Goose obsługuje MCP przez extensions. Dodaj extension client lub skonfiguruj
streamable HTTP transport żeby goose widział 161 narzędzi.

Test: `goose run --text "list available tools"` — powinien pokazać 161 narzędzi.

### KROK 3: CodeAct agent działa autonomicznie

Goose już JEST CodeAct agentem (core w `crates/goose/src/agents/`).
Upewnij się że:
- Agent może pisać i wykonywać kod (shell tool, python tool)
- Agent ma dostęp do MCP tools (161 narzędzi)
- Agent używa Qwen3:8b (tanio!)
- Pętla: think → code → execute → observe → repeat

Test końcowy:
```bash
goose run --text "Write a Python script that fetches weather for Warsaw and saves to weather.json"
# Agent powinien autonomicznie: napisać kod → uruchomić → zapisać plik → zgłosić sukces
```

### KROK 4: 150+ testów Rust

Gdzie: `crates/*/tests/` + inline `#[cfg(test)]`

Priorytety:
1. `crates/goose/src/providers/ollama.rs` — testy nowego providera (mock HTTP)
2. `crates/goose/src/agents/` — state machine, tool routing, loop control
3. `crates/goose-mcp/` — extension registration, tool dispatch
4. `crates/goose-server/src/routes/` — wszystkie endpointy (axum::test)
5. `crates/goose-acp/` — serializacja ACP schema (round-trip tests)
6. `crates/goose/src/context_mgmt/` — token budget, context pruning

Zasady Rust:
- `#[tokio::test]` dla async
- mockall lub ręczne doubles — ZERO real API calls w testach
- proptest dla parserów i serializerów
- Każda publiczna funkcja core = min 1 test

### KROK 5: 130+ testów Python

Gdzie: `mcp-server/tests/`, `knowledge/tests/`

Priorytety:
1. Każdy tool w `mcp-server/modules/` — 3 testy per tool (happy, bad input, edge)
2. `rest_gateway.py` — /api/v1/tools, /api/v1/tools/{name}, /tools/call, /mojo_exec
3. `server.py` lifespan — startup, shutdown, config injection
4. `config.py` — env parsing, defaults, missing required → ValueError
5. `llm/client.py` — timeout, retry, fallback gdy Ollama niedostępna
6. `knowledge/` — KB lookup, hacker-laws, context7

Zasady Python:
- pytest + pytest-asyncio + httpx.AsyncClient dla FastAPI routes
- Mockuj zewnętrzny HTTP z `unittest.mock` lub `respx`
- `@pytest.mark.parametrize` — min 50 sparametryzowanych cases
- Fixtures w `conftest.py` — jeden per major component

### KROK 6: CI + coverage

Dodaj do `.github/workflows/ci.yml`:
- `cargo tarpaulin` lub `llvm-cov` — Rust coverage
- `pytest --cov=mcp-server` — Python coverage  
- Coverage badge w README
- Matrix build: ubuntu-latest × stable rust

### KROK 7: README + release prep

- Screenshots agenta w akcji
- CI badge (green!)
- Architektura diagram (ASCII lub Mermaid)
- CHANGELOG kompletny
- Tag v1.0.0 gdy wszystkie testy zielone

---

## Struktura monorepo

```
Gangoos-coder/
├── crates/
│   ├── goose/            ← core agent (Rust) — NAJWAŻNIEJSZE
│   ├── goose-cli/        ← binary: goose
│   ├── goose-server/     ← binary: goosed (HTTP API)
│   ├── goose-mcp/        ← MCP extensions
│   ├── goose-acp/        ← Agent Client Protocol
│   ├── goose-acp-macros/
│   ├── goose-test/
│   └── goose-test-support/
├── mcp-server/           ← 161 tools, Python FastMCP + REST gateway
│   ├── server.py         ← FastMCP entrypoint (port 8080)
│   ├── rest_gateway.py   ← /api/v1/tools/* + /tools/call + /mojo_exec
│   ├── config.py         ← TYLKO env vars, dataclass
│   ├── modules/          ← jeden plik per tool group
│   └── tests/
├── llm/                  ← Qwen3:8b config
│   ├── Modelfile         ← persona "Gangus"
│   ├── config.yaml
│   └── client.py         ← fallback HTTP klient Ollama
├── knowledge/            ← hacker-laws KB + context7
├── training/             ← fine-tune pipeline (później)
├── docker-compose.yml    ← gangus-agent + mcp-server + ollama
└── pytest.ini            ← pythonpath = mcp-server
```

---

## Zasady kodu (AGENTS.md)

- Samodokumentujący kod — dobre nazwy > komentarze
- `anyhow::Result` dla błędów Rust
- Ufaj systemowi typów Rust
- Nie dodawaj logów — chyba że error/security
- Nigdy nie edytuj `ui/desktop/openapi.json` ręcznie
- `cargo add` zamiast ręcznej edycji Cargo.toml
- `cargo fmt` przed każdym commitem

## Commit discipline

```
type(scope): message
git commit -s  ← DCO wymagane
```
- feat / fix / test / refactor / ci / docs
- Jeden commit per logiczna jednostka
- NIGDY: .env, prywatne IP, tokeny

## Czego NIE robić

- Nie hardcoduj IP ani tokenów — ZAWSZE env vars
- Nie zostawiaj TODO/FIXME — napraw od razu
- Nie skipuj czerwonych testów — napraw
- Nie amenduj publicznych commitów
- Nie dodawaj ficzerów spoza planu
