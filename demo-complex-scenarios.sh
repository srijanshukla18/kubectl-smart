#!/usr/bin/env bash
# Recording-grade kubectl-smart demo stories.
# Creates isolated, idempotent scenarios in kubectl-smart-complex without
# modifying the existing kubectl-smart-lab namespace.

set -euo pipefail

ACTION="${1:-apply}"
NAMESPACE="${NAMESPACE:-kubectl-smart-complex}"
KUBECTL_SMART_CONTEXT="${KUBECTL_SMART_CONTEXT:-$(kubectl config current-context 2>/dev/null || true)}"
RBAC_KUBECONFIG="${RBAC_KUBECONFIG:-.kubectl-smart-rbac.kubeconfig}"
SAFE_CONTEXT_PATTERN="${KUBECTL_SMART_SAFE_CONTEXT_PATTERN:-^(kind-|minikube$|colima$)}"
REAL_KUBECTL="$(command -v kubectl || true)"

log() { echo "[$(date +%H:%M:%S)] $*"; }

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
  log "Using Kubernetes context: $KUBECTL_SMART_CONTEXT"
}

kubectl() {
  "$REAL_KUBECTL" --context "$KUBECTL_SMART_CONTEXT" "$@"
}

ensure_namespace() {
  kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE"
}

apply_short_lived_tls() {
  if ! command -v openssl >/dev/null 2>&1; then
    log "openssl missing; skipping short-lived TLS secret"
    return
  fi

  local tmpdir
  tmpdir=$(mktemp -d)

  openssl req -x509 -nodes -days 3 -newkey rsa:2048 \
    -keyout "${tmpdir}/tls.key" \
    -out "${tmpdir}/tls.crt" \
    -subj "/CN=checkout.demo.local" >/dev/null 2>&1

  kubectl create secret tls checkout-demo-tls \
    --cert="${tmpdir}/tls.crt" \
    --key="${tmpdir}/tls.key" \
    -n "$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -
  rm -rf "$tmpdir"
}

apply_checkout_cascade() {
  log "Applying checkout cascade: crashlooping StatefulSet with config, secret, PVC, services, ingress, and TLS expiry..."
  apply_short_lived_tls

  cat <<'EOF' | kubectl apply -n "$NAMESPACE" -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-runtime
  labels:
    demo.kubectl-smart/story: checkout-cascade
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-config
  labels:
    demo.kubectl-smart/story: checkout-cascade
data:
  PAYMENT_PROVIDER: stripe-v2
  INVENTORY_ENDPOINT: inventory-db:5432
  FEATURE_FLAGS: "checkout.asyncInventory=true,payment.idempotency=false"
---
apiVersion: v1
kind: Secret
metadata:
  name: checkout-secret
  labels:
    demo.kubectl-smart/story: checkout-cascade
type: Opaque
stringData:
  token: demo-token
  signing-key: demo-signing-key
---
apiVersion: v1
kind: Service
metadata:
  name: checkout-api
  labels:
    demo.kubectl-smart/story: checkout-cascade
spec:
  selector:
    app: checkout-api
  ports:
  - name: http
    port: 80
    targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: inventory-db
  labels:
    demo.kubectl-smart/story: checkout-cascade
spec:
  selector:
    app: inventory-db
    release: stable
  ports:
  - name: postgres
    port: 5432
    targetPort: 5432
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-db-canary
  labels:
    demo.kubectl-smart/story: checkout-cascade
spec:
  replicas: 1
  selector:
    matchLabels:
      app: inventory-db
      release: canary
  template:
    metadata:
      labels:
        app: inventory-db
        release: canary
        demo.kubectl-smart/story: checkout-cascade
    spec:
      tolerations:
      - key: smart-lab
        operator: Equal
        value: diskpressure
        effect: NoSchedule
      containers:
      - name: pretend-db
        image: busybox
        command: ["/bin/sh", "-c", "while true; do echo inventory canary has wrong label; sleep 60; done"]
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: checkout-api
  labels:
    demo.kubectl-smart/story: checkout-cascade
spec:
  serviceName: checkout-api
  replicas: 1
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
        demo.kubectl-smart/story: checkout-cascade
    spec:
      serviceAccountName: checkout-runtime
      tolerations:
      - key: smart-lab
        operator: Equal
        value: diskpressure
        effect: NoSchedule
      containers:
      - name: api
        image: busybox
        command:
        - /bin/sh
        - -c
        - |
          echo "INFO checkout boot: release=2026.05.13 provider=stripe-v2"
          echo "ERROR dependency inventory-db:5432 returned connection refused"
          echo "ERROR payment idempotency disabled while retry budget is exhausted"
          echo "FATAL checkout startup aborted: cannot build order reservation graph"
          echo "panic: circuit breaker open after 3 attempts"
          exit 1
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: checkout-config
        volumeMounts:
        - name: config
          mountPath: /etc/checkout/config
        - name: secret
          mountPath: /etc/checkout/secret
          readOnly: true
        - name: cache
          mountPath: /var/cache/checkout
      volumes:
      - name: config
        configMap:
          name: checkout-config
      - name: secret
        secret:
          secretName: checkout-secret
  volumeClaimTemplates:
  - metadata:
      name: cache
      labels:
        demo.kubectl-smart/story: checkout-cascade
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 512Mi
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: checkout-demo
  labels:
    demo.kubectl-smart/story: checkout-cascade
spec:
  tls:
  - hosts:
    - checkout.demo.local
    secretName: checkout-demo-tls
  rules:
  - host: checkout.demo.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: checkout-api
            port:
              number: 80
EOF
}

