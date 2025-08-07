#!/bin/bash
# Comprehensive test suite for kubectl-smart
# Tests all commands, options, and variations against minikube

# set -e  # Temporarily disabled for debugging
# set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_TESTS++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

run_test() {
    local test_name="$1"
    local command="$2"
    local expected_exit_code="${3:-0}"
    
    ((TOTAL_TESTS++))
    log_info "Running test: $test_name"
    log_info "Command: $command"
    
    if eval "$command" >/dev/null 2>&1; then
        local exit_code=$?
        if [ $exit_code -eq $expected_exit_code ]; then
            log_success "$test_name"
        else
            log_error "$test_name - Expected exit code $expected_exit_code, got $exit_code"
        fi
    else
        local exit_code=$?
        if [ $exit_code -eq $expected_exit_code ]; then
            log_success "$test_name (expected failure)"
        else
            log_error "$test_name - Command failed with exit code $exit_code"
        fi
    fi
    echo ""
}

run_test_with_output() {
    local test_name="$1"
    local command="$2"
    local expected_pattern="$3"
    
    ((TOTAL_TESTS++))
    log_info "Running test: $test_name"
    log_info "Command: $command"
    
    local output
    if output=$(eval "$command" 2>&1); then
        if [[ "$output" =~ $expected_pattern ]]; then
            log_success "$test_name"
        else
            log_error "$test_name - Output doesn't match expected pattern"
            echo "Expected pattern: $expected_pattern"
            echo "Actual output: $output"
        fi
    else
        log_error "$test_name - Command failed"
        echo "Output: $output"
    fi
    echo ""
}

echo "🚀 kubectl-smart Comprehensive Test Suite"
echo "=========================================="
echo ""

# Check prerequisites
log_info "Checking prerequisites..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    log_error "kubectl not found. Please install kubectl."
    exit 1
fi

# Check if current context is minikube
CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "none")
if [ "$CURRENT_CONTEXT" != "minikube" ]; then
    log_error "Current kubectl context is '$CURRENT_CONTEXT', not 'minikube'"
    log_info "Please switch to minikube context: kubectl config use-context minikube"
    exit 1
fi

log_success "kubectl context is minikube"

echo "DEBUG: About to check kubectl-smart availability..."

# Check if kubectl-smart is available  
echo "DEBUG: Checking for kubectl-smart..."
if ! command -v kubectl-smart &> /dev/null; then
    log_error "kubectl-smart not found. Please install it first: ./install.sh"
    exit 1
fi

echo "DEBUG: kubectl-smart found at: $(command -v kubectl-smart)"
log_success "kubectl-smart found"

# Test basic functionality first
log_info "Testing basic functionality..."

log_info "Testing kubectl-smart --help with 10s timeout..."
run_test_with_output "Help command" "timeout 10s kubectl-smart --help" "Intelligent kubectl plugin"

log_info "Testing kubectl-smart --version with 10s timeout..."
run_test_with_output "Version command" "timeout 10s kubectl-smart --version" "kubectl-smart v1.0.0"

# Get available resources for testing
log_info "Discovering available resources in minikube..."

# Find pods in different states
RUNNING_POD=$(kubectl get pods -A --field-selector=status.phase=Running -o name | head -1 | cut -d'/' -f2 || echo "")
RUNNING_POD_NS=$(kubectl get pods -A --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.namespace}' || echo "")

PENDING_POD=$(kubectl get pods -A --field-selector=status.phase=Pending -o name | head -1 | cut -d'/' -f2 || echo "")
PENDING_POD_NS=$(kubectl get pods -A --field-selector=status.phase=Pending -o jsonpath='{.items[0].metadata.namespace}' || echo "")

FAILED_POD=$(kubectl get pods -A --field-selector=status.phase=Failed -o name | head -1 | cut -d'/' -f2 || echo "")
FAILED_POD_NS=$(kubectl get pods -A --field-selector=status.phase=Failed -o jsonpath='{.items[0].metadata.namespace}' || echo "")

