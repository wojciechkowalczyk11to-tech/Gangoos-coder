#!/bin/bash
# Setup Ollama + Qwen3:8b on a dedicated LLM machine
#
# Usage (on separate LLM VM):
#   ./setup_ollama.sh
#
# This script:
#   1. Installs Ollama
#   2. Configures it to listen on all interfaces (0.0.0.0:11434)
#   3. Pulls Qwen3:8b model
#   4. Creates custom Modelfile variant
#   5. Performs health check
#
# For production, run this on a separate VM with good GPU resources.
# Then set OLLAMA_HOST in agent .env to: http://<this-vm-ip>:11434

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ────────────────────────────────────────────────────────────────────────────
# Install Ollama
# ────────────────────────────────────────────────────────────────────────────

if command -v ollama &> /dev/null; then
    log_success "Ollama is already installed"
    OLLAMA_VERSION=$(ollama --version)
    echo "   $OLLAMA_VERSION"
else
    log_info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    log_success "Ollama installed"
fi

# ────────────────────────────────────────────────────────────────────────────
# Configure Ollama to listen on all interfaces
# ────────────────────────────────────────────────────────────────────────────

log_info "Configuring Ollama to listen on 0.0.0.0:11434..."

mkdir -p /etc/systemd/system/ollama.service.d

cat > /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

log_success "Created systemd override"

# Reload and restart
systemctl daemon-reload
systemctl enable ollama || log_info "Ollama service auto-enable might need manual setup"
systemctl restart ollama || systemctl start ollama

log_success "Ollama service restarted"

# Wait for service to be ready
log_info "Waiting for Ollama to start..."
sleep 3

# ────────────────────────────────────────────────────────────────────────────
# Pull Qwen3:8b model
# ────────────────────────────────────────────────────────────────────────────

log_info "Pulling Qwen3:8b model (this may take 5-10 minutes)..."
echo "   Model size: ~5 GB"
echo ""

ollama pull qwen3:8b

log_success "Qwen3:8b model downloaded"

# ────────────────────────────────────────────────────────────────────────────
# Create custom Modelfile (optional)
# ────────────────────────────────────────────────────────────────────────────

# Check if Modelfile is provided
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELFILE="$SCRIPT_DIR/Modelfile"

if [ -f "$MODELFILE" ]; then
    log_info "Loading custom Modelfile..."
    ollama create gangus -f "$MODELFILE"
    log_success "Custom model 'gangus' created"
else
    log_info "Modelfile not found, using default qwen3:8b"
    log_info "To create a custom variant, add Modelfile to this directory"
fi

# ────────────────────────────────────────────────────────────────────────────
# Health check
# ────────────────────────────────────────────────────────────────────────────

log_info "Testing Ollama connection..."
sleep 2

if curl -sf http://localhost:11434/api/tags > /dev/null; then
    log_success "Ollama is responding on http://localhost:11434"
else
    log_error "Ollama health check failed"
    exit 1
fi

# ────────────────────────────────────────────────────────────────────────────
# List models
# ────────────────────────────────────────────────────────────────────────────

log_info "Available models:"
curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | sed 's/"name":"/  → /' | sed 's/"$//'

# ────────────────────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────────────────────

echo ""
log_success "Ollama setup complete!"
echo ""
echo "────────────────────────────────────────────────────────────────────────────"
echo -e "${GREEN}Next steps:${NC}"
echo ""
echo "  1. Get this machine's IP address:"
echo "     ip addr show | grep 'inet ' | grep -v 127.0.0.1"
echo ""
echo "  2. On the agent machine, set in .env:"
echo "     OLLAMA_HOST=http://<this-ip>:11434"
echo ""
echo "  3. Test connection from agent:"
echo "     curl http://<this-ip>:11434/api/tags"
echo ""
echo "  4. Test inference (optional):"
echo "     ollama run qwen3:8b 'Write hello world in Rust'"
echo ""
echo "────────────────────────────────────────────────────────────────────────────"
echo ""
echo "For monitoring, watch logs:"
echo "  journalctl -u ollama -f"
echo ""
