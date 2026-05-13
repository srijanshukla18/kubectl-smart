# Test Coverage Report - kubectl-smart

## Current Status

- Unit test command: `uv run --extra dev pytest`
- Coverage command: `uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing`
- Latest local result: `413 passed`
- Latest measured coverage: `83%`

Coverage is measured, not estimated. The default `pytest` command does not enforce
coverage so contributors get a clear functional signal first. Use the explicit
coverage command above when working on test depth.

## Strongly Covered Areas

- Data models and validation
- Kubernetes collectors and parser selection
- Shared kubectl runner read-only guardrails
- Cloud-provider kube context names and malformed context rejection
- Collector creation failures surfaced as command data gaps
- Graph relationship extraction and traversal
- Scoring heuristics and custom weight loading
- Log evidence target attribution from collector metadata through scoring
- Forecasting primitives
- Terminal rendering, including root-cause and contributing-factor evidence
- JSON rendering contracts, including surfaced diagnostic issues, data gaps, and
  batch summaries
- CLI option parsing and backwards-compatible aliases
- Command help/short-option contracts, including `top -h` help and `top -H`
  horizon
- Batch diagnosis exit-code semantics, empty selections, list failures, and
  per-resource data-gap preservation
- Batch kubectl plural handling for supported resource kinds
- Watch-state extraction for warning, critical, and unexpected exit codes, plus
  diagnosis-detail change detection

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
