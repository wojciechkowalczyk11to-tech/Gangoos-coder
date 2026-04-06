# Gangoos-coder — Copilot Agent Instructions

> Model: claude-opus-4-5 | extended thinking ON | Workspace: GitHub Codespaces

## GDZIE PRACUJESZ

**Codespaces** — otwierasz repo na github.com → Code → Codespaces → New codespace.
NIE pracujesz lokalnie, NIE logujesz się na DigitalOcean.

Backend serwisy (LLM + MCP) są już live i dostępne przez env vars:
- `OLLAMA_HOST` → Qwen3:8b (tani LLM, prawie free)
- `NEXUS_MCP_URL` → 161 tools MCP REST API
- `NEXUS_AUTH_TOKEN` → token do MCP

Wszystkie adresy tylko z env vars — NIGDY hardcode IP ani tokenu.

## MISJA

Gangoos-coder = fork goose (Block Inc) + 161-tool Python MCP + Qwen3:8b.

**Cel #1 — działający goose CLI (zrób to PIERWSZE):**
```bash
goose run   # używa Qwen3:8b przez $OLLAMA_HOST, widzi 161 MCP tools
```

**Cel #2 — 300+ testów, zero czerwonych, dużo commitów**

**Cel #3 — repo w idealnym stanie (potem transfer do org)**

---

## PLAN — kolejność bezwzględna

### KROK 0: Sprawdź połączenie z backend serwisami

```bash
# W terminalu Codespaces (env vars powinny być ustawione z Codespaces Secrets)
echo $OLLAMA_HOST       # powinien zwrócić URL Ollama
echo $NEXUS_MCP_URL     # powinien zwrócić URL MCP
echo $NEXUS_AUTH_TOKEN  # powinien zwrócić token

# Connectivity test
curl -sf "$NEXUS_MCP_URL/health"    # {"status":"ok","tools_registered":161}
curl -sf "$OLLAMA_HOST/api/tags"    # {"models":[{"name":"qwen3:8b",...}]}
```

Jeśli env vars puste — sprawdź Codespaces Secrets w ustawieniach repo na GitHub.

### KROK 1: Zbuduj goose CLI

```bash
source bin/activate-hermit  # lub po prostu cargo
cargo build --release -p goose-cli
```

### KROK 2: Skonfiguruj goose dla Qwen3:8b

```bash
export GOOSE_PROVIDER=ollama
export GOOSE_MODEL=qwen3:8b
# OLLAMA_HOST już ustawiony z secrets
```

Sprawdź `crates/goose/src/providers/` — czy jest `ollama.rs`.
Jeśli nie: utwórz go wzorując się na `openai.rs`, endpoint: `$OLLAMA_HOST/api/chat`.
Zarejestruj w `crates/goose/src/providers/mod.rs`.

### KROK 3: Podłącz MCP tools

Goose obsługuje MCP przez extensions. Skonfiguruj:
```toml
# config dla goose — przez env lub config file
NEXUS_MCP_URL  ← adres REST gateway (161 tools)
NEXUS_AUTH_TOKEN ← Bearer token
```

Test: `./target/release/goose run --text "list available tools"`
→ powinien widzieć 161 narzędzi.

### KROK 4: Test end-to-end

```bash
./target/release/goose run --text   "Write a Python hello world script and run it"
# Agent: think → write code → execute → report
```

### KROK 5: 150+ testów Rust

Gdzie: `crates/*/tests/` + inline `#[cfg(test)]`

Priorytety:
1. Nowy `ollama.rs` provider — testy z mock HTTP (nie wywołuj prawdziwego Ollama)
2. `crates/goose/src/agents/` — state machine, tool routing, loop
3. `crates/goose-mcp/` — extension registration, dispatch
4. `crates/goose-server/src/routes/` — wszystkie endpointy (axum::test)
5. `crates/goose-acp/` — serializacja ACP (round-trip)
6. `crates/goose/src/context_mgmt/` — token budget, pruning

Zasady:
- `#[tokio::test]` dla async
- mockall lub ręczne doubles — ZERO real API calls w testach
- proptest dla parserów
- Każda publiczna funkcja core = min 1 test

### KROK 6: 130+ testów Python

Gdzie: `mcp-server/tests/`, `knowledge/tests/`

Priorytety:
1. Każdy tool w `mcp-server/modules/` — 3 testy per tool
2. `rest_gateway.py` — wszystkie route'y (/api/v1/tools, /tools/call, /mojo_exec)
3. `server.py` lifespan
4. `config.py` — env parsing, missing required → ValueError
5. `llm/client.py` — timeout, retry, fallback
6. `knowledge/` — KB lookup

Zasady:
- pytest + pytest-asyncio + httpx.AsyncClient
- Mock zewnętrzny HTTP z respx lub unittest.mock
- @pytest.mark.parametrize — min 50 cases
- Fixtures w conftest.py

### KROK 7: CI + coverage + README

- cargo tarpaulin lub llvm-cov — Rust coverage
- pytest --cov — Python coverage
- Coverage badge w README
- Screenshot agenta w akcji
- CHANGELOG kompletny
- Tag v1.0.0

---

## Struktura monorepo

```
Gangoos-coder/
├── crates/
│   ├── goose/            ← core agent (Rust)
│   ├── goose-cli/        ← binary: goose
│   ├── goose-server/     ← binary: goosed
│   ├── goose-mcp/        ← MCP extensions
│   ├── goose-acp/        ← Agent Client Protocol
│   └── goose-test*/
├── mcp-server/           ← 161 tools Python FastMCP + REST
│   ├── server.py
│   ├── rest_gateway.py   ← /api/v1/tools/* /tools/call /mojo_exec
│   ├── config.py
│   ├── modules/
│   └── tests/
├── llm/                  ← Qwen3:8b config
├── knowledge/            ← hacker-laws KB
├── training/             ← fine-tune pipeline
└── docker-compose.yml
```

---

## Zasady kodu

- Samodokumentujący kod — dobre nazwy > komentarze
- `anyhow::Result` dla Rust errors
- Nie hardcoduj IP, tokenów, URL — ZAWSZE env vars
- `cargo fmt` przed każdym commitem
- Nie edytuj `ui/desktop/openapi.json` ręcznie
- `cargo add` zamiast ręcznej edycji Cargo.toml

## Commit discipline

```
type(scope): message  ← feat/fix/test/refactor/ci/docs
git commit -s         ← DCO wymagane
```
Jeden commit per logiczna jednostka. NIGDY: .env, IP, tokeny w kodzie.

## Czego NIE robić

- Nie hardcoduj żadnych adresów IP ani tokenów
- Nie loguj się na VM przez SSH — pracujesz w Codespaces
- Nie zostawiaj TODO/FIXME
- Nie skipuj czerwonych testów
- Nie amenduj publicznych commitów
