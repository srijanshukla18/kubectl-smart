# Proposal: Universal Resource Support (Generic CRDs)

## 1. Problem Statement
`kubectl-smart` is currently restricted to a hardcoded list of native Kubernetes resources (Pod, Deployment, etc.). Users cannot diagnose Custom Resources (CRDs) like:
*   Flux `HelmRelease` / `Kustomization`
*   ArgoCD `Application`
*   KEDA `ScaledObject`
*   Cert-Manager `Certificate`
*   Karpenter `Provisioner`

Since the modern cloud-native stack relies heavily on operators, this limits the tool's utility.

## 2. Solution Strategy

We will move from a "Allow-List" model to a "Generic Fallback" model.

### A. CLI Changes (`cli/main.py`)
1.  **Loosen Typing:** Change `resource_type` argument from `ResourceType` Enum to `str`.
2.  **Validation:** Instead of checking against an Enum, validation will occur at runtime by attempting to fetch the resource.

### B. Model Updates (`models.py`)
1.  **Generic Kind:** Add `ResourceKind.GENERIC` to the Enum.
2.  **Resource Record:** Allow `kind` to be a string or map unknown strings to `GENERIC` while preserving the original kind string in `properties`.

### C. Generic Diagnosis Logic (`scoring/engine.py`)
Most Kubernetes Operators follow the **Conditions Pattern** (`status.conditions`). We can exploit this.

**Algorithm:**
1.  **Fetch:** `kubectl get <kind> <name> -o json` works for *any* resource.
2.  **Parse:** Look for `status.conditions[]`.
3.  **Score:**
    *   Iterate through conditions.
    *   If `Type=Ready` and `Status=False`: **CRITICAL Issue**.
        *   Title: `Not Ready: <Reason>`
        *   Message: `<Message>` from condition.
    *   If `Type=Healthy` and `Status=False`: **CRITICAL Issue**.
    *   If `Type=Progressing` and `Status=True` (for long duration): **WARNING**.

### D. Generic Event Correlation
The `DiagCommand` fetches events using:
```bash
kubectl get events --field-selector involvedObject.kind=<Kind>,involvedObject.name=<Name>
```
This works universally for CRDs. No code change needed in the collector, just ensuring the `kind` string is passed correctly.

## 3. Example Workflow: Flux HelmRelease

**User runs:**
```bash
kubectl-smart diag helmrelease my-app
```

**Internal Execution:**
1.  **Collector:** Runs `kubectl get helmrelease my-app -o json`.
2.  **Parser:**
    *   Detects `kind: HelmRelease`.
    *   Extracts `status.conditions`.
        ```json
        {
          "type": "Ready",
          "status": "False",
          "reason": "InstallFailed",
          "message": "helm install failed: release already exists"
        }
        ```
3.  **Scorer:**
    *   Matches `Ready=False` -> Score 95.
    *   Extracts Reason "InstallFailed".
4.  **Renderer:**
    ```
    📋 DIAGNOSIS: HelmRelease/my-app
    Status: InstallFailed

    🔴 ROOT CAUSE
      💥 Not Ready: InstallFailed (score: 95.0)
        helm install failed: release already exists
    ```

## 4. Implementation Plan

1.  **Refactor Models:** Update `ResourceKind` to handle dynamic kinds.
2.  **Update CLI:** Remove `ResourceType` enum restriction.
3.  **Enhance Scorer:** Add `score_generic_conditions()` method to `ScoringEngine`.
4.  **Testing:** Verify with a mock CRD (or just a ConfigMap with fake status for testing).

## 5. Future: "Knowledge Packs"
Later, we can add specific logic for popular CRDs via a plugin system, e.g., "If Kind=HelmRelease, also check the referenced HelmChart resource."
