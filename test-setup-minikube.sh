#!/bin/bash
# -----------------------------------------------------------------------------
# test-setup-minikube.sh
# -----------------------------------------------------------------------------
# Bootstrap a local Minikube cluster with artificial workloads that exercise
# *every* scenario listed in todo.md.  The goal is to create predictable
# objects that kubectl-smart can diagnose / graph / forecast against.
#
# Safe to run multiple times – all manifests live in the dedicated namespace
# "kubectl-smart-fixtures" and are reapplied idempotently.  No existing user
# workloads are touched.
# -----------------------------------------------------------------------------

set -euo pipefail

NAMESPACE="kubectl-smart-fixtures"

echo "🔧 Preparing namespace ${NAMESPACE}..."
kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${NAMESPACE}"

# Helper: detect if an ingress controller is ready (Minikube-friendly)
ingress_controller_ready() {
  # Minikube ingress addon path
  if command -v minikube >/dev/null 2>&1; then
    if minikube addons list 2>/dev/null | grep -E '^\s*ingress\s+.*Enabled' >/dev/null 2>&1; then
      # Wait for controller rollout to finish (up to 2 minutes)
      if ! kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=120s >/dev/null 2>&1; then
        return 1
      fi
      # Admission webhook service must have endpoints
      local eps
      eps=$(kubectl -n ingress-nginx get endpoints ingress-nginx-controller-admission \
              -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || true)
      if [ -z "${eps}" ]; then
        return 1
      fi
      # Final guard: server-side dry-run the manifest to confirm the webhook responds
      cat <<EOF | kubectl apply -n ${NAMESPACE} -f - --dry-run=server >/dev/null 2>&1
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tls-ref-ingress
spec:
  tls:
  - hosts:
    - example.local
    secretName: expiring-cert
  rules:
  - host: example.local
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
      if [ $? -ne 0 ]; then
        return 1
      fi
      return 0
    fi
  fi
  return 1
}

# Ensure default service account exists in the namespace (avoid race with SA controller)
echo "⏳ Ensuring default service account in ${NAMESPACE}..."
for i in {1..30}; do
  if kubectl -n "${NAMESPACE}" get sa default >/dev/null 2>&1; then
    break
  fi
  kubectl -n "${NAMESPACE}" create sa default >/dev/null 2>&1 || true
  sleep 1
done

################################################################################
# 1. ImagePullBackOff (bad image) – single failing pod
################################################################################
kubectl -n ${NAMESPACE} delete pod image-pull-error --ignore-not-found >/dev/null 2>&1 || true
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Pod
metadata:
  name: image-pull-error
  labels:
    scenario: imagepullbackoff
spec:
  containers:
  - name: bad
    image: doesnotexist.invalid/badimage:latest  # guaranteed to 404
    command: ["sleep", "3600"]
  restartPolicy: Always
EOF

################################################################################
# 2. CrashLoopBackOff – container exits immediately
################################################################################
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
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
        imagePullPolicy: IfNotPresent
EOF

################################################################################
# 3. Pending due to PVC (FailedMount) – missing storageclass
################################################################################
kubectl -n ${NAMESPACE} delete pod pvc-pending --ignore-not-found >/dev/null 2>&1 || true
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
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
EOF
# Note: claim deliberately not created – pod will stay Pending with FailedMount.

################################################################################
# 4. FailedScheduling – resource request beyond node capacity
################################################################################
kubectl -n ${NAMESPACE} delete pod impossible-cpu-request --ignore-not-found >/dev/null 2>&1 || true
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
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
        cpu: "3000"   # 3000 CPUs > any minikube node
EOF

################################################################################
# 5. NodeSelector mismatch – no node has the label
################################################################################
kubectl -n ${NAMESPACE} delete pod nodeselector-miss --ignore-not-found >/dev/null 2>&1 || true
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Pod
metadata:
  name: nodeselector-miss
  labels:
    scenario: affinity
spec:
  nodeSelector:
    nonexistent: "true"
  containers:
  - name: app
    image: busybox
    command: ["sleep", "3600"]
EOF

################################################################################
# 6. Expiring certificate secret (<14 days)
################################################################################
# Create once if missing to keep reruns strictly idempotent
if ! kubectl -n ${NAMESPACE} get secret expiring-cert >/dev/null 2>&1; then
  echo "🔐 Creating expiring TLS secret (7 days) ..."
  tmpdir=$(mktemp -d)
  openssl req -x509 -nodes -days 7 -newkey rsa:2048 \
    -keyout ${tmpdir}/tls.key -out ${tmpdir}/tls.crt \
    -subj "/CN=expiring"
  kubectl create secret tls expiring-cert -n ${NAMESPACE} \
    --cert=${tmpdir}/tls.crt --key=${tmpdir}/tls.key
  rm -rf ${tmpdir}
else
  echo "🔐 TLS secret expiring-cert already exists; leaving as-is"
fi

# Service used by the optional Ingress
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Service
metadata:
  name: tls-ref-svc
spec:
  selector:
    app: backend-1
  ports:
  - port: 80
    targetPort: 80
EOF

# Optional: Ingress referencing the TLS secret (only if controller ready)
if ingress_controller_ready; then
  echo "🌐 Ingress controller detected; applying tls-ref-ingress"
  cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tls-ref-ingress