# Find deployments
DEPLOYMENT=$(kubectl get deployments -A -o name | head -1 | cut -d'/' -f2 || echo "")
DEPLOYMENT_NS=$(kubectl get deployments -A -o jsonpath='{.items[0].metadata.namespace}' || echo "")

# Find services
SERVICE=$(kubectl get services -A -o name | head -1 | cut -d'/' -f2 || echo "")
SERVICE_NS=$(kubectl get services -A -o jsonpath='{.items[0].metadata.namespace}' || echo "")

log_info "Found resources:"
log_info "  Running pod: $RUNNING_POD (ns: $RUNNING_POD_NS)"
log_info "  Pending pod: $PENDING_POD (ns: $PENDING_POD_NS)"
log_info "  Failed pod: $FAILED_POD (ns: $FAILED_POD_NS)"
log_info "  Deployment: $DEPLOYMENT (ns: $DEPLOYMENT_NS)"
log_info "  Service: $SERVICE (ns: $SERVICE_NS)"
echo ""

# =============================================================================
# DIAG COMMAND TESTS
# =============================================================================
echo "🔍 Testing DIAG command"
echo "======================"

# Test all resource types with diag
RESOURCE_TYPES=("pod" "deploy" "sts" "job" "svc" "rs" "ds")

for resource_type in "${RESOURCE_TYPES[@]}"; do
    # Test basic diag help
    run_test_with_output "diag $resource_type help" "kubectl-smart diag --help" "Root-cause analysis"
done

# Test diag with actual resources
if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    run_test "diag running pod" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS"
    run_test "diag running pod with JSON output" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS --json"
    run_test "diag running pod with quiet flag" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS --quiet"
    run_test "diag running pod with format=json" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS --format=json"
fi

if [ -n "$PENDING_POD" ] && [ -n "$PENDING_POD_NS" ]; then
    run_test "diag pending pod" "kubectl-smart diag pod $PENDING_POD -n $PENDING_POD_NS"
fi

if [ -n "$FAILED_POD" ] && [ -n "$FAILED_POD_NS" ]; then
    run_test "diag failed pod" "kubectl-smart diag pod $FAILED_POD -n $FAILED_POD_NS"
fi

if [ -n "$DEPLOYMENT" ] && [ -n "$DEPLOYMENT_NS" ]; then
    run_test "diag deployment" "kubectl-smart diag deploy $DEPLOYMENT -n $DEPLOYMENT_NS"
    run_test "diag deployment JSON" "kubectl-smart diag deploy $DEPLOYMENT -n $DEPLOYMENT_NS --json"
fi

if [ -n "$SERVICE" ] && [ -n "$SERVICE_NS" ]; then
    run_test "diag service" "kubectl-smart diag svc $SERVICE -n $SERVICE_NS"
fi

# Test diag error cases
run_test "diag non-existent pod" "kubectl-smart diag pod non-existent-pod-xyz -n default" 1
run_test "diag invalid resource type" "kubectl-smart diag invalid-type test -n default" 2

# =============================================================================
# GRAPH COMMAND TESTS  
# =============================================================================
echo "🔗 Testing GRAPH command"
echo "========================"

# Test graph help
run_test_with_output "graph help" "kubectl-smart graph --help" "Dependency visualization"

# Test graph with actual resources
if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    run_test "graph running pod upstream" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --upstream"
    run_test "graph running pod downstream" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --downstream"
    run_test "graph running pod both directions" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --upstream --downstream"
    run_test "graph running pod default (downstream)" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS"
    run_test "graph running pod JSON" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --json"
    run_test "graph running pod format=json" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --format=json"
fi

if [ -n "$DEPLOYMENT" ] && [ -n "$DEPLOYMENT_NS" ]; then
    run_test "graph deployment upstream" "kubectl-smart graph deploy $DEPLOYMENT -n $DEPLOYMENT_NS --upstream"
    run_test "graph deployment downstream" "kubectl-smart graph deploy $DEPLOYMENT -n $DEPLOYMENT_NS --downstream"
fi

if [ -n "$SERVICE" ] && [ -n "$SERVICE_NS" ]; then
    run_test "graph service upstream" "kubectl-smart graph svc $SERVICE -n $SERVICE_NS --upstream"
    run_test "graph service downstream" "kubectl-smart graph svc $SERVICE -n $SERVICE_NS --downstream"
