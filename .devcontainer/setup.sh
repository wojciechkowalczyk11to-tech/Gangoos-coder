#!/bin/bash
# Gangoos-coder Codespace setup
set -e

echo "=== [1/6] Rust dependencies ==="
cargo fetch

echo "=== [2/6] Python MCP server ==="
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r mcp-server/requirements.txt --quiet

echo "=== [3/6] Python LLM + test deps ==="
python3 -m pip install httpx pydantic pytest pytest-asyncio pytest-cov respx python-dotenv --quiet

echo "=== [4/6] Node / UI ==="
if [ -f ui/package.json ]; then
  cd ui && npm install --silent && cd ..
fi

echo "=== [5/6] Mojo (optional) ==="
if command -v mojo &>/dev/null; then
  echo "Mojo found: $(mojo --version)"
fi

echo "=== [6/6] Env validation ==="
for var in NEXUS_AUTH_TOKEN OLLAMA_HOST NEXUS_MCP_URL GOOSE_PROVIDER GOOSE_MODEL; do
  if [ -n "${!var}" ]; then
    echo "  ✓ $var"
  else
    echo "  ✗ $var (not set — add to .env or Codespaces secrets)"
  fi
done

if [ -f .env ]; then
  echo "  .env found — loading"
  set -a; source .env; set +a
fi

echo ""
echo "=== Connectivity checks ==="
MCP_URL="${NEXUS_MCP_URL:?Set NEXUS_MCP_URL in Codespaces secrets}"
OLLAMA="${OLLAMA_HOST:?Set OLLAMA_HOST in Codespaces secrets}"

if curl -sf --connect-timeout 5 "$MCP_URL/health" > /dev/null 2>&1; then
  TOOLS=$(curl -sf "$MCP_URL/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tools_registered','?'))" 2>/dev/null)
  echo "  ✓ MCP server ($MCP_URL) — $TOOLS tools"
else
  echo "  ✗ MCP server unreachable: $MCP_URL"
fi

if curl -sf --connect-timeout 5 "$OLLAMA/api/tags" > /dev/null 2>&1; then
  MODEL=$(curl -sf "$OLLAMA/api/tags" | python3 -c "import sys,json; d=json.load(sys.stdin); m=d.get('models',[]); print(m[0]['name'] if m else 'none')" 2>/dev/null)
  echo "  ✓ Ollama ($OLLAMA) — model: $MODEL"
else
  echo "  ✗ Ollama unreachable: $OLLAMA"
fi

echo ""
echo "=== Setup complete ==="
echo "Next: cargo build --release -p goose-cli"
echo "Then: ./target/release/goose run"
