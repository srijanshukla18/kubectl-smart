#!/usr/bin/env bash
# Quick bootstrap for kubectl-smart demo scenarios on a local kind/minikube context.
# Usage: ./kubectl-smart-lab.sh [apply|cleanup] [scenario]
# Scenarios: base, network, graph, tls, pvc, taint, silent, links, config, all (default)

set -euo pipefail

ACTION="${1:-apply}"
SCENARIO="${2:-all}"
NAMESPACE="${NAMESPACE:-kubectl-smart-lab}"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-kubectl-smart-demo}"
KUBECTL_SMART_CONTEXT="${KUBECTL_SMART_CONTEXT:-kind-${KIND_CLUSTER_NAME}}"
KUBECTL_SMART_KUBECONFIG="${KUBECTL_SMART_KUBECONFIG:-$PWD/.kubectl-smart-demo.kubeconfig}"
SAFE_CONTEXT_PATTERN="${KUBECTL_SMART_SAFE_CONTEXT_PATTERN:-^(kind-|minikube$|colima$)}"
REAL_KUBECTL="$(command -v kubectl || true)"

log() { echo "[$(date +%H:%M:%S)] $*"; }

require_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required binary: $1" >&2
    exit 1
  fi
}

guard_context() {
  if [ -z "$REAL_KUBECTL" ]; then
    echo "Missing required binary: kubectl" >&2
    exit 1
  fi
  if ! [[ "$KUBECTL_SMART_CONTEXT" =~ $SAFE_CONTEXT_PATTERN ]]; then
    echo "Refusing to use Kubernetes context '$KUBECTL_SMART_CONTEXT'." >&2
    echo "Set KUBECTL_SMART_CONTEXT to a local context matching: $SAFE_CONTEXT_PATTERN" >&2
    exit 1
  fi
  export KUBECTL_SMART_CONTEXT
  export KUBECONFIG="$KUBECTL_SMART_KUBECONFIG"
  log "Using Kubernetes context: $KUBECTL_SMART_CONTEXT"
  log "Using kubeconfig: $KUBECONFIG"
}

kubectl() {
  "$REAL_KUBECTL" --context "$KUBECTL_SMART_CONTEXT" "$@"
}

ensure_local_cluster() {
  if [[ "$KUBECTL_SMART_CONTEXT" == kind-* ]]; then
    require_bin kind
    local cluster_name="${KUBECTL_SMART_CONTEXT#kind-}"
    if ! kind get clusters 2>/dev/null | grep -qx "$cluster_name"; then
      log "Creating local kind cluster ${cluster_name}..."
      kind create cluster --name "$cluster_name" --kubeconfig "$KUBECONFIG"
    else
      kind export kubeconfig --name "$cluster_name" --kubeconfig "$KUBECONFIG" >/dev/null 2>&1
    fi
    return
  fi

  if [[ "$KUBECTL_SMART_CONTEXT" == "minikube" ]] && command -v minikube >/dev/null 2>&1; then
    if ! minikube status >/dev/null 2>&1; then
      log "Starting local minikube profile..."
      minikube start
    fi
    log "Enabling metrics-server addon (for top forecasts)..."
    minikube addons enable metrics-server >/dev/null 2>&1 || true
    log "Enabling ingress addon (for TLS scenario)..."
    minikube addons enable ingress >/dev/null 2>&1 || true
  fi
}

ensure_namespace() {
  if ! kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
    log "Creating namespace $NAMESPACE"
    kubectl create ns "$NAMESPACE"
  else
    log "Namespace $NAMESPACE already exists"
  fi
}

clear_lab_taint() {
  kubectl taint node --all smart-lab=diskpressure:NoSchedule- >/dev/null 2>&1 || true
}

apply_base_failures() {
  log "Applying core failure scenarios (image pull, crashloop, pvc pending, over-ask, dns)..."
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: Pod
metadata:
  name: image-pull-error
  labels:
    scenario: imagepull
spec:
  containers:
  - name: bad
    image: doesnotexist.invalid/badimage:latest
    command: ["sleep", "3600"]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crashloop
  labels:
    scenario: crashloop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: crashloop
  template:
    metadata:
      labels:
        app: crashloop
    spec:
      containers:
      - name: boom
        image: busybox
        command: ["/bin/sh", "-c", "echo boom && exit 1"]
---
apiVersion: v1
kind: Pod
metadata:
  name: pvc-pending
  labels:
    scenario: failedmount
spec:
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: fake-claim
  containers:
  - name: app
    image: busybox
    command: ["sleep", "3600"]
    volumeMounts:
    - mountPath: /data
      name: data
---
apiVersion: v1
kind: Pod
metadata:
  name: impossible-cpu-request
  labels:
    scenario: failedscheduling
spec:
  containers:
  - name: heavy
    image: busybox
    command: ["sleep", "3600"]
    resources:
      requests:
        cpu: "3000"
---
apiVersion: v1
kind: Pod
metadata:
  name: dns-fail
  labels:
    scenario: dns
spec:
  restartPolicy: Never
  containers:
  - name: busy
    image: busybox
    command: ["/bin/sh", "-c", "nslookup no.such.host.invalid; sleep 3600"]
EOF
}

