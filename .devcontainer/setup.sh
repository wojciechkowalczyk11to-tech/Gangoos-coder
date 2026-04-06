#!/bin/bash
# Gangus-coder Codespace setup
set -e

echo "=== [1/5] Rust dependencies ==="
cargo fetch

echo "=== [2/5] Python MCP server ==="
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r mcp-server/requirements.txt --quiet

echo "=== [3/5] Python LLM client ==="
python3 -m pip install httpx pydantic --quiet

echo "=== [4/5] Node / UI ==="
if [ -f ui/package.json ]; then
  cd ui && npm install --silent && cd ..
fi

echo "=== [5/5] Mojo (optional) ==="
if command -v mojo >/dev/null 2>&1; then
  echo "Mojo $(mojo --version) available"
else
  echo "Mojo SDK not available — skipping (CPU-only Codespace)"
fi

echo ""
echo "✓ Gangus-coder ready."
echo "  docker compose up          → agent + MCP server"
echo "  docker compose --profile llm up → + local Qwen3:8b"
echo "  Set OLLAMA_HOST in .env to use remote LLM VM"