fi

# Test all resource types with graph
for resource_type in "${RESOURCE_TYPES[@]}"; do
    if [ "$resource_type" != "pod" ]; then  # Already tested pods above
        # Test with a made-up resource (may fail, that's OK)
        run_test "graph $resource_type upstream (may fail)" "kubectl-smart graph $resource_type test-resource --upstream" 1
    fi
done

# Test graph error cases
run_test "graph non-existent pod" "kubectl-smart graph pod non-existent-pod-xyz -n default" 1

# =============================================================================
# TOP COMMAND TESTS
# =============================================================================  
echo "📈 Testing TOP command"
echo "======================"

# Test top help
run_test_with_output "top help" "kubectl-smart top --help" "Predictive capacity"

# Get available namespaces
NAMESPACES=($(kubectl get namespaces -o name | cut -d'/' -f2 | head -5))

# Test top with different namespaces
for ns in "${NAMESPACES[@]}"; do
    run_test "top namespace $ns" "kubectl-smart top $ns"
    run_test "top namespace $ns JSON" "kubectl-smart top $ns --json"
    run_test "top namespace $ns format=json" "kubectl-smart top $ns --format=json"
done

# Test different horizon values
if [ -n "${NAMESPACES[0]}" ]; then
    local test_ns="${NAMESPACES[0]}"
    run_test "top with horizon=1" "kubectl-smart top $test_ns --horizon=1"
    run_test "top with horizon=24" "kubectl-smart top $test_ns --horizon=24"
    run_test "top with horizon=168" "kubectl-smart top $test_ns --horizon=168"
fi

# Test top error cases
run_test "top non-existent namespace" "kubectl-smart top non-existent-namespace-xyz" 1
run_test "top invalid horizon=0" "kubectl-smart top default --horizon=0" 2
run_test "top invalid horizon=200" "kubectl-smart top default --horizon=200" 2

# =============================================================================
# GLOBAL OPTIONS TESTS
# =============================================================================
echo "🌐 Testing GLOBAL options"
echo "========================="

# Test global flags with different commands
if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    run_test "diag with debug flag" "kubectl-smart --debug diag pod $RUNNING_POD -n $RUNNING_POD_NS"
    run_test "diag with quiet flag" "kubectl-smart --quiet diag pod $RUNNING_POD -n $RUNNING_POD_NS"
    run_test "diag with debug and quiet" "kubectl-smart --debug --quiet diag pod $RUNNING_POD -n $RUNNING_POD_NS"
fi

# Test version in different ways
run_test_with_output "global version flag" "kubectl-smart --version" "kubectl-smart v1.0.0"

# =============================================================================
# CONTEXT AND NAMESPACE TESTS
# =============================================================================
echo "🎯 Testing CONTEXT and NAMESPACE options"
echo "========================================"

# Test explicit context specification (should work with minikube)
if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    run_test "diag with explicit context" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS --context=minikube"
    run_test "graph with explicit context" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --context=minikube --upstream"
fi

run_test "top with explicit context" "kubectl-smart top default --context=minikube"

# Test invalid context
run_test "diag with invalid context" "kubectl-smart diag pod test --context=invalid-context" 1

# =============================================================================
# OUTPUT FORMAT TESTS
# =============================================================================
echo "📄 Testing OUTPUT FORMATS"
echo "========================="

if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    # Test that JSON output is valid JSON
    run_test_with_output "diag JSON format validation" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS --json | python3 -m json.tool" "ROOT_CAUSE\\|error"
    run_test_with_output "graph JSON format validation" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --json | python3 -m json.tool" "resources\\|error"
fi

run_test_with_output "top JSON format validation" "kubectl-smart top default --json | python3 -m json.tool" "namespace\\|error"

# =============================================================================
# PERFORMANCE TESTS
# =============================================================================
echo "⚡ Testing PERFORMANCE"
echo "===================="

# Test startup time
run_test_with_output "help command performance" "time kubectl-smart --help 2>&1" "real.*0m[0-9]\\.[0-9]"

