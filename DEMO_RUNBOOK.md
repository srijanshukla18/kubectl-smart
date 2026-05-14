# Complex Demo Runbook

These scenarios live in `kubectl-smart-complex` and do not modify the existing
`kubectl-smart-lab` failures.

For the narration track, use `DEMO_TRANSCRIPT.md`. This file stays focused on
setup, validation, and command order.

Context rule: do not rely on the global kube context while recording. Pin every
demo command to `kind-kubectl-smart-demo` through `KUBECTL_SMART_CONTEXT` or an
explicit `--context` flag.

## Setup

```bash
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
export KUBECTL_SMART_CMD=./kubectl-smart

./demo-complex-scenarios.sh apply
kubectl --context "$KUBECTL_SMART_CONTEXT" get pods -n kubectl-smart-complex
./demo-smoke.sh
```

The setup also writes `.kubectl-smart-rbac.kubeconfig`, a restricted kubeconfig
for validating how `kubectl-smart` behaves when events and pod logs are hidden
by RBAC.

Do not run cleanup before recording. The failing resources are the demo.

## 3-Minute Recording Path

### Case 1: Checkout Cascade, Root Cause, Graph, and Forecast

This one shows a crashlooping checkout StatefulSet with a realistic dependency
shape: ServiceAccount, ConfigMap, Secret, PVC, Node, Service, an intentionally
empty inventory Service, metrics/PVC signal handling, and a short-lived TLS
certificate.

```bash
./kubectl-smart diag sts checkout-api -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart diag svc inventory-db -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart top kubectl-smart-complex --horizon 72 --context "$KUBECTL_SMART_CONTEXT"
```

For a narrower batch view while recording or debugging a large namespace:

```bash
./kubectl-smart diag pod --all -n kubectl-smart-complex -l demo.kubectl-smart/story=checkout-cascade --context "$KUBECTL_SMART_CONTEXT"
```

### Case 2: Honest Degradation Under RBAC

This one shows the same debugging posture when the kubeconfig can read pods but
cannot read Events or pod logs. It proves the tool reports explicit data gaps
instead of inventing certainty.

```bash
env KUBECONFIG=.kubectl-smart-rbac.kubeconfig \
  ./kubectl-smart diag pod checkout-api-0 \
  -n kubectl-smart-complex \
  --context kubectl-smart-rbac-demo
```

Expected behavior:

- `diag` still returns the pod status evidence it can support.
- Events and pod logs appear under `DATA GAPS` with exact RBAC errors.
- The diagnosis exits warning-level instead of overstating a critical root cause
  from incomplete evidence.

## Optional Longer Second Failure: Fulfillment Config Trap

Use this if the video can run longer than three minutes or if you want the
second case to be a different broken workload instead of the RBAC trust cutaway.
It shows a pod that is scheduled and has rich dependencies, but it cannot start
because a runtime Secret referenced through `env` is missing.

```bash
./kubectl-smart diag pod fulfillment-worker-0 -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart graph pod fulfillment-worker-0 -n kubectl-smart-complex --upstream --downstream --context "$KUBECTL_SMART_CONTEXT"
kubectl --context "$KUBECTL_SMART_CONTEXT" get events -n kubectl-smart-complex --field-selector involvedObject.name=fulfillment-worker-0 --sort-by=.lastTimestamp
```

## Optional: Manual RBAC Checks

This proves the tool still gives a bounded diagnosis when the Kubernetes API
does not allow every collector to run.

```bash
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl --context kubectl-smart-rbac-demo get pods -n kubectl-smart-complex --no-headers
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl --context kubectl-smart-rbac-demo auth can-i list events -n kubectl-smart-complex
KUBECONFIG=.kubectl-smart-rbac.kubeconfig kubectl --context kubectl-smart-rbac-demo logs checkout-api-0 -n kubectl-smart-complex --tail=5
KUBECONFIG=.kubectl-smart-rbac.kubeconfig ./kubectl-smart diag pod checkout-api-0 -n kubectl-smart-complex --context kubectl-smart-rbac-demo
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
