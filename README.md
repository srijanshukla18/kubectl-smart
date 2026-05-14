# kubectl-smart [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/srijanshukla18/kubectl-smart)

## 🎯 What is kubectl-smart?

**kubectl-smart** (beta) is a kubectl plugin that improves Kubernetes debugging by prioritizing issues and providing structured analysis. It provides three focused commands to help reduce incident resolution time.

> ⚠️ **Early feedback welcome** - This project is in active development. Please report issues and share your experience.

**Read-only operations only** - Safe to run in production, never modifies your
cluster. The shared kubectl runner rejects non-read-only verbs before spawning
`kubectl`.

## 🚀 Quick Start

```bash
# One-command installation using uv
./install.sh

# Or run directly from the checkout
./kubectl-smart --help

# Now kubectl-smart is available globally in your terminal
kubectl-smart --help
kubectl-smart diag pod failing-pod              # Root-cause analysis
kubectl-smart diag pod failing-pod -o json      # Machine-readable diagnosis
kubectl-smart diag pod --all -n production      # Batch diagnosis
kubectl-smart graph pod my-app --upstream       # Dependency visualization  
kubectl-smart top production                    # Predictive outlook
```

## 🎯 The Three Commands

### 1. `diag` - Root-cause Analysis
```bash
kubectl-smart diag pod failing-pod
kubectl-smart diag deploy my-app -n production
kubectl-smart diag pod failing-pod -o json
kubectl-smart diag pod failing-pod --watch --interval 5
kubectl-smart diag pod --all -n production --max-concurrent 2
kubectl-smart diag pod --all -n production -l app=checkout
kubectl-smart diag pod failing-pod --timeout 3
```
**Purpose**: One-shot diagnosis that surfaces root cause and contributing factors

Supported resource types: `pod`, `deploy`/`deployment`, `sts`/`statefulset`, `job`, `svc`/`service`, `ingress`, `rs`/`replicaset`, `ds`/`daemonset`.

Output and modes:
- Text output is the default; `-o json` is available for automation.
- Controller diagnosis follows bounded child context: Deployments through owned
  ReplicaSets to Pods, and StatefulSets/DaemonSets/ReplicaSets/Jobs to their
  Pods. Child Pod status, Events, and recent logs can become the controller's
  root cause when that is the strongest evidence.
- `--watch` reruns diagnosis on an interval for a single resource and currently
  supports text output only. `--watch -o json` is rejected instead of emitting a
  misleading mixed contract.
- `--all` diagnoses every resource of the selected type in the namespace/current context.
- `--max-concurrent` controls batch diagnosis concurrency so you can reduce API pressure in degraded clusters.
- `--selector`/`-l` limits `--all` to matching labels, which is useful for
  narrowing a large namespace during incident triage.
- In batch text output, rows with data gaps are labeled `incomplete analysis`
  instead of healthy/clean, even if no warning or critical issue was surfaced.
- Batch summaries include a separate `Not found` / `summary.not_found` count
  for resources that disappeared or could not be retrieved after the initial
  list.
- `--timeout` sets the per-kubectl collector timeout, including the initial
  batch list call and each per-resource diagnosis in `--all` mode.
- `--context` pins the kubectl context. For repeatable local demos/tests, you can also set `KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo`.
- Exit code is `0` when no warning or critical issues are found, `1` for warning-only diagnoses, and `2` for critical issues or command errors.

JSON automation contract:
- `exit_code` mirrors the process exit status for single-resource and batch diagnosis.
- `analysis_complete: false` means the result should not be treated as fully
  observed. For diagnosis JSON this includes unavailable collectors
  (`data_gap_count > 0`), missing target resources, and surfaced diagnostic
  issues without supporting evidence. Batch JSON exposes this both in
  `summary.analysis_complete` and on each item in `results`.
- Inspect `data_gaps` before treating a clean result as complete; an empty
  `data_gaps` list only means no collector gap was recorded.
- `diagnostic_issues` is the deduplicated set that backs `issue_summary`, root-cause severity, and exit-code decisions. `issues` remains the raw scored issue list.