spec:
  tls:
  - hosts:
    - example.local
    secretName: expiring-cert
  rules:
  - host: example.local
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
else
  echo "⚠️  No ready ingress controller detected; skipping Ingress creation"
fi

################################################################################
# 7. Node DiskPressure simulation (taint) – mark node condition
################################################################################
# Not straightforward to create real DiskPressure; instead taint the node so
# the scheduler surfaces FailedScheduling events referencing DiskPressure.
NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
if ! kubectl get node "$NODE" -o json | grep -q "disk-pressure-sim"; then
  kubectl taint node "$NODE" disk-pressure-sim=true:NoSchedule --overwrite || true
fi

################################################################################
# 8. Deployment with partial unhealthy replicas
################################################################################
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: partial-unhealthy
  labels:
    scenario: partial
spec:
  replicas: 3
  selector:
    matchLabels:
      app: partial
  template:
    metadata:
      labels:
        app: partial
    spec:
      containers:
      - name: good
        image: nginx
        imagePullPolicy: IfNotPresent
      - name: bad
        image: doesnotexist.invalid/badimage:latest
        imagePullPolicy: IfNotPresent
EOF

################################################################################
# 9. Service selecting multiple pods (downstream)
################################################################################
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Service
metadata:
  name: multi-backend
  labels:
    scenario: downstream
spec:
  selector:
    app: multi-backend
  ports:
  - port: 80
    targetPort: 80
EOF

# Create 5 backend pods
for i in $(seq 1 5); do
  kubectl -n ${NAMESPACE} delete pod backend-${i} --ignore-not-found >/dev/null 2>&1 || true
  cat <<EOF | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Pod
metadata:
  name: backend-${i}
  labels:
    app: multi-backend
spec:
  containers:
  - name: web
    image: nginx
    imagePullPolicy: IfNotPresent
EOF
done

################################################################################
# 10. ConfigMap / Secret as volumes (external edge)
################################################################################
kubectl create configmap external-config -n ${NAMESPACE} --from-literal=key=val --dry-run=client -o yaml | kubectl apply -f -
kubectl -n ${NAMESPACE} delete pod configmap-volume --ignore-not-found >/dev/null 2>&1 || true
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Pod
metadata:
  name: configmap-volume
  labels:
    scenario: ext-edge
spec:
  containers:
  - name: app
    image: busybox
    command: ["sleep", "3600"]
    volumeMounts:
    - mountPath: /etc/config
      name: cfg
  volumes:
  - name: cfg
    configMap:
      name: external-config
EOF

################################################################################
# 11. High-edge graph – service with 60 pods
################################################################################
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Service
metadata:
  name: huge-service
  labels:
    scenario: huge
spec:
  selector:
    app: huge-backend
  ports:
  - port: 80
    targetPort: 80
EOF

for i in $(seq 1 60); do
  kubectl -n ${NAMESPACE} delete pod huge-backend-${i} --ignore-not-found >/dev/null 2>&1 || true
  cat <<EOF | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: Pod
metadata:
  name: huge-backend-${i}
  labels:
    app: huge-backend
spec:
  containers:
  - name: web
    image: nginx
EOF
done

################################################################################
# 12. PVC nearly full (disk forecast) – create 1Gi volume, fill 950Mi
################################################################################
# Create StorageClass + PVC (uses default StorageClass on Minikube)
# Detect default StorageClass name (fallback to 'standard' or first available)
SC=$(kubectl get sc -o jsonpath='{range .items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")]}{.metadata.name}{"\n"}{end}' | head -1)
if [ -z "$SC" ]; then
  SC=$(kubectl get sc -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo standard)
fi

cat <<EOF | kubectl apply -n ${NAMESPACE} -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: fillpvc
  labels:
    scenario: pvcfull
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: ${SC}
EOF

kubectl -n ${NAMESPACE} delete pod pvc-filler --ignore-not-found >/dev/null 2>&1 || true
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
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
      claimName: fillpvc
  containers:
  - name: filler
    image: busybox
    command: ["/bin/sh", "-c", "dd if=/dev/zero of=/data/bigfile bs=1M count=950; sync; sleep 3600"]
    volumeMounts:
    - mountPath: /data
      name: data
EOF

################################################################################
# 13. CPU / Memory stress – single pod mining /stress
################################################################################
cat <<'EOF' | kubectl apply -n ${NAMESPACE} -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stress-cpu
  labels:
    scenario: cpustress
spec:
  replicas: 1
  selector:
    matchLabels:
      app: stress
  template:
    metadata:
      labels:
        app: stress
    spec:
      containers:
      - name: stress
        image: progrium/stress
        args: ["--cpu", "2", "--vm", "1", "--vm-bytes", "300M"]
        resources:
          limits:
            cpu: "1"
            memory: 512Mi
EOF

################################################################################
# 14. Optionally uninstall metrics-server to test graceful degradation
################################################################################
if [[ "${1-}" == "--remove-metrics-server" ]]; then
  echo "🚫 Removing metrics-server to test Top command fallback..."
  kubectl delete -n kube-system deployment metrics-server 2>/dev/null || true
fi

echo "✅  Fixture deployment complete.  Give Kubernetes ~60 seconds to settle."

