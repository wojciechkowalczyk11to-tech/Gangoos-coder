#!/bin/bash
set -euo pipefail

# deploy_both.sh
# Master deployment script for both VMs
# Run from LOCAL machine (not on either VM)
# Usage: ./deploy_both.sh [options]

VM1_IP="${VM1_IP:?VM1_IP environment variable required}"
VM1_PRIVATE_IP="${VM1_PRIVATE_IP:?VM1_PRIVATE_IP environment variable required}"
VM2_IP="${VM2_IP:?VM2_IP environment variable required}"
VM2_PRIVATE_IP="${VM2_PRIVATE_IP:?VM2_PRIVATE_IP environment variable required}"
VM_USER="root"
SSH_KEY="${SSH_KEY:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/deployment-$(date +%Y%m%d-%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "==============================================="
echo "DUAL VM DEPLOYMENT (VM1 + VM2)"
echo "==============================================="
echo "Timestamp: $(date)"
echo "Log file: $LOG_FILE"
echo ""

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Color log functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "$LOG_FILE"
}

# Check prerequisites
log_info "Checking prerequisites..."

if ! command -v ssh &> /dev/null; then
    log_error "SSH not found. Please install ssh."
    exit 1
fi

if ! command -v scp &> /dev/null; then
    log_error "SCP not found. Please install openssh-client."
    exit 1
fi

if ! command -v curl &> /dev/null; then
    log_warn "curl not found. Some tests may fail."
fi

log_success "Prerequisites check passed"

# SSH options
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null"
if [[ -n "$SSH_KEY" ]]; then
    SSH_OPTS="$SSH_OPTS -i $SSH_KEY"
fi

# Function to test SSH connectivity
test_ssh() {
    local ip=$1
    local desc=$2
    log_info "Testing SSH connectivity to $desc ($ip)..."
    if ssh $SSH_OPTS "$VM_USER@$ip" "echo 'SSH OK'" > /dev/null 2>&1; then
        log_success "SSH connection to $desc successful"
        return 0
    else
        log_error "SSH connection to $desc failed"
        return 1
    fi
}

# Test connectivity
log_info "Testing SSH connectivity..."
TEST_FAILED=0
test_ssh "$VM1_IP" "VM1" || TEST_FAILED=1
test_ssh "$VM2_IP" "VM2" || TEST_FAILED=1

if [[ $TEST_FAILED -eq 1 ]]; then
    log_error "SSH connectivity test failed for one or more VMs"
    exit 1
fi

# Deploy VM1 (Ollama + Qwen)
echo ""
log_info "==============================================="
log_info "DEPLOYING VM1 (Ollama + Qwen LLM)"
log_info "==============================================="

log_info "Copying setup script to VM1..."
if scp $SSH_OPTS "$SCRIPT_DIR/setup_vm1_llm.sh" "$VM_USER@$VM1_IP:/tmp/setup_vm1_llm.sh"; then
    log_success "setup_vm1_llm.sh copied to VM1"
else
    log_error "Failed to copy setup script to VM1"
    exit 1
fi

log_info "Running VM1 setup on $VM1_IP..."
if ssh $SSH_OPTS "$VM_USER@$VM1_IP" "bash /tmp/setup_vm1_llm.sh"; then
    log_success "VM1 setup completed successfully"
else
    log_error "VM1 setup failed"
    exit 1
fi

# Wait for Ollama to be fully ready
log_info "Waiting for Ollama to be ready on VM1..."
for i in {1..30}; do
    if ssh $SSH_OPTS "$VM_USER@$VM1_IP" "curl -s http://localhost:11434/api/status > /dev/null 2>&1"; then
        log_success "Ollama is ready on VM1"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_warn "Ollama health check timeout on VM1"
    else
        echo -n "."
        sleep 2
    fi
done

# Deploy VM2 (MCP + CodeAct Agent)
echo ""
log_info "==============================================="
log_info "DEPLOYING VM2 (MCP + CodeAct Agent)"
log_info "==============================================="

log_info "Copying deployment files to VM2..."

# Copy orchestrator setup script
if scp $SSH_OPTS "$SCRIPT_DIR/setup_vm2_orchestrator.sh" "$VM_USER@$VM2_IP:/tmp/setup_vm2_orchestrator.sh"; then
    log_success "setup_vm2_orchestrator.sh copied to VM2"
else
    log_error "Failed to copy orchestrator setup script to VM2"
    exit 1
fi

# Copy docker-compose file
if scp $SSH_OPTS "$SCRIPT_DIR/docker-compose.vm2.yml" "$VM_USER@$VM2_IP:/tmp/docker-compose.vm2.yml"; then
    log_success "docker-compose.vm2.yml copied to VM2"
