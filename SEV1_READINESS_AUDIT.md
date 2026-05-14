# Sev-1 Readiness Audit

Date: 2026-05-14
Status: not complete; high-confidence beta

Objective: move `kubectl-smart` from promising beta toward a tool I would trust
during a real Sev-1 without skepticism.

## Success Criteria

- Read-only by construction: no command path should mutate cluster state.
- Context-safe: demo and validation commands must not depend on or disturb the
  user's global kube context.
- Evidence-backed diagnosis: root-cause claims must cite concrete logs, events,
  status, or Kubernetes object facts.
- Honest degradation: missing logs, events, metrics, PVC stats, RBAC, parse
  failures, and not-found states must surface as explicit data gaps.
- Useful incident surfaces: `diag`, `graph`, `top`, batch mode, JSON output, and
  watch mode should work under realistic degraded-cluster conditions.
- Demo-ready: complex scenarios and narration should be reproducible without
  altering the existing demo failures.
- Metrics-ready: `top` should behave correctly when metrics-server and kubelet
  PVC stats are present, absent, blocked, or partially parseable.
- Quality-gated: unit, lint, warning-as-error, demo smoke, and local integration
  gates should be green on the current tree.

## Prompt-To-Artifact Checklist

| Requirement | Evidence |
| --- | --- |
| Read-only operations only | `README.md`; `kubectl_smart/collectors/base.py` allowlist `READ_ONLY_KUBECTL_VERBS`; `tests/test_collectors.py::TestRunKubectl::test_run_kubectl_rejects_mutating_verbs_before_spawn` |
| Do not disturb existing cluster failures | `DEMO_RUNBOOK.md` documents `kubectl-smart-complex`; `demo-smoke.sh` validates existing intentional failures; latest `demo-smoke.sh` passed |
| Keep global context on `colima` | `kubectl config current-context` returned `colima` after the latest checkpoint |
| Add/validate global kubeconfig and explicit demo context | `demo-smoke.sh`, `test.sh`, and README local demo safety use explicit `KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo` |
| Complex 1-2 demo scenarios | `DEMO_RUNBOOK.md` has Checkout Cascade and Fulfillment Config Trap |
| 3-minute narration transcript | `DEMO_TRANSCRIPT.md` contains the intro, two demo cases, close, optional RBAC cutaway, and 60-second version |
| Evidence-backed diagnosis | `demo-smoke.sh` checks root-cause and evidence sections; `DEMO_TRANSCRIPT.md` includes raw `kubectl get events` evidence; `tests/test_commands.py` covers event/log/status evidence promotion |
| Controller child-pod promotion | `tests/test_commands.py` controller tests; `demo-smoke.sh` checks StatefulSet diagnosis promotes child pod evidence |
| Service endpoint/selector diagnosis | `tests/test_commands.py` service context tests; `demo-smoke.sh` checks endpoint count and selector evidence |
| Graph blast-radius context | `tests/test_graph.py`; `demo-smoke.sh` checks upstream/downstream checkout graph and missing Secret graph dependency |
| Data-gap honesty | `TEST_COVERAGE.md`; `tests/test_commands.py`; `tests/test_renderers.py`; `demo-smoke.sh` restricted RBAC checks |
| Batch mode honesty | `tests/test_batch.py`; `demo-smoke.sh` restricted batch text and JSON checks |
| JSON automation contract | `tests/test_renderers.py`; `tests/test_cli.py`; `demo-smoke.sh` missing-resource and restricted-batch JSON checks |
| Watch cleanup and cancellation | `tests/test_watch.py`; commit `c91f602 Clean up cancelled watch sessions` |
| Terminal safety for control bytes | `tests/test_renderers.py`; `tests/test_cli.py`; commits covering ANSI/control sequence sanitization |
| Missing metrics-server behavior | `demo-smoke.sh`; `test.sh`; `tests/test_collectors.py`; `tests/test_commands.py` |
| Metrics-server-present behavior | `tests/test_cli.py::TestTopCommand::test_top_metrics_happy_path_with_fake_kubectl` |
| Node metrics duplicate prevention | `tests/test_forecast.py::TestPredictCapacityIssues::test_predict_capacity_issues_ignores_metrics_only_node_inventory` |
| Kubelet PVC happy path | `tests/test_cli.py::TestTopCommand::test_top_metrics_happy_path_with_fake_kubectl`; `tests/test_commands.py::TestTopCommand::test_execute_merges_kubelet_pvc_metrics_before_forecast` |
| Kubelet PVC missing stats honesty | `demo-smoke.sh`; `tests/test_commands.py::TestTopCommand::test_execute_records_missing_pvc_metric_gap` |
| Metrics RBAC guidance | `tests/test_collectors.py` pod-vs-node `metrics.k8s.io` checks; commit `9d6348d Clarify metrics RBAC checks` |
| Node context collector failure honesty | `tests/test_commands.py` node context creation/runtime/parse gap tests; commit `ca006da Cover node context data gaps` |
| Current quality gates | `uv run --extra dev pytest --cov=kubectl_smart --cov-report=term-missing` -> `517 passed`, `88%`; ruff gate passed; warning-as-error pytest passed; `demo-smoke.sh` passed; `test.sh` -> `54 passed, 0 failed` |

## Current Evidence Snapshot

- Unit and coverage gate: `517 passed`, `88%`.
- Warning-as-error gate: `517 passed`.
- Lint gate: `uv run --frozen --extra dev ruff check kubectl_smart tests --select F,B,C4 --ignore B904` passed.
- Whitespace gate: `git diff --check` passed.
- Demo smoke: `KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo KUBECTL_SMART_CMD=./kubectl-smart ./demo-smoke.sh` passed.
- Local integration: `KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo KUBECTL_SMART_CMD=./kubectl-smart ./test.sh` reported `54 passed, 0 failed`.
- Global kube context after work: `colima`.

## Residual Risk

- No true live-cluster run has installed metrics-server and exercised real
  metrics.k8s.io responses; the current coverage uses a hermetic fake `kubectl`
  fixture plus parser/collector/unit tests.
- No production-provider matrix has been run across EKS, GKE, AKS, OpenShift,
  and restricted enterprise RBAC variants.
- No release artifact has been cut and installed as an end-user package in a
  clean environment during this audit.
- Some rare display and exception branches remain uncovered, though the main
  incident flows and degradation paths are covered.

## Completion Decision

Do not mark the objective complete yet. The tool is substantially hardened and
demo-ready, but "without skepticism" still needs either a real metrics-server
cluster validation or a small provider-style compatibility pass before calling
the Sev-1 trust objective achieved.