apply_fulfillment_config_trap() {
  log "Applying fulfillment config trap: scheduled pod blocked by a missing env Secret while still carrying rich dependencies..."

  cat <<'EOF' | kubectl apply -n "$NAMESPACE" -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fulfillment-runtime
  labels:
    demo.kubectl-smart/story: fulfillment-config-trap
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: fulfillment-routing
  labels:
    demo.kubectl-smart/story: fulfillment-config-trap
data:
  QUEUE_NAME: priority-shipments
  REGION_FAILOVER: "enabled"
---
apiVersion: v1
kind: Secret
metadata:
  name: fulfillment-mounted-secret
  labels:
    demo.kubectl-smart/story: fulfillment-config-trap
type: Opaque
stringData:
  mounted-token: present-but-not-the-runtime-token
---
apiVersion: v1
kind: Service
metadata:
  name: fulfillment-worker
  labels:
    demo.kubectl-smart/story: fulfillment-config-trap
spec:
  selector:
    app: fulfillment-worker
  ports:
  - name: worker
    port: 9090
    targetPort: 9090
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: fulfillment-worker
  labels:
    demo.kubectl-smart/story: fulfillment-config-trap
spec:
  serviceName: fulfillment-worker
  replicas: 1
  selector:
    matchLabels:
      app: fulfillment-worker
  template:
    metadata:
      labels:
        app: fulfillment-worker
        demo.kubectl-smart/story: fulfillment-config-trap
    spec:
      serviceAccountName: fulfillment-runtime
      tolerations:
      - key: smart-lab
        operator: Equal
        value: diskpressure
        effect: NoSchedule
      containers:
      - name: worker
        image: busybox
        command: ["/bin/sh", "-c", "echo should-not-start; sleep 3600"]
        env:
        - name: RUNTIME_TOKEN
          valueFrom:
            secretKeyRef:
              name: missing-fulfillment-runtime-token
              key: token
        - name: QUEUE_NAME
          valueFrom:
            configMapKeyRef:
              name: fulfillment-routing
              key: QUEUE_NAME
        volumeMounts:
        - name: routing
          mountPath: /etc/fulfillment/routing
        - name: mounted-secret
          mountPath: /etc/fulfillment/secret
          readOnly: true
        - name: workdir
          mountPath: /var/lib/fulfillment
      volumes:
      - name: routing
        configMap:
          name: fulfillment-routing
      - name: mounted-secret
        secret:
          secretName: fulfillment-mounted-secret
  volumeClaimTemplates:
  - metadata:
      name: workdir
      labels:
        demo.kubectl-smart/story: fulfillment-config-trap
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 512Mi
EOF
}