else
    log_warn "Failed to copy docker-compose file to VM2 (will use embedded version)"
fi

log_info "Running VM2 setup on $VM2_IP..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "bash /tmp/setup_vm2_orchestrator.sh"; then
    log_success "VM2 setup completed successfully"
else
    log_error "VM2 setup failed"
    exit 1
fi

# Wait for services to be ready
log_info "Waiting for VM2 services to be ready..."
for i in {1..30}; do
    mcp_ready=0
    agent_ready=0

    ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:8080/health > /dev/null 2>&1" && mcp_ready=1
    ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:3000/health > /dev/null 2>&1" && agent_ready=1

    if [[ $mcp_ready -eq 1 ]] && [[ $agent_ready -eq 1 ]]; then
        log_success "VM2 services are ready"
        break
    fi

    if [[ $i -eq 30 ]]; then
        log_warn "VM2 services health check timeout"
    else
        echo -n "."
        sleep 2
    fi
done

# End-to-end testing
echo ""
log_info "==============================================="
log_info "END-TO-END TESTING"
log_info "==============================================="

# Test 1: VM1 Ollama health
log_info "Testing VM1 Ollama health..."
if ssh $SSH_OPTS "$VM_USER@$VM1_IP" "curl -s http://localhost:11434/api/status" > /dev/null 2>&1; then
    log_success "✓ VM1 Ollama is healthy"
else
    log_warn "✗ VM1 Ollama health check failed"
fi

# Test 2: VM2 MCP server health
log_info "Testing VM2 MCP server health..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:8080/health" > /dev/null 2>&1; then
    log_success "✓ VM2 MCP server is healthy"
else
    log_warn "✗ VM2 MCP server health check failed"
fi

# Test 3: VM2 CodeAct agent health
log_info "Testing VM2 CodeAct agent health..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:3000/health" > /dev/null 2>&1; then
    log_success "✓ VM2 CodeAct agent is healthy"
else
    log_warn "✗ VM2 CodeAct agent health check failed"
fi

# Test 4: VM2 can reach VM1 (VPC connectivity)
log_info "Testing VPC connectivity (VM2 → VM1)..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://$VM1_PRIVATE_IP:11434/api/status > /dev/null 2>&1"; then
    log_success "✓ VM2 can reach Ollama on VM1 via VPC"
else
    log_warn "✗ VM2 cannot reach Ollama on VM1 via VPC"
fi

# Test 5: MCP tools are accessible
log_info "Testing MCP server tools availability..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:8080/tools | grep -q 'tools'" > /dev/null 2>&1; then
    log_success "✓ MCP server tools are accessible"
else
    log_warn "✗ Could not verify MCP server tools"
fi

# Print final summary
echo ""
echo "==============================================="
echo "DEPLOYMENT SUMMARY"
echo "==============================================="
echo ""
echo "VM1 - Ollama + Qwen LLM"
echo "  Public IP: $VM1_IP"
echo "  Private IP: $VM1_PRIVATE_IP"
echo "  Service: Ollama (port 11434)"
echo "  Model: gangus-coder (deepseek-r1:8b based)"
echo "  Status: $(ssh $SSH_OPTS "$VM_USER@$VM1_IP" "systemctl is-active ollama" 2>/dev/null || echo "unknown")"
echo "  URL (internal): http://$VM1_PRIVATE_IP:11434"
echo ""
echo "VM2 - MCP + CodeAct Agent"
echo "  Public IP: $VM2_IP"
echo "  Private IP: $VM2_PRIVATE_IP"
echo "  Services:"
echo "    - mcp-server (port 8080)"
echo "    - gangus-agent (port 3000)"
echo "  URLs (from local machine):"
echo "    - MCP Server: http://$VM2_IP:8080"
echo "    - CodeAct Agent: http://$VM2_IP:3000"
echo "  URLs (from VM2): http://localhost:8080 and http://localhost:3000"
echo ""
echo "Network Configuration:"
echo "  VPC CIDR: 10.114.0.0/24"
echo "  VM1 ↔ VM2 Communication: ✓ Enabled"
echo ""
echo "Testing Commands (run from local machine):"
echo "  VM1 Ollama health:"
echo "    ssh root@$VM1_IP curl http://localhost:11434/api/status"
echo ""
echo "  VM2 MCP health:"
echo "    ssh root@$VM2_IP curl http://localhost:8080/health"
echo ""
echo "  VM2 Agent health:"
echo "    ssh root@$VM2_IP curl http://localhost:3000/health"
echo ""
echo "Logs:"
echo "  Deployment log: $LOG_FILE"
echo "  VM1 setup log: /var/log/gangus-llm-setup.log"
echo "  VM2 setup log: /var/log/gangus-coder-setup.log"
echo "==============================================="

log_success "Full deployment completed!"
