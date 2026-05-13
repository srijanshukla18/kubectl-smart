#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-kubectl-smart-complex}"
RBAC_KUBECONFIG="${RBAC_KUBECONFIG:-.kubectl-smart-rbac.kubeconfig}"
RBAC_CONTEXT="${RBAC_CONTEXT:-kubectl-smart-rbac-demo}"
KUBECTL_SMART_CONTEXT="${KUBECTL_SMART_CONTEXT:-$(kubectl config current-context 2>/dev/null || true)}"
KUBECTL_SMART_CMD_STRING="${KUBECTL_SMART_CMD:-./kubectl-smart}"
SAFE_CONTEXT_PATTERN="${KUBECTL_SMART_SAFE_CONTEXT_PATTERN:-^(kind-|minikube$|colima$)}"
KUBECTL_SMART_CMD=()
read -r -a KUBECTL_SMART_CMD <<< "$KUBECTL_SMART_CMD_STRING"

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

refresh_restricted_kubeconfig() {
  if [ ! -x ./demo-complex-scenarios.sh ]; then
    fail "Cannot refresh restricted kubeconfig; missing executable ./demo-complex-scenarios.sh"
  fi

  log "Refreshing restricted kubeconfig token..."
  env \
    NAMESPACE="$NAMESPACE" \
    KUBECTL_SMART_CONTEXT="$KUBECTL_SMART_CONTEXT" \
    RBAC_KUBECONFIG="$RBAC_KUBECONFIG" \
    ./demo-complex-scenarios.sh rbac >/dev/null
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

assert_missing_diag_json_contract() {
  local file="$1"
  if ! uv run python3 - "$file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

assert data["type"] == "diagnosis"
assert data["resource"] is None
assert data["status"] is None
assert data["analysis_complete"] is False
assert data["exit_code"] == 2
assert data["data_gap_count"] > 0
PY
  then
    echo "---- invalid missing-resource diagnosis JSON ----" >&2
    cat "$file" >&2
    fail "Missing-resource diagnosis JSON contract failed"
  fi
}

assert_restricted_batch_json_contract() {
  local file="$1"
  if ! uv run python3 - "$file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

assert data["type"] == "batch_diagnosis"
assert data["summary"]["analysis_complete"] is False
assert data["summary"]["data_gaps"] == 6
assert len(data["results"]) == 3
for result in data["results"]:
    assert result["analysis_complete"] is False
    assert result["data_gap_count"] == 2
PY
  then
    echo "---- invalid restricted batch JSON ----" >&2
    cat "$file" >&2
    fail "Restricted batch JSON contract failed"
  fi
}

guard_context
log "Using kubectl-smart command: $KUBECTL_SMART_CMD_STRING"
tmpdir="$(mktemp -d)"

log "Checking demo namespace and pods exist..."
kubectl --context "$KUBECTL_SMART_CONTEXT" get pod checkout-api-0 -n "$NAMESPACE" >/dev/null
kubectl --context "$KUBECTL_SMART_CONTEXT" get pod fulfillment-worker-0 -n "$NAMESPACE" >/dev/null
kubectl --context "$KUBECTL_SMART_CONTEXT" get service inventory-db -n "$NAMESPACE" >/dev/null

log "Checking checkout diagnosis includes evidence-backed root cause..."
checkout_diag="$(capture checkout_diag "${KUBECTL_SMART_CMD[@]}" diag pod checkout-api-0 -n "$NAMESPACE" --context "$KUBECTL_SMART_CONTEXT")"
assert_status checkout_diag 2
assert_contains "$checkout_diag" "LIKELY ROOT CAUSE" "checkout root cause section"
assert_contains "$checkout_diag" "Evidence:" "checkout evidence section"
assert_contains "$checkout_diag" "Log line:" "checkout log evidence"

log "Checking StatefulSet diagnosis promotes child pod evidence..."
checkout_sts_diag="$(capture checkout_sts_diag "${KUBECTL_SMART_CMD[@]}" diag sts checkout-api -n "$NAMESPACE" --context "$KUBECTL_SMART_CONTEXT")"
assert_status checkout_sts_diag 2
assert_contains "$checkout_sts_diag" "DIAGNOSIS: StatefulSet/${NAMESPACE}/checkout-api" "checkout statefulset header"
assert_contains "$checkout_sts_diag" "Pod checkout-api-0: Log Errors" "checkout child pod root cause"
assert_contains "$checkout_sts_diag" "OwnerReference: Pod/${NAMESPACE}/checkout-api-0 is owned by" "checkout child ownership evidence"
assert_contains "$checkout_sts_diag" "StatefulSet/${NAMESPACE}/checkout-api" "checkout child owner evidence"

log "Checking checkout graph shows upstream and downstream blast-radius context..."
checkout_graph="$(capture checkout_graph "${KUBECTL_SMART_CMD[@]}" graph pod checkout-api-0 -n "$NAMESPACE" --context "$KUBECTL_SMART_CONTEXT" --upstream --downstream --timeout 2)"
assert_status checkout_graph 0
assert_contains "$checkout_graph" "UPSTREAM DEPENDENCIES" "checkout graph upstream section"
assert_contains "$checkout_graph" "DOWNSTREAM DEPENDENCIES" "checkout graph downstream section"
assert_contains "$checkout_graph" "ConfigMap/${NAMESPACE}/checkout-config" "checkout graph config dependency"
assert_contains "$checkout_graph" "Service/${NAMESPACE}/checkout-api" "checkout graph service dependency"
assert_contains "$checkout_graph" "Ingress/${NAMESPACE}/checkout-demo" "checkout graph ingress dependency"

log "Checking service diagnosis cites endpoint and selector evidence..."
service_diag="$(capture service_diag "${KUBECTL_SMART_CMD[@]}" diag svc inventory-db -n "$NAMESPACE" --context "$KUBECTL_SMART_CONTEXT")"
assert_status service_diag 2
assert_contains "$service_diag" "Service has no ready endpoints" "service endpoint root cause"
assert_contains "$service_diag" "Endpoints/${NAMESPACE}/inventory-db: ready addresses=0" "endpoint count evidence"
assert_contains "$service_diag" "No Pods in namespace match selector" "selector evidence"

log "Checking predictive outlook shows TLS warning and explicit metrics data gap..."
top_outlook="$(capture top_outlook "${KUBECTL_SMART_CMD[@]}" top "$NAMESPACE" --context "$KUBECTL_SMART_CONTEXT" --horizon 72 --timeout 2)"
assert_status top_outlook 0
assert_contains "$top_outlook" "PREDICTIVE OUTLOOK: namespace ${NAMESPACE}" "top namespace header"
assert_contains "$top_outlook" "CERTIFICATE WARNINGS" "top certificate warning"
assert_contains "$top_outlook" "DATA GAPS (1)" "top data-gap count"
assert_contains "$top_outlook" "metrics pods unavailable" "top metrics data gap"

log "Checking top fails closed when the namespace is missing..."
missing_top="$(capture missing_top "${KUBECTL_SMART_CMD[@]}" top kubectl-smart-definitely-missing --context "$KUBECTL_SMART_CONTEXT" --timeout 2)"
assert_status missing_top 2
assert_contains "$missing_top" "Namespace kubectl-smart-definitely-missing not found" "missing namespace top error"
assert_contains "$missing_top" "get namespace unavailable (not_found)" "missing namespace top evidence"

log "Checking admin batch diagnosis reports namespace-scale data gaps..."
batch_diag="$(capture batch_diag "${KUBECTL_SMART_CMD[@]}" diag pod --all -n "$NAMESPACE" --max-concurrent 1 --context "$KUBECTL_SMART_CONTEXT")"
assert_status batch_diag 2
assert_contains "$batch_diag" "Total: 3 | Analyzed: 3 | Failed: 0" "batch summary"
assert_contains "$batch_diag" "Data gaps:" "batch data-gap summary"
assert_contains "$batch_diag" "Concurrency: 1" "batch concurrency summary"

log "Checking label-selected batch diagnosis narrows namespace scope..."
selector_batch="$(capture selector_batch "${KUBECTL_SMART_CMD[@]}" diag pod --all -n "$NAMESPACE" -l demo.kubectl-smart/story=checkout-cascade --context "$KUBECTL_SMART_CONTEXT")"
assert_status selector_batch 2
assert_contains "$selector_batch" "Total: 2 | Analyzed: 2 | Failed: 0" "label-selected batch summary"
assert_contains "$selector_batch" "Selector: demo.kubectl-smart/story=checkout-cascade" "label-selected batch selector"
assert_contains "$selector_batch" "checkout-api-0:" "label-selected checkout pod"
assert_contains "$selector_batch" "inventory-db-canary" "label-selected inventory pod"

log "Checking missing-resource JSON marks diagnosis incomplete..."
missing_diag_json="$(capture missing_diag_json "${KUBECTL_SMART_CMD[@]}" diag pod kubectl-smart-definitely-missing -n "$NAMESPACE" -o json --context "$KUBECTL_SMART_CONTEXT")"
assert_status missing_diag_json 2
assert_missing_diag_json_contract "$missing_diag_json"

if [ ! -f "$RBAC_KUBECONFIG" ]; then
  refresh_restricted_kubeconfig
fi

log "Checking restricted kubeconfig permission envelope..."
restricted_pods="$(capture restricted_pods env KUBECONFIG="$RBAC_KUBECONFIG" kubectl --context "$RBAC_CONTEXT" get pods -n "$NAMESPACE" --no-headers)"
if [ "$(cat "${tmpdir}/restricted_pods.status")" != "0" ] && grep -Fq "Unauthorized" "$restricted_pods"; then
  log "Restricted kubeconfig token is stale; refreshing it and retrying once..."
  refresh_restricted_kubeconfig
  restricted_pods="$(capture restricted_pods env KUBECONFIG="$RBAC_KUBECONFIG" kubectl --context "$RBAC_CONTEXT" get pods -n "$NAMESPACE" --no-headers)"
fi
assert_status restricted_pods 0
assert_contains "$restricted_pods" "checkout-api-0" "restricted pod list"

restricted_events="$(capture restricted_events env KUBECONFIG="$RBAC_KUBECONFIG" kubectl --context "$RBAC_CONTEXT" auth can-i list events -n "$NAMESPACE")"
assert_status restricted_events 1
assert_contains "$restricted_events" "no" "restricted event denial"

restricted_logs="$(capture restricted_logs env KUBECONFIG="$RBAC_KUBECONFIG" kubectl --context "$RBAC_CONTEXT" logs checkout-api-0 -n "$NAMESPACE" --tail=5)"
assert_status restricted_logs 1
assert_contains "$restricted_logs" "cannot get resource \"pods/log\"" "restricted log denial"

log "Checking restricted diagnosis surfaces exact RBAC data gaps..."
restricted_diag="$(capture restricted_diag env KUBECONFIG="$RBAC_KUBECONFIG" "${KUBECTL_SMART_CMD[@]}" diag pod checkout-api-0 -n "$NAMESPACE" --context "$RBAC_CONTEXT")"
assert_status restricted_diag 1
assert_contains "$restricted_diag" "DATA GAPS (2)" "restricted diag gap count"
assert_contains "$restricted_diag" "events events unavailable (rbac)" "restricted event gap"
assert_contains "$restricted_diag" "logs pods unavailable (rbac)" "restricted log gap"

restricted_fulfillment="$(capture restricted_fulfillment env KUBECONFIG="$RBAC_KUBECONFIG" "${KUBECTL_SMART_CMD[@]}" diag pod fulfillment-worker-0 -n "$NAMESPACE" --context "$RBAC_CONTEXT")"
assert_status restricted_fulfillment 2
assert_contains "$restricted_fulfillment" "Verify missing Secret: kubectl get secret missing-fulfillment-runtime-token" "restricted missing Secret action"
assert_contains "$restricted_fulfillment" "DATA GAPS (2)" "restricted fulfillment gap count"

log "Checking fulfillment graph preserves the missing env Secret dependency..."
fulfillment_graph="$(capture fulfillment_graph "${KUBECTL_SMART_CMD[@]}" graph pod fulfillment-worker-0 -n "$NAMESPACE" --context "$KUBECTL_SMART_CONTEXT" --upstream --downstream --timeout 2)"
assert_status fulfillment_graph 0
assert_contains "$fulfillment_graph" "Secret/${NAMESPACE}/missing-fulfillment-runtime-token" "fulfillment graph missing env secret"
assert_contains "$fulfillment_graph" "ConfigMap/${NAMESPACE}/fulfillment-routing" "fulfillment graph config dependency"
assert_contains "$fulfillment_graph" "Service/${NAMESPACE}/fulfillment-worker" "fulfillment graph service dependency"

log "Checking restricted batch JSON preserves per-resource data gaps..."
restricted_batch_json="$(capture restricted_batch_json env KUBECONFIG="$RBAC_KUBECONFIG" "${KUBECTL_SMART_CMD[@]}" diag pod --all -n "$NAMESPACE" -o json --context "$RBAC_CONTEXT")"
assert_status restricted_batch_json 2
assert_contains "$restricted_batch_json" '"data_gaps": 6' "restricted batch total gaps"
assert_contains "$restricted_batch_json" '"analysis_complete": false' "restricted batch incomplete summary"
assert_contains "$restricted_batch_json" '"data_gap_count": 2' "restricted batch per-resource gaps"
assert_contains "$restricted_batch_json" 'cannot get resource \"pods/log\"' "restricted batch log evidence"
assert_restricted_batch_json_contract "$restricted_batch_json"

log "Demo smoke passed."
