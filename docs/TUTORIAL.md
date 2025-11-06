# kubectl-smart Tutorial

Complete step-by-step guide to mastering kubectl-smart for Kubernetes debugging.

## Table of Contents

- [Getting Started](#getting-started)
- [Basic Diagnosis](#basic-diagnosis)
- [Dependency Analysis](#dependency-analysis)
- [Predictive Monitoring](#predictive-monitoring)
- [Advanced Features](#advanced-features)
- [Real-World Scenarios](#real-world-scenarios)

---

## Getting Started

### Prerequisites

Before using kubectl-smart, ensure you have:

1. **kubectl installed** (v1.20+)
2. **Python 3.9+**
3. **Access to a Kubernetes cluster**
4. **kubectl-smart installed**:
   ```bash
   pip install kubectl-smart
   ```

### Verify Installation

```bash
# Check version
kubectl-smart --version

# Run health checks
kubectl-smart --help
```

### First Steps

1. **Check cluster connectivity**:
   ```bash
   kubectl cluster-info
   ```

2. **List pods in your namespace**:
   ```bash
   kubectl get pods
   ```

3. **Run your first diagnosis**:
   ```bash
   kubectl-smart diag pod <pod-name>
   ```

---

## Basic Diagnosis

### Diagnosing a Pod

**Scenario**: Your pod is in CrashLoopBackOff state.

```bash
# Basic diagnosis
kubectl-smart diag pod my-failing-pod

# With namespace
kubectl-smart diag pod my-failing-pod -n production

# JSON output for automation
kubectl-smart diag pod my-failing-pod -o json
```

**Output Explanation**:

```
🔍 DIAGNOSIS: pod/my-failing-pod (namespace: default)
════════════════════════════════════════════════════════════

📊 SUMMARY
Status: CrashLoopBackOff
Health Score: 15/100

🔴 ROOT CAUSE (Score: 85)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reason: CrashLoopBackOff
Message: Back-off restarting failed container
Source: Pod Condition
Impact: HIGH - Container cannot start

📋 CONTRIBUTING FACTORS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Container exit code: 1
2. Restart count: 15

💡 SUGGESTED ACTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Inspect previous logs: kubectl logs my-failing-pod -p
2. Check container start command, readiness of dependencies, and exit code

🔧 AUTOMATED REMEDIATION OPTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Restart pod to clear crash loop
   Risk: 🟡 MEDIUM
   Status: ✅ Automated

   Command:
   kubectl delete pod my-failing-pod

   Details:
   • Deleting pod will trigger controller to create new one
     - Brief downtime during pod restart
```

### Diagnosing a Deployment

```bash
kubectl-smart diag deploy my-app

# With specific context
kubectl-smart diag deploy my-app --context staging
```

### Diagnosing Multiple Resources

```bash
# Diagnose all pods in a namespace
kubectl-smart diag pod --all -n production

# Output shows summary and top issues
```

---

## Dependency Analysis

### Viewing Downstream Dependencies

**Scenario**: You want to see what resources depend on your service.

```bash
# Show what depends on this service
kubectl-smart graph svc my-service --downstream

# Example output:
# svc/my-service
# ├── deploy/frontend
# │   └── rs/frontend-abc123
# │       └── pod/frontend-abc123-xyz
# └── deploy/backend
#     └── rs/backend-def456
#         └── pod/backend-def456-uvw
```

### Viewing Upstream Dependencies

**Scenario**: You want to see what your deployment depends on.

```bash
# Show what this deployment depends on
kubectl-smart graph deploy my-app --upstream

# Example output:
# deploy/my-app
# ├── svc/database
# ├── svc/cache
# └── secret/app-credentials
```

### Understanding the Graph

Health indicators in the graph:
- `✅` - Healthy
- `⚠️` - Warning
- `❌` - Critical issue

```bash
kubectl-smart graph deploy my-app --downstream
```

---

## Predictive Monitoring

### Forecasting Capacity Issues

**Scenario**: You want to predict if your namespace will run out of resources.

```bash
# 48-hour forecast (default)
kubectl-smart top production

# Custom forecast horizon
kubectl-smart top production --horizon=24  # 24 hours
kubectl-smart top production --horizon=168 # 1 week
```

**Output Explanation**:

```
📈 PREDICTIVE ANALYSIS: namespace/production
════════════════════════════════════════════════════════════

⏰ Forecast Horizon: 48 hours

🔴 CAPACITY WARNINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PVC: data-postgres-0
  Current: 85% (85GB/100GB)
  Predicted: 95% in 36 hours
  Action: Expand PVC or clean up data

Pod: worker-cpu-intensive
  Memory: Current 70%, will reach 90% in 24 hours
  Action: Increase memory limits

🔐 CERTIFICATE WARNINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Secret: api-tls
  Expires: 2025-11-18 (12 days)
  Used by: ingress/api-gateway
  Action: Renew certificate before expiration
```

### Monitoring Certificate Expiry

```bash
# Check certificates in namespace
kubectl-smart top kube-system

# JSON output for alerting
kubectl-smart top production -o json | jq '.certificate_warnings'
```

---

## Advanced Features

### Watch Mode

**Scenario**: Continuous monitoring of a failing pod.

```bash
# Watch pod every 5 seconds (default)
kubectl-smart diag pod failing-pod --watch

# Custom interval
kubectl-smart diag pod failing-pod --watch --interval=10

# Stop with Ctrl+C
```

**Output**:
```
👁️  Watching pod/failing-pod every 5s (Ctrl+C to stop)...

[2025-11-06 10:30:15] Status: CrashLoopBackOff, Issues: 3
[2025-11-06 10:30:20] Status: CrashLoopBackOff, Issues: 3
[2025-11-06 10:30:25] ⚠️  NEW ISSUE DETECTED: ImagePullBackOff
[2025-11-06 10:30:30] Status: ImagePullBackOff, Issues: 4

⏹️  Watch stopped
```

### Batch Operations

**Scenario**: Diagnose all failing pods in a namespace.

```bash
# Diagnose all pods
kubectl-smart diag pod --all -n production

# Filter by labels (future feature)
# kubectl-smart diag pod --all -n production --selector=app=frontend
```

**Output**:
```
📊 Batch Analysis: pod in namespace 'production'
════════════════════════════════════════════════════════════
Total resources: 45
With issues: 8
Healthy: 35
Failed: 2

🔍 Top Issues:
  • pod/worker-1: CRITICAL - CrashLoopBackOff
  • pod/worker-2: CRITICAL - OOMKilled
  • pod/api-3: WARNING - High restart count
  • pod/db-primary: WARNING - Disk pressure
```

### JSON Output for Automation

**Scenario**: Integrate kubectl-smart with monitoring/alerting.

```bash
# Get diagnosis in JSON
kubectl-smart diag pod my-pod -o json > diagnosis.json

# Parse with jq
kubectl-smart diag pod my-pod -o json | jq '.root_cause'

# Check exit code in scripts
kubectl-smart diag pod my-pod
if [ $? -eq 2 ]; then
  echo "Critical issues found!"
  # Send alert
fi
```

**JSON Structure**:
```json
{
  "command": "diag",
  "timestamp": "2025-11-06T10:30:00Z",
  "summary": {
    "total_issues": 3,
    "critical_issues": 1,
    "warning_issues": 2
  },
  "root_cause": {
    "reason": "CrashLoopBackOff",
    "message": "Back-off restarting failed container",
    "severity": "critical",
    "score": 85
  },
  "suggested_actions": [
    "kubectl logs my-pod -p"
  ]
}
```

### Configuration File

**Scenario**: Customize kubectl-smart behavior globally.

1. **Create config file**:
   ```bash
   mkdir -p ~/.kubectl-smart
   cat > ~/.kubectl-smart/config.yaml <<EOF
   output:
     colors_enabled: true
     max_display_issues: 15
     default_format: text

   performance:
     max_concurrent_collectors: 10
     collector_timeout_seconds: 15.0

   logging:
     enabled: true
     level: INFO
     file: ~/.kubectl-smart/logs/kubectl-smart.log
   EOF
   ```

2. **Test configuration**:
   ```bash
   kubectl-smart diag pod my-pod
   ```

---

## Real-World Scenarios

### Scenario 1: Production Outage

**Problem**: Production API is down.

**Steps**:

1. **Quick diagnosis**:
   ```bash
   kubectl-smart diag deploy api-gateway -n production
   ```

2. **Check dependencies**:
   ```bash
   kubectl-smart graph deploy api-gateway --upstream -n production
   ```

3. **Look for issues in dependent services**:
   ```bash
   # If graph shows dependency on database service
   kubectl-smart diag svc database -n production
   ```

4. **Check all pods**:
   ```bash
   kubectl-smart diag pod --all -n production
   ```

**Result**: Found that database service has no healthy endpoints.

### Scenario 2: Memory Leak Investigation

**Problem**: Pods are being OOMKilled frequently.

**Steps**:

1. **Diagnose the pod**:
   ```bash
   kubectl-smart diag pod worker-123 -n production
   ```

2. **Watch memory usage**:
   ```bash
   kubectl-smart diag pod worker-123 -n production --watch --interval=10
   ```

3. **Predictive analysis**:
   ```bash
   kubectl-smart top production --horizon=24
   ```

4. **Check automated remediation**:
   ```
   🔧 AUTOMATED REMEDIATION OPTIONS
   1. Increase memory limits for worker-123
      Risk: 🟢 LOW
      Command:
      kubectl set resources deployment worker --limits=memory=512Mi -n production
   ```

**Result**: Increased memory limits, monitoring for 24 hours.

### Scenario 3: Certificate Expiry

**Problem**: Need to audit certificates across all namespaces.

**Steps**:

1. **Check production certificates**:
   ```bash
   kubectl-smart top production -o json | jq '.certificate_warnings'
   ```

2. **Check system certificates**:
   ```bash
   kubectl-smart top kube-system
   ```

3. **Automated monitoring** (cron job):
   ```bash
   #!/bin/bash
   # Check certificates daily
   WARNINGS=$(kubectl-smart top production -o json | jq -r '.certificate_warnings | length')
   if [ "$WARNINGS" -gt 0 ]; then
     echo "Certificate warnings detected!"
     kubectl-smart top production | mail -s "Certificate Alert" admin@example.com
   fi
   ```

**Result**: Set up daily automated certificate monitoring.

### Scenario 4: New Deployment Validation

**Problem**: Verify new deployment is healthy.

**Steps**:

1. **Deploy application**:
   ```bash
   kubectl apply -f deployment.yaml
   ```

2. **Wait for rollout**:
   ```bash
   kubectl rollout status deploy/my-app
   ```

3. **Diagnose**:
   ```bash
   kubectl-smart diag deploy my-app
   ```

4. **Check dependencies**:
   ```bash
   kubectl-smart graph deploy my-app --downstream
   ```

5. **Continuous monitoring**:
   ```bash
   kubectl-smart diag pod my-app-xyz --watch
   ```

**Result**: Deployment is healthy, no issues detected.

### Scenario 5: Capacity Planning

**Problem**: Planning for Black Friday traffic spike.

**Steps**:

1. **Current resource usage**:
   ```bash
   kubectl-smart top production
   ```

2. **Forecast for next week**:
   ```bash
   kubectl-smart top production --horizon=168
   ```

3. **Check all namespaces**:
   ```bash
   for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
     echo "Namespace: $ns"
     kubectl-smart top $ns --horizon=168
   done
   ```

4. **JSON output for capacity report**:
   ```bash
   kubectl-smart top production -o json > capacity-report.json
   ```

**Result**: Identified PVCs that need expansion, planned node scaling.

---

## Next Steps

- [Troubleshooting Guide](TROUBLESHOOTING.md) - Common issues and solutions
- [Best Practices](BEST_PRACTICES.md) - Recommended usage patterns
- [Integrations](INTEGRATIONS.md) - CI/CD and monitoring integration
- [FAQ](FAQ.md) - Frequently asked questions

---

## Quick Reference

### Common Commands

```bash
# Basic diagnosis
kubectl-smart diag pod <name> [-n namespace]

# Watch mode
kubectl-smart diag pod <name> --watch [--interval=5]

# Batch analysis
kubectl-smart diag pod --all -n <namespace>

# Dependency graph
kubectl-smart graph <type> <name> [--upstream|--downstream]

# Predictive analysis
kubectl-smart top <namespace> [--horizon=48]

# JSON output
kubectl-smart <command> -o json
```

### Exit Codes

- `0` - No issues (score < 50)
- `1` - Warnings detected (score 50-89)
- `2` - Critical issues or errors (score ≥ 90)

### Getting Help

```bash
# Command help
kubectl-smart --help
kubectl-smart diag --help
kubectl-smart graph --help
kubectl-smart top --help

# Version
kubectl-smart --version
```