apply_network_lockdown() {
  log "Applying deny-all NetworkPolicy and blocked client/server pair..."
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: Service
metadata:
  name: np-target
spec:
  selector:
    app: np-target
  ports:
  - port: 80
    targetPort: 80
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: np-target
spec:
  replicas: 1
  selector:
    matchLabels:
      app: np-target
  template:
    metadata:
      labels:
        app: np-target
    spec:
      containers:
      - name: web
        image: nginx
---
apiVersion: v1
kind: Pod
metadata:
  name: np-client
  labels:
    scenario: networkpolicy
spec:
  containers:
  - name: curl
    image: curlimages/curl
    command: ["/bin/sh", "-c", "while true; do curl -sS np-target || true; sleep 5; done"]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
EOF
}

apply_graph_chain() {
  log "Applying multi-hop dependency chain (frontend -> backend -> PVC/config/secret)..."
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: ConfigMap
metadata:
  name: frontend-config
data:
  WELCOME_MSG: "hello from configmap"
---
apiVersion: v1
kind: Secret
metadata:
  name: frontend-secret
type: Opaque
stringData:
  token: "super-secret"
---
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
spec:
  selector:
    app: backend
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: backend
spec:
  serviceName: backend-svc
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: api
        image: nginx
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: data
          mountPath: /var/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 1Gi
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
      - name: web
        image: nginx
        ports:
        - containerPort: 8080
        env:
        - name: BACKEND_URL
          value: http://backend-svc
        volumeMounts:
        - name: cfg
          mountPath: /etc/config
        - name: secret
          mountPath: /etc/secret
        readinessProbe:
          httpGet:
            path: /
            port: 8080
          initialDelaySeconds: 2
          periodSeconds: 5
      volumes:
      - name: cfg
        configMap:
          name: frontend-config
      - name: secret
        secret:
          secretName: frontend-secret
EOF
}

apply_cert_and_ingress() {
  if ! command -v openssl >/dev/null 2>&1; then
    log "openssl missing; skipping short-lived certificate scenario"
    return
  fi
  log "Creating TLS secret that expires in 5 days..."
  tmpdir=$(mktemp -d)
  openssl req -x509 -nodes -days 5 -newkey rsa:2048 \
    -keyout "${tmpdir}/tls.key" -out "${tmpdir}/tls.crt" \
    -subj "/CN=expiring-cert" >/dev/null 2>&1
  kubectl create secret tls expiring-cert -n "$NAMESPACE" \
    --cert="${tmpdir}/tls.crt" --key="${tmpdir}/tls.key" \
    --dry-run=client -o yaml | kubectl apply -f - 
  rm -rf "${tmpdir}"

  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: Service
metadata:
  name: tls-ref-svc
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tls-ref-ingress
spec:
  tls:
  - hosts:
    - smart.local
    secretName: expiring-cert
  rules:
  - host: smart.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: tls-ref-svc
            port:
              number: 80
EOF
}

apply_pvc_pressure() {
  log "Creating PVC and filler pod to push disk usage toward 90%..."
  SC=$(kubectl get sc -o jsonpath='{range .items[?(@.metadata.annotations.storageclass.kubernetes.io/is-default-class=="true")]}{.metadata.name}{"\n"}{end}' | head -1)
  if [ -z "$SC" ]; then
    SC=$(kubectl get sc -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo standard)
  fi
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-forecast
  labels:
    scenario: pvcfull
spec:
  accessModes: [ "ReadWriteOnce" ]
  resources:
    requests:
      storage: 1Gi
  storageClassName: ${SC}
---
apiVersion: v1
kind: Pod
metadata:
  name: pvc-filler
  labels:
    scenario: pvcfull
spec:
  restartPolicy: Never
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: pvc-forecast
  containers:
  - name: filler
    image: busybox
    command: ["/bin/sh", "-c", "dd if=/dev/zero of=/data/bigfile bs=1M count=900; sync; sleep 3600"]
    volumeMounts:
    - mountPath: /data
      name: data
EOF
}

