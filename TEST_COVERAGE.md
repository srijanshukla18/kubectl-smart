# Test Coverage Report - kubectl-smart

## Current Status

- Unit test command: `uv run --extra dev pytest`
- Coverage command: `uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing`
- Local integration command: `KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo KUBECTL_SMART_CMD=./kubectl-smart ./test.sh`
- Live metrics command: `KUBECTL_SMART_CMD=./kubectl-smart ./metrics-live-smoke.sh`
- Provider compatibility command: `KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo NAMESPACE=kube-system KUBECTL_SMART_CMD=./kubectl-smart ./provider-compat-smoke.sh`
- Latest local result: `519 passed`
- Latest measured coverage: `88%`
- Latest local integration result: `54 passed, 0 failed`
- Latest live metrics result: passed against a throwaway kind cluster
- Latest provider compatibility result: passed against `kind-kubectl-smart-demo/kube-system`

Coverage is measured, not estimated. The default `pytest` command does not enforce
coverage so contributors get a clear functional signal first. Use the explicit
coverage command above when working on test depth.

## Strongly Covered Areas

- Data models and validation
- Analysis configuration rejects invalid explicit values and ignores invalid
  environment timeout/cache overrides
- Not-found diagnoses preserve data gaps and nonzero exit codes
- Command error rendering preserves data gaps
- Kubernetes collectors and parser selection
- Shared kubectl runner read-only guardrails, malformed resource-argument
  rejection, and raw API path restriction to the kubelet metrics endpoint
- Retry classification for transient apiserver pressure
- Cloud-provider kube context names and malformed context rejection
- Collector creation failures surfaced as command data gaps
- Kubelet node-proxy scrape failures surfaced as capacity data gaps
- Metrics-server RBAC data gaps suggest pod-vs-node specific
  `metrics.k8s.io` permission checks
- Metrics-server warmup gaps suggest waiting for a scrape or checking
  metrics-server readiness instead of implying metrics-server is absent
- Graph relationship extraction and traversal
- Graph not-found messaging distinguishes incomplete target inventory from
  confirmed absence in a complete graph collection
- Graph collection runtime and parse failures preserve Kubernetes resource-type
  context in data gaps
- Controller diagnoses promote child Pod failures through ownerReference and
  selector relationships, with StatefulSet/DaemonSet/ReplicaSet readiness
  counters parsed into availability status
- Controller context and child-pod log collection failures preserve
  Kubernetes resource-type context in data gaps
- Service diagnosis keeps endpoint and namespace pod context collection failures
  bounded as data gaps instead of failing the whole diagnosis
- Scoring heuristics and custom weight loading
- Log evidence target attribution from collector metadata through scoring
- Forecasting primitives
- Certificate forecasts avoid Ingress TLS reference false positives when Secret
  inventory is incomplete or the referenced Secret exists
- Terminal rendering, including root-cause and contributing-factor evidence
- Terminal missing-resource wording distinguishes explicit Kubernetes not-found
  evidence from incomplete visibility
- Terminal data-gap rendering announces when additional gaps are hidden past
  the display cap
- Terminal data-gap rendering escapes Rich markup so kubectl/log text remains
  literal
- Terminal issue titles, descriptions, evidence, and actions escape Rich markup
  so log/event text remains literal
- Terminal status, recent-event rows, graph lines, top warning tables, errors,
  and RBAC permission text escape Rich markup so evidence remains literal
- Terminal recent-event tables fold long values instead of ellipsizing evidence,
  and predictive warnings render inspectable resource/action values
- Terminal and batch-text evidence escapes ANSI/control sequences from logs,
  events, errors, and other Kubernetes strings before rendering
- CLI text error paths sanitize ANSI/control sequences before writing stderr
- JSON rendering contracts, including surfaced diagnostic issues, data gaps,
  per-resource batch completeness, and issue metadata/evidence completeness for
  automation, plus batch summaries
