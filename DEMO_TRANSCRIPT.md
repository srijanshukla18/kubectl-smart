# kubectl-smart 3-Minute Demo Transcript

## Setup Before Recording

Run from the repository checkout. Pin the demo context for this shell so the
recording does not depend on the global kubectl context:

```bash
export KUBECTL_SMART_CONTEXT=kind-kubectl-smart-demo
kubectl --context "$KUBECTL_SMART_CONTEXT" get pods -n kubectl-smart-complex
./demo-smoke.sh
```

Expected demo context:

```text
kind-kubectl-smart-demo
```

## Transcript

### 0:00-0:25 - Hook

Say:

> Kubernetes debugging usually starts with a pile of separate commands: get pods,
> describe, logs, events, services, PVCs, secrets, and then you mentally stitch
> the story together.
>
> I built `kubectl-smart` for that messy middle part. It is a read-only kubectl
> plugin that pulls the usual debugging signals together and turns them into
> three views: root cause, dependency graph, and predictive warnings.

Run:

```bash
./kubectl-smart --help
```

Say:

> The three commands are intentionally simple: `diag`, `graph`, and `top`.
> Let me show you two failure stories that are a little more realistic than a
> single broken pod.

### 0:25-1:35 - Case 1: Checkout Cascade

Say:

> First scenario: a checkout service is failing. In a real incident, this kind of
> thing is annoying because the pod is only the visible symptom. It depends on a
> ConfigMap, Secret, PVC, ServiceAccount, Service, StatefulSet, and there is also
> TLS sitting in the namespace.

Run:

```bash
./kubectl-smart diag sts checkout-api -n kubectl-smart-complex
```

Say:

> I do not even need to start at the exact pod. I can start at the owning
> StatefulSet, and `diag` follows the ownership chain down to the child pod.
> Kubernetes is reporting BackOff, but the tool promotes the more useful
> evidence: the application logs show fatal startup errors and a panic. So
> instead of me treating BackOff as the answer, the first screen tells me what
> failed inside the container, and keeps the BackOff event as supporting context.

Run:

```bash
./kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream
```

Say:

> Now `graph` gives me the shape of the blast radius. Upstream, I can see the
> node, PVC, ConfigMap, Secret, ServiceAccount, and the owning StatefulSet.
> Downstream, I can see the Service that points at this pod.
>
> This is the part I wanted while debugging: not just "what is broken", but "what
> is this thing connected to?"

Run:

```bash
./kubectl-smart diag svc inventory-db -n kubectl-smart-complex
```

Say:

> Here is the same idea applied to a Service. `diag` does not just say "the
> service exists." It checks the Endpoints object and the selector. The useful
> evidence is right there: zero ready endpoint addresses, selector
> `app=inventory-db,release=stable`, and no pods in the namespace matching that
> selector.

Run:

```bash
./kubectl-smart top kubectl-smart-complex --horizon 72
```

Say:

> Finally, `top` looks at predictive risks in the namespace. In this demo it
> spots an actually short-lived TLS Secret, not just an Ingress reference, so
> the same tool can help with immediate debugging and with "this will bite us
> soon" problems. If a signal is missing, like metrics-server or kubelet PVC
> volume stats, it says that explicitly under data gaps instead of pretending
> the analysis was complete.

### 1:35-2:35 - Case 2: Fulfillment Config Trap

Say:

> Second scenario: a fulfillment worker looks like a scheduling/config problem.
> The pod exists, it is assigned to a node, the image pulls, but it never starts.
> This is the sort of issue where the useful evidence is buried in events.

Run:

```bash
./kubectl-smart diag pod fulfillment-worker-0 -n kubectl-smart-complex
```

Say:

> Here `diag` points directly at the actual failure: Kubernetes cannot find the
> runtime Secret referenced by the pod. It shows the exact Warning event as
> evidence and suggests checking or restoring that Secret, instead of sending me
> down a useless log-checking path.

Run:

```bash
./kubectl-smart graph pod fulfillment-worker-0 -n kubectl-smart-complex --upstream --downstream
```

Say:

> And the graph is still useful even though the container never starts. I can see
> that the pod has a PVC, ConfigMap, mounted Secret, ServiceAccount, owning
> StatefulSet, and downstream Service. The important bit is that the missing env
> Secret also appears as a red upstream dependency, so the graph does not hide
> required resources just because they are absent.

Run:

```bash
kubectl --context "$KUBECTL_SMART_CONTEXT" get events -n kubectl-smart-complex --field-selector involvedObject.name=fulfillment-worker-0 --sort-by=.lastTimestamp
```

Say:

> This is the raw kubectl evidence underneath the diagnosis: scheduled, image
> pulled, then `secret missing-fulfillment-runtime-token not found`.

### 2:35-3:00 - Close

Say:

> The point of `kubectl-smart` is not to replace kubectl. It is to compress the
> first few minutes of debugging into one or two commands, while staying
> read-only and transparent about the evidence.
>
> If you already know Kubernetes, this gives you a faster first pass. If you are
> still learning Kubernetes, it shows you which signals matter and how resources
> are connected.
>
> The project is open source, early, and I would love feedback from people who
> debug real clusters.

## Optional Trust Cutaway

Use this only if you want to show the safety behavior instead of the shorter
close.

Run:

```bash
env KUBECONFIG=.kubectl-smart-rbac.kubeconfig ./kubectl-smart diag pod checkout-api-0 -n kubectl-smart-complex --context kubectl-smart-rbac-demo
```

Say:

> One design choice I care about is not pretending. This kubeconfig can read the
> pod, but it cannot read Events or pod logs. So `kubectl-smart` still gives me
> the diagnosis it can support from pod status, and then it shows those missing
> collectors under `DATA GAPS` with the exact RBAC errors. Notice it does not
> upgrade that limited evidence into a critical claim. That is the behavior I
> want in real incidents: useful, but honest about what it could not see.

## Shorter 60-Second Version

Say:

> `kubectl-smart` is a read-only kubectl plugin for the first few minutes of
> Kubernetes debugging. It has three commands: `diag` for root cause, `graph` for
> dependencies, and `top` for predictive risks like certificates and capacity.

Run:

```bash
./kubectl-smart diag pod checkout-api-0 -n kubectl-smart-complex
./kubectl-smart graph pod checkout-api-0 -n kubectl-smart-complex --upstream --downstream
./kubectl-smart diag svc inventory-db -n kubectl-smart-complex
./kubectl-smart top kubectl-smart-complex --horizon 72
```

Say:

> In one flow, I get the actual fatal log evidence behind a restart loop, the
> dependency shape around the workload, a selector-to-endpoints failure on a
> Service, and an expiring TLS certificate in the namespace. That is the job:
> keep kubectl, but make the first debugging pass much faster.
