# Test Coverage Report - kubectl-smart

## Current Status

- Unit test command: `uv run --extra dev pytest`
- Coverage command: `uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing`
- Latest local result: `488 passed`
- Latest measured coverage: `86%`

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
- Graph relationship extraction and traversal
- Graph not-found messaging distinguishes incomplete target inventory from
  confirmed absence in a complete graph collection
- Controller diagnoses promote child Pod failures through ownerReference and
  selector relationships, with StatefulSet/DaemonSet/ReplicaSet readiness
  counters parsed into availability status
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
- Terminal and batch-text evidence sanitizes ANSI/control sequences from logs,
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
- Watch-state extraction for warning, critical, and unexpected exit codes,
  diagnosis-detail change detection, and data-gap appearance/resolution
- Watch mode exits nonzero when the watch loop itself fails
- Watch mode sanitizes ANSI/control sequences in fatal errors and change lines
- Terminal/watch identity headers and watch log fields sanitize ANSI/control
  sequences before display/logging
- Watch mode records failed checks and recovery in the event stream/summary

## Known Coverage Gaps

- `kubectl_smart/watch.py` long-running start/stop loop, terminal refresh, and
  signal handling branches
- Some command orchestration fallbacks and optional collector paths
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