apply_taint_and_unschedulable() {
  NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
  log "Applying taint smart-lab=diskpressure:NoSchedule on node ${NODE}..."
  kubectl delete pod taint-intolerant -n "$NAMESPACE" --ignore-not-found --grace-period=0 --force >/dev/null 2>&1 || true
  kubectl taint node "${NODE}" smart-lab=diskpressure:NoSchedule --overwrite || true
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: Pod
metadata:
  name: taint-intolerant
  labels:
    scenario: taint
spec:
  containers:
  - name: sleepy
    image: busybox
    command: ["sleep", "3600"]
EOF
}

apply_silent_failures() {
  log "Applying silent failures (Readiness Probe fail & OOMKilled)..."
  cat <<'EOF' | kubectl apply -n "$NAMESPACE" -f -
apiVersion: v1
kind: Pod
metadata:
  name: probe-failure
  labels:
    scenario: silent
spec:
  containers:
  - name: nginx
    image: nginx
    readinessProbe:
      httpGet:
        path: /healthz-does-not-exist
        port: 80
      initialDelaySeconds: 2
      periodSeconds: 5
---
apiVersion: v1
kind: Pod
metadata:
  name: oom-killed
  labels:
    scenario: silent
spec:
  containers:
  - name: memory-hog
    image: busybox
    command: ["/bin/sh", "-c", "X='a'; while true; do X=\"
$X$X\"; done"]
    resources:
      limits:
        memory: "16Mi"
EOF
}

apply_broken_links() {
  log "Applying broken links (Service selector mismatch)..."
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: Service
metadata:
  name: orphan-service
spec:
  selector:
    app: non-existent-app
  ports:
  - port: 80
    targetPort: 80
---
apiVersion: v1
kind: Pod
metadata:
  name: lonely-pod
  labels:
    app: lonely-app
spec:
  containers:
  - name: nginx
    image: nginx
EOF
}

apply_missing_config() {
  log "Applying missing config/secret references..."
  cat <<EOF | kubectl apply -n "$NAMESPACE" -f - 
apiVersion: v1
kind: Pod
metadata:
  name: missing-configmap
  labels:
    scenario: config
spec:
  containers:
  - name: app
    image: busybox
    command: ["sleep", "3600"]
    env:
    - name: MISSING_VAR
      valueFrom:
        configMapKeyRef:
          name: non-existent-cm
          key: some-key
---
apiVersion: v1
kind: Pod
metadata:
  name: missing-secret
  labels:
    scenario: config
spec:
  containers:
  - name: app
    image: busybox
    command: ["sleep", "3600"]
    env:
    - name: MISSING_SECRET
      valueFrom:
        secretKeyRef:
          name: non-existent-secret
          key: token
EOF
}

cleanup() {
  if [ ! -f "$KUBECONFIG" ]; then
    log "No repo-local kubeconfig found at ${KUBECONFIG}; nothing to clean up."
    return
  fi

  log "Removing namespace ${NAMESPACE} and taints..."
  kubectl delete ns "$NAMESPACE" --ignore-not-found || true
  kubectl taint node --all smart-lab=diskpressure:NoSchedule- >/dev/null 2>&1 || true
  log "Cleanup complete"
}

run_scenario() {
  case "$1" in
    base) apply_base_failures ;; 
    network) apply_network_lockdown ;; 
    graph) apply_graph_chain ;; 
    tls) apply_cert_and_ingress ;; 
    pvc) apply_pvc_pressure ;; 
    taint) apply_taint_and_unschedulable ;; 
    silent) apply_silent_failures ;; 
    links) apply_broken_links ;; 
    config) apply_missing_config ;; 
    all)
      apply_base_failures
      apply_network_lockdown
      apply_graph_chain
      apply_cert_and_ingress
      apply_pvc_pressure
      apply_silent_failures
      apply_broken_links
      apply_missing_config
      apply_taint_and_unschedulable
      ;; 
    *)
      echo "Unknown scenario: $1"
      exit 1
      ;; 
  esac
}

case "$ACTION" in
  apply|setup)
    guard_context
    ensure_local_cluster
    ensure_namespace
    clear_lab_taint
    run_scenario "$SCENARIO"
    log "Scenarios applied. Use 'kubectl --context $KUBECTL_SMART_CONTEXT get pods -n $NAMESPACE' to check status."
    ;; 
  cleanup|destroy)
    guard_context
    cleanup
    ;; 
  *)
    echo "Usage: $0 [apply|cleanup] [scenario]"
    echo "Scenarios: base, network, graph, tls, pvc, taint, silent, links, config, all (default)"
    exit 1
    ;; 
esac
