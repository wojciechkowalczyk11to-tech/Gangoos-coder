#!/bin/bash
set -euo pipefail

# setup_vm2_orchestrator.sh
# Deployment script for VM2 (gangus-coder)
# Installs Docker, clones repo, and starts MCP server + CodeAct agent
# IPs configured via environment variables

WORKSPACE_DIR="/home/ubuntu/workspace"
REPO_DIR="$WORKSPACE_DIR/gangoos-coder"
REPO_URL="https://github.com/wojciechkowalczyk11to-tech/Gangoos-coder.git"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/gangus-coder-setup.log"

echo "==============================================="
echo "VM2 Orchestrator Setup (MCP + CodeAct)"
echo "==============================================="
echo "Timestamp: $(date)"
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

log "Starting VM2 deployment..."

# Install Docker if not present
log "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    log "Installing Docker and Docker Compose..."
    apt-get update
    apt-get install -y docker.io docker-compose
    systemctl start docker
    systemctl enable docker
    log "✓ Docker and Docker Compose installed"
else
    log "✓ Docker found: $(docker --version)"
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    log "Installing Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    log "✓ Docker Compose installed"
else
    log "✓ Docker Compose found: $(docker-compose --version)"
fi

# Create workspace directory
log "Creating workspace directory..."
mkdir -p "$WORKSPACE_DIR"
log "✓ Workspace directory: $WORKSPACE_DIR"

# Clone or update repository
log "Cloning/updating Gangoos-coder repository..."
if [[ -d "$REPO_DIR/.git" ]]; then
    log "Repository already exists, pulling latest changes..."
    cd "$REPO_DIR"
    git pull origin main || git pull origin master || true
    log "✓ Repository updated"
else
    log "Cloning repository..."
    cd "$WORKSPACE_DIR"
    git clone "$REPO_URL" || git clone --depth 1 "$REPO_URL"
    log "✓ Repository cloned"
fi

# Ensure proper permissions
chown -R ubuntu:ubuntu "$WORKSPACE_DIR"
chmod -R 755 "$WORKSPACE_DIR"
log "✓ Workspace permissions set"

# Create .env file for docker-compose
log "Creating .env file..."
ENV_FILE="$REPO_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    log "Backing up existing .env to .env.bak"
    cp "$ENV_FILE" "$ENV_FILE.bak"
fi

# Generate secure token
NEXUS_AUTH_TOKEN=$(openssl rand -hex 32)

cat > "$ENV_FILE" << EOF
# VM2 Configuration (gangus-coder)
NEXUS_AUTH_TOKEN=$NEXUS_AUTH_TOKEN
OLLAMA_HOST=http://10.114.0.3:11434
OLLAMA_MODEL=gangus-coder
XAI_API_KEY=\${XAI_API_KEY:-your-xai-key-here}
GOOSE_PROVIDER=ollama
GOOSE_MODEL=gangus-coder
NEXUS_URL=http://localhost:8080
PORT=8080
GOOSE_PORT=3000
MCP_ALLOWED_HOSTS=localhost,127.0.0.1,mcp-server,gangus-agent
MOJO_EXEC_BACKEND=disabled
ALLOWED_SSH_HOSTS=localhost
EOF

chown ubuntu:ubuntu "$ENV_FILE"
chmod 600 "$ENV_FILE"
log "✓ .env file created with secure token"

# Copy docker-compose.yml if it exists in deploy directory
log "Setting up Docker Compose..."
if [[ -f "$DEPLOY_DIR/docker-compose.vm2.yml" ]]; then
    log "Copying docker-compose.yml from deploy directory..."
    cp "$DEPLOY_DIR/docker-compose.vm2.yml" "$REPO_DIR/docker-compose.yml"
    chown ubuntu:ubuntu "$REPO_DIR/docker-compose.yml"
    log "✓ docker-compose.yml configured"
else
    log "WARNING: docker-compose.vm2.yml not found in $DEPLOY_DIR"
    log "Using existing docker-compose.yml if present, or will create default"
fi

# Create docker-compose.yml if it doesn't exist
if [[ ! -f "$REPO_DIR/docker-compose.yml" ]]; then
    log "Creating default docker-compose.yml..."
    cat > "$REPO_DIR/docker-compose.yml" << 'COMPOSE_EOF'
version: '3.8'

