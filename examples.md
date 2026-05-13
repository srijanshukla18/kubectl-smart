# kubectl-smart Examples - Complete Guide

This guide shows kubectl-smart's capabilities with real-world examples and use cases.

## 🚀 Quick Start

```bash
# Install kubectl-smart
./install.sh

# Check it's working
kubectl-smart --help
kubectl-smart --version
```

## 📋 The Three Core Commands

kubectl-smart provides three focused commands for common Kubernetes debugging scenarios:

### 1. 🔍 `diag` - Root-Cause Analysis
**When to use**: When something is broken and you need to know why

### 2. 🔗 `graph` - Dependency Visualization  
**When to use**: When you need to understand what depends on what (blast radius analysis)

### 3. 📈 `top` - Predictive Capacity & Certificate Outlook
**When to use**: When you want to prevent future problems

---

## 🔍 DIAG Command - Complete Examples

### Basic Pod Diagnosis

```bash
# Diagnose a failing pod
kubectl-smart diag pod failing-app-xyz

# Diagnose with namespace specified
kubectl-smart diag pod failing-app-xyz -n production

# Diagnose with specific context
kubectl-smart diag pod failing-app-xyz -n staging --context=staging-cluster

# For local demos/tests, set a default context once
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
```

**Sample Output:**
```
📋 DIAGNOSIS: Pod/production/failing-app-xyz
Status: CrashLoopBackOff

🔴 LIKELY ROOT CAUSE
  💥 CrashLoopBackOff: failing-app-xyz (score: 85.0)
    Container exits immediately after start, in restart loop
    Evidence:
    • Event Warning/BackOff: Back-off restarting failed container

🟡 CONTRIBUTING FACTORS
  ⚠️ ImagePullBackOff: failing-app-xyz (score: 75.0)
    Failed to pull image "invalid-registry.com/app:latest"
  📋 Event: Back-off restarting failed container (score: 65.0)

💡 SUGGESTED ACTIONS
  1. kubectl logs failing-app-xyz -n production
  2. docker pull invalid-registry.com/app:latest
  3. kubectl get secrets -n production
  4. Review container spec (resources, env, command)

⏱️  Analysis completed in 1.2s
```

### All Resource Types

```bash
# Pods
kubectl-smart diag pod my-pod -n default

# Deployments  
kubectl-smart diag deploy my-deployment -n production
kubectl-smart diag deployment my-deployment -n production  # full name also works

# StatefulSets
kubectl-smart diag sts my-statefulset -n database
kubectl-smart diag statefulset my-statefulset -n database

# Jobs
kubectl-smart diag job my-batch-job -n data-processing

# Services
kubectl-smart diag svc my-service -n api
kubectl-smart diag service my-service -n api

# ReplicaSets
kubectl-smart diag rs my-replicaset -n web

# DaemonSets  
kubectl-smart diag ds my-daemonset -n monitoring
kubectl-smart diag daemonset my-daemonset -n monitoring
```

### Output

```bash
# Default terminal output (colorized, human-readable)
kubectl-smart diag pod my-pod
```

### Exit Codes & Automation

kubectl-smart diag returns automation-friendly exit codes:

```bash
# Exit code 0: No issues detected
kubectl-smart diag pod healthy-pod >/dev/null
echo $?  # 0

# Exit code 2: Issues detected (warning or critical)
kubectl-smart diag pod failing-pod >/dev/null
echo $?  # 2

# Use in scripts
kubectl-smart diag pod "$POD_NAME" -n "$NAMESPACE" >/dev/null
exit_code=$?
if [ $exit_code -ne 0 ]; then
  echo "Issues detected in $POD_NAME (exit=$exit_code)"
  # Optional: print details for humans
  kubectl-smart diag pod "$POD_NAME" -n "$NAMESPACE"
fi
```

---

## 🔗 GRAPH Command - Complete Examples

### Basic Dependency Visualization

```bash
# Show what depends on this service (downstream)
kubectl-smart graph svc frontend-service --downstream

# Show what this pod depends on (upstream)
kubectl-smart graph pod api-pod --upstream  

# Show both directions
kubectl-smart graph pod api-pod --upstream --downstream
```

