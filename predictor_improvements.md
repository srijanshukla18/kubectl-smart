Predictive features: current state and improvements
=================================================

Scope: kubectl-smart `top` command (ForecastingEngine) and underlying collectors/parsers.

Current implementation (as of now)
----------------------------------

1) Metrics collection
- Source: metrics-server via `kubectl top` (pods/nodes). Parsed from the plain-text table into pseudo ResourceRecords with properties.metrics.cpu/memory.
- Limitation: a single snapshot per run. Forecasting requires historical samples (≥7 for Holt–Winters, ≥2 for linear). No cross-run persistence yet.

2) Node capacity forecasting
- Checks Node.status.conditions for DiskPressure/MemoryPressure/PIDPressure; if True → immediate warning with predicted_utilization ≈95%.
- Optional forecast from metrics if sufficient samples are available, else linear fallback with ≥2 samples.
- Limitation: in practice, no time series is available without caching/polling, so forecasts rarely trigger.

3) PVC “usage” forecasting
- Currently not measuring real usage. If PVC is Bound, emits a placeholder predicted_utilization=85%, which is then filtered out by ≥90% threshold → no warning is shown.
- Limitation: no disk usage data collected; no mapping from PVC to bytes used.

4) Certificate expiry
- Scans TLS Secrets and Ingress TLS references.
- Placeholder expiry parsing: assumes tls.crt expires in 30 days, no base64/X.509 parsing. Only warns if days_until_expiry ≤14 (which never happens with the placeholder).

5) Degradation behaviour
- If metrics-server is missing or errors, forecasting degrades gracefully (returns no warnings, prints "No capacity or certificate issues predicted").

Proposed improvements (100/100 UX target)
-----------------------------------------

A) Accurate PVC disk usage and forecasting
- Collector: kubelet metrics scrape
  - kubectl get --raw /api/v1/nodes/<node>/proxy/metrics (and /metrics/cadvisor) – Prometheus text format.
  - Parse series:
    - kubelet_volume_stats_used_bytes{namespace, persistentvolumeclaim}
    - kubelet_volume_stats_capacity_bytes{namespace, persistentvolumeclaim}
  - Join with PVC objects by (ns,pvc). Compute current utilization = used/capacity*100.
- Fallback collector: df from running pod (read-only)
  - For a PVC in use, find a pod mounting it; `kubectl exec -- df -k <mount>` and parse used/capacity.
  - Guard with timeouts and optional flag `--allow-exec` (defaults to on; stays read-only).
- Forecasting
  - Introduce a local metrics cache at ~/.cache/kubectl-smart/metrics.json storing timestamped used_bytes per (ns,pvc).
  - On each run, append the current sample; with ≥2 samples, compute linear slope; with ≥7 samples and statsmodels, run Holt–Winters.
  - Emit warning when predicted utilization ≥90% within horizon; emit immediate critical when current ≥90%.

B) Real certificate expiry
- Implement base64 decode + X.509 parse for Secret.data['tls.crt'] using `cryptography`.
- Extract notValidAfter (UTC) → days_until_expiry.
- For Ingress, resolve referenced Secret and evaluate its expiry.
- Threshold configurable (default 14 days). Add immediate critical when ≤3 days.

C) CPU/Memory forecasting that actually works for users
- Continue using metrics-server for snapshots.
- Persist node and (optionally) per-pod CPU/memory over time in the same local cache.
- With ≥2 samples, do linear forecast; with ≥7 + statsmodels, do Holt–Winters; cap runtime ≤3s by avoiding intra-run polling.
- Emit immediate warnings if current CPU/mem ≥90%.

D) Node pressure
- Keep immediate checks on Node.status.conditions for Disk/Memory/PID pressure.
- Optionally enrich with kubelet /metrics/cadvisor filesystem stats for node rootfs.

E) UX & safety
- Add `--enable-kubelet-scrape` (default on) to control kubelet metrics collection; if RBAC forbids, auto-fallback to exec or silent degrade.
- Clear section in help text documenting data sources (metrics-server, kubelet metrics, X.509 parsing) and fallbacks.

Implementation sketch
---------------------

- New collector `kubelet_metrics`:
  - For each node in scope: GET /api/v1/nodes/<node>/proxy/metrics (Prometheus text)
  - Parser: extract volume stats into ResourceRecords keyed by (ns,pvc) with used_bytes, capacity_bytes.
- Update ForecastingEngine:
  - PVC: use used/capacity if present; otherwise try exec fallback; otherwise skip.
  - Cache: read/append timeseries per key; perform forecast; emit warnings accordingly.
  - Cert: implement X.509 parsing; compute days_until_expiry accurately.
- Add small local cache module with atomic write.

Testing strategy
----------------
- Extend `test-setup-minikube.sh` to:
  - Mount a PVC and fill it over time (job writes more data every N seconds) – so multiple runs see growth.
  - Create a TLS Secret with <14d expiry to trigger warning.
  - Optionally simulate node pressure or high CPU with stress pod.
- Add integration tests in `test.sh` to call `top kubectl-smart-fixtures` and assert presence of CAPACITY and CERTIFICATE warning tables.
