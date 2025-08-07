# kubectl-smart — Technical Specification

## 0. Purpose of this Document

This specification is the *single source of truth* for engineers implementing **kubectl‑smart**.  It defines the scope, architecture, interfaces, performance budgets, security posture, and quality requirements for v1.0 ("bare‑bones power trio").  All implementation and design discussions MUST converge on this spec; changes require an RFC.

---

## 1. Scope & Goals

### 1.1 In‑Scope

* **CLI‑only binary** that wraps the user’s installed `kubectl` (>= 1.23).
* Three sub‑commands:

  * `diag` — root‑cause analysis of a single workload.
  * `graph` — dependency/blast‑radius graph for that workload.
  * `top` — predictive capacity and certificate outlook.
* Works on macOS, Linux, Windows; Python 3.9+; no server/agent.
* Must render actionable insight in **≤ 3 seconds** on a 2 000‑resource cluster.

---

## 2. Key Assumptions

1. The user already has a configured, working `kubectl` that handles auth & context.
2. Clusters expose the *metrics‑server* API; if not, `top` falls back to best‑effort using pod resource requests.
3. Python packages may depend on GPL‑compatible licences only.

---

## 3. High‑Level Architecture

```
┌──────────────┐  fan‑out  ┌──────────────┐  parse  ┌──────────────┐
│  CLI Front   │──────────▶│ Collectors   │────────▶│ Insight Core │
└──────────────┘           └──────────────┘          └──────────────┘
       ▲                         │                       │
       ▼ render                  ▼                       ▼
┌──────────────┐           ┌──────────────┐        ┌──────────────┐
│  Renderer    │◀─────────│  Parsers      │◀──────│  Scorers      │
└──────────────┘           └──────────────┘        └──────────────┘
```

### 3.1 Components

| Component           | Primary Responsibilities                                                              |
| ------------------- | ------------------------------------------------------------------------------------- |
| **CLI Front‑End**   | argument parsing (Typer), shell completion, global flags (`--json`, `--quiet`).       |
| **Collector Layer** | Spawn subprocesses to run kubectl commands; stream stdout/stderr; time‑box each call. |
| **Parser Layer**    | Convert raw JSON/YAML/log lines into typed Python objects (pydantic models).          |
| **Graph Builder**   | Build in‑memory directed graph (igraph) of resources & relations.                     |
| **Signal Scorer**   | Rank potential issues via heuristic weights; seriousness 0‑100.                       |
| **Forecaster**      | Holt‑Winters on time‑series for disk & memory; cert date math.                        |
| **Renderer**        | Produce ANSI or JSON output; respects `--quiet`.                                      |

All components live in the top‑level Python package `kubectl_smart`.  Cross‑layer imports are prohibited except via declared service interfaces.

---

## 4. Detailed Module Specs

### 4.1 CLI Front‑End (`kubectl_smart.cli`)

* Sub‑commands map 1‑to‑1 with public methods in `kubectl_smart.commands.*`.
* Global options:

  * `--context`, `--namespace` forward to kubectl.
  * `--json` forces JSON renderer; exit code 0 if **no critical** scores ≥ 90.
  * `--quiet` prints nothing but still returns exit code based on status.

### 4.2 Collector API (`kubectl_smart.collectors.base`)

```python
class Collector(ABC):
    name: str
    async def collect(self, subject: SubjectCtx) -> RawBlob: ...  # time‑bounded
```

* Built‑in collectors: `KubectlGet`, `KubectlDescribe`, `KubectlEvents`, `KubectlLogs`, `MetricsServer`.
* Collectors **never parse** data; they hand off raw bytes plus metadata.

### 4.3 Parser API (`kubectl_smart.parsers.base`)

```python
class Parser(ABC):
    def feed(self, blob: RawBlob) -> list[ResourceRecord]: ...
```

* Must be deterministic & side‑effect free.
* `ResourceRecord` is a pydantic model with standardised fields: `kind`, `name`, `uid`, `properties`, `events`.

