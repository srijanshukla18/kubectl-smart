# Complex Demo Runbook

These scenarios live in `kubectl-smart-complex` and do not modify the existing
`kubectl-smart-lab` failures.

## Setup

```bash
./demo-complex-scenarios.sh apply
kubectl get pods -n kubectl-smart-complex
```

## 3-Minute Recording Path

### Case 1: Checkout Cascade

This one shows a crashlooping checkout StatefulSet with a realistic dependency
shape: ServiceAccount, ConfigMap, Secret, PVC, Node, Service, an intentionally
empty inventory Service, and a short-lived TLS certificate.

```bash
kubectl-smart diag pod checkout-api-0 -n kubectl-smart-complex
kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream
kubectl-smart diag svc inventory-db -n kubectl-smart-complex
kubectl-smart graph ingress checkout-demo -n kubectl-smart-complex --upstream --downstream
kubectl-smart top kubectl-smart-complex --horizon 72
```

### Case 2: Fulfillment Config Trap

This one shows a pod that is scheduled and has rich dependencies, but it cannot
start because a runtime Secret referenced through `env` is missing.

```bash
kubectl-smart diag pod fulfillment-worker-0 -n kubectl-smart-complex
kubectl-smart graph pod fulfillment-worker-0 -n kubectl-smart-complex --upstream --downstream
kubectl get events -n kubectl-smart-complex --field-selector involvedObject.name=fulfillment-worker-0 --sort-by=.lastTimestamp
```

## Cleanup

```bash
./demo-complex-scenarios.sh cleanup
```
