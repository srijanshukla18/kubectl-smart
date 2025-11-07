# Best Practices for kubectl-smart

Recommended patterns and practices for effective use of kubectl-smart.

## Table of Contents

- [General Best Practices](#general-best-practices)
- [Diagnosis Best Practices](#diagnosis-best-practices)
- [Automation Best Practices](#automation-best-practices)
- [Performance Best Practices](#performance-best-practices)
- [Security Best Practices](#security-best-practices)
- [Team Best Practices](#team-best-practices)

---

## General Best Practices

### 1. Always Specify Namespace

**Why**: Faster execution, clearer intent, avoids ambiguity

```bash
# ✅ Good - Explicit namespace
kubectl-smart diag pod my-pod -n production

# ❌ Avoid - Searches all namespaces
kubectl-smart diag pod my-pod
```

**Exception**: When specifically searching across namespaces

---

### 2. Use JSON Output for Automation

**Why**: Stable format, easy parsing, machine-readable

```bash
# ✅ Good - JSON for scripts
kubectl-smart diag pod my-pod -o json | jq '.root_cause.reason'

# ❌ Avoid - Parsing text output in scripts
kubectl-smart diag pod my-pod | grep "Root Cause"
```

**Benefit**: Text format may change between versions, JSON won't

---

### 3. Check Exit Codes in Scripts

**Why**: Proper error handling, automation-friendly

```bash
# ✅ Good - Check exit code
kubectl-smart diag pod my-pod -n production
exit_code=$?

if [ $exit_code -eq 2 ]; then
  echo "Critical issues found!"
  # Send alert
  send_alert "Production pod has critical issues"
elif [ $exit_code -eq 1 ]; then
  echo "Warnings detected"
fi
```

**Exit codes**:
- `0` = No issues (score < 50)
- `1` = Warnings (score 50-89)
- `2` = Critical or error (score ≥ 90)

---

### 4. Use Configuration File for Consistency

**Why**: Team-wide consistency, reproducible results

```bash
# Create team config
cat > ~/.kubectl-smart/config.yaml <<EOF
output:
  colors_enabled: true
  max_display_issues: 15
  default_format: text

performance:
  max_concurrent_collectors: 5
  collector_timeout_seconds: 10.0

logging:
  enabled: true
  level: INFO
  file: ~/.kubectl-smart/logs/kubectl-smart.log
EOF
```

**Benefit**: Same behavior for all team members

---

### 5. Start with Diagnosis, Then Graph

**Why**: Diagnosis is faster, identifies issues first

```bash
# ✅ Good workflow
kubectl-smart diag pod my-pod -n production
# If issues found, check dependencies
kubectl-smart graph pod my-pod --upstream -n production

# ❌ Less efficient
kubectl-smart graph pod my-pod --downstream -n production
# Then checking each dependent resource individually
```

---

## Diagnosis Best Practices

### 1. Diagnose Specific Resources First

**Why**: Faster, more focused results

```bash
# ✅ Good - Specific resource
kubectl-smart diag pod failing-pod-xyz -n production

# ⚠️ Use sparingly - All resources
kubectl-smart diag pod --all -n production  # Only for overview
```

**When to use --all**:
- Initial triage of unknown issues
- Periodic health checks
- Post-deployment validation

---

### 2. Use Watch Mode for Intermittent Issues

**Why**: Catches transient problems, continuous monitoring

```bash
# ✅ Good - Watch for changes
kubectl-smart diag pod flaky-pod --watch --interval=10

# ❌ Avoid - Manual polling
while true; do
  kubectl-smart diag pod flaky-pod
  sleep 10
done
```

**Use cases**:
- CrashLoopBackOff with varying restart times
- Intermittent network issues
- Resource pressure scenarios

---

### 3. Combine with kubectl logs

**Why**: kubectl-smart shows last 100 lines, may need more

```bash
# ✅ Good - Complete investigation
kubectl-smart diag pod my-pod -n production

# Then check full logs if needed
kubectl logs my-pod -n production --tail=1000

# Or previous container
kubectl logs my-pod -n production -p
```

---

### 4. Understand Score Ranges

**Why**: Prioritize issues effectively

**Score interpretation**:
- **90-100**: Critical - Immediate action required
- **70-89**: High - Address soon
- **50-69**: Medium - Monitor and plan fix
- **25-49**: Low - Not urgent
- **0-24**: Info - Awareness only

```bash
# ✅ Good - Prioritize by score
kubectl-smart diag pod my-pod -o json | \
  jq '.all_issues[] | select(.score >= 90) | .reason'
```

---

### 5. Validate Before and After Changes

**Why**: Confirm issues are resolved

```bash
# ✅ Good workflow
# 1. Before fix
kubectl-smart diag pod my-pod -n production -o json > before.json

# 2. Apply fix
kubectl apply -f fixed-deployment.yaml

# 3. Wait for rollout
kubectl rollout status deploy/my-app -n production

# 4. After fix
kubectl-smart diag pod my-pod -n production -o json > after.json

# 5. Compare
diff <(jq -S '.all_issues' before.json) <(jq -S '.all_issues' after.json)
```

---

## Automation Best Practices

### 1. Use in CI/CD for Deployment Validation

**Why**: Catch issues early, automated quality gate

```yaml
# ✅ Good - GitLab CI example
validate_deployment:
  stage: test
  script:
    - kubectl apply -f deployment.yaml
    - kubectl rollout status deploy/my-app
    - kubectl-smart diag deploy my-app -o json > diagnosis.json
    - |
      CRITICAL=$(jq '.summary.critical_issues' diagnosis.json)
      if [ "$CRITICAL" -gt 0 ]; then
        echo "Deployment has critical issues!"
        exit 1
      fi
  artifacts:
    paths:
      - diagnosis.json
```

See [INTEGRATIONS.md](INTEGRATIONS.md) for more examples.

---

### 2. Regular Health Checks with Cron

**Why**: Proactive monitoring, early detection

```bash
# ✅ Good - Daily health check
#!/bin/bash
# /usr/local/bin/k8s-health-check.sh

NAMESPACES="production staging"
ALERT_EMAIL="oncall@example.com"

for ns in $NAMESPACES; do
  echo "Checking namespace: $ns"

  # Diagnose all pods
  kubectl-smart diag pod --all -n $ns -o json > /tmp/$ns-health.json

  # Check for critical issues
  CRITICAL=$(jq '.with_issues' /tmp/$ns-health.json)

  if [ "$CRITICAL" -gt 0 ]; then
    echo "Critical issues found in $ns!"
    kubectl-smart diag pod --all -n $ns | \
      mail -s "K8s Health Alert: $ns" $ALERT_EMAIL
  fi

  # Capacity forecast
  kubectl-smart top $ns --horizon=168 -o json > /tmp/$ns-capacity.json

  # Check for capacity warnings
  WARNINGS=$(jq '.capacity_warnings | length' /tmp/$ns-capacity.json)

  if [ "$WARNINGS" -gt 0 ]; then
    echo "Capacity warnings in $ns"
    kubectl-smart top $ns | \
      mail -s "K8s Capacity Warning: $ns" $ALERT_EMAIL
  fi
done
```

**Crontab**:
```bash
# Run daily at 6 AM
0 6 * * * /usr/local/bin/k8s-health-check.sh
```

---

### 3. Store Historical Diagnostics

**Why**: Trend analysis, incident review

```bash
# ✅ Good - Historical tracking
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_DIR="/var/log/kubectl-smart"

mkdir -p $REPORT_DIR

kubectl-smart diag pod --all -n production -o json > \
  $REPORT_DIR/diagnosis-$TIMESTAMP.json

kubectl-smart top production -o json > \
  $REPORT_DIR/capacity-$TIMESTAMP.json

# Cleanup old reports (keep 30 days)
find $REPORT_DIR -name "*.json" -mtime +30 -delete
```

---

### 4. Integrate with Monitoring/Alerting

**Why**: Unified observability, automated response

**Prometheus example**:
```bash
# Export metrics from kubectl-smart
kubectl-smart diag pod my-pod -o json | \
  jq -r '.summary | "kubectl_smart_critical_issues \(.critical_issues)\nkubectl_smart_warning_issues \(.warning_issues)"' | \
  curl --data-binary @- http://pushgateway:9091/metrics/job/kubectl_smart
```

**Grafana dashboard**: Query Prometheus metrics for visualization

---

### 5. Use as Pre-deployment Gate

**Why**: Prevent broken deployments

```bash
# ✅ Good - Pre-deployment validation
#!/bin/bash
# pre-deploy-check.sh

NAMESPACE="production"
DEPLOYMENT="my-app"

echo "Running pre-deployment checks..."

# Check current state
kubectl-smart diag deploy $DEPLOYMENT -n $NAMESPACE -o json > current-state.json

CURRENT_ISSUES=$(jq '.summary.critical_issues' current-state.json)

if [ "$CURRENT_ISSUES" -gt 0 ]; then
  echo "❌ Cannot deploy: Current deployment has critical issues!"
  echo "Fix existing issues before deploying new version"
  exit 1
fi

# Check capacity
kubectl-smart top $NAMESPACE -o json > capacity.json

CAPACITY_WARNINGS=$(jq '.capacity_warnings | length' capacity.json)

if [ "$CAPACITY_WARNINGS" -gt 0 ]; then
  echo "⚠️  Warning: Capacity issues detected"
  echo "Consider scaling cluster before deploying"
  # Don't block, just warn
fi

echo "✅ Pre-deployment checks passed"
exit 0
```

---

## Performance Best Practices

### 1. Use Namespaces to Reduce Scope

**Why**: Faster execution, less data to process

```bash
# ✅ Fast
kubectl-smart diag pod my-pod -n production  # ~2s

# ❌ Slow
kubectl-smart diag pod my-pod  # ~10s (searches all namespaces)
```

---

### 2. Adjust Concurrent Collectors for Cluster Size

**Why**: Balance speed vs cluster load

**Small clusters (<100 resources)**:
```yaml
# ~/.kubectl-smart/config.yaml
performance:
  max_concurrent_collectors: 10  # More parallelism
```

**Large clusters (>1000 resources)**:
```yaml
performance:
  max_concurrent_collectors: 3  # Less cluster load
```

**Slow networks**:
```yaml
performance:
  max_concurrent_collectors: 5
  collector_timeout_seconds: 30.0  # Longer timeout
```

---

### 3. Use Batch Operations Wisely

**Why**: Batch is powerful but resource-intensive

```bash
# ✅ Good - Specific namespace
kubectl-smart diag pod --all -n my-small-namespace

# ⚠️ Use carefully - Large namespace
kubectl-smart diag pod --all -n production  # May be slow

# ❌ Avoid - Cluster-wide
# kubectl-smart diag pod --all  # Very slow, high load
```

**Alternative for large namespaces**:
```bash
# Filter with kubectl first
for pod in $(kubectl get pods -n production --field-selector=status.phase=Failed -o name); do
  kubectl-smart diag $pod -n production
done
```

---

### 4. Cache Results When Appropriate

**Why**: Avoid redundant analysis

```bash
# ✅ Good - Cache diagnosis
kubectl-smart diag pod my-pod -o json > my-pod-diagnosis.json

# Reuse cached results
ISSUE_COUNT=$(jq '.summary.total_issues' my-pod-diagnosis.json)
ROOT_CAUSE=$(jq -r '.root_cause.reason' my-pod-diagnosis.json)

# Only re-run if state changes
NEW_GENERATION=$(kubectl get pod my-pod -o jsonpath='{.metadata.generation}')
if [ "$NEW_GENERATION" != "$CACHED_GENERATION" ]; then
  kubectl-smart diag pod my-pod -o json > my-pod-diagnosis.json
fi
```

---

### 5. Run During Off-Peak Hours

**Why**: Minimize impact on production

```bash
# ✅ Good - Schedule batch operations
# Crontab: 2 AM daily
0 2 * * * kubectl-smart diag pod --all -n production -o json > /var/log/daily-health.json

# ❌ Avoid - During peak hours
# Don't run heavy batch operations during business hours
```

---

## Security Best Practices

### 1. Use Least Privilege RBAC

**Why**: Minimize attack surface

**Required permissions** (read-only):
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kubectl-smart-reader
  namespace: production
rules:
- apiGroups: [""]
  resources: ["pods", "services", "events", "persistentvolumeclaims"]
  verbs: ["get", "list"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
```

**Bind to service account**:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kubectl-smart-reader-binding
  namespace: production
subjects:
- kind: ServiceAccount
  name: kubectl-smart
  namespace: production
roleRef:
  kind: Role
  name: kubectl-smart-reader
  apiGroup: rbac.authorization.k8s.io
```

---

### 2. Avoid Logging Sensitive Data

**Why**: Prevent credential leakage

```bash
# ✅ Good - Redirect logs safely
kubectl-smart diag pod my-pod -o json 2>/dev/null | \
  jq 'del(.resource.properties.env)'  # Remove env vars

# ❌ Avoid - Logging everything
kubectl-smart --debug diag pod my-pod &> full-debug.log
# May contain secrets in env vars
```

---

### 3. Use Separate Contexts for Production

**Why**: Prevent accidental production changes (future versions)

```bash
# ✅ Good - Explicit production context
kubectl-smart diag pod my-pod --context=production-readonly -n production

# Set default context for production
kubectl config use-context production-readonly
```

---

### 4. Audit kubectl-smart Usage

**Why**: Track who diagnosed what

```bash
# ✅ Good - Audit logging
# ~/.kubectl-smart/config.yaml
logging:
  enabled: true
  level: INFO
  file: ~/.kubectl-smart/logs/audit.log

# Log includes:
# - User (from $USER)
# - Command executed
# - Timestamp
# - Working directory
```

**Review audit logs**:
```bash
# See who ran what
tail -f ~/.kubectl-smart/logs/audit.log | jq .
```

---

### 5. Validate JSON Output Before Using

**Why**: Prevent injection attacks in automation

```bash
# ✅ Good - Validate JSON
OUTPUT=$(kubectl-smart diag pod my-pod -o json)

if echo "$OUTPUT" | jq empty 2>/dev/null; then
  # Valid JSON
  REASON=$(echo "$OUTPUT" | jq -r '.root_cause.reason')
else
  echo "Invalid JSON output!"
  exit 1
fi

# ❌ Avoid - Direct eval
# eval $(kubectl-smart diag pod my-pod -o json)  # DANGEROUS!
```

---

## Team Best Practices

### 1. Create Runbooks with kubectl-smart

**Why**: Standardize troubleshooting across team

**Example runbook** (Production Pod Failure):
```markdown
# Runbook: Production Pod Failure

## 1. Initial Diagnosis
kubectl-smart diag pod <pod-name> -n production

## 2. Check Dependencies
kubectl-smart graph pod <pod-name> --upstream -n production

## 3. If Database Issue Found
kubectl-smart diag svc database -n production

## 4. Check Capacity
kubectl-smart top production --horizon=24

## 5. Escalation Criteria
- Critical score ≥ 90: Page on-call
- Warning score 50-89: Create ticket
- Info score < 50: Monitor only
```

---

### 2. Share Configuration Across Team

**Why**: Consistent experience, reproducible results

```bash
# ✅ Good - Team config in git
# Create team repo: kubectl-smart-config
git clone https://github.com/company/kubectl-smart-config
ln -s $(pwd)/kubectl-smart-config/config.yaml ~/.kubectl-smart/config.yaml

# Everyone uses same config
```

**config.yaml**:
```yaml
# Team-wide configuration
output:
  colors_enabled: true
  max_display_issues: 15

performance:
  max_concurrent_collectors: 5

logging:
  enabled: true
  level: INFO
```

---

### 3. Train Team on Exit Codes

**Why**: Automated workflows need consistent interpretation

**Training checklist**:
- ✅ Exit code 0: No action needed (score < 50)
- ✅ Exit code 1: Warnings (score 50-89) - Monitor
- ✅ Exit code 2: Critical (score ≥ 90) - Take action
- ✅ Exit code 2: Also means error (resource not found, etc.)

**Example script**:
```bash
kubectl-smart diag pod my-pod -n production
case $? in
  0)
    echo "✅ No issues detected"
    ;;
  1)
    echo "⚠️  Warnings detected - monitoring required"
    ;;
  2)
    echo "❌ Critical issues or error - action required"
    send_alert "Critical K8s issue detected"
    ;;
esac
```

---

### 4. Establish Review Process for Automated Remediation

**Why**: Safety first when automation is involved (future feature)

**Process** (when `--apply` is available):
1. **Test in staging first**
2. **Require approval for production**
3. **Audit all changes**
4. **Have rollback plan**

```bash
# ✅ Good - Require confirmation
kubectl-smart diag pod my-pod --apply --confirm

# ❌ Avoid - Blind automation
# kubectl-smart diag pod my-pod --apply --no-confirm  # DANGEROUS
```

---

### 5. Document Known Limitations

**Why**: Set correct expectations

**Example team wiki**:
```markdown
# kubectl-smart Limitations

## Current Limitations (v0.1.0)
- Read-only (no remediation yet)
- Last 100 log lines only
- No streaming logs
- Single-cluster only

## Workarounds
- Use `kubectl logs` for full logs
- Use `k9s` for streaming
- Run kubectl-smart per cluster
```

---

## Anti-Patterns to Avoid

### ❌ Don't Use as Only Monitoring Tool

**Problem**: kubectl-smart is diagnostic, not monitoring

```bash
# ❌ Bad
# Using only kubectl-smart, no Prometheus/Grafana

# ✅ Good
# Use kubectl-smart for diagnosis
# Use Prometheus for metrics
# Use Grafana for dashboards
# Use kubectl-smart in CI/CD and incident response
```

---

### ❌ Don't Ignore Warnings

**Problem**: Small issues become big issues

```bash
# ❌ Bad
kubectl-smart diag pod my-pod
# Exit code 1 (warnings)
# Ignore and move on

# ✅ Good
kubectl-smart diag pod my-pod -o json > warnings.json
# Create ticket to address warnings
# Monitor for escalation
```

---

### ❌ Don't Run Without Understanding Output

**Problem**: Misinterpretation leads to wrong fixes

```bash
# ❌ Bad
kubectl-smart diag pod my-pod
# See "ImagePullBackOff"
# Immediately restart pod (doesn't help)

# ✅ Good
kubectl-smart diag pod my-pod
# Read full diagnosis
# Understand root cause
# Check suggested actions
# Apply correct fix (fix image name, not restart)
```

---

### ❌ Don't Parse Text Output in Scripts

**Problem**: Fragile, breaks between versions

```bash
# ❌ Bad
kubectl-smart diag pod my-pod | grep "Root Cause" | awk '{print $3}'

# ✅ Good
kubectl-smart diag pod my-pod -o json | jq -r '.root_cause.reason'
```

---

### ❌ Don't Skip Namespace in Production

**Problem**: Slower, may hit wrong resource

```bash
# ❌ Bad
kubectl-smart diag pod my-pod  # Searches all namespaces

# ✅ Good
kubectl-smart diag pod my-pod -n production  # Explicit namespace
```

---

## Checklist for Production Use

Before using kubectl-smart in production:

- [ ] Tested in development/staging environments
- [ ] RBAC permissions configured (read-only)
- [ ] Team trained on exit codes and output
- [ ] Configuration file created and shared
- [ ] Integrated into runbooks
- [ ] Logging/audit enabled
- [ ] Monitoring/alerting integration tested
- [ ] Escalation procedures documented
- [ ] Known limitations documented
- [ ] Backup manual troubleshooting procedures in place

---

## Additional Resources

- [Tutorial](TUTORIAL.md) - Step-by-step guides
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues
- [FAQ](FAQ.md) - Frequently asked questions
- [Integrations](INTEGRATIONS.md) - CI/CD and monitoring
- [Positioning](../POSITIONING.md) - Why kubectl-smart exists
