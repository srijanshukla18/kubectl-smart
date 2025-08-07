
High-signal “truth gaps” to fix

- PVC usage forecasting
  - Claim implied to users: Predict PVC nearing full.
  - Actual: In ForecastingEngine._predict_pvc_usage(), any Bound PVC generates a placeholder with predicted_utilization=85.0 and is filtered out by ≥90% so no warnings ever show. No real usage read. Not accurate.

- Certificate expiry
  - Claim: Predict certificate expiry (<14 days).
  - Actual: predict_certificate_expiry() calls _check_secret_certificates(), which does not base64 decode tls.crt or parse X.509. It hardcodes expiry_date = now + 30 days. Therefore days_until_expiry > 14, so no warnings ever show. Not accurate.

- CPU/memory forecasting
  - Claim: Holt-Winters or linear fallback over horizon using metrics.
  - Actual: MetricsServer collector reads one “kubectl top” snapshot; there is no accumulation of ≥2 or ≥7 samples in a single run and no persistent history. As a result, _forecast_time_series() almost never runs and _linear_forecast() needs ≥2 samples which aren’t present. Forecasts rarely trigger. Accurate outputs only for immediate “≥90% now” would make sense, but that immediate check is not implemented; only forecast thresholds are applied.

- Node pressure
  - Claim: Node capacity/pressure handled.
  - Actual: _predict_node_capacity() does detect Node.status.conditions for DiskPressure/MemoryPressure/PIDPressure and emits a “node_pressure” warning with predicted_utilization ≈95%. This is accurate when the condition is set. If a test only taints the node, this won’t appear; that’s a test setup gap, not a code truth issue.

- Graph relationships completeness
  - Claim: Graph shows upstream/downstream dependencies with health indicators.
  - Actual: GraphBuilder extracts edges from:
    - pod: node, pvc/configmap/secret volumes, serviceAccount
    - deployment → replicaset (owns)
    - replicaset → pods (owns)
    - service → pods via selectors (selects)
    - pvc → pv (binds-to)
    - statefulset → pods (owns)
    - daemonset → pods (owns)
  - Missing relationships frequently expected by users (not “false”, but incomplete):
    - ingress ↔ service
    - service ↔ endpointslice (vs endpoints)
    - HPA ↔ targetRef
    - networkpolicy, cronjob, job → pods mapping
  - Output is truthful for what is implemented; just not exhaustive.

- Diag scoring truthfulness
  - Claim: Root cause, contributing factors.
  - Actual: Scoring is heuristic via weights.toml; issues come from events + resource status; that’s fine. But “Unhealthy” readiness/liveness messages surfaced as critical are based on events/log messages if present; otherwise it falls back to status scores. This is truthful but heuristic; not a gap.

- Top output wording
  - Claim: “Predictive capacity & certificate outlook” with tables for capacity warnings and certificate warnings.
  - Actual: If no real predictions are generated (most likely), renderer prints “No capacity or certificate issues predicted.” This can mislead if the user expects disk usage or cert checks; the underlying capabilities aren’t present. This is the key UX truth gap.

What’s accurate today

- diag: status-based and event-based scoring; logs/events/describe collected concurrently; robust.
- graph: ASCII tree and counts; health indicators reflect parsed status; truthful for supported edges.
- top: gracefully degrades if metrics-server missing; truthful about having no warnings under the current simplistic predictive logic, but the feature’s scope is narrower than implied.

Proposed remediation plan (kept minimal and truthful)

- Remove placeholders and report “not available”
  - If we cannot read PVC usage or cert expiry, do not emit “No issues predicted”; explicitly state “PVC usage data not available (no kubelet metrics and no in-use pod mount found)” and “Certificate expiry cannot be evaluated (no tls.crt parse)”. That keeps UX honest until we implement the data.
- Implement the improvements in predictor_improvements.md
  - Kubelet metrics scrape, X.509 parse, local cache, immediate ≥90% checks.
- Adjust wording in help/output
  - Clarify data sources and fallbacks; when only partial data is available, mark sections as “incomplete data”.

If you want, I can:

- Add a “truth-mode” to Top that flags missing data explicitly (small change).
- Start implementing kubelet metrics collector and cert parsing next.

Summary of changes produced
- Added `predictor_improvements.md` outlining exact technical plan to make capacity and cert forecasts accurate.
- Performed a code-level review and identified concrete truth gaps: PVC usage, certificate expiry, and forecasting sample accumulation. The rest is largely truthful but incomplete (graph edges coverage).