### 2. `graph` - Dependency Visualization
```bash
kubectl-smart graph pod my-app --upstream
kubectl-smart graph deploy checkout --downstream
kubectl-smart graph deploy checkout --downstream --timeout 3
```
**Purpose**: ASCII dependency tree for blast-radius analysis

Direction semantics:
- `--upstream` shows what the target depends on, such as a Pod's PVCs, ConfigMaps, Secrets, ServiceAccount, and Node.
- `--downstream` shows resources impacted by the target, such as Pods owned by a Deployment/ReplicaSet or selected by a Service.
- Passing both flags shows both sections in one output.
- If neither flag is provided, `graph` defaults to downstream.
- `--timeout` sets the per-kubectl collector timeout for graph discovery in
  slow or degraded API servers.

### 3. `top` - Predictive Outlook
```bash
kubectl-smart top production
kubectl-smart top kube-system --horizon=24
kubectl-smart top production --timeout 3
```
**Purpose**: 48h outlook for capacity issues and certificate expiry

Data sources and behavior:
- CPU/Memory: metrics-server (`kubectl top`) snapshots for namespace pod
  usage and current node CPU/memory pressure. If node utilization is already
  above the warning threshold, `top` surfaces it immediately.
- PVC Disk usage: kubelet Prometheus metrics (kubelet_volume_stats_* via API
  proxy). PVC utilization samples are cached locally so repeated runs can
  forecast short-term storage growth. If PVCs exist but usable volume stats are
  unavailable, output records an explicit data gap instead of treating storage
  usage as clean.
- Certificate expiry: parses Secret `tls.crt` via X.509; warns when ≤ 14 days.
  If Secret inventory is available, also warns when an Ingress references a
  missing TLS Secret. If Secret collection is blocked, the missing-reference
  check is suppressed and the output shows a data gap instead.
- Read-only; no cluster writes. If a source is unavailable, `top` succeeds,
  prints `DATA GAPS`, qualifies clean forecasts as based on available signals,
  and avoids unsupported warnings from missing signals.
- A missing target namespace is treated as a command failure (`exit 2`) with
  the exact `kubectl get namespace` not-found evidence shown in `DATA GAPS`.

Requirements and graceful degradation:
- For full predictions, ensure metrics-server is installed and kubelet metrics
  are accessible via API proxy.
- If metrics-server is absent or kubelet metrics are blocked by RBAC, `top`
  still runs and prints explicit `DATA GAPS` for the missing pod metrics, node
  metrics, or PVC volume stats.
- Use `--timeout <seconds>` or `KUBECTL_SMART_TIMEOUT=<seconds>` to tune each
  kubectl collector timeout for slow or degraded API servers.

## ✨ Visual Preview

Below are sample, outputs so you can see how kubectl-smart renders information.

### 🔍 diag (root-cause analysis)

```
📋 DIAGNOSIS: Pod/production/failing-app-xyz
Status: CrashLoopBackOff

🔴 LIKELY ROOT CAUSE
  💥 Log Errors: Found 3 error(s) (score: 95.0)
    Log analysis detected 3 unique error patterns. Recent: panic: database connection refused
    Evidence:
    • Log line: panic: database connection refused

🟡 CONTRIBUTING FACTORS
  ⚠️ CrashLoopBackOff: failing-app-xyz (score: 85.0)
    Container exits immediately after start, in restart loop
  ⚠️ ImagePullBackOff: failing-app-xyz (score: 75.0)
    Failed to pull image "invalid-registry.com/app:latest"

📅 RECENT EVENTS
  Time      Type      Reason             Message
  10:05:02  Warning   BackOff            Back-off restarting failed container
  10:04:58  Normal    Pulled             Successfully pulled image
  10:04:55  Normal    Scheduled          Successfully assigned to node-1

💡 SUGGESTED ACTIONS
  1. Review full logs for context
  2. docker pull invalid-registry.com/app:latest
  3. Check application configuration

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

⚪ DATA GAPS (3)
Analysis used the available signals; these collectors were incomplete:
  • metrics pods unavailable (unavailable): error: Metrics API not available |
    Check: Install or enable metrics-server for capacity forecasting
  • metrics nodes unavailable (unavailable): error: Metrics API not available |
    Check: Install or enable metrics-server for capacity forecasting
  • kubelet persistentvolumeclaims unavailable (rbac): RBAC permission denied:
    cannot get nodes/proxy | Check: kubectl auth can-i get nodes/proxy
```