### 4.4 Graph (`kubectl_smart.graph`)

* Library: **python‑igraph** (C backend) for speed.
* Vertex key: Kubernetes UID.
* Edge labels: `"owns"`, `"mounts"`, `"scheduled‑on"`, `"selects"`.
* Provide `to_ascii(root_uid, direction="upstream"|"downstream") -> str`.

### 4.5 Scoring (`kubectl_smart.scoring`)

* Heuristic matrix defined in `weights.toml`; unit tests assert default output for canned fixtures.
* Severity thresholds: Critical ≥ 90, Warning ≥ 50, Info < 50.
* `score_issue(issue: Issue) -> int` must be pure.

### 4.6 Forecasting (`kubectl_smart.forecast`)

* Library: **statsmodels** `ExponentialSmoothing`; fall back to linear fit if < 7 samples.
* Cert expiry: parse X509 `notAfter`; raise issue if < 14 days.

### 4.7 Renderer (`kubectl_smart.renderers`)

* ANSI renderer uses **rich** (no external colour themes).
* JSON renderer outputs a stable schema documented in `docs/schema.json`.
* Both honour environment width; wrap lines at 100 chars.

---

## 5. Command Semantics

### 5.1 `diag`

```
Usage: kubectl-smart diag (pod|deploy|sts|job) <name> [--namespace N]
```

* Collectors invoked: Get, Describe, Events, Logs
* Output sections:

  1. **Header** — object identity.
  2. **Root Cause** — highest‑score issue.
  3. **Contributing Factors** — next 2 issues (if ≥ 50).
  4. **Suggested Action** — textual; may include kubectl snippet.
* Exit codes: 0 = no issues ≥ 50; 1 = warnings; 2 = critical.

### 5.2 `graph`

```
Usage: kubectl-smart graph (pod|deploy|sts|job) <name> [--upstream/--downstream]
```

* Uses graph built during last `diag` run in same process; else re‑collect minimal data.

### 5.3 `top`

```
Usage: kubectl-smart top namespace <name>
```

* Pulls `kubectl top pods -n <name>`; groups by PVC and Secret expiries.
* Forecast horizon: 48 h; list only issues predicted to cross 90 % or expire.

---

## 6. Performance Budgets

* **Cold start** (no prior cache) on 2 000 objects: ≤ 3 s (p99).

  * kubectl calls each limited to 1.0 s via `async_timeout`.
* **Memory** footprint ≤ 100 MB RSS during analysis.
* **CPU** ≤ 2 full cores for <= 3 s (burst).

---

## 7. Observability & Logging

* Logs emitted via `structlog`; default level WARN.
* Env var `SMART_DEBUG=1` sets level to DEBUG and prints kubectl command strings.
* No user‑sensitive tokens logged.

---

## 8. Packaging & Distribution

* PyPI package & PyInstaller single‑binary artefacts.
* `pipx install kubectl-smart` must succeed on macOS+Linux; `pip install` supported for CI.

---

## 9. Security & Compliance

* Read‑only.
* Respects kubeconfig contexts and user RBAC.
* No outbound network calls except the in‑cluster API reached via kubectl.

---

## 10. Testing Strategy

* **Unit tests**: ≥ 90 % statement coverage.
* **Golden tests**: stored fixtures for known failure modes; diff against expected ANSI & JSON.
* **Integration**: GitHub Action spins up `kind` matrix with latest three K8s minors.
* **Load test**: synthetic cluster generator; measure SLA budget.

---

## 11. Release & Versioning

* Semantic Versioning.  v0.x for pre‑release; v1.0 when all power‑trio commands hit SLA on Linux + macOS.
* Release artefacts pushed via GitHub Actions; binaries checksum‑signed.

---

## 12. Open Questions / Future Work

1. Should `top` fall back to Prometheus if metrics‑server absent?
2. How to persist time‑series between runs without the abandoned knowledge store?
3. Can we de‑duplicate multiple concurrent `diag` runs (shared cache)?

