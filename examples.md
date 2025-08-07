# kubectl-smart Examples - Complete Guide

This guide shows you **everything** kubectl-smart can do with real-world examples and use cases.

## 🚀 Quick Start

```bash
# Install kubectl-smart
./install.sh

# Check it's working
kubectl-smart --help
kubectl-smart --version
```

## 📋 The Three Core Commands

kubectl-smart provides exactly three commands that cover all Kubernetes debugging scenarios:

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
```

**Sample Output:**
```
📋 DIAGNOSIS: Pod/production/failing-app-xyz
Status: CrashLoopBackOff

🔴 ROOT CAUSE
  💥 CrashLoopBackOff: failing-app-xyz (score: 85.0)
    Container exits immediately after start, in restart loop

🟡 CONTRIBUTING FACTORS  
  ⚠️ ImagePullBackOff: failing-app-xyz (score: 75.0)
    Failed to pull image "invalid-registry.com/app:latest"
  📋 Event: Back-off restarting failed container (score: 65.0)

💡 SUGGESTED ACTIONS
  1. Check container logs: kubectl logs failing-app-xyz -n production
  2. Verify image exists: docker pull invalid-registry.com/app:latest
  3. Check image pull secrets: kubectl get secrets -n production
  4. Review container configuration in deployment

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

### Output Formats

```bash
# Default terminal output (colorized, human-readable)
kubectl-smart diag pod my-pod

# JSON output for automation
kubectl-smart diag pod my-pod --json
kubectl-smart diag pod my-pod --format=json
kubectl-smart diag pod my-pod -o json

# Silent mode (only exit codes, no output)
kubectl-smart diag pod my-pod --quiet
kubectl-smart diag pod my-pod -q
```

**JSON Output Sample:**
```json
{
  "subject": "Pod/default/my-pod",
  "status": "Running", 
  "root_cause": {
    "issue": "HighMemoryUsage",
    "score": 78.0,
    "description": "Memory usage at 89% of limit"
  },
  "contributing_factors": [
    {
      "issue": "CPUThrottling", 
      "score": 65.0,
      "description": "CPU being throttled due to limits"
    }
  ],
  "suggested_actions": [
    "Consider increasing memory limits",
    "Review resource requests and limits",
    "Check for memory leaks in application"
  ],
  "exit_code": 1,
  "analysis_duration": "1.45s"
}
```

### Exit Codes & Automation

kubectl-smart diag returns meaningful exit codes for automation:

```bash
# Exit code 0: No critical issues (score < 50)
kubectl-smart diag pod healthy-pod -q
echo $?  # 0

# Exit code 1: Warning issues (score 50-89)  
kubectl-smart diag pod slow-pod -q
echo $?  # 1

# Exit code 2: Critical issues (score ≥ 90)
kubectl-smart diag pod failing-pod -q  
echo $?  # 2

# Use in scripts
if kubectl-smart diag pod $POD_NAME -q; then
    echo "Pod is healthy"
else
    exit_code=$?
    if [ $exit_code -eq 1 ]; then
        echo "Pod has warnings"
        # Send alert
    elif [ $exit_code -eq 2 ]; then  
        echo "Pod is critically broken"
        # Page on-call
    fi
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

**Sample Output:**
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
✅ Healthy   ⚠️  Warning   ❌ Critical

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

### Output Formats

```bash
# Human-readable ASCII tree (default)
kubectl-smart graph pod my-pod --upstream

# JSON for automation/tooling
kubectl-smart graph pod my-pod --upstream --json

# Use JSON with jq for processing
kubectl-smart graph pod my-pod --upstream --json | jq '.dependencies[]'
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
kubectl-smart top production -h 24

# 7-day forecast (168 hours)
kubectl-smart top production --horizon=168

# Minimal 1-hour forecast
kubectl-smart top production --horizon=1
```

**Sample Output:**
```
📈 PREDICTIVE OUTLOOK: namespace production
Forecast horizon: 48h

⚠️  CAPACITY WARNINGS
  🔴 Memory: 94% utilization predicted in 36h
    Current: 78% → Projected: 94% 
    Affected: api-deployment (3/3 pods)
    Action: Scale horizontally or increase limits

  🟡 CPU: 87% utilization predicted in 42h  
    Current: 65% → Projected: 87%
    Affected: worker-deployment (5/5 pods)
    Action: Consider CPU limits review

🔒 CERTIFICATE WARNINGS  
  🔴 Expires in 8 days: api-tls-secret
    Used by: api-ingress, api-service
    Action: Renew certificate before 2024-01-15
    
  🟡 Expires in 12 days: internal-ca-cert
    Used by: 5 workloads
    Action: Plan certificate rotation

📊 FORECAST SUMMARY
  Resources analyzed: 15
  Capacity risks: 2 critical, 1 warning
  Certificate risks: 1 critical, 1 warning
  
💡 RECOMMENDED ACTIONS
  1. Scale api-deployment: kubectl scale deploy api-deployment --replicas=5
  2. Increase worker memory limits in deployment spec
  3. Renew api-tls-secret: kubectl create secret tls api-tls-secret --cert=...
  4. Schedule internal-ca-cert renewal

⏱️  Analysis completed in 1.1s
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

### Output Formats

```bash
# Human-readable forecast (default)
kubectl-smart top production

# JSON for automation
kubectl-smart top production --json

# Use with monitoring systems
kubectl-smart top production --json | jq '.warnings[] | select(.severity == "critical")'
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
# Monthly certificate audit
for ns in production staging development; do
    echo "=== $ns ==="
    kubectl-smart top $ns --horizon=720  # 30 days
done
```

