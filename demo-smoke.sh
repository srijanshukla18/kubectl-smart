#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-kubectl-smart-complex}"
RBAC_KUBECONFIG="${RBAC_KUBECONFIG:-.kubectl-smart-rbac.kubeconfig}"
KUBECTL_SMART_CONTEXT="${KUBECTL_SMART_CONTEXT:-$(kubectl config current-context 2>/dev/null || true)}"
SAFE_CONTEXT_PATTERN="${KUBECTL_SMART_SAFE_CONTEXT_PATTERN:-^(kind-|minikube$|colima$)}"

tmpdir=""

log() { echo "[$(date +%H:%M:%S)] $*"; }

finish() {
  if [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then
    rm -rf "$tmpdir"
  fi
}
trap finish EXIT

fail() {
  echo "❌ $*" >&2
  exit 1
}

guard_context() {
  if [ -z "$KUBECTL_SMART_CONTEXT" ]; then
    fail "No Kubernetes context is selected"
  fi
  if ! [[ "$KUBECTL_SMART_CONTEXT" =~ $SAFE_CONTEXT_PATTERN ]]; then
    fail "Refusing context '$KUBECTL_SMART_CONTEXT'; expected local context matching $SAFE_CONTEXT_PATTERN"
  fi
  log "Using Kubernetes context: $KUBECTL_SMART_CONTEXT"
}

capture() {
  local name="$1"
  shift
  local outfile="${tmpdir}/${name}.out"
  local statusfile="${tmpdir}/${name}.status"

  set +e
  "$@" >"$outfile" 2>&1
  local status=$?
  set -e

  echo "$status" >"$statusfile"
  echo "$outfile"
}

assert_status() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(cat "${tmpdir}/${name}.status")"
  if [ "$actual" != "$expected" ]; then
    echo "---- ${name} output ----" >&2
    cat "${tmpdir}/${name}.out" >&2
    fail "${name}: expected exit ${expected}, got ${actual}"
  fi
}

assert_contains() {
  local file="$1"
  local needle="$2"
  local description="$3"
  if ! grep -Fq "$needle" "$file"; then
    echo "---- output missing: ${description} ----" >&2
    cat "$file" >&2
    fail "Missing expected text: ${needle}"
  fi
}

guard_context
tmpdir="$(mktemp -d)"

log "Checking demo namespace and pods exist..."
kubectl --context "$KUBECTL_SMART_CONTEXT" get pod checkout-api-0 -n "$NAMESPACE" >/dev/null
kubectl --context "$KUBECTL_SMART_CONTEXT" get pod fulfillment-worker-0 -n "$NAMESPACE" >/dev/null
kubectl --context "$KUBECTL_SMART_CONTEXT" get service inventory-db -n "$NAMESPACE" >/dev/null

log "Checking checkout diagnosis includes evidence-backed root cause..."
checkout_diag="$(capture checkout_diag kubectl-smart diag pod checkout-api-0 -n "$NAMESPACE")"
assert_status checkout_diag 2
assert_contains "$checkout_diag" "LIKELY ROOT CAUSE" "checkout root cause section"
assert_contains "$checkout_diag" "Evidence:" "checkout evidence section"
assert_contains "$checkout_diag" "Log line:" "checkout log evidence"

log "Checking service diagnosis cites endpoint and selector evidence..."
service_diag="$(capture service_diag kubectl-smart diag svc inventory-db -n "$NAMESPACE")"
assert_status service_diag 2
assert_contains "$service_diag" "Service has no ready endpoints" "service endpoint root cause"
assert_contains "$service_diag" "Endpoints/${NAMESPACE}/inventory-db: ready addresses=0" "endpoint count evidence"
assert_contains "$service_diag" "No Pods in namespace match selector" "selector evidence"

log "Checking admin batch diagnosis reports namespace-scale data gaps..."
batch_diag="$(capture batch_diag kubectl-smart diag pod --all -n "$NAMESPACE")"
assert_status batch_diag 2
assert_contains "$batch_diag" "Total: 3 | Analyzed: 3 | Failed: 0" "batch summary"
assert_contains "$batch_diag" "Data gaps:" "batch data-gap summary"

if [ ! -f "$RBAC_KUBECONFIG" ]; then
  fail "Missing restricted kubeconfig $RBAC_KUBECONFIG; run ./demo-complex-scenarios.sh apply"
fi

log "Checking restricted kubeconfig permission envelope..."
restricted_pods="$(capture restricted_pods env KUBECONFIG="$RBAC_KUBECONFIG" kubectl get pods -n "$NAMESPACE" --no-headers)"
assert_status restricted_pods 0
assert_contains "$restricted_pods" "checkout-api-0" "restricted pod list"

restricted_events="$(capture restricted_events env KUBECONFIG="$RBAC_KUBECONFIG" kubectl auth can-i list events -n "$NAMESPACE")"
assert_status restricted_events 1
assert_contains "$restricted_events" "no" "restricted event denial"

restricted_logs="$(capture restricted_logs env KUBECONFIG="$RBAC_KUBECONFIG" kubectl logs checkout-api-0 -n "$NAMESPACE" --tail=5)"
assert_status restricted_logs 1
assert_contains "$restricted_logs" "cannot get resource \"pods/log\"" "restricted log denial"

log "Checking restricted diagnosis surfaces exact RBAC data gaps..."
restricted_diag="$(capture restricted_diag env KUBECONFIG="$RBAC_KUBECONFIG" kubectl-smart diag pod checkout-api-0 -n "$NAMESPACE")"
assert_status restricted_diag 2
assert_contains "$restricted_diag" "DATA GAPS (2)" "restricted diag gap count"
assert_contains "$restricted_diag" "events events unavailable (rbac)" "restricted event gap"
assert_contains "$restricted_diag" "logs pods unavailable (rbac)" "restricted log gap"

restricted_fulfillment="$(capture restricted_fulfillment env KUBECONFIG="$RBAC_KUBECONFIG" kubectl-smart diag pod fulfillment-worker-0 -n "$NAMESPACE")"
assert_status restricted_fulfillment 2
assert_contains "$restricted_fulfillment" "Verify missing Secret: kubectl get secret missing-fulfillment-runtime-token" "restricted missing Secret action"
assert_contains "$restricted_fulfillment" "DATA GAPS (2)" "restricted fulfillment gap count"

log "Checking restricted batch JSON preserves per-resource data gaps..."
restricted_batch_json="$(capture restricted_batch_json env KUBECONFIG="$RBAC_KUBECONFIG" kubectl-smart diag pod --all -n "$NAMESPACE" -o json)"
assert_status restricted_batch_json 2
assert_contains "$restricted_batch_json" '"data_gaps": 6' "restricted batch total gaps"
assert_contains "$restricted_batch_json" '"data_gap_count": 2' "restricted batch per-resource gaps"
assert_contains "$restricted_batch_json" 'cannot get resource \"pods/log\"' "restricted batch log evidence"

log "Demo smoke passed."