## 🔧 Architecture

The implementation features:

- **CLI Front-End** → **Collectors** → **Parsers** → **Graph Builder** → **Scorers** → **Renderers**
- **Async collectors** with bounded kubectl calls and graceful degradation for optional data sources
- **Issue scoring**: Configurable heuristic weights for prioritization
- **Professional output**: Rich terminal formatting

## 🧪 Testing

```bash
# Run unit tests
uv run --extra dev pytest

# Match the CI warning-as-error gate
uv run --frozen --extra dev pytest -W error::RuntimeWarning -W error::DeprecationWarning

# Match the CI high-signal lint gate
uv run --frozen --extra dev ruff check kubectl_smart tests --select F,B,C4 --ignore B904

# Optional: run coverage
uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing

# Optional: build and smoke-test an installable wheel
uv build --wheel --out-dir /tmp/kubectl-smart-dist
uv venv /tmp/kubectl-smart-venv
uv pip install \
  --python /tmp/kubectl-smart-venv/bin/python \
  /tmp/kubectl-smart-dist/kubectl_smart-0.1.0-py3-none-any.whl
/tmp/kubectl-smart-venv/bin/kubectl-smart --version

# Optional: run Kubernetes scenario tests against an explicit local context
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
./kubectl-smart-lab.sh apply all
./test.sh

# To validate an installed binary instead of the current checkout:
KUBECTL_SMART_CMD=kubectl-smart ./test.sh

# Optional: verify the complex local demo and RBAC data-gap behavior
./demo-complex-scenarios.sh apply
./demo-smoke.sh

# Optional: create a throwaway kind cluster and verify live metrics-server behavior
./metrics-live-smoke.sh

# Optional: run a read-only compatibility smoke against an explicit context
KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo NAMESPACE=kube-system ./provider-compat-smoke.sh

# Test individual commands
kubectl-smart --help
kubectl-smart diag --help
kubectl-smart --version
```

Local demo safety:
- `kubectl-smart-lab.sh`, `test-setup-minikube.sh`, and `test.sh` refuse to run unless `KUBECTL_SMART_CONTEXT` matches a local context pattern: `kind-*`, `minikube`, or `colima`.
- The CLI also honors `KUBECTL_SMART_CONTEXT` when `--context` is omitted, which keeps demo commands pinned even if another terminal changes the global kubectl context.
- `test.sh` and `demo-smoke.sh` default to the current checkout via
  `./kubectl-smart`. Set `KUBECTL_SMART_CMD=kubectl-smart` when you
  specifically want to validate an installed binary.
- `metrics-live-smoke.sh` creates and deletes a separate throwaway kind cluster
  so metrics-server validation does not alter the demo cluster or its
  intentional failures.
- `provider-compat-smoke.sh` is read-only and requires an explicit context. It
  cross-checks direct `kubectl top` availability against `kubectl-smart top`
  data gaps and runs `diag`/`graph` on an existing Pod when one is available.
- `test.sh` exits nonzero if any integration check fails, so it is safe to use
  as a local gate instead of a best-effort transcript.
- `demo-smoke.sh` passes explicit contexts for both the admin demo context and
  the restricted RBAC kubeconfig, so an exported shell context cannot bleed
  across the two checks.

## 🔬 Current Status (v0.x Beta)

**Early stage project - feedback welcome!**
- ✅ Core functionality implemented
- ✅ Async collectors with bounded kubectl calls
- ✅ Read-only safety guarantee
- ✅ Modular, extensible architecture
- 🔄 Actively seeking user feedback and real-world testing
- 📋 [Issues and feature requests welcome](https://github.com/srijanshukla18/kubectl-smart/issues)

Help improve kubectl-smart by trying it out and sharing your experience!

## 📚 Documentation

- **`README.md`**: Project overview and quick start
- **`examples.md`**: Comprehensive usage examples and scenarios
- **`SEV1_READINESS_AUDIT.md`**: Current evidence checklist, gates, and residual
  risks for real-incident trust
