# kubectl-smart — Product Brief

## 0. Why Does This Product Exist?

SREs and on‑call engineers are drowning in *too much Kubernetes data* during incidents.  `kubectl describe` prints hundreds of lines, events have no weighting, and root causes hide behind noise.  **kubectl‑smart** turns that raw state into a tiny set of answers so teams resolve outages faster and sleep better.

---

## 1. Problem Statement

* **Information Overload** • Engineers scroll through 200 + lines of YAML to find one failed mount event.
* **Correlation Blindness** • Troubles need traversing Pods → PVCs → Nodes manually; humans miss subtle links.
* **Predictable Pain** • 60 % of incidents are disk or memory exhaustion we could have foreseen.
* **No Time to Think** • Under pager pressure, every extra `kubectl` command stretches MTTR and escalates stress.

### Opportunity

A CLI that keeps engineers inside their familiar terminal but tells them **why** things break, **what** else is affected, and **what** will break next—within seconds—creates huge leverage: lower MTTR, fewer escalations, happier teams.

---

## 2. Target Users

| Persona                   | Pain Today                            | Win with kubectl‑smart               |
| ------------------------- | ------------------------------------- | ------------------------------------ |
| **On‑call SRE** (primary) | Must triage Sev‑2 in the dark at 3 AM | 10‑line root cause, immediate action |
| Junior Engineer           | Unsure which kubectl flags to run     | One command gives guidance           |
| Platform Lead             | Wants proactive capacity insights     | `top` warns days before disk fills   |

---

## 3. Product Vision

> *“Slash incident resolution time from minutes to seconds by distilling kube state into the three things you actually need to know.”*

The first GA release focuses on a *bare‑bones power trio* of commands that already cover 80 % of real‑world debugging cases.

---

## 4. Core Feature Set (v1.0)

1. **diag** — One‑shot diagnosis of a workload; surfaces root cause and top two contributing factors with suggested kubectl fix snippet.
2. **graph** — Dependency view (ASCII) to show what's upstream/downstream of the target; allows quick blast‑radius checks.
3. **top** — Predictive glance at disk, memory, CPU, and certificate expirations over the next 48 h; flags only actionable risks.

No servers, no agents, no cluster writes—pure *kubectl in, insight out*.

---

## 5. User Journey

### 5.1 Pager Goes Off (diag)

* **Trigger** — Alert: checkout‑prod CrashLoop.
* **Action** — `kubectl-smart diag pod checkout‑xyz`.
* **Outcome** — Reads as:

  * *Root cause: OOMKilled (limit 512 Mi, peak 768 Mi).*
  * *Contributing: Memory limit cut by PR‑742 two hours ago.*
* **Value** — Engineer fixes pod in < 5 min instead of 20 min.

### 5.2 Validate Fix (graph)

* **Action** — `kubectl-smart graph pod checkout‑xyz --upstream`.
* **Outcome** — ASCII map shows only one PVC and node impacted; no hidden victims.
* **Value** — Confidence that rollout won’t cascade.

### 5.3 Stay Ahead (top)

* **Action** — Over coffee: `kubectl-smart top namespace prod`.
* **Outcome** — List of two predictable failures (PVC nearly full, cert expiring).
* **Value** — Prevent weekend pages by filing maintenance tickets early.

---

## 6. Success Metrics

* **MTTR Reduction** — 30 % drop in Sev‑2 MTTR within three months of adoption.
* **Adoption** — 80 % of on‑call SREs use `kubectl-smart diag` at least once per week.
* **Prediction Accuracy** — ≥ 95 % of "top" warnings occur before impact (no false positives > 5 %).
* **User Satisfaction** — CSAT 4.5/5 from incident retrospectives.

---

## 7. Release Plan

1. **Alpha (internal)** • Dog‑food in the platform team; collect feedback on message clarity.
2. **Beta (selected SRE squads)** • Harden heuristics, tune performance budgets < 3 s.
3. **GA** • Publish v1.0; blog, internal brown‑bag; add to golden path docs.

---

## 8. Pricing / Licensing

* Open‑source Apache‑2.0; internal support SLA via Platform team.

---

## 9. Risks & Mitigations

* **Heuristic Misses Cause Blind Spots** → Provide JSON output so users can escalate log bundles for tuning.
* **Very Large Clusters > 50 k Objects** → Scope flag to limit namespaces; enforce kubectl timeouts.
* **Metrics‑server Absent** → Document degraded mode; future plug‑in for Prometheus.

---

## 10. Future Ideas (post‑v1.0, non‑commit)

* Plugin ecosystem, snapshot diffing, LLM summariser.
* GUI/TUI watch mode.
* Team knowledge sharing layer.

---

## 11. Stakeholders

* **Product Lead** — Drives roadmap, success metrics.
* **Engineering Lead** — Owns technical delivery and SLA compliance.
* **SRE Guild** — Design partners, acceptance testers.
* **Documentation Team** — Writes quick‑start & cheat‑sheet.

---

## 12. Next Steps

* Form squad: 1 EM, 3 backend, 1 DX engineer, 1 doc writer.
* Sprint 0: finalise spec (this doc + tech.md), create Git repo, CI pipeline skeleton.
* Sprint 1: implement minimal `diag` path on minikube, collect latency data.

