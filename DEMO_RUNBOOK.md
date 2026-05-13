# Complex Demo Runbook

These scenarios live in `kubectl-smart-complex` and do not modify the existing
`kubectl-smart-lab` failures.

For the narration track, use `DEMO_TRANSCRIPT.md`. This file stays focused on
setup, validation, and command order.

## Setup

```bash
./demo-complex-scenarios.sh apply
kubectl get pods -n kubectl-smart-complex
./demo-smoke.sh
```

The setup also writes `.kubectl-smart-rbac.kubeconfig`, a restricted kubeconfig
for validating how `kubectl-smart` behaves when events and pod logs are hidden
by RBAC.

## 3-Minute Recording Path

### Case 1: Checkout Cascade

This one shows a crashlooping checkout StatefulSet with a realistic dependency
shape: ServiceAccount, ConfigMap, Secret, PVC, Node, Service, an intentionally
empty inventory Service, and a short-lived TLS certificate.

```bash
kubectl-smart diag sts checkout-api -n kubectl-smart-complex
kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream
kubectl-smart diag svc inventory-db -n kubectl-smart-complex
kubectl-smart graph ingress checkout-demo -n kubectl-smart-complex --upstream --downstream
kubectl-smart top kubectl-smart-complex --horizon 72
```

For a narrower batch view while recording or debugging a large namespace:

```bash
kubectl-smart diag pod --all -n kubectl-smart-complex -l demo.kubectl-smart/story=checkout-cascade
```

### Case 2: Fulfillment Config Trap

This one shows a pod that is scheduled and has rich dependencies, but it cannot
start because a runtime Secret referenced through `env` is missing.

```bash
kubectl-smart diag pod fulfillment-worker-0 -n kubectl-smart-complex
kubectl-smart graph pod fulfillment-worker-0 -n kubectl-smart-complex --upstream --downstream
kubectl get events -n kubectl-smart-complex --field-selector involvedObject.name=fulfillment-worker-0 --sort-by=.lastTimestamp
```

## Optional: RBAC Data-Gap Validation

This proves the tool still gives a bounded diagnosis when the Kubernetes API
does not allow every collector to run.

```bash
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl get pods -n kubectl-smart-complex --no-headers
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl auth can-i list events -n kubectl-smart-complex
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl logs checkout-api-0 -n kubectl-smart-complex --tail=5
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl-smart diag pod checkout-api-0 -n kubectl-smart-complex
```

Expected behavior:

- `kubectl get pods` succeeds.
- `kubectl auth can-i list events` prints `no`.
- `kubectl logs` returns a Forbidden error for `pods/log`.
- `kubectl-smart diag` still reports the pod status evidence, but includes
  `DATA GAPS` entries for both events and logs with the exact RBAC errors.
- Because only warning-level status evidence is available in this restricted
  view, that diagnosis exits `1` instead of overstating the case as critical.

## Cleanup

```bash
./demo-complex-scenarios.sh cleanup
```
