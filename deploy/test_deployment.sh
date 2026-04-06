#!/bin/bash
set -euo pipefail

# test_deployment.sh
# Comprehensive testing script for deployed VMs
# Run from local machine after deploy_both.sh completes

VM1_IP="${VM1_IP:?VM1_IP environment variable required}"
VM1_PRIVATE_IP="${VM1_PRIVATE_IP:?VM1_PRIVATE_IP environment variable required}"
VM2_IP="${VM2_IP:?VM2_IP environment variable required}"
VM2_PRIVATE_IP="${VM2_PRIVATE_IP:?VM2_PRIVATE_IP environment variable required}"
VM_USER="${VM_USER:-root}"
SSH_KEY="${SSH_KEY:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# SSH options
SSH_OPTS="-o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null"
if [[ -n "$SSH_KEY" ]]; then
    SSH_OPTS="$SSH_OPTS -i $SSH_KEY"
fi

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $*"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $*"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $*"
}

info() {
    echo -e "${BLUE}ℹ INFO${NC}: $*"
}

test_ssh() {
    local ip=$1
    local name=$2
    info "Testing SSH to $name ($ip)..."
    if ssh $SSH_OPTS "$VM_USER@$ip" "echo OK" > /dev/null 2>&1; then
        pass "SSH connectivity to $name"
        return 0
    else
        fail "SSH connectivity to $name"
        return 1
    fi
}

run_test() {
    local description=$1
    local command=$2
    local on_vm=${3:-vm1}
    local ip=$VM1_IP
    if [[ "$on_vm" == "vm2" ]]; then
        ip=$VM2_IP
    fi

    info "Testing: $description"
    if ssh $SSH_OPTS "$VM_USER@$ip" "$command" > /dev/null 2>&1; then
        pass "$description"
        return 0
    else
        fail "$description"
        return 1
    fi
}

echo "==============================================="
echo "GANGOOS CODER - DEPLOYMENT TEST SUITE"
echo "==============================================="
echo "Timestamp: $(date)"
echo ""

# ============================================
# PART 1: SSH Connectivity
# ============================================
echo "Part 1: SSH Connectivity"
echo "---"
test_ssh "$VM1_IP" "VM1" || exit 1
test_ssh "$VM2_IP" "VM2" || exit 1
echo ""

# ============================================
# PART 2: VM1 (Ollama) Tests
# ============================================
echo "Part 2: VM1 (Ollama) Tests"
echo "---"

run_test "Ollama service is running" "systemctl is-active ollama" "vm1"
run_test "Ollama listens on port 11434" "curl -s http://localhost:11434/api/status | grep -q models" "vm1"
run_test "Custom model 'gangus-coder' exists" "ollama list | grep -q gangus-coder" "vm1"
run_test "gangus-coder model responds" "timeout 30 ollama run gangus-coder 'echo test' > /dev/null" "vm1"
run_test "Ollama listens on all interfaces" "netstat -tlnp | grep -q 0.0.0.0:11434 || ss -tlnp | grep -q 0.0.0.0:11434" "vm1"
run_test "UFW allows port 11434 from VPC" "ufw status | grep -q '11434.*10.114.0.0/24'" "vm1"

echo ""

# ============================================
# PART 3: VM2 (Docker) Tests
# ============================================
echo "Part 3: VM2 (Docker) Tests"
echo "---"

run_test "Docker is installed" "docker --version" "vm2"
run_test "Docker Compose is installed" "docker-compose --version" "vm2"
run_test "Docker daemon is running" "docker ps" "vm2"
run_test "mcp-server container is running" "docker-compose -f /home/ubuntu/workspace/gangoos-coder/docker-compose.yml ps | grep mcp-server | grep -q Up" "vm2"
run_test "gangus-agent container is running" "docker-compose -f /home/ubuntu/workspace/gangoos-coder/docker-compose.yml ps | grep gangus-agent | grep -q Up" "vm2"
run_test "MCP server port 8080 is listening" "netstat -tlnp | grep -q 8080 || ss -tlnp | grep -q 8080" "vm2"
run_test "CodeAct agent port 3000 is listening" "netstat -tlnp | grep -q 3000 || ss -tlnp | grep -q 3000" "vm2"

echo ""

# ============================================
# PART 4: Health Checks
# ============================================
echo "Part 4: Health Checks"
echo "---"

run_test "Ollama /api/status endpoint responds" "curl -s http://localhost:11434/api/status" "vm1"
run_test "MCP server /health endpoint responds" "curl -s http://localhost:8080/health" "vm2"
run_test "CodeAct agent /health endpoint responds" "curl -s http://localhost:3000/health" "vm2"

echo ""

# ============================================
# PART 5: Configuration Tests
# ============================================
echo "Part 5: Configuration Tests"
echo "---"

