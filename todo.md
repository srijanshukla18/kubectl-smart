Uncovered / untested feature scenarios (cluster prerequisites may be missing)
===========================================================

The following items are obvious capabilities a kubectl-smart user will expect, based on the CLI contract and help-text, but are NOT exercised by our current `test.sh` (or require specific cluster conditions that a vanilla Minikube usually lacks).

Diag command
------------
1. Image-pull failures (e.g. `ImagePullBackOff`, `ErrImagePull`) – resource in Failed state.
2. CrashLoopBackOff / OOMKilled pod – repeated restarts.
3. Pods Pending due to PVC provisioning error (FailedMount).
4. FailedScheduling due to node pressure / taints / unsatisfied affinities.
5. Node affinity / tolerations mis-match.
6. Certificate secrets about to expire (<14 days) causing warning severity.
7. Kubelet eviction events (disk pressure) surfaced as contributing factors.
8. Aggregated diagnosis when multiple replicas of a Deployment are unhealthy (partial availability).
9. Exit code 1 path (warnings but no critical issues).

Graph command
-------------
10. Upstream dependency chain depth >1 (pod → service → deployment).
11. Downstream resources (service selecting multiple pods).
12. Edges involving external services (ConfigMaps/Secrets mounted via volumes).
13. Graph rendering when resource has >50 edges (truncation logic).

Top command
-----------
15. CPU forecast crossing 90 % within horizon → capacity warning printed.
16. Memory forecast crossing 90 %.
17. PVC disk usage forecast crossing 90 %.
18. Secret / certificate expiry forecast <14 days.
19. Behaviour when metrics-server is absent (graceful degradation).

Integration-test TODOs
----------------------
• Extend `test.sh` (or new suite) to spin up dummy workloads that trigger the scenarios above (e.g. bad image, expiring cert secret, full PVC via Filler job).
• Add JSON output snapshot tests for each command.
• Replace remaining `eval` strings with array-based invocations for safety.

