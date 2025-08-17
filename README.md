# kubectl-smart

## 🎯 What is kubectl-smart?

**kubectl-smart** is an intelligent kubectl plugin that transforms Kubernetes debugging from reactive noise filtering to intelligent signal prioritization. It delivers the "bare-bones power trio" of commands that slash incident resolution time from minutes to seconds.

**Read-only operations only** - Safe to run in production, never modifies your cluster.

## 🚀 Quick Start

```bash
# One-command installation using uv
./install.sh

# Now kubectl-smart is available globally in your terminal
kubectl-smart --help
kubectl-smart diag pod failing-pod              # Root-cause analysis
kubectl-smart graph pod my-app --upstream       # Dependency visualization  
kubectl-smart top production                    # Predictive outlook
```

## 🎯 The Three Commands

### 1. `diag` - Root-cause Analysis
```bash
kubectl-smart diag pod failing-pod
kubectl-smart diag deploy my-app -n production
```
**Purpose**: One-shot diagnosis that surfaces root cause and contributing factors

### 2. `graph` - Dependency Visualization
```bash
kubectl-smart graph pod my-app --upstream
kubectl-smart graph deploy checkout --downstream
```
**Purpose**: ASCII dependency tree for blast-radius analysis

### 3. `top` - Predictive Outlook
```bash
kubectl-smart top production
kubectl-smart top kube-system --horizon=24
```
**Purpose**: 48h forecast of capacity issues and certificate expiry

Data sources and behavior:
- CPU/Memory: metrics-server (`kubectl top`) snapshot; forecasts improve across runs using a small local cache.
- PVC Disk usage: kubelet Prometheus metrics (kubelet_volume_stats_* via API proxy). If unavailable, output notes that signals may be limited.
- Certificate expiry: parses Secret `tls.crt` via X.509; warns when ≤ 14 days.
- Read-only; no cluster writes. If a source is unavailable, `top` succeeds but shows no warnings and prints a note.

Requirements and graceful degradation:
- For full predictions, ensure metrics-server is installed and kubelet metrics accessible via API proxy.
- If metrics-server is absent or kubelet metrics are blocked by RBAC, `top` still runs and prints a note indicating limited signals.

## ✨ Visual Preview

Below are sample, outputs so you can see how kubectl-smart renders information.

### 🔍 diag (root-cause analysis)

```
📋 DIAGNOSIS: Pod/production/failing-app-xyz
Status: CrashLoopBackOff

🔴 ROOT CAUSE
  💥 CrashLoopBackOff: failing-app-xyz (score: 85.0)
    Container exits immediately after start, in restart loop

🟡 CONTRIBUTING FACTORS
  ⚠️ ImagePullBackOff: failing-app-xyz (score: 75.0)
    Failed to pull image "invalid-registry.com/app:latest"

💡 SUGGESTED ACTIONS
  1. kubectl logs failing-app-xyz -n production
  2. docker pull invalid-registry.com/app:latest
  3. kubectl get secrets -n production

⏱️  Analysis completed in 1.2s
```

### 🔗 graph (dependency visualization)

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

⏱️  Analysis completed in 0.8s
```

### 📈 top (predictive outlook)

```
📈 PREDICTIVE OUTLOOK: namespace production
Forecast horizon: 48h

🔒 CERTIFICATE WARNINGS (1)
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Resource         ┃ Type       ┃ Expires              ┃ Days Left ┃ Action               ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Secret/prod/tls  │ tls_secret │ 2024-01-15T12:00:00Z │ 8         │ Renew before expiry  │
└──────────────────┴────────────┴──────────────────────┴───────────┴──────────────────────┘

⏱️  Analysis completed in 1.1s

[Note] Some signals (PVC disk usage, CPU/memory trends) need metrics-server and kubelet metrics. If unavailable, `top` succeeds but shows limited output.
```

## 🔧 Architecture

The new implementation follows the exact technical specification:

- **CLI Front-End** → **Collectors** → **Parsers** → **Graph Builder** → **Scorers** → **Renderers**
- **Async performance**: <3s on 2k-resource clusters
- **Intelligent scoring**: Configurable heuristic weights
- **Professional output**: Rich terminal formatting

## 🧪 Testing

```bash
# Run test suite
./test.sh

# Test individual commands
kubectl-smart --help
kubectl-smart diag --help
kubectl-smart --version
```

## 📚 Documentation

- **`README.md`**: Project overview and quick start
- **`examples.md`**: Comprehensive usage examples and scenarios