apply_rbac_limited_viewer() {
  log "Applying RBAC-limited viewer for data-gap validation..."

  cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kubectl-smart-limited-reader
  labels:
    demo.kubectl-smart/story: rbac-data-gaps
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kubectl-smart-limited-reader
  labels:
    demo.kubectl-smart/story: rbac-data-gaps
rules:
- apiGroups: [""]
  resources:
  - pods
  - services
  - endpoints
  - configmaps
  - secrets
  - persistentvolumeclaims
  - serviceaccounts
  verbs: ["get", "list"]
- apiGroups: ["apps"]
  resources:
  - deployments
  - replicasets
  - statefulsets
  - daemonsets
  verbs: ["get", "list"]
- apiGroups: ["networking.k8s.io"]
  resources:
  - ingresses
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kubectl-smart-limited-reader
  labels:
    demo.kubectl-smart/story: rbac-data-gaps
subjects:
- kind: ServiceAccount
  name: kubectl-smart-limited-reader
  namespace: ${NAMESPACE}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: kubectl-smart-limited-reader
EOF

  local cluster_name server ca_data token
  cluster_name="$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].name}')"
  server="$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}')"
  ca_data="$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
  token="$(kubectl -n "$NAMESPACE" create token kubectl-smart-limited-reader --duration=2h)"

  rm -f "$RBAC_KUBECONFIG"
  (
    umask 077
    cat > "$RBAC_KUBECONFIG" <<EOF
apiVersion: v1
kind: Config
clusters:
- name: ${cluster_name}
  cluster:
    server: ${server}
    certificate-authority-data: ${ca_data}
users:
- name: kubectl-smart-limited-reader
  user:
    token: ${token}
contexts:
- name: kubectl-smart-rbac-demo
  context:
    cluster: ${cluster_name}
    namespace: ${NAMESPACE}
    user: kubectl-smart-limited-reader
current-context: kubectl-smart-rbac-demo
EOF
  )

  log "Wrote restricted kubeconfig: $RBAC_KUBECONFIG"
}

print_runbook() {
  cat <<EOF

Complex demo scenarios are ready in namespace: $NAMESPACE

Case 1: checkout cascade
  kubectl-smart diag pod checkout-api-0 -n $NAMESPACE
  kubectl-smart graph pod checkout-api-0 -n $NAMESPACE --upstream --downstream
  kubectl get endpoints inventory-db -n $NAMESPACE
  kubectl-smart top $NAMESPACE --horizon 72

Case 2: fulfillment config trap
  kubectl-smart diag pod fulfillment-worker-0 -n $NAMESPACE
  kubectl-smart graph pod fulfillment-worker-0 -n $NAMESPACE --upstream --downstream
  kubectl get events -n $NAMESPACE --field-selector involvedObject.name=fulfillment-worker-0 --sort-by=.lastTimestamp

RBAC data-gap validation
  KUBECONFIG=$RBAC_KUBECONFIG kubectl-smart diag pod checkout-api-0 -n $NAMESPACE
EOF
}

case "$ACTION" in
  apply|setup)
    guard_context
    ensure_namespace
    apply_checkout_cascade
    apply_fulfillment_config_trap
    apply_rbac_limited_viewer
    print_runbook
    ;;
  rbac|refresh-rbac)
    guard_context
    ensure_namespace
    apply_rbac_limited_viewer
    ;;
  cleanup|destroy)
    guard_context
    kubectl delete ns "$NAMESPACE" --ignore-not-found
    ;;
  *)
    echo "Usage: $0 [apply|rbac|cleanup]" >&2
    exit 1
    ;;
esac
