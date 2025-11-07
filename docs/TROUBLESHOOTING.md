# Troubleshooting Guide

Common issues and solutions for kubectl-smart.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Connection Issues](#connection-issues)
- [Permission Issues](#permission-issues)
- [Performance Issues](#performance-issues)
- [Data Collection Issues](#data-collection-issues)
- [Output Issues](#output-issues)
- [Advanced Troubleshooting](#advanced-troubleshooting)

---

## Installation Issues

### Issue: `pip install kubectl-smart` fails

**Symptoms**:
```
ERROR: Could not find a version that satisfies the requirement kubectl-smart
```

**Solutions**:

1. **Check Python version**:
   ```bash
   python --version  # Should be 3.9+
   ```

2. **Upgrade pip**:
   ```bash
   pip install --upgrade pip
   ```

3. **Use virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install kubectl-smart
   ```

4. **Install from source**:
   ```bash
   git clone https://github.com/srijanshukla18/kubectl-smart
   cd kubectl-smart
   pip install -e .
   ```

---

### Issue: Missing dependencies

**Symptoms**:
```
ModuleNotFoundError: No module named 'igraph'
```

**Solutions**:

1. **Install all dependencies**:
   ```bash
   pip install kubectl-smart[all]
   ```

2. **Install specific dependency**:
   ```bash
   pip install python-igraph
   ```

3. **On macOS with M1/M2 chip**:
   ```bash
   brew install igraph
   pip install python-igraph
   ```

4. **On Linux (Ubuntu/Debian)**:
   ```bash
   sudo apt-get install python3-igraph
   pip install python-igraph
   ```

---

## Connection Issues

### Issue: Cannot connect to cluster

**Symptoms**:
```
❌ Cluster connection timed out (>5s)
Error: Unable to connect to the server
```

**Solutions**:

1. **Verify kubectl connectivity**:
   ```bash
   kubectl cluster-info
   ```

2. **Check current context**:
   ```bash
   kubectl config current-context
   kubectl config get-contexts
   ```

3. **Use specific context**:
   ```bash
   kubectl-smart diag pod my-pod --context=production
   ```

4. **Check kubeconfig**:
   ```bash
   echo $KUBECONFIG
   # Default: ~/.kube/config
   ```

5. **Test with simple kubectl command**:
   ```bash
   kubectl get pods
   # If this fails, kubectl-smart will also fail
   ```

---

### Issue: Context/namespace not found

**Symptoms**:
```
❌ Input validation error: Invalid namespace 'production'
Resource not found
```

**Solutions**:

1. **List available namespaces**:
   ```bash
   kubectl get namespaces
   ```

2. **List available contexts**:
   ```bash
   kubectl config get-contexts
   ```

3. **Create namespace if needed**:
   ```bash
   kubectl create namespace production
   ```

4. **Use correct namespace**:
   ```bash
   kubectl-smart diag pod my-pod -n <correct-namespace>
   ```

---

## Permission Issues

### Issue: RBAC permission denied

**Symptoms**:
```
Error: forbidden: User "john@example.com" cannot get resource "pods" in API group "" in the namespace "production"
```

**Solutions**:

1. **Check your permissions**:
   ```bash
   kubectl auth can-i get pods -n production
   kubectl auth can-i get pods --all-namespaces
   ```

2. **List all permissions**:
   ```bash
   kubectl auth can-i --list -n production
   ```

3. **Required permissions for kubectl-smart**:
   - `get` on: pods, deployments, services, events
   - `list` on: pods, deployments, services, events
   - Optional: `get` on secrets (for certificate checks)

4. **Request access from cluster admin**:
   ```bash
   # Example RBAC role for kubectl-smart
   kubectl create role kubectl-smart-reader \
     --verb=get,list \
     --resource=pods,deployments,services,events,replicasets,statefulsets \
     -n production
   ```

5. **Test with read-only mode**:
   ```bash
   kubectl-smart diag pod my-pod -n <namespace-with-access>
   ```

---

### Issue: Cannot read logs

**Symptoms**:
```
Warning: Failed to collect logs
Error: pods "my-pod" is forbidden
```

**Solutions**:

1. **Check log permissions**:
   ```bash
   kubectl auth can-i get pods/log -n production
   ```

2. **kubectl-smart will continue without logs**:
   - Diagnosis still works
   - Log-based insights will be missing

3. **Request log permissions**:
   ```yaml
   # Role with log access
   apiVersion: rbac.authorization.k8s.io/v1
   kind: Role
   metadata:
     name: log-reader
   rules:
   - apiGroups: [""]
     resources: ["pods/log"]
     verbs: ["get", "list"]
   ```

---

## Performance Issues

### Issue: Commands are slow (>10s)

**Symptoms**:
```
# Command takes 15+ seconds to complete
```

**Solutions**:

1. **Check cluster size**:
   ```bash
   kubectl get nodes
   kubectl get pods --all-namespaces | wc -l
   ```

2. **Reduce concurrent collectors** (create config file):
   ```yaml
   # ~/.kubectl-smart/config.yaml
   performance:
     max_concurrent_collectors: 3  # Default: 5
     collector_timeout_seconds: 5.0  # Default: 10.0
   ```

3. **Use specific namespace**:
   ```bash
   # Faster
   kubectl-smart diag pod my-pod -n production

   # Slower (searches all namespaces)
   kubectl-smart diag pod my-pod
   ```

4. **Disable logs collection** (future feature):
   ```bash
   # kubectl-smart diag pod my-pod --no-logs
   ```

5. **Check network latency**:
   ```bash
   time kubectl get pods
   # If slow, kubectl-smart will also be slow
   ```

---

### Issue: High memory usage

**Symptoms**:
```
Process killed (OOM)
Memory usage >2GB
```

**Solutions**:

1. **Reduce batch size**:
   ```bash
   # Instead of --all
   kubectl-smart diag pod --all -n large-namespace

   # Diagnose specific pods
   kubectl-smart diag pod pod-1 -n large-namespace
   ```

2. **Use JSON output for large datasets**:
   ```bash
   kubectl-smart diag pod my-pod -o json | jq '.root_cause'
   ```

3. **Increase system resources**:
   - Run on machine with more RAM
   - Close other applications

---

## Data Collection Issues

### Issue: No metrics available

**Symptoms**:
```
⚠️  metrics-server not available
Forecast: degraded (using fallback method)
```

**Solutions**:

1. **Check if metrics-server is installed**:
   ```bash
   kubectl get deployment metrics-server -n kube-system
   ```

2. **Install metrics-server** (if missing):
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```

3. **kubectl-smart works without metrics**:
   - Diagnosis still works
   - Forecasting uses fallback methods
   - Some insights may be missing

4. **Verify metrics-server is working**:
   ```bash
   kubectl top nodes
   kubectl top pods
   ```

---

### Issue: Missing events

**Symptoms**:
```
No events found for pod
Event collection failed
```

**Solutions**:

1. **Events may have expired** (default TTL: 1 hour):
   ```bash
   kubectl get events --all-namespaces
   ```

2. **Check event retention** (cluster-wide setting):
   ```bash
   # Events are garbage collected after 1 hour by default
   # Check kube-apiserver --event-ttl flag
   ```

3. **kubectl-smart will work with available data**:
   - Uses pod status, conditions, logs
   - Events provide additional context

---

### Issue: Cannot collect logs

**Symptoms**:
```
Warning: Failed to collect logs: container "app" in pod "my-pod" is waiting to start
```

**Solutions**:

1. **Pod may not be running**:
   ```bash
   kubectl get pod my-pod -o jsonpath='{.status.phase}'
   ```

2. **Container may not have started**:
   ```bash
   kubectl describe pod my-pod
   ```

3. **Check previous logs**:
   ```bash
   kubectl logs my-pod -p  # Previous container
   ```

4. **kubectl-smart handles this gracefully**:
   - Continues with other data sources
   - Uses container status instead

---

## Output Issues

### Issue: Colors not showing

**Symptoms**:
```
# Output has no colors, looks plain
```

**Solutions**:

1. **Check if terminal supports colors**:
   ```bash
   echo $TERM
   # Should be xterm-256color or similar
   ```

2. **Force colors**:
   ```bash
   # Edit ~/.kubectl-smart/config.yaml
   output:
     colors_enabled: true
   ```

3. **Disable colors**:
   ```bash
   # Edit ~/.kubectl-smart/config.yaml
   output:
     colors_enabled: false
   ```

4. **Use NO_COLOR environment variable**:
   ```bash
   NO_COLOR=1 kubectl-smart diag pod my-pod
   ```

---

### Issue: JSON output is malformed

**Symptoms**:
```
Error parsing JSON
Unexpected token
```

**Solutions**:

1. **Ensure using -o json flag**:
   ```bash
   kubectl-smart diag pod my-pod -o json
   ```

2. **Redirect errors**:
   ```bash
   kubectl-smart diag pod my-pod -o json 2>/dev/null
   ```

3. **Validate JSON**:
   ```bash
   kubectl-smart diag pod my-pod -o json | jq .
   ```

4. **Check for mixed output**:
   ```bash
   # Debug messages may mix with JSON
   # Use --no-debug or redirect stderr
   ```

---

### Issue: Truncated output

**Symptoms**:
```
# Output cuts off mid-sentence
# Missing sections
```

**Solutions**:

1. **Pipe to less**:
   ```bash
   kubectl-smart diag pod my-pod | less -R
   ```

2. **Save to file**:
   ```bash
   kubectl-smart diag pod my-pod > diagnosis.txt
   ```

3. **Increase terminal buffer**:
   - Terminal preferences > scrollback lines

4. **Use JSON output for complete data**:
   ```bash
   kubectl-smart diag pod my-pod -o json > full-diagnosis.json
   ```

---

## Advanced Troubleshooting

### Enable Debug Logging

**Enable debug mode**:
```bash
# Method 1: Command line flag
kubectl-smart --debug diag pod my-pod

# Method 2: Environment variable
export KUBECTL_SMART_DEBUG=1
kubectl-smart diag pod my-pod

# Method 3: Config file
# Edit ~/.kubectl-smart/config.yaml
logging:
  level: DEBUG
```

**Debug output location**:
```bash
# Default log file
tail -f ~/.kubectl-smart/logs/kubectl-smart.log

# Or to stderr (when using --debug)
kubectl-smart --debug diag pod my-pod 2>&1 | grep DEBUG
```

---

### Verbose Output

**Get detailed output**:
```bash
# JSON output with full details
kubectl-smart diag pod my-pod -o json | jq .

# Save complete diagnosis
kubectl-smart diag pod my-pod -o json > diagnosis.json
cat diagnosis.json | jq .
```

---

### Check Health

**Run health checks**:
```bash
# Quick health check
kubectl version --short
kubectl cluster-info

# Comprehensive checks (future feature)
# kubectl-smart health --verbose
```

---

### Trace kubectl Calls

**See exact kubectl commands**:
```bash
# Enable debug mode
kubectl-smart --debug diag pod my-pod 2>&1 | grep "kubectl"

# Manually test collectors
kubectl get pod my-pod -o json
kubectl describe pod my-pod
kubectl logs my-pod --tail=100
kubectl get events --field-selector involvedObject.name=my-pod
```

---

### Reset Configuration

**Remove all config and cache**:
```bash
# Backup first
cp -r ~/.kubectl-smart ~/.kubectl-smart.backup

# Remove config
rm -rf ~/.kubectl-smart

# kubectl-smart will use defaults
kubectl-smart diag pod my-pod
```

---

### Report a Bug

**Information to include**:

1. **kubectl-smart version**:
   ```bash
   kubectl-smart --version
   ```

2. **Environment**:
   ```bash
   python --version
   kubectl version
   uname -a
   ```

3. **Error message**:
   ```bash
   kubectl-smart diag pod my-pod 2>&1 | tee error.log
   ```

4. **Debug output**:
   ```bash
   kubectl-smart --debug diag pod my-pod 2>&1 | tee debug.log
   ```

5. **Redact sensitive information**:
   - Remove cluster URLs
   - Remove pod/container names if sensitive
   - Remove any credentials

**Submit issue**:
- GitHub: https://github.com/srijanshukla18/kubectl-smart/issues
- Include all information above

---

## Common Error Messages

### "Resource not found"

**Meaning**: Pod/deployment doesn't exist

**Fix**:
```bash
# Verify resource exists
kubectl get pod <name> -n <namespace>

# List all pods
kubectl get pods --all-namespaces | grep <name>
```

---

### "Connection refused"

**Meaning**: Cannot reach cluster API server

**Fix**:
```bash
# Test connectivity
kubectl cluster-info

# Check kubeconfig
cat ~/.kube/config

# Verify VPN/network access
```

---

### "Collector timeout"

**Meaning**: kubectl command took too long

**Fix**:
```bash
# Increase timeout in config
# ~/.kubectl-smart/config.yaml
performance:
  collector_timeout_seconds: 30.0  # Increase from 10.0
```

---

### "Invalid resource name"

**Meaning**: Resource name violates Kubernetes naming rules

**Fix**:
```bash
# Names must:
# - Be lowercase alphanumeric with hyphens
# - Not start/end with hyphen
# - Max 253 characters

# Valid: my-pod, app-123, nginx
# Invalid: My-Pod, app_123, -nginx
```

---

## Still Having Issues?

1. **Check documentation**:
   - [Tutorial](TUTORIAL.md)
   - [FAQ](FAQ.md)
   - [Best Practices](BEST_PRACTICES.md)

2. **Search existing issues**:
   - https://github.com/srijanshukla18/kubectl-smart/issues

3. **Ask for help**:
   - Create new issue with debug information
   - Include kubectl-smart version, environment, error logs

4. **Workarounds**:
   - Use kubectl directly
   - Use alternative tools (k9s, Lens)
   - Manual inspection of resources
