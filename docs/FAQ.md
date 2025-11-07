# Frequently Asked Questions (FAQ)

Common questions about kubectl-smart.

## Table of Contents

- [General Questions](#general-questions)
- [Usage Questions](#usage-questions)
- [Technical Questions](#technical-questions)
- [Comparison Questions](#comparison-questions)
- [Troubleshooting Questions](#troubleshooting-questions)

---

## General Questions

### What is kubectl-smart?

kubectl-smart is an intelligent kubectl plugin for Kubernetes debugging. It provides:
- Root-cause analysis of failing workloads
- Dependency visualization
- Predictive capacity monitoring
- Automated remediation suggestions

Think of it as an "autopilot for kubectl debugging" that helps you quickly diagnose and fix Kubernetes issues.

---

### Why should I use kubectl-smart?

**Use kubectl-smart if you**:
- Spend hours debugging Kubernetes issues manually
- Need to automate diagnostics in CI/CD pipelines
- Want predictive alerts before issues occur
- Need to quickly onboard new team members to Kubernetes troubleshooting

**Skip kubectl-smart if you**:
- Prefer manual inspection with kubectl
- Use comprehensive platforms like Lens or k9s for all operations
- Have mature observability stack (Prometheus, Grafana, etc.)

See [POSITIONING.md](../POSITIONING.md) for detailed comparison.

---

### Is kubectl-smart free?

Yes! kubectl-smart is **100% open source** under the MIT License.

- Free to use in commercial and non-commercial projects
- No hidden costs, premium tiers, or paywalls
- Community-driven development

---

### Is kubectl-smart production-ready?

**Current status**: v0.1.0 - Early release, use with caution

**Production readiness**:
- ✅ Read-only operations (safe to use)
- ✅ Works on real clusters
- ⚠️ Test coverage: ~15% (growing)
- ⚠️ Limited real-world testing
- ❌ No automated remediation yet (dry-run only)

**Recommendation**:
- **Development/Staging**: Safe to use
- **Production**: Use for diagnosis only, not remediation
- **CI/CD**: Great for automated checks

See [TESTING.md](../TESTING.md) for honest assessment.

---

### Does kubectl-smart modify my cluster?

**Current version (v0.1.0)**: NO

kubectl-smart is **read-only** and makes only:
- `kubectl get`
- `kubectl describe`
- `kubectl logs`
- `kubectl top`
- `kubectl cluster-info`

**Future versions**:
- Optional `--apply` flag for remediation (with confirmation)
- All changes will be explicit and require approval

---

## Usage Questions

### How do I install kubectl-smart?

```bash
# Using pip
pip install kubectl-smart

# From source
git clone https://github.com/srijanshukla18/kubectl-smart
cd kubectl-smart
pip install -e .

# Verify installation
kubectl-smart --version
```

See [Installation Guide](../README.md#installation) for details.

---

### What kubectl version do I need?

**Minimum**: kubectl v1.20+

**Recommended**: kubectl v1.25+

**Check your version**:
```bash
kubectl version --client
```

kubectl-smart will warn you if your version is too old.

---

### What Python version do I need?

**Minimum**: Python 3.9+

**Recommended**: Python 3.11+

**Check your version**:
```bash
python --version
```

---

### Does kubectl-smart work with all Kubernetes distributions?

**Tested on**:
- ✅ minikube
- ✅ kind (Kubernetes in Docker)
- ✅ GKE (Google Kubernetes Engine)
- ✅ EKS (Amazon Elastic Kubernetes Service)
- ✅ AKS (Azure Kubernetes Service)

**Should work on**:
- Any standard Kubernetes distribution
- OpenShift
- Rancher
- k3s/k0s

**Requirements**:
- Standard Kubernetes API
- kubectl access

---

### Can I use kubectl-smart without metrics-server?

**Yes!** kubectl-smart works without metrics-server.

**With metrics-server**:
- Better forecasting accuracy
- Resource utilization insights
- Capacity predictions

**Without metrics-server**:
- Basic diagnosis still works
- Forecasting uses fallback methods
- Certificate checks still work

Install metrics-server for best experience:
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

---

### How do I get JSON output?

```bash
# Add -o json to any command
kubectl-smart diag pod my-pod -o json
kubectl-smart graph deploy my-app -o json
kubectl-smart top production -o json

# Parse with jq
kubectl-smart diag pod my-pod -o json | jq '.root_cause'
```

See [Tutorial - JSON Output](TUTORIAL.md#json-output-for-automation) for examples.

---

### Can I watch resources continuously?

**Yes!** Use the `--watch` flag:

```bash
# Watch pod every 5 seconds (default)
kubectl-smart diag pod my-pod --watch

# Custom interval
kubectl-smart diag pod my-pod --watch --interval=10

# Stop with Ctrl+C
```

See [Tutorial - Watch Mode](TUTORIAL.md#watch-mode) for details.

---

### Can I diagnose multiple resources at once?

**Yes!** Use the `--all` flag:

```bash
# Diagnose all pods in namespace
kubectl-smart diag pod --all -n production

# Get summary and top issues
```

See [Tutorial - Batch Operations](TUTORIAL.md#batch-operations) for details.

---

## Technical Questions

### How does kubectl-smart work?

**Architecture**:

1. **Data Collection**: Runs kubectl commands concurrently
   - `kubectl get pod -o json`
   - `kubectl describe pod`
   - `kubectl logs --tail=100`
   - `kubectl get events`

2. **Parsing**: Extracts structured data

3. **Analysis**:
   - Builds dependency graph
   - Scores issues using weighted algorithm
   - Identifies root cause

4. **Output**: Renders diagnosis with suggestions

**Performance**:
- Concurrent data collection (5 collectors)
- Efficient parsing
- Typical runtime: 2-5 seconds

---

### What algorithm does kubectl-smart use?

**Scoring algorithm**:
```
Issue Score = (Severity × 40) + (Frequency × 30) + (Age × 20) + (Impact × 10)

Severity: Critical (100), High (75), Medium (50), Low (25)
Frequency: Number of occurrences
Age: How long issue has existed
Impact: Blast radius (downstream dependencies)
```

**Root Cause**:
- Highest scoring issue
- Must be ≥ 50 score

**Contributing Factors**:
- Next 2-3 issues
- Must be ≥ 50 score

See [ARCHITECTURE.md](../ARCHITECTURE.md) for details.

---

### Does kubectl-smart use AI/ML?

**Not currently**. kubectl-smart uses:
- **Rule-based scoring** for issue detection
- **Time-series forecasting** (Holt-Winters) for capacity prediction
- **Graph algorithms** for dependency analysis

**No external APIs**, **no data sharing**, **fully local**.

**Future**: May add optional ML-based anomaly detection.

---

### How accurate is the forecasting?

**Depends on data quality**:

**Good accuracy** (±5%):
- Stable workloads with metrics-server
- 7+ days of historical data
- Predictable patterns

**Moderate accuracy** (±15%):
- Variable workloads
- 3-7 days of data
- Some outliers

**Low accuracy** (±30%):
- Highly variable workloads
- <3 days of data
- No metrics-server (fallback method)

**Use forecasting as guidance, not gospel**.

---

### What data does kubectl-smart collect?

**Only cluster data**:
- Resource definitions (pods, deployments, etc.)
- Resource status and conditions
- Events
- Logs (last 100 lines)
- Metrics (if metrics-server available)

**No external data**:
- No telemetry sent to external servers
- No usage analytics
- No crash reports
- Fully offline tool

**Privacy**: All data stays local.

---

### Can kubectl-smart auto-fix issues?

**Current version (v0.1.0)**: NO

**What kubectl-smart does**:
- ✅ Identifies issues
- ✅ Suggests fixes
- ✅ Shows exact commands to run
- ❌ Does not auto-apply fixes

**Future versions**:
- Optional `--apply` flag for automated remediation
- Confirmation required
- Audit log of all changes

**Why not auto-fix now?**:
- Safety first
- Need comprehensive testing
- User should understand changes

---

## Comparison Questions

### kubectl-smart vs kubectl?

**kubectl**:
- ✅ Standard Kubernetes CLI
- ✅ All operations (get, apply, delete, etc.)
- ✅ Universal, well-documented
- ❌ Manual analysis required
- ❌ No root-cause detection
- ❌ No predictive capabilities

**kubectl-smart**:
- ✅ Automated diagnosis
- ✅ Root-cause detection
- ✅ Predictive forecasting
- ✅ Dependency visualization
- ❌ Read-only (currently)
- ❌ Limited to debugging

**Verdict**: kubectl-smart complements kubectl, doesn't replace it.

---

### kubectl-smart vs k9s?

**k9s**:
- ✅ Real-time TUI (text UI)
- ✅ Interactive navigation
- ✅ Tail logs, port-forward, shell
- ✅ Great for exploration
- ❌ Manual analysis
- ❌ No automation/scripting

**kubectl-smart**:
- ✅ Automated diagnosis
- ✅ Scriptable (JSON output)
- ✅ Predictive forecasting
- ❌ No interactive UI
- ❌ Single-shot analysis

**Verdict**: Use k9s for interactive exploration, kubectl-smart for automated diagnosis.

---

### kubectl-smart vs Lens?

**Lens**:
- ✅ Full-featured IDE for Kubernetes
- ✅ Multi-cluster management
- ✅ Extensions, charts, monitoring
- ✅ Great for developers
- ❌ Desktop app (GUI required)
- ❌ Not scriptable

**kubectl-smart**:
- ✅ CLI tool (no GUI needed)
- ✅ Scriptable and automatable
- ✅ Lightweight (<10MB)
- ❌ Single-cluster focus
- ❌ Limited features

**Verdict**: Use Lens for daily development, kubectl-smart for automation/CI/CD.

---

### kubectl-smart vs Prometheus/Grafana?

**Prometheus/Grafana**:
- ✅ Comprehensive monitoring
- ✅ Custom dashboards
- ✅ Alerting rules
- ✅ Long-term storage
- ❌ Requires setup/maintenance
- ❌ No root-cause analysis

**kubectl-smart**:
- ✅ Zero setup
- ✅ Root-cause detection
- ✅ Works anywhere kubectl works
- ❌ No long-term storage
- ❌ No custom dashboards

**Verdict**: Use Prometheus for monitoring, kubectl-smart for quick diagnosis.

See [POSITIONING.md](../POSITIONING.md) for detailed comparison.

---

## Troubleshooting Questions

### Why is kubectl-smart slow?

**Common causes**:
1. **Large cluster** (>500 resources)
2. **Network latency** to cluster
3. **Slow log collection**
4. **Many namespaces**

**Solutions**:
```bash
# Use specific namespace
kubectl-smart diag pod my-pod -n production

# Reduce concurrent collectors
# Edit ~/.kubectl-smart/config.yaml
performance:
  max_concurrent_collectors: 3
```

See [Troubleshooting - Performance Issues](TROUBLESHOOTING.md#performance-issues).

---

### Why am I getting "permission denied"?

**Cause**: Insufficient RBAC permissions

**Required permissions**:
- `get` on: pods, deployments, services, events
- `list` on: pods, deployments, services, events

**Check permissions**:
```bash
kubectl auth can-i get pods -n production
kubectl auth can-i list events -n production
```

**Solution**: Request access from cluster admin

See [Troubleshooting - Permission Issues](TROUBLESHOOTING.md#permission-issues).

---

### Why is there no output?

**Common causes**:
1. **Resource doesn't exist**
2. **Wrong namespace**
3. **Terminal doesn't support colors**

**Solutions**:
```bash
# Verify resource exists
kubectl get pod my-pod -n production

# Disable colors
NO_COLOR=1 kubectl-smart diag pod my-pod

# Use JSON output
kubectl-smart diag pod my-pod -o json
```

---

### Can I disable colors?

**Yes!**

```bash
# Method 1: Environment variable
NO_COLOR=1 kubectl-smart diag pod my-pod

# Method 2: Config file
# Edit ~/.kubectl-smart/config.yaml
output:
  colors_enabled: false

# Method 3: Pipe to less
kubectl-smart diag pod my-pod | less -R
```

---

### How do I report a bug?

1. **Check existing issues**: https://github.com/srijanshukla18/kubectl-smart/issues

2. **Gather information**:
   ```bash
   kubectl-smart --version
   python --version
   kubectl version
   kubectl-smart --debug diag pod my-pod 2>&1 | tee debug.log
   ```

3. **Create new issue** with:
   - kubectl-smart version
   - Environment (OS, Python, kubectl version)
   - Steps to reproduce
   - Error message
   - Debug log (redact sensitive info)

---

## Contributing Questions

### How can I contribute?

**Ways to contribute**:
1. **Report bugs** - Help us improve quality
2. **Suggest features** - What would be useful?
3. **Write documentation** - Improve guides and examples
4. **Submit PRs** - Fix bugs or add features
5. **Share feedback** - How can we improve?

**Getting started**:
```bash
git clone https://github.com/srijanshukla18/kubectl-smart
cd kubectl-smart
pip install -e ".[dev]"
pytest tests/
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) (if exists).

---

### What features are planned?

**v0.2.0 (Short-term)**:
- Automated remediation with `--apply`
- More collectors (node metrics, HPA, etc.)
- Enhanced forecasting
- Improved test coverage (50%+)

**v0.3.0 (Medium-term)**:
- Multi-resource batch operations with filters
- Real-time streaming diagnosis
- Custom rules/scoring
- Export reports (PDF, HTML)

**v1.0.0 (Long-term)**:
- ML-based anomaly detection
- Cost optimization insights
- Security scanning
- Plugin system

See [IMPROVEMENT_PLAN.md](../IMPROVEMENT_PLAN.md) for roadmap.

---

### Can I request a feature?

**Yes! Please do!**

1. **Check existing requests**: https://github.com/srijanshukla18/kubectl-smart/issues?q=is%3Aissue+is%3Aopen+label%3Aenhancement

2. **Create feature request** with:
   - Use case (what problem does it solve?)
   - Proposed solution
   - Alternative solutions considered
   - Examples of similar features in other tools

3. **Discuss with community** in issue comments

---

## Still Have Questions?

- **Documentation**: [Tutorial](TUTORIAL.md), [Troubleshooting](TROUBLESHOOTING.md), [Best Practices](BEST_PRACTICES.md)
- **GitHub Issues**: https://github.com/srijanshukla18/kubectl-smart/issues
- **Stack Overflow**: Tag with `kubectl-smart` (check first if anyone already asked)
- **Email**: (if provided in README)

---

## Quick Links

- [Installation Guide](../README.md#installation)
- [Tutorial](TUTORIAL.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Best Practices](BEST_PRACTICES.md)
- [Integrations](INTEGRATIONS.md)
- [Positioning](../POSITIONING.md)
- [Improvement Plan](../IMPROVEMENT_PLAN.md)
- [Testing Status](../TESTING.md)
