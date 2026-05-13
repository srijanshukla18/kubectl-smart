# Test Coverage Report - kubectl-smart

## Current Status

- Unit test command: `uv run --extra dev pytest`
- Coverage command: `uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing`
- Latest local result: `328 passed`
- Latest measured coverage: `70%`

Coverage is measured, not estimated. The default `pytest` command does not enforce
coverage so contributors get a clear functional signal first. Use the explicit
coverage command above when working on test depth.

## Strongly Covered Areas

- Data models and validation
- Kubernetes collectors and parser selection
- Graph relationship extraction and traversal
- Scoring heuristics and custom weight loading
- Forecasting primitives
- Terminal rendering
- CLI option parsing and backwards-compatible aliases

## Known Coverage Gaps

- `kubectl_smart/batch.py`
- `kubectl_smart/watch.py`
- `kubectl_smart/renderers/json_renderer.py`
- Some error paths in command orchestration and optional collectors

## Notes

The remaining gaps are mostly integration-heavy paths that should be covered with
focused tests before reintroducing a coverage gate. Until then, the public quality
gate is the functional test suite plus local demo validation against an explicit
local Kubernetes context.