services:
  gangus-agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: gangus-agent
    ports:
      - "3000:3000"
    environment:
      - GOOSE_PROVIDER=ollama
      - GOOSE_MODEL=gangus-coder
      - OLLAMA_HOST=${OLLAMA_HOST}
      - NEXUS_URL=${NEXUS_URL}
      - PORT=3000
    depends_on:
      - mcp-server
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    networks:
      - gangus-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    container_name: mcp-server
    ports:
      - "8080:8080"
    environment:
      - NEXUS_AUTH_TOKEN=${NEXUS_AUTH_TOKEN}
      - OLLAMA_HOST=${OLLAMA_HOST}
      - OLLAMA_MODEL=${OLLAMA_MODEL}
      - XAI_API_KEY=${XAI_API_KEY}
      - PORT=8080
      - MCP_ALLOWED_HOSTS=${MCP_ALLOWED_HOSTS}
      - MOJO_EXEC_BACKEND=${MOJO_EXEC_BACKEND}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    networks:
      - gangus-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  gangus-network:
    driver: bridge

COMPOSE_EOF
    chown ubuntu:ubuntu "$REPO_DIR/docker-compose.yml"
    log "✓ Default docker-compose.yml created"
fi

# Run tests (Python only)
log "Running Python tests..."
cd "$REPO_DIR"
if [[ -f "requirements-test.txt" ]]; then
    python3 -m pip install -q -r requirements-test.txt 2>/dev/null || true
fi

if [[ -d "tests" ]] && [[ -f "tests/__init__.py" ]]; then
    log "Running pytest..."
    python3 -m pytest tests/ -v --tb=short 2>&1 | tee -a "$LOG_FILE" || log "WARNING: Some tests failed"
else
    log "INFO: No tests directory found"
fi

# Start services
log "Starting Docker services..."
cd "$REPO_DIR"
if docker-compose up -d; then
    log "✓ Docker services started"
    sleep 5
else
    log "ERROR: Failed to start Docker services"
    exit 1
fi

# Health checks
log "Performing health checks..."
sleep 5

# Check mcp-server
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    log "✓ mcp-server (port 8080) is healthy"
else
    log "WARNING: mcp-server health check failed"
    docker-compose logs mcp-server | tail -20 >> "$LOG_FILE"
fi

# Check gangus-agent
if curl -s http://localhost:3000/health > /dev/null 2>&1; then
    log "✓ gangus-agent (port 3000) is healthy"
else
    log "WARNING: gangus-agent health check failed"
    docker-compose logs gangus-agent | tail -20 >> "$LOG_FILE"
fi

# Test connectivity to VM1
log "Testing connectivity to VM1 (Ollama)..."
if curl -s http://10.114.0.3:11434/api/status > /dev/null 2>&1; then
    log "✓ Ollama on VM1 (10.114.0.3:11434) is reachable"
else
    log "WARNING: Could not reach Ollama on VM1 (10.114.0.3:11434)"
fi

# Configure UFW firewall
log "Configuring UFW firewall..."
if command -v ufw &> /dev/null; then
    if ufw status | grep -q "Status: active"; then
        # Allow agent and MCP ports
        ufw allow 3000/tcp || true
        ufw allow 8080/tcp || true
        log "✓ UFW configured to allow ports 3000 and 8080"
    else
        log "INFO: UFW is not active. Skipping firewall configuration."
    fi
else
    log "WARNING: UFW not found. Firewall configuration skipped."
fi

# Print status
echo ""
echo "==============================================="
echo "VM2 DEPLOYMENT COMPLETE"
echo "==============================================="
echo "Repository: $REPO_DIR"
echo "Docker Status:"
docker-compose ps --no-trunc
echo ""
echo "Service Status:"
echo "  gangus-agent (CodeAct): http://localhost:3000"
echo "  mcp-server: http://localhost:8080"
echo ""
echo "Configuration:"
echo "  OLLAMA_HOST: http://10.114.0.3:11434"
echo "  OLLAMA_MODEL: gangus-coder"
echo "  NEXUS_AUTH_TOKEN: $(echo $NEXUS_AUTH_TOKEN | cut -c1-16)... (stored in .env)"
echo ""
echo "Logs:"
echo "  Setup log: $LOG_FILE"
echo "  Docker logs: docker-compose logs -f"
echo ""
echo "Next steps:"
echo "  1. Verify VM1 is running: curl http://10.114.0.3:11434/api/status"
echo "  2. Test mcp-server: curl http://localhost:8080/health"
echo "  3. Test agent: curl http://localhost:3000/health"
echo "==============================================="

log "VM2 deployment completed successfully"