**Sample Output (clean ASCII tree):**
```
🔗 DEPENDENCY GRAPH: Pod/default/api-pod

📊 UPSTREAM DEPENDENCIES (what api-pod depends on):
api-pod
├── ConfigMap/api-config ✅
├── Secret/api-secrets ✅
├── Service/database-svc ⚠️
│   └── Pod/database-pod ❌
└── PersistentVolumeClaim/api-storage ✅

📊 DOWNSTREAM DEPENDENCIES (what depends on api-pod):
api-pod
├── Service/api-service ✅
│   └── Ingress/api-ingress ✅
└── HorizontalPodAutoscaler/api-hpa ⚠️

🔍 LEGEND:
✅ Healthy   ⚠️ Warning   ❌ Critical

📊 GRAPH STATISTICS
  Resources: 8
  Dependencies: 6
  Upstream: 4
  Downstream: 3

⏱️  Analysis completed in 0.8s
```

### Direction Options

```bash  
# Default: show downstream (what depends on this)
kubectl-smart graph pod my-pod

# Explicitly show downstream
kubectl-smart graph pod my-pod --downstream

# Show upstream (what this depends on)
kubectl-smart graph pod my-pod --upstream

# Show complete picture (both directions)
kubectl-smart graph pod my-pod --upstream --downstream
```

### All Resource Types with Graph

```bash
# Pods - see container dependencies, volumes, configs
kubectl-smart graph pod checkout-pod --upstream

# Deployments - see full application stack  
kubectl-smart graph deploy web-app --downstream

# Services - see what uses this service and what it connects to
kubectl-smart graph svc api-service --upstream --downstream

# StatefulSets - see persistent storage and network dependencies
kubectl-smart graph sts database --upstream

# Jobs - see data pipeline dependencies
kubectl-smart graph job data-processor --upstream

# ReplicaSets - see controller dependencies
kubectl-smart graph rs web-rs --downstream

# DaemonSets - see node-level dependencies
kubectl-smart graph ds log-collector --upstream
```

### Output

```bash
# Human-readable ASCII tree (default)
kubectl-smart graph pod my-pod --upstream
```

### Real-World Graph Scenarios

**1. Blast Radius Analysis**
```bash
# "If I delete this service, what breaks?"
kubectl-smart graph svc critical-service --downstream

# "If this database goes down, what's affected?"  
kubectl-smart graph sts postgres-db --downstream
```

**2. Dependency Troubleshooting**
```bash
# "My pod won't start - what does it need?"
kubectl-smart graph pod failing-pod --upstream

# "This service is slow - what's it waiting for?"
kubectl-smart graph svc slow-service --upstream
```

**3. Security Analysis**
```bash
# "What has access to this sensitive service?"
kubectl-smart graph svc sensitive-api --downstream

# "What external resources does this pod access?"
kubectl-smart graph pod suspicious-pod --upstream
```

---

## 📈 TOP Command - Complete Examples

### Namespace Capacity Forecasting

```bash
# Default 48-hour forecast for namespace
kubectl-smart top production

# 24-hour forecast  
kubectl-smart top production --horizon=24

# 7-day forecast (168 hours)
kubectl-smart top production --horizon=168

# Minimal 1-hour forecast
kubectl-smart top production --horizon=1
```

**Sample Output:**
```
📈 PREDICTIVE OUTLOOK: namespace production
Forecast horizon: 48h

🔒 CERTIFICATE WARNINGS (2)
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Resource             ┃ Type       ┃ Expires              ┃ Days Left ┃ Action                     ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Secret/prod/api-tls  │ tls_secret │ 2024-01-15T12:00:00Z │ 8         │ Renew certificate          │
│                      │            │                      │           │ before expiry              │
│ Secret/prod/internal │ tls_secret │ 2024-01-19T12:00:00Z │ 12        │ Schedule rotation          │
└──────────────────────┴────────────┴──────────────────────┴───────────┴────────────────────────────┘

⚠️ CAPACITY WARNINGS
  🔴 Memory: 94% utilization predicted in 36h
    Current: 78% → Projected: 94%
    Affected: api-deployment (3/3 pods)
    Action: Scale horizontally or increase limits

⏱️  Analysis completed in 1.1s

[Note] Some signals (PVC disk usage, CPU/memory trends) need metrics-server and kubelet metrics. If unavailable, `top` succeeds but shows limited output.
```

### Different Namespaces

```bash
# Production workloads
kubectl-smart top production

# Development environment  
kubectl-smart top development

# System components
kubectl-smart top kube-system

# Monitoring stack
kubectl-smart top monitoring

# Database namespace
kubectl-smart top database
```

