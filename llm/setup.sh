#!/bin/bash
# Setup Qwen3:8b on gangus-llm VM
# Run this on the LLM VM (164.90.217.149)
set -e

echo "Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "Configuring Ollama to listen on all interfaces..."
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
systemctl daemon-reload
systemctl enable --now ollama
sleep 3

echo "Pulling Qwen3:8b..."
ollama pull qwen3:8b

echo "Loading custom Modelfile (gangus)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ollama create gangus -f "$SCRIPT_DIR/Modelfile"

echo "Done. Test:"
ollama run gangus "Write hello world in Rust"
