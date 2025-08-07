# kubectl‑smart

*A pocket‑sized CLI that turns noisy‑as‑hell Kubernetes output into the three answers a junior SRE needs most.*

---

## Why does it exist?

1. **Root‑cause in seconds** – No more scrolling through 300‑line `kubectl describe` walls.
2. **See the blast radius** – One ASCII graph shows every PVC, PV, node and configmap tied to your pod.
3. **Stop tomorrow’s pager** – Quick forecast warns if a disk or cert will fail within 48 h.

No servers, no agents, no extra RBAC.  If you can run `kubectl`, you can run kubectl‑smart.

---

## Install

```bash
pipx install kubectl-smart       # Python 3.9+
```

That’s it.  It shells out to *your* kubectl so all existing kube‑configs and auth methods “just work”.

---

## Quick start

```bash
# 1 — Why is this thing broken?
kubectl-smart diag pod myapp‑abc

# 2 — What else is touched?
kubectl-smart graph pod myapp‑abc --upstream

# 3 — Anything about to blow up?
kubectl-smart top namespace prod
```

All commands finish in \~3 s on a medium cluster and **never** change cluster state.

---

## Output at a glance

```
⎈  myapp‑abc (Pod)
❗  Root cause (score 96): OOMKilled – container hit 512Mi limit
• Memory limit was lowered by PR‑#742 2h ago
• Node worker‑05 92 % memory
Fix: kubectl set resources pod/myapp‑abc -c app --limits=1Gi
```

---

## When not to use it

* You already use Lens/k9s and love their full GUIs.
* You need exotic kernel‑level tracing (that’s outside v1.0 scope).

For everything else—especially when you’re new to on‑call—kubectl‑smart is the fastest sanity check you can type.

---

## Roadmap blurb

* **v1.0** – `diag`, `graph`, `top` (this repo)
* **Maybe later** – plugin SDK, eBPF trace, shared notes… depending on community demand.

---

## Contributing

Bug reports and PRs welcome!  All heuristics live under `/kubectl_smart/rules`.  New test fixtures proving a mis‑diagnosis are the best way to help.

