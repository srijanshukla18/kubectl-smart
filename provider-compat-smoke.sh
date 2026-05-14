#!/usr/bin/env bash
set -euo pipefail

CONTEXT="${KUBECTL_SMART_CONTEXT:-${1:-}}"
NAMESPACE="${NAMESPACE:-kube-system}"
KUBECTL_SMART_CMD_STRING="${KUBECTL_SMART_CMD:-./kubectl-smart}"
KUBECTL_SMART_TIMEOUT="${KUBECTL_SMART_TIMEOUT:-5}"
KUBECTL_SMART_CMD=()
read -r -a KUBECTL_SMART_CMD <<< "$KUBECTL_SMART_CMD_STRING"

tmpdir=""
previous_context=""

log() { echo "[$(date +%H:%M:%S)] $*"; }

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cleanup() {
  if [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then
    rm -rf "$tmpdir"
  fi
}
trap cleanup EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
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

status_of() {
  cat "${tmpdir}/${1}.status"
}

assert_status() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(status_of "$name")"
  if [ "$actual" != "$expected" ]; then
    echo "---- ${name} output ----" >&2
    cat "${tmpdir}/${name}.out" >&2
    fail "${name}: expected exit ${expected}, got ${actual}"
  fi
}

assert_status_in() {
  local name="$1"
  shift
  local actual
  actual="$(status_of "$name")"
  local allowed
  for allowed in "$@"; do
    if [ "$actual" = "$allowed" ]; then
      return
    fi
  done
  echo "---- ${name} output ----" >&2
  cat "${tmpdir}/${name}.out" >&2
  fail "${name}: unexpected exit ${actual}; allowed: $*"
}

assert_contains() {
  local file="$1"
  local needle="$2"
  local description="$3"
  if ! grep -Fq "$needle" "$file"; then
    echo "---- output missing: ${description} ----" >&2
    cat "$file" >&2
    fail "Missing expected text: $needle"
  fi
}

assert_missing() {
  local file="$1"
  local needle="$2"
  local description="$3"
  if grep -Fq "$needle" "$file"; then
    echo "---- unexpected output: ${description} ----" >&2
    cat "$file" >&2
    fail "Unexpected text present: $needle"
  fi
}

if [ -z "$CONTEXT" ]; then
  fail "Set KUBECTL_SMART_CONTEXT or pass a context as the first argument"
fi

require_command kubectl

tmpdir="$(mktemp -d)"
previous_context="$(kubectl config current-context 2>/dev/null || true)"

log "Provider compatibility smoke context: $CONTEXT"
log "Namespace: $NAMESPACE"
log "kubectl-smart command: $KUBECTL_SMART_CMD_STRING"

kubectl --context "$CONTEXT" get namespace "$NAMESPACE" >/dev/null
kubectl --context "$CONTEXT" get --raw /version >/dev/null

top_node="${tmpdir}/kubectl-top-node.out"
set +e
kubectl --context "$CONTEXT" top node >"$top_node" 2>&1
node_metrics_status=$?
set -e
if [ "$node_metrics_status" = "0" ]; then
  log "kubectl top node succeeded"
else
  log "kubectl top node unavailable; kubectl-smart should report a node metrics data gap"
  cat "$top_node"
fi

top_pods="${tmpdir}/kubectl-top-pods.out"
set +e
kubectl --context "$CONTEXT" -n "$NAMESPACE" top pods >"$top_pods" 2>&1
pod_metrics_status=$?
set -e
if [ "$pod_metrics_status" = "0" ]; then
  log "kubectl top pods succeeded in $NAMESPACE"
else
  log "kubectl top pods unavailable in $NAMESPACE; kubectl-smart should report a pod metrics data gap"
  cat "$top_pods"
fi

log "Running kubectl-smart top"
top_out="$(capture top \
  "${KUBECTL_SMART_CMD[@]}" top "$NAMESPACE" --context "$CONTEXT" --timeout "$KUBECTL_SMART_TIMEOUT")"
assert_status top 0
assert_contains "$top_out" "PREDICTIVE OUTLOOK: namespace ${NAMESPACE}" "top header"

if [ "$node_metrics_status" = "0" ]; then
  assert_missing "$top_out" "metrics nodes unavailable" "node metrics gap"
else
  assert_contains "$top_out" "metrics nodes unavailable" "node metrics gap"
fi

if [ "$pod_metrics_status" = "0" ]; then
  assert_missing "$top_out" "metrics pods unavailable" "pod metrics gap"
else
  assert_contains "$top_out" "metrics pods unavailable" "pod metrics gap"
fi

first_pod="$(
  kubectl --context "$CONTEXT" -n "$NAMESPACE" get pods \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
)"

if [ -n "$first_pod" ]; then
  log "Running kubectl-smart diag and graph against existing pod: $first_pod"
  diag_out="$(capture diag \
    "${KUBECTL_SMART_CMD[@]}" diag pod "$first_pod" -n "$NAMESPACE" \
      --context "$CONTEXT" --timeout "$KUBECTL_SMART_TIMEOUT")"
  assert_status_in diag 0 1 2
  assert_contains "$diag_out" "DIAGNOSIS: Pod/${NAMESPACE}/${first_pod}" "diag header"

  graph_out="$(capture graph \
    "${KUBECTL_SMART_CMD[@]}" graph pod "$first_pod" -n "$NAMESPACE" \
      --context "$CONTEXT" --upstream --timeout "$KUBECTL_SMART_TIMEOUT")"
  assert_status_in graph 0 2
  assert_contains "$graph_out" "DEPENDENCY GRAPH: Pod/${NAMESPACE}/${first_pod}" "graph header"
else
  log "No pods found in $NAMESPACE; skipping diag/graph compatibility checks"
fi

current_context="$(kubectl config current-context 2>/dev/null || true)"
if [ "$current_context" != "$previous_context" ]; then
  fail "Global kubectl context changed from '$previous_context' to '$current_context'"
fi

log "Provider compatibility smoke passed for $CONTEXT/$NAMESPACE"