- JSON diagnosis and batch completeness distinguish missing target resources
  from fully analyzed resources with findings
- JSON diagnosis and batch completeness mark unsupported surfaced issues without
  evidence as incomplete
- JSON error responses preserve data gaps and mark analysis incomplete for
  automation
- CLI option parsing and backwards-compatible aliases
- Command help/short-option contracts, including `top -h` help and `top -H`
  horizon
- Batch diagnosis exit-code semantics, empty selections, list failures, and
  per-resource data-gap/not-found preservation
- Batch kubectl plural handling for supported resource kinds
- Batch resource listing validates namespace and context before spawning kubectl
- Batch `--selector`/`-l` narrows resource listing before diagnosis
- Batch text and JSON summaries preserve label selector scope
- Batch text rows with data gaps are labeled as incomplete analysis instead of
  healthy/clean
- Batch text and JSON summaries expose a separate not-found resource count
- Explicit `--timeout` flows through single-resource diagnosis, graph, top,
  watch mode, batch resource listing, and batch per-resource collectors
- Top-level predictive outlook fails closed when the target namespace is missing
  while preserving the exact not-found data gap evidence
- Top-level predictive outlook qualifies clean no-warning text when only partial
  signals were available
- Top-level predictive outlook says no data gaps were recorded when all
  collected signals completed cleanly
- Top-level predictive outlook preserves collected data gaps when an unexpected
  forecasting exception forces an error response
- Top-level predictive outlook preserves optional collector resource type on
  collect/parse failures so incomplete Secret inventory still qualifies TLS
  forecasts
- Top-level predictive outlook merges kubelet PVC metric records into PVC
  inventory before forecasting, and reports missing `kubelet_volume_stats`
  evidence when PVCs exist without usable volume metrics
- Top-level predictive outlook collects node inventory and metrics-server node
  rows so current node CPU/memory pressure is visible without historical samples
- Top-level predictive outlook preserves node inventory and node metrics
  creation, collection, and parse failures as explicit data gaps
- CLI-level predictive outlook is exercised with a fake `kubectl` happy path
  for metrics-server pod metrics, node metrics, and kubelet PVC volume stats
- Live metrics-server validation in a throwaway kind cluster verifies
  `kubectl-smart top` does not report pod/node metrics gaps when metrics-server
  is available
- Read-only provider compatibility smoke cross-checks `kubectl top` availability
  against `kubectl-smart top` data gaps and exercises `diag`/`graph` on an
  existing Pod without changing the selected global context; kubectl API
  checks use a configurable request timeout so offline contexts fail visibly
- Metrics-server node rows feed capacity forecasting without becoming duplicate
  node inventory targets
- Watch-state extraction for warning, critical, and unexpected exit codes,
  diagnosis-detail change detection, and data-gap appearance/resolution
- Watch mode exits nonzero when the watch loop itself fails
- Watch mode escapes ANSI/control sequences in fatal errors and change lines
- Terminal/watch identity headers and watch log fields escape ANSI/control
  sequences before display/logging
- Watch mode records failed checks and recovery in the event stream/summary
- Watch mode clean-stop and keyboard-interrupt paths return success, avoid
  unnecessary post-stop sleeping, and print a session summary
- Watch mode cleans up and prints a summary on external asyncio cancellation
  before propagating the cancellation

## Known Coverage Gaps

- `kubectl_smart/watch.py` terminal refresh and a few rare display branches
- Some command exception and edge branches outside the main incident flows
- Integration-heavy collector behavior that depends on live Kubernetes API
  availability, metrics-server, kubelet proxy access, and RBAC envelopes

## Notes

The remaining gaps are mostly integration-heavy paths that should be covered with
focused tests before reintroducing a coverage gate. Until then, the public quality
gate is the functional test suite plus local demo validation against an explicit
local Kubernetes context.

Latest measured command:

```bash
uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing
```