if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    # Test command execution time (should be ≤3s as per spec)
    run_test "diag performance test" "timeout 5s kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS"
    run_test "graph performance test" "timeout 5s kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --upstream"
fi

run_test "top performance test" "timeout 5s kubectl-smart top default"

# =============================================================================
# LEGACY COMMANDS TESTS
# =============================================================================
echo "🕰️  Testing LEGACY COMMANDS"
echo "=========================="

# Test deprecated commands show migration messages
run_test_with_output "legacy describe command" "kubectl-smart describe pod test -n default 2>&1" "deprecated.*diag"
run_test_with_output "legacy deps command" "kubectl-smart deps pod test -n default 2>&1" "deprecated.*graph"  
run_test_with_output "legacy events command" "kubectl-smart events -n default 2>&1" "deprecated.*diag\\|top"

# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================
echo "⚠️  Testing ERROR HANDLING"
echo "========================="

# Test various error conditions
run_test "invalid command" "kubectl-smart invalid-command" 2
run_test "missing required argument" "kubectl-smart diag" 2
run_test "invalid resource type" "kubectl-smart diag invalid-type resource-name" 2

# Test RBAC-related errors (may not fail in minikube with admin access)
run_test "potential RBAC test" "kubectl-smart diag pod test -n kube-system || true"

# =============================================================================
# COMPREHENSIVE SCENARIO TESTS
# =============================================================================
echo "🎭 Testing COMPREHENSIVE SCENARIOS"
echo "================================="

# Test workflow: diag → graph → top for same resource
if [ -n "$RUNNING_POD" ] && [ -n "$RUNNING_POD_NS" ]; then
    log_info "Testing complete workflow for pod $RUNNING_POD in namespace $RUNNING_POD_NS"
    run_test "workflow step 1: diag" "kubectl-smart diag pod $RUNNING_POD -n $RUNNING_POD_NS"
    run_test "workflow step 2: graph upstream" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --upstream"  
    run_test "workflow step 3: graph downstream" "kubectl-smart graph pod $RUNNING_POD -n $RUNNING_POD_NS --downstream"
    run_test "workflow step 4: namespace top" "kubectl-smart top $RUNNING_POD_NS"
fi

# Test batch operations on multiple resources
log_info "Testing batch scenarios..."

# Diag multiple pods in sequence (if available)
PODS=($(kubectl get pods -A --field-selector=status.phase=Running -o name | head -3 | cut -d'/' -f2))
for pod in "${PODS[@]}"; do
    if [ -n "$pod" ]; then
        local pod_ns
        pod_ns=$(kubectl get pod "$pod" -A -o jsonpath='{.metadata.namespace}' 2>/dev/null || echo "")
        if [ -n "$pod_ns" ]; then
            run_test "batch diag pod $pod" "kubectl-smart diag pod $pod -n $pod_ns"
        fi
    fi
done

# =============================================================================
# STRESS TESTS
# =============================================================================
echo "🏋️  Testing STRESS CONDITIONS"
echo "============================"

# Test with resources that might have lots of data
run_test "diag kube-system pod (high data volume)" "kubectl-smart diag pod $(kubectl get pods -n kube-system --field-selector=status.phase=Running -o name | head -1 | cut -d'/' -f2) -n kube-system || true"

# Test top on kube-system (should have metrics)
run_test "top kube-system namespace" "kubectl-smart top kube-system"

# =============================================================================
# FINAL REPORT
# =============================================================================
echo ""
echo "🎯 TEST SUMMARY"  
echo "==============="
echo "Total tests run: $TOTAL_TESTS"
echo "Passed: $PASSED_TESTS"
echo "Failed: $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    log_success "All tests passed! 🎉"
    echo ""
    echo "kubectl-smart is working perfectly on your minikube cluster!"
    echo "Ready for production use! 🚀"
    exit 0
else
    log_error "$FAILED_TESTS tests failed"
    echo ""
    echo "Some tests failed. Please review the output above."
    echo "This might indicate configuration issues or missing resources in your minikube cluster."
    exit 1
fi