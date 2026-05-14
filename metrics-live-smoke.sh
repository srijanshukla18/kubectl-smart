#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-kubectl-smart-metrics-smoke-$$}"
CONTEXT="kind-${CLUSTER_NAME}"
KUBECTL_SMART_CMD_STRING="${KUBECTL_SMART_CMD:-./kubectl-smart}"
KEEP_CLUSTER="${KEEP_CLUSTER:-0}"
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
  if [ "$KEEP_CLUSTER" != "1" ]; then
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
  if [ -n "$previous_context" ]; then
    kubectl config use-context "$previous_context" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

assert_missing_text() {
  local file="$1"
  local needle="$2"
  local description="$3"
  if grep -Fq "$needle" "$file"; then
    echo "---- ${description} ----" >&2
    cat "$file" >&2
    fail "Unexpected text present: $needle"
  fi
}

capture() {
  local outfile="$1"
  shift
  "$@" >"$outfile" 2>&1
}

require_command kind
require_command docker
require_command kubectl

tmpdir="$(mktemp -d)"
previous_context="$(kubectl config current-context 2>/dev/null || true)"

log "Creating throwaway kind cluster: $CLUSTER_NAME"
kind create cluster --name "$CLUSTER_NAME"

log "Restoring previous kubectl context while using explicit smoke context"
if [ -n "$previous_context" ]; then
  kubectl config use-context "$previous_context" >/dev/null
fi

log "Installing metrics-server into $CONTEXT"
kubectl --context "$CONTEXT" apply -f \
  https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml \
  >/dev/null
kubectl --context "$CONTEXT" -n kube-system patch deployment metrics-server \
  --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' \
  >/dev/null
kubectl --context "$CONTEXT" -n kube-system rollout status deployment metrics-server \
  --timeout=180s

log "Waiting for metrics-server node metrics"
top_node="${tmpdir}/top-node.out"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if kubectl --context "$CONTEXT" top node >"$top_node" 2>&1; then
    break
  fi
  sleep 5
done
kubectl --context "$CONTEXT" top node >"$top_node" 2>&1
cat "$top_node"

log "Checking kubectl-smart top has no metrics-server data gaps in default namespace"
top_default="${tmpdir}/top-default.out"
capture "$top_default" \
  "${KUBECTL_SMART_CMD[@]}" top default --context "$CONTEXT" --timeout 5
cat "$top_default"
assert_missing_text "$top_default" "metrics pods unavailable" "default top output"
assert_missing_text "$top_default" "metrics nodes unavailable" "default top output"

log "Creating a PVC-backed pod to exercise PVC data-gap behavior"
kubectl --context "$CONTEXT" apply -f - <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: kubectl-smart-metrics-smoke
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
  namespace: kubectl-smart-metrics-smoke
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 32Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: pvc-writer
  namespace: kubectl-smart-metrics-smoke
spec:
  restartPolicy: Never
  containers:
    - name: writer
      image: busybox:1.36
      command:
        - sh
        - -c
        - dd if=/dev/zero of=/data/blob bs=1M count=4; sleep 3600
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: data-pvc
YAML
kubectl --context "$CONTEXT" -n kubectl-smart-metrics-smoke wait \
  --for=condition=Ready pod/pvc-writer --timeout=180s

log "Waiting for namespace pod metrics"
top_pods="${tmpdir}/top-pods.out"
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if kubectl --context "$CONTEXT" -n kubectl-smart-metrics-smoke top pods \
    >"$top_pods" 2>&1; then
    break
  fi
  sleep 5
done
kubectl --context "$CONTEXT" -n kubectl-smart-metrics-smoke top pods \
  >"$top_pods" 2>&1
cat "$top_pods"

top_pvc="${tmpdir}/top-pvc.out"
capture "$top_pvc" \
  "${KUBECTL_SMART_CMD[@]}" top kubectl-smart-metrics-smoke --context "$CONTEXT" --timeout 5
cat "$top_pvc"
assert_missing_text "$top_pvc" "metrics pods unavailable" "PVC top output"
assert_missing_text "$top_pvc" "metrics nodes unavailable" "PVC top output"

log "Metrics-server live smoke passed for $CONTEXT"
