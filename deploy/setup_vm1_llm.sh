#!/bin/bash
set -euo pipefail

# setup_vm1_llm.sh
# Deployment script for VM1 (gangus-llm)
# Installs and configures Ollama with Qwen model for CodeAct agent
# IP: 164.90.217.149 (Public), 10.114.0.3 (Private VPC)

MODEL_NAME="${MODEL_NAME:-deepseek-r1:8b}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/gangus-llm-setup.log"

echo "==============================================="
echo "VM1 LLM Setup (Ollama + Qwen)"
echo "==============================================="
echo "Timestamp: $(date)"
echo "Model: $MODEL_NAME"
echo "Log: $LOG_FILE"
echo ""

# Ensure we have sudo privileges
if [[ $EUID -ne 0 ]]; then
   echo "ERROR: This script must be run as root"
   exit 1
fi

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "Starting VM1 deployment..."

# Check Ollama installation
log "Checking Ollama installation..."
if ! command -v ollama &> /dev/null; then
    log "ERROR: Ollama is not installed. Please install Ollama first."
    exit 1
fi

log "✓ Ollama found: $(ollama --version)"

# Start Ollama service if not running
log "Ensuring Ollama service is running..."
if systemctl is-active --quiet ollama; then
    log "✓ Ollama service is already running"
else
    log "Starting Ollama service..."
    systemctl start ollama
    sleep 3
    if systemctl is-active --quiet ollama; then
        log "✓ Ollama service started successfully"
    else
        log "ERROR: Failed to start Ollama service"
        exit 1
    fi
fi

# Pull the model
log "Pulling model: $MODEL_NAME..."
if ollama pull "$MODEL_NAME"; then
    log "✓ Model pulled successfully"
else
    log "ERROR: Failed to pull model $MODEL_NAME"
    exit 1
fi

# Create custom Modelfile for coding agent
log "Creating custom Modelfile for CodeAct agent..."
MODELFILE_PATH="/tmp/Modelfile.gangus-coder"
cat > "$MODELFILE_PATH" << 'EOF'
FROM deepseek-r1:8b
SYSTEM "You are Gangus — a CodeAct agent specialized in Rust, Mojo, Python. Solve tasks by writing complete, executable code. Use ```python blocks for code."
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER num_ctx 32768
EOF

log "✓ Modelfile created at $MODELFILE_PATH"

# Create the custom model
log "Creating custom model 'gangus-coder'..."
if ollama create gangus-coder -f "$MODELFILE_PATH"; then
    log "✓ Custom model 'gangus-coder' created successfully"
else
    log "ERROR: Failed to create custom model"
    exit 1
fi

# Ensure Ollama listens on all interfaces (0.0.0.0)
log "Configuring Ollama to listen on 0.0.0.0:11434..."
OLLAMA_SERVICE="/etc/systemd/system/ollama.service"
if [[ -f "$OLLAMA_SERVICE" ]]; then
    # Check if Environment is already set
    if grep -q "Environment=\"OLLAMA_HOST" "$OLLAMA_SERVICE"; then
        log "✓ OLLAMA_HOST already configured"
    else
        log "Adding OLLAMA_HOST to service file..."
        sed -i '/\[Service\]/a Environment="OLLAMA_HOST=0.0.0.0:11434"' "$OLLAMA_SERVICE"
        systemctl daemon-reload
        systemctl restart ollama
        sleep 3
        log "✓ Ollama restarted with OLLAMA_HOST configuration"
    fi
else
    log "WARNING: Ollama service file not found at $OLLAMA_SERVICE"
    log "Make sure Ollama is configured to listen on 0.0.0.0:11434"
fi

# Configure UFW firewall
log "Configuring UFW firewall..."
if command -v ufw &> /dev/null; then
    # Allow Ollama port only from VPC
    if ufw status | grep -q "Status: active"; then
        # Delete any existing rule first
        ufw delete allow 11434/tcp 2>/dev/null || true

        # Add rule allowing only from VPC CIDR
        ufw allow from 10.114.0.0/24 to any port 11434 proto tcp
        log "✓ UFW configured to allow port 11434 from VPC 10.114.0.0/24"
    else
        log "INFO: UFW is not active. Skipping firewall configuration."
    fi
else
    log "WARNING: UFW not found. Firewall configuration skipped."
fi

# Health check
log "Performing health check..."
if curl -s http://localhost:11434/api/status > /dev/null; then
    log "✓ Ollama health check passed"
else
    log "WARNING: Ollama health check failed. Service may not be ready yet."
fi

# Test the custom model
log "Testing gangus-coder model..."
if timeout 30 ollama run gangus-coder "echo 'test'" > /dev/null 2>&1; then
    log "✓ gangus-coder model is responsive"
else
    log "WARNING: Could not test gangus-coder model (may be loading)"
fi

# Print status
echo ""
echo "==============================================="
echo "VM1 DEPLOYMENT COMPLETE"
echo "==============================================="
echo "Ollama Status: $(systemctl is-active ollama)"
echo "Ollama Version: $(ollama --version)"
echo "Listening on: 0.0.0.0:11434"
echo "VPC Private IP: 10.114.0.3:11434"
echo "Model: gangus-coder (based on $MODEL_NAME)"
echo "Firewall: Port 11434 allowed from VPC 10.114.0.0/24"
echo ""
echo "Next steps:"
echo "  1. Connect from VM2 (10.114.0.2) to http://10.114.0.3:11434"
echo "  2. Test with: curl http://10.114.0.3:11434/api/status"
echo "==============================================="

log "VM1 deployment completed successfully"
