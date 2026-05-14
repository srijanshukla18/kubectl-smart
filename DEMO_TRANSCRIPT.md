# kubectl-smart 3-Minute Demo Transcript

## Setup Before Recording

Run from the repository checkout. Pin the demo context for this shell so the
recording does not depend on the global kubectl context.

```bash
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
export KUBECTL_SMART_CMD=./kubectl-smart

./demo-complex-scenarios.sh apply
kubectl --context "$KUBECTL_SMART_CONTEXT" get pods -n kubectl-smart-complex
./demo-smoke.sh
```

Expected demo context:

```text
kind-kubectl-smart-demo
```

Do not use `colima` for the recording. Keep the demo pinned to the explicit
`kind-kubectl-smart-demo` context.

## Recommended 3-Minute Transcript

### 0:00-0:22 - Hook

Say:

> Kubernetes debugging usually starts with a pile of separate commands:
> describe, logs, events, services, selectors, PVCs, secrets, metrics, and then
> you mentally stitch the story together while something is broken.
>
> `kubectl-smart` is a read-only kubectl helper for that first pass. It gives me
> three views: `diag` for evidence-backed root cause, `graph` for dependency
> context, and `top` for predictive risks and missing signals.

Run:

```bash
./kubectl-smart --help
```

Say:

> The important part is that it does not try to replace kubectl. It compresses
> the first few minutes of kubectl work, and it tells me when the cluster did
> not give it enough evidence.

### 0:22-1:52 - Case 1: Checkout Cascade

Say:

> First case: checkout is failing. This is intentionally more realistic than one
> bad pod. There is an owning StatefulSet, a child pod, ConfigMaps, Secrets,
> PVCs, a ServiceAccount, a Service, an Ingress, metrics signals, and a short
> lived TLS Secret in the namespace.

Run:

```bash
./kubectl-smart diag sts checkout-api -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> I can start at the StatefulSet instead of knowing the exact pod name.
> `kubectl-smart` follows the owner chain to the child pod and separates the
> symptom from the useful evidence.
>
> Kubernetes is reporting BackOff, but the diagnosis promotes the better clue:
> the application log evidence shows fatal startup errors and a panic. The
> BackOff event is still there as supporting evidence, but it is not treated as
> the root cause by itself.

Run:

```bash
./kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> Now `graph` shows the blast radius around that pod. Upstream, I can see the
> node, PVC, ConfigMap, Secret, ServiceAccount, and owning StatefulSet.
> Downstream, I can see the Service that sends traffic here.
>
> This is the mental map I usually build manually during an incident: what is
> broken, what feeds it, and what depends on it.

Run:

```bash
./kubectl-smart diag svc inventory-db -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> Here is a Service-level failure. The Service exists, but the useful evidence
> is the Endpoints and selector check: zero ready endpoint addresses, selector
> `app=inventory-db,release=stable`, and no pods matching that selector.
>
> That is the difference I want: not "the object exists", but "this object is
> not routing to anything, and here is the exact Kubernetes evidence."

Run:

```bash
./kubectl-smart top kubectl-smart-complex --horizon 72 --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> Finally, `top` is the proactive view. It looks for risks like certificate
> expiry, pod and node capacity signals from metrics-server, and PVC usage when
> kubelet volume stats are exposed.
>
> The trust detail is the data-gap behavior. If metrics-server is missing, still
> warming up, blocked by RBAC, or kubelet does not expose PVC stats, it says that
> explicitly. If the collected signals are clean, it says no data gaps were
> recorded. It does not silently pretend the analysis is complete.

### 1:52-2:42 - Case 2: Restricted RBAC Honesty

Say:

> Second case is about trust. This kubeconfig is intentionally restricted: it
> can read the pod, but it cannot read Events or pod logs. A lot of tools either
> fail hard here or make the output look more certain than it is.

Run:

```bash
env KUBECONFIG=.kubectl-smart-rbac.kubeconfig \
  ./kubectl-smart diag pod checkout-api-0 \
  -n kubectl-smart-complex \
  --context kubectl-smart-rbac-demo
```

Say:

> Here the tool still gives the pod status evidence it can support, but the
> missing collectors are called out under `DATA GAPS` with the exact RBAC errors
> for Events and logs.
>
> Notice the posture: it stays useful, but it does not upgrade incomplete
> evidence into a critical claim. That is the behavior I want during a real
> incident.

### 2:42-3:00 - Close

Say:

> So the pitch is simple: keep kubectl, but make the first debugging pass
> faster. Start from the object you know, get evidence-backed root cause, see
> the dependency shape, and understand which signals were missing.
>
> This is still early and open source, but it is built around the thing I care
> about most in cluster debugging: useful output that stays honest.

## Optional Longer Case: Fulfillment Config Trap

Use this if you want the second story to be a separate workload failure instead
of the RBAC cutaway.

Say:

> Here is another realistic failure. The pod is scheduled, the image pulls, and
> the dependency graph is rich, but the container never starts because a runtime
> Secret referenced through environment variables is missing.

Run:

```bash
./kubectl-smart diag pod fulfillment-worker-0 -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> `diag` points directly at the Kubernetes event: the runtime Secret is not
> found. That matters because logs will not help when the container never
> starts.

Run:

```bash
./kubectl-smart graph pod fulfillment-worker-0 -n kubectl-smart-complex --upstream --downstream --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> The graph still helps before the container starts. It shows the PVC,
> ConfigMap, mounted Secret, ServiceAccount, owning StatefulSet, downstream
> Service, and the missing env Secret as an upstream dependency.

Run:

```bash
kubectl --context "$KUBECTL_SMART_CONTEXT" get events -n kubectl-smart-complex --field-selector involvedObject.name=fulfillment-worker-0 --sort-by=.lastTimestamp
```

Say:

> This is the raw kubectl evidence underneath the diagnosis: scheduled, image
> pulled, then `secret missing-fulfillment-runtime-token not found`.

## Shorter 60-Second Version

Say:

> `kubectl-smart` is a read-only kubectl helper for the first few minutes of
> Kubernetes debugging. It has three commands: `diag` for root cause, `graph`
> for dependencies, and `top` for predictive risks and missing signals.

Run:

```bash
./kubectl-smart diag sts checkout-api -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart diag svc inventory-db -n kubectl-smart-complex --context "$KUBECTL_SMART_CONTEXT"
./kubectl-smart top kubectl-smart-complex --horizon 72 --context "$KUBECTL_SMART_CONTEXT"
```

Say:

> In one flow, I get the fatal log evidence behind a restart loop, the dependency
> graph around the workload, a selector-to-endpoints failure on a Service, and
> proactive risk checks with explicit data gaps. That is the job: keep kubectl,
> but make the first pass faster and more honest.