### Horizon Options

```bash
# Short-term (1-6 hours) - for immediate capacity planning
kubectl-smart top api --horizon=1
kubectl-smart top api --horizon=6

# Medium-term (12-48 hours) - for daily operations  
kubectl-smart top web --horizon=12
kubectl-smart top web --horizon=48

# Long-term (3-7 days) - for weekly planning
kubectl-smart top data --horizon=72   # 3 days
kubectl-smart top data --horizon=168  # 7 days (max)
```

### Output

```bash
# Human-readable forecast (default)
kubectl-smart top production
```

### Real-World TOP Scenarios

**1. Capacity Planning**
```bash
# Weekly capacity review
kubectl-smart top production --horizon=168

# Pre-deployment capacity check  
kubectl-smart top staging --horizon=24

# Post-incident capacity validation
kubectl-smart top api --horizon=6
```

**2. Certificate Management**
```bash
# Monthly certificate audit (human-readable)
for ns in production staging development; do
    echo "=== $ns ==="
    kubectl-smart top "$ns" --horizon=168  # 7 days (max)
done
```

**3. Capacity Review**
```bash
# Identify scaling opportunities
kubectl-smart top microservices --horizon=72
```

---

## 🌐 Global Options & Advanced Usage

### Debug Mode

```bash
# Enable debug logging for troubleshooting
kubectl-smart --debug diag pod my-pod

# Debug with any command
kubectl-smart --debug graph svc my-service --upstream
kubectl-smart --debug top production
```

### Suppress Output in Scripts

Use shell redirection to suppress output when only exit codes are needed:

```bash
if kubectl-smart diag pod "$CRITICAL_POD" >/dev/null; then
  echo "All good"
else
  echo "Issue detected, exit code: $?"
fi
```

### Context Switching

```bash
# Use specific kubectl context
kubectl-smart diag pod my-pod --context=production-cluster
kubectl-smart graph svc my-svc --context=staging-cluster  
kubectl-smart top default --context=dev-cluster

# Or pin a default context for repeated local demo/test commands
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
kubectl-smart diag pod my-pod -n default

# Combine with namespace
kubectl-smart diag pod api-pod -n api --context=prod-east
```

### Combining Options

```bash
# Debug mode
kubectl-smart --debug diag pod my-pod

# Context + namespace
kubectl-smart graph svc api --context=production --upstream -n api
```

---

## 🎭 Real-World Scenarios & Workflows

### Incident Response Workflow

**Step 1: Initial Triage**
```bash
# Quick health check
# Note: use shell redirection to suppress output
kubectl-smart diag pod $FAILING_POD -n $NAMESPACE >/dev/null
exit_code=$?

if [ $exit_code -eq 2 ]; then
    echo "CRITICAL: Immediate attention required"
fi
```

**Step 2: Root Cause Analysis**
```bash
# Get detailed diagnosis
kubectl-smart diag pod $FAILING_POD -n $NAMESPACE

# Check dependencies that might be affected
kubectl-smart graph pod $FAILING_POD -n $NAMESPACE --upstream --downstream
```

**Step 3: Impact Assessment**
```bash
# Check blast radius - what else might be affected
kubectl-smart graph svc $RELATED_SERVICE --downstream

# Check if this will cause capacity issues
kubectl-smart top $NAMESPACE --horizon=6
```

### Pre-Deployment Validation

```bash
#!/bin/bash
# pre-deploy-check.sh

NAMESPACE=$1
APP_NAME=$2

echo "Pre-deployment validation for $APP_NAME in $NAMESPACE"

# Check current capacity
echo "=== Capacity Check ==="
kubectl-smart top $NAMESPACE --horizon=24

# Check dependencies are healthy
echo "=== Dependency Check ==="  
kubectl-smart graph deploy $APP_NAME -n $NAMESPACE --upstream

# Overall namespace health
echo "=== Health Summary ==="
for resource in $(kubectl get pods -n $NAMESPACE -o name); do
    kubectl-smart diag $resource >/dev/null
    if [ $? -ne 0 ]; then
        echo "⚠️  $resource has issues"
    fi
done
```

### Daily Health Check