**3. Cost Optimization**
```bash
# Find over-provisioned namespaces
kubectl-smart top expensive-app --json | jq '.forecast.utilization'

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

### Quiet Mode

```bash
# Silent execution (only exit codes)
kubectl-smart --quiet diag pod my-pod
kubectl-smart -q diag pod my-pod

# Perfect for scripts and automation
if kubectl-smart -q diag pod $CRITICAL_POD; then
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

# Combine with namespace
kubectl-smart diag pod api-pod -n api --context=prod-east
```

### Combining Options

```bash
# Debug mode + JSON output
kubectl-smart --debug diag pod my-pod --json

# Quiet mode + specific context
kubectl-smart -q graph svc api --context=production --upstream

# All options combined
kubectl-smart --debug diag deploy my-app -n production --context=prod-cluster --json
```

---

## 🎭 Real-World Scenarios & Workflows

### Incident Response Workflow

**Step 1: Initial Triage**
```bash
# Quick health check
kubectl-smart diag pod $FAILING_POD -n $NAMESPACE -q
exit_code=$?

if [ $exit_code -eq 2 ]; then
    echo "CRITICAL: Immediate attention required"
elif [ $exit_code -eq 1 ]; then  
    echo "WARNING: Investigation needed"
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
    kubectl-smart diag $resource -q
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
        kubectl-smart diag $deploy -q
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
# cert-monitor.sh - Check certificate expiration across all namespaces

echo "🔒 Certificate Expiration Report"
echo "==============================="

for ns in $(kubectl get namespaces -o name | cut -d'/' -f2); do
    output=$(kubectl-smart top $ns --horizon=336 --json 2>/dev/null)  # 14 days
    
    if echo "$output" | jq -e '.certificate_warnings[]' >/dev/null 2>&1; then
        echo "Namespace: $ns"
        echo "$output" | jq -r '.certificate_warnings[] | "  ⚠️  \(.name) expires in \(.days_remaining) days"'
        echo ""
    fi
done
```

### Automated Scaling Decisions

```bash
#!/bin/bash
# auto-scaler.sh - Scale based on kubectl-smart predictions

NAMESPACE=$1
THRESHOLD=90

forecast=$(kubectl-smart top $NAMESPACE --horizon=12 --json)

# Check CPU predictions
cpu_prediction=$(echo "$forecast" | jq -r '.predictions.cpu.utilization_percentage')

if [ "$cpu_prediction" -gt "$THRESHOLD" ]; then
    echo "CPU utilization will reach $cpu_prediction% - scaling up"
    
    # Find deployments to scale
    deployments=$(echo "$forecast" | jq -r '.predictions.cpu.affected_resources[]')
    
    for deploy in $deployments; do
        current_replicas=$(kubectl get deploy $deploy -n $NAMESPACE -o jsonpath='{.spec.replicas}')
        new_replicas=$((current_replicas + 2))
        
        echo "Scaling $deploy from $current_replicas to $new_replicas"
        kubectl scale deploy $deploy -n $NAMESPACE --replicas=$new_replicas
    done
fi
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
# Check current context
kubectl config current-context

# List available contexts
kubectl config get-contexts

# Switch context
kubectl config use-context minikube
```

**3. Slow Performance**
```bash
# Enable debug mode to see what's taking time
kubectl-smart --debug diag pod slow-pod

# Use quiet mode for faster automation
kubectl-smart -q diag pod my-pod
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
# Always use --quiet for scripts
# Always use --json for parsing
# Always check exit codes

if kubectl-smart diag pod $POD -q; then
    status="healthy"
else
    status="unhealthy"
    details=$(kubectl-smart diag pod $POD --json)
fi
```

---

## 📊 Performance Characteristics

kubectl-smart is designed for production use with these performance guarantees:

- **Startup time**: ~0.8s (help/version commands)
- **Execution time**: ≤3s on 2k-resource clusters
- **Memory usage**: <100MB
- **Network calls**: Minimized with intelligent caching
- **Read-only operations**: Never modifies your cluster

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
    if ! kubectl-smart diag deploy ${{ env.APP_NAME }} -n ${{ env.NAMESPACE }} -q; then
      echo "Deployment health check failed"
      kubectl-smart diag deploy ${{ env.APP_NAME }} -n ${{ env.NAMESPACE }}
      exit 1
    fi

- name: Capacity Check  
  run: |
    kubectl-smart top ${{ env.NAMESPACE }} --horizon=24 --json > capacity.json
    if jq -e '.warnings[] | select(.severity == "critical")' capacity.json; then
      echo "Critical capacity warnings detected"
      exit 1
    fi
```

### Monitoring Integration

**Prometheus/Grafana:**
```bash
# Export metrics to Prometheus format
kubectl-smart top production --json | jq '.predictions' > /tmp/kubectl-smart-metrics.json
```

**Alert Manager:**
```bash  
# Certificate expiration alerts
kubectl-smart top production --json | \
  jq '.certificate_warnings[] | select(.days_remaining < 7)' | \
  while read cert; do
    # Send alert
    echo "Certificate expiring: $cert"
  done
```

---

This comprehensive guide shows you everything kubectl-smart can do. It's designed to be your intelligent co-pilot for Kubernetes debugging - turning chaos into clarity, and reactive troubleshooting into proactive problem prevention! 🎯