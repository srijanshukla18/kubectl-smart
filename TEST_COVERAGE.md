# Test Coverage Report - kubectl-smart

## Current Status

- Unit test command: `uv run --extra dev pytest`
- Coverage command: `uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing`
- Latest local result: `450 passed`
- Latest measured coverage: `84%`

Coverage is measured, not estimated. The default `pytest` command does not enforce
coverage so contributors get a clear functional signal first. Use the explicit
coverage command above when working on test depth.

## Strongly Covered Areas

- Data models and validation
- Not-found diagnoses preserve data gaps and nonzero exit codes
- Command error rendering preserves data gaps
- Kubernetes collectors and parser selection
- Shared kubectl runner read-only guardrails
- Retry classification for transient apiserver pressure
- Cloud-provider kube context names and malformed context rejection
- Collector creation failures surfaced as command data gaps
- Kubelet node-proxy scrape failures surfaced as capacity data gaps
- Graph relationship extraction and traversal
- Controller diagnoses promote child Pod failures through ownerReference and
  selector relationships, with StatefulSet/DaemonSet/ReplicaSet readiness
  counters parsed into availability status
- Scoring heuristics and custom weight loading
- Log evidence target attribution from collector metadata through scoring
- Forecasting primitives
- Certificate forecasts avoid Ingress TLS reference false positives when Secret
  inventory is incomplete or the referenced Secret exists
- Terminal rendering, including root-cause and contributing-factor evidence
- JSON rendering contracts, including surfaced diagnostic issues, data gaps, and
  issue metadata for automation, plus batch summaries
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
- Explicit `--timeout` flows through single-resource diagnosis, watch mode,
  batch resource listing, and batch per-resource collectors
- Watch-state extraction for warning, critical, and unexpected exit codes,
  diagnosis-detail change detection, and data-gap appearance/resolution
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