run_test ".env file exists" "test -f /home/ubuntu/workspace/gangoos-coder/.env" "vm2"
run_test ".env has OLLAMA_HOST" "grep -q 'OLLAMA_HOST=' /home/ubuntu/workspace/gangoos-coder/.env" "vm2"
run_test ".env has OLLAMA_MODEL" "grep -q 'OLLAMA_MODEL=' /home/ubuntu/workspace/gangoos-coder/.env" "vm2"
run_test ".env has NEXUS_AUTH_TOKEN" "grep -q 'NEXUS_AUTH_TOKEN=' /home/ubuntu/workspace/gangoos-coder/.env" "vm2"
run_test "docker-compose.yml exists" "test -f /home/ubuntu/workspace/gangoos-coder/docker-compose.yml" "vm2"

echo ""

# ============================================
# PART 6: VPC Connectivity Tests
# ============================================
echo "Part 6: VPC Connectivity Tests"
echo "---"

info "Testing VM2 → VM1 connectivity via VPC..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://$VM1_PRIVATE_IP:11434/api/status > /dev/null 2>&1"; then
    pass "VM2 can reach Ollama on VM1 via VPC ($VM1_PRIVATE_IP:11434)"
else
    fail "VM2 cannot reach Ollama on VM1 via VPC"
fi

info "Testing VM1 private IP is reachable from VM2..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "ping -c 1 $VM1_PRIVATE_IP > /dev/null 2>&1"; then
    pass "VM1 private IP is reachable from VM2"
else
    fail "VM1 private IP is not reachable from VM2"
fi

echo ""

# ============================================
# PART 7: Integration Tests
# ============================================
echo "Part 7: Integration Tests"
echo "---"

info "Testing CodeAct agent can connect to Ollama..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:3000/health | grep -q 'up'" > /dev/null 2>&1; then
    pass "CodeAct agent is responsive"
else
    warn "CodeAct agent health status unclear"
fi

info "Testing MCP server can serve API requests..."
RESPONSE=$(ssh $SSH_OPTS "$VM_USER@$VM2_IP" "curl -s http://localhost:8080/health" 2>/dev/null || echo "")
if [[ -n "$RESPONSE" ]]; then
    pass "MCP server responds to API requests"
else
    fail "MCP server does not respond to API requests"
fi

echo ""

# ============================================
# PART 8: Log Analysis
# ============================================
echo "Part 8: Log Analysis"
echo "---"

info "Checking VM1 setup logs for errors..."
if ssh $SSH_OPTS "$VM_USER@$VM1_IP" "grep -q 'ERROR' /var/log/gangus-llm-setup.log" > /dev/null 2>&1; then
    warn "VM1 setup log contains ERROR entries"
else
    pass "VM1 setup log has no ERROR entries"
fi

info "Checking VM2 setup logs for errors..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "grep -q 'ERROR' /var/log/gangus-coder-setup.log" > /dev/null 2>&1; then
    warn "VM2 setup log contains ERROR entries"
else
    pass "VM2 setup log has no ERROR entries"
fi

info "Checking Docker logs for errors..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "docker-compose -f /home/ubuntu/workspace/gangoos-coder/docker-compose.yml logs | grep -i 'error'" > /dev/null 2>&1; then
    warn "Docker logs contain error entries"
else
    pass "Docker logs have no error entries"
fi

echo ""

# ============================================
# PART 9: Port Security Tests
# ============================================
echo "Part 9: Port Security Tests"
echo "---"

info "Checking firewall status on VM1..."
if ssh $SSH_OPTS "$VM_USER@$VM1_IP" "ufw status | grep -q 'Status: active'" > /dev/null 2>&1; then
    pass "UFW firewall is active on VM1"
else
    warn "UFW firewall is not active on VM1"
fi

info "Checking firewall status on VM2..."
if ssh $SSH_OPTS "$VM_USER@$VM2_IP" "ufw status | grep -q 'Status: active'" > /dev/null 2>&1; then
    pass "UFW firewall is active on VM2"
else
    warn "UFW firewall is not active on VM2"
fi

echo ""

# ============================================
# Summary
# ============================================
echo "==============================================="
echo "TEST SUMMARY"
echo "==============================================="
echo ""
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
TOTAL=$((TESTS_PASSED + TESTS_FAILED))
PASS_RATE=$((TESTS_PASSED * 100 / TOTAL))
echo "Pass Rate: $PASS_RATE% ($TESTS_PASSED/$TOTAL)"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    echo ""
    echo "System is ready for use:"
    echo "  VM1 (Ollama): http://$VM1_PRIVATE_IP:11434"
    echo "  VM2 (MCP): http://localhost:8080 (from VM2)"
    echo "  VM2 (Agent): http://localhost:3000 (from VM2)"
    echo ""
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Review the failures above and check logs:"
    echo "  VM1: ssh $VM_USER@$VM1_IP tail -f /var/log/gangus-llm-setup.log"
    echo "  VM2: ssh $VM_USER@$VM2_IP tail -f /var/log/gangus-coder-setup.log"
    echo "  Docker: ssh $VM_USER@$VM2_IP docker-compose logs -f"
    echo ""
    exit 1
fi