```bash
#!/bin/bash
# daily-health-check.sh

CRITICAL_NAMESPACES=("production" "api" "database")

for ns in "${CRITICAL_NAMESPACES[@]}"; do
    echo "=== Daily Health Check: $ns ==="
    
    # Capacity forecast
    kubectl-smart top $ns --horizon=48
    
    # Check all deployments
    for deploy in $(kubectl get deployments -n $ns -o name); do
        kubectl-smart diag $deploy >/dev/null
        if [ $? -ne 0 ]; then
            echo "❌ Issues found in $deploy"
            kubectl-smart diag $deploy  # Full details
        fi
    done
    
    echo ""
done
```

### Certificate Monitoring

```bash
#!/bin/bash
# cert-monitor.sh - Quick scan across all namespaces (human-readable)

for ns in $(kubectl get namespaces -o name | cut -d'/' -f2); do
  out=$(kubectl-smart top "$ns" --horizon=168 2>/dev/null)
  if echo "$out" | grep -q "CERTIFICATE WARNINGS"; then
    echo "=== $ns ==="
    echo "$out" | sed -n '/CERTIFICATE WARNINGS/,$p' | sed -n '1,10p'
  fi
done
```

### Automated Checks

```bash
# Fail a pipeline if capacity warnings show up
out=$(kubectl-smart top production --horizon=24)
echo "$out"
echo "$out" | grep -q "CAPACITY WARNINGS" && exit 1 || true
```

---

## 🔧 Troubleshooting & Tips

### Common Issues

**1. Permission Errors**
```bash
# Check RBAC permissions
kubectl auth can-i get pods --all-namespaces

# kubectl-smart gracefully handles RBAC issues
kubectl-smart diag pod my-pod  # Will show what it can access
```

**2. Context Issues**
```bash
# Check current context before running kubectl directly
kubectl config current-context

# List available contexts
kubectl config get-contexts

# For demos, prefer explicit contexts over switching global state
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
```

**3. Slow Performance**
```bash
# Enable debug mode to see what's taking time
kubectl-smart --debug diag pod slow-pod

# Use redirection for faster automation
kubectl-smart diag pod my-pod >/dev/null
```

### Best Practices

**1. Use Appropriate Horizons**
- Immediate issues: `--horizon=1` to `--horizon=6`
- Daily planning: `--horizon=24` to `--horizon=48` (default)
- Weekly planning: `--horizon=168`

**2. Combine Commands**
```bash
# Full investigation workflow
kubectl-smart diag pod $POD          # What's wrong?
kubectl-smart graph pod $POD --upstream  # What does it need?
kubectl-smart top $NAMESPACE         # Will this cause more issues?
```

**3. Automation-Friendly**
```bash
# Always check exit codes
if kubectl-smart diag pod $POD >/dev/null; then
    status="healthy"
else
    status="unhealthy"
    details=$(kubectl-smart diag pod $POD)
fi
```

---

## 📊 Performance Characteristics

kubectl-smart is designed for production use with bounded, read-only collection:

- **Startup path**: lazy imports keep help/version commands lightweight
- **Execution path**: collectors run asynchronously with per-command timeouts
- **Network calls**: limited to kubectl read operations and optional metrics sources
- **Read-only operations**: never modifies your cluster

### Performance Testing

```bash
# Test help performance
time kubectl-smart --help

# Test command performance
time kubectl-smart diag pod my-pod
time kubectl-smart graph svc my-service --upstream  
time kubectl-smart top production
```

---

## 🚀 Integration Examples

### CI/CD Pipeline Integration

**GitHub Actions Example:**
```yaml
- name: Health Check
  run: |
    if kubectl-smart diag deploy ${{ env.APP_NAME }} -n ${{ env.NAMESPACE }} >/dev/null; then
      echo "Deployment healthy"
    else
      echo "Deployment health check failed"
      kubectl-smart diag deploy ${{ env.APP_NAME }} -n ${{ env.NAMESPACE }}
      exit 1
    fi

- name: Capacity Check  
  run: |
    out=$(kubectl-smart top ${{ env.NAMESPACE }} --horizon=24)
    echo "$out"
    echo "$out" | grep -q "CAPACITY WARNINGS" && exit 1 || true
```

### Monitoring Integration

kubectl-smart is human-first output. For automation, rely on exit codes (diag) and simple text checks (top).

---

This guide covers kubectl-smart's current capabilities. The tool is designed to help with Kubernetes debugging by providing structured analysis and issue prioritization. 

> ⚠️ **Beta software** - Please report any issues or share feedback on your experience!
