# kubectl-smart Prediction Feature PRD

## Executive Summary

Add predictive failure prevention to kubectl-smart, focusing on mathematically predictable "boring" failures that cause 80% of incidents. This feature leverages our existing dependency graph analysis to prioritize predictions by business impact and provides specific remediation commands.

## Problem Statement

### The Reality of K8s Incidents
- **60% of production incidents** are predictable resource exhaustions (disk full, OOM, CPU throttling)
- **15% of incidents** are certificate expirations - completely preventable with basic date math
- **10% of incidents** are gradual degradations (memory leaks, disk growth) with clear patterns

### Current Pain Points
1. **Weekend Pages**: Cert expires Saturday night, even though expiry date was known 90 days ago
2. **Gradual Then Sudden**: PVC grows 2GB/day for months, then fills up during critical business hours
3. **Predictable OOMs**: Java app leaks 100MB/day consistently, OOMs after exactly 14 days
4. **Capacity Surprises**: Node resources exhausted by gradual pod scaling, causing scheduling failures

### Why Existing Tools Fall Short
- **Prometheus/AlertManager**: Alerts when already at threshold (90% disk), too late to prevent
- **Monitoring Dashboards**: Show current state, require human interpretation of trends
- **Generic Predictors**: Lack Kubernetes context and business impact understanding

## Solution: Predictive Failure Prevention

### Core Capability
Predict resource exhaustions and configuration failures 1-7 days in advance, ranked by business impact, with specific prevention commands.

### Key Differentiator
Combines kubectl-smart's existing critical path analysis with simple trend analysis to answer: "What will break, how bad will it hurt, and how do I prevent it?"

## User Personas & Use Cases

### SRE On-Call
**Need**: Don't get paged for preventable failures
```bash
kubectl smart predict --on-call
→ NEXT 72H RISKS:
🔴 prod-ingress cert expires in 68h (impacts ALL traffic)
   FIX NOW: kubectl -n cert-manager delete cert prod-tls --force
```

### DevOps Engineer
**Need**: Proactive capacity management across services
```bash
kubectl smart predict --capacity
→ RESOURCE EXHAUSTION TIMELINE:
Day 3: payment-db PVC hits 95% (2.1GB/day growth)
Day 5: worker-pool-2 CPU capacity exhausted
Day 12: prometheus memory limit (leak detected)
```

### Developer
**Need**: Know if my app will break without learning K8s internals
```bash
kubectl smart predict app user-service
→ YOUR APP HEALTH:
⚠️ Memory leak detected: +100MB/day since last deploy
  Will OOM in ~6 days at current rate
  FIX: Check for unclosed connections or caches
```

### Platform Architect
**Need**: System-wide patterns and cost optimization
```bash
kubectl smart predict --patterns
→ SYSTEM INSIGHTS:
- 12 Java services show similar memory leak pattern
- Storage costs growing 18%/month from unrotated logs
- 3 node pools will need expansion within 2 weeks
```

## Feature Specifications

### Prediction Types (Priority Order)

#### 1. Certificate Expiration (P0)
- **Detection**: Parse certificate expiry dates from secrets/ingresses
- **Prediction**: Simple date math
- **Prevention**: Exact kubectl commands to trigger renewal
- **Accuracy**: 100%

#### 2. Disk/PVC Exhaustion (P0)
- **Detection**: Linear regression on disk usage metrics
- **Prediction**: Days until 95% full based on growth rate
- **Prevention**: PVC expansion commands or cleanup suggestions
- **Accuracy**: 90%+ for steady workloads

#### 3. Memory Exhaustion (P1)
- **Detection**: Trend analysis on container memory usage
- **Prediction**: Time until OOM based on limit and growth pattern
- **Prevention**: Resource limit adjustments or leak investigation
- **Accuracy**: 85%+ for consistent patterns

#### 4. CPU Throttling (P1)
- **Detection**: CPU usage patterns vs limits
- **Prediction**: When daily peaks will hit throttling
- **Prevention**: Limit adjustments or HPA configuration
- **Accuracy**: 80%+ for regular traffic patterns

#### 5. Node Capacity (P2)
- **Detection**: Resource allocation trends across nodes
- **Prediction**: When nodes will be unschedulable
- **Prevention**: Node pool scaling or pod redistribution
- **Accuracy**: 75%+ based on growth trends

### Command Interface

```bash
# Default: Show all predictions for next 7 days
kubectl smart predict

# Focus on critical path resources only
kubectl smart predict --critical-path

# Specific time horizons
kubectl smart predict --horizon=24h  # Urgent only
kubectl smart predict --horizon=30d  # Long-term planning

# Filter by risk level
kubectl smart predict --risk=critical  # Will cause outages
kubectl smart predict --risk=warning   # Will degrade service

# Specific resource prediction
kubectl smart predict pod payment-api
kubectl smart predict pvc user-data

# Output formats
kubectl smart predict                 # For automation via exit codes/text
kubectl smart predict --format=slack  # For notifications
```

### Output Format

```
🔮 PREDICTIVE FAILURE ANALYSIS
Generated: 2024-01-15 09:30 UTC
Horizon: 7 days
Confidence: Based on 30 days of history

🔴 CRITICAL - Will cause outages (2)
├─ ingress-prod certificate expires in 72h
│  Impact: ALL external traffic will fail
│  Root cause: cert-manager webhook failing
│  PREVENT: kubectl delete cert -n prod ingress-tls && kubectl apply -f ingress-cert.yaml
│  Confidence: 100%
│
└─ payment-db PVC exhaustion in 4.2 days
   Impact: Payment processing will stop
   Growth rate: 2.1GB/day (30d average)
   PREVENT: kubectl patch pvc payment-db-data -p '{"spec":{"resources":{"requests":{"storage":"500Gi"}}}}'
   Confidence: 92%

🟡 WARNING - Will degrade service (3)
├─ api-gateway memory leak: OOM in ~8 days
│  Growth: 98MB/day since deploy v2.3.1
│  PREVENT: kubectl set resources deploy/api-gateway --limits=memory=4Gi
│  INVESTIGATE: Memory profile shows heap growth in cache layer
│
├─ prometheus CPU throttling risk in 6 days
│  Peak usage trending toward 95% of limit
│  PREVENT: kubectl autoscale deployment prometheus --min=2 --max=4 --cpu-percent=70
│
└─ logs-pv filling: 89% in 7 days
   Growth varies 3-8GB/day
   PREVENT: Configure log rotation or expand PV
   
💰 COST OPTIMIZATION OPPORTUNITIES
├─ 12 unused PVs: $340/month
├─ Over-provisioned nodes: $1,200/month (avg 20% CPU)
└─ Orphaned load balancers: $180/month
```

## Technical Implementation

### Architecture

```
┌─────────────────────┐     ┌──────────────────┐
│ kubectl-smart CLI   │────▶│ Prediction Engine │
└─────────────────────┘     └──────────────────┘
                                     │
                  ┌──────────────────┼──────────────────┐
                  ▼                  ▼                  ▼
          ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
          │ Metrics API  │  │ Resource API │  │ Graph Cache  │
          │ (Prometheus) │  │  (kubectl)   │  │  (existing)  │
          └──────────────┘  └──────────────┘  └──────────────┘
```

### Key Components

#### 1. Metrics Collector
- Query Prometheus or metrics-server API
- Cache 30 days of key metrics (disk, memory, CPU)
- Update cache incrementally

#### 2. Trend Analyzer
- Simple linear regression for steady trends
- Exponential smoothing for volatile metrics
- Pattern detection for cyclical behaviors

#### 3. Impact Calculator
- Use existing dependency graph
- Calculate business impact score
- Rank predictions by criticality

#### 4. Prevention Generator
- Resource-specific kubectl commands
- Context-aware suggestions
- Runbook references for complex issues

### Data Requirements

#### Minimum Metrics Needed
- Container memory/CPU usage (from metrics-server)
- PVC usage (from df metrics or CSI driver)
- Certificate expiry (from K8s secrets)
- Node resource allocation (from node status)

#### Optional Enhanced Metrics
- Prometheus histograms for percentile analysis
- Custom metrics for application-specific predictions
- Cost data for optimization recommendations

### Algorithm Overview

```python
def predict_failure(resource, metrics_history):
    # 1. Calculate trend
    daily_change = calculate_daily_trend(metrics_history)
    
    # 2. Project forward
    days_to_limit = (resource.limit - resource.current) / daily_change
    
    # 3. Assess impact
    critical_path_score = graph.get_criticality_score(resource)
    
    # 4. Generate prevention
    if days_to_limit < 7:
        return {
            'resource': resource,
            'days_to_failure': days_to_limit,
            'impact': critical_path_score,
            'prevention': generate_fix_command(resource),
            'confidence': calculate_confidence(metrics_history)
        }
```

## Success Metrics

### Quantitative
- **Prevented Incidents**: Track predictions that prevented actual outages
- **Accuracy Rate**: Measure prediction accuracy (target: >85% for critical predictions)
- **MTTR Reduction**: 40% reduction in incidents caused by predictable failures
- **Weekend Pages**: 60% reduction in off-hours incidents

### Qualitative  
- "I haven't been paged for cert expiry in 3 months"
- "We caught the memory leak before it impacted production"
- "Capacity planning is now proactive instead of reactive"

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- Certificate expiry prediction
- PVC growth prediction  
- Basic CLI interface
- JSON output format

### Phase 2: Memory & CPU (Week 3-4)
- Memory leak detection
- CPU throttling prediction
- Slack notification format
- Pattern detection across services

### Phase 3: Intelligence (Week 5-6)
- Node capacity planning
- Cost optimization insights
- Historical pattern learning
- Prevention playbook integration

## Differentiation from Competitors

### vs Prometheus Alerts
- **Predictive vs Reactive**: Prevent the alert from ever firing
- **Business Context**: Understands K8s dependencies and critical paths
- **Actionable**: Provides specific kubectl commands, not just notifications

### vs APM Tools (DataDog, New Relic)
- **K8s Native**: Deep understanding of K8s resources and patterns
- **CLI-First**: Integrated into SRE workflow
- **Cost**: No agent overhead or data egress costs

### vs Cloud Provider Tools
- **Multi-Cloud**: Works across any K8s cluster
- **Open Source**: Transparent, extensible, no vendor lock-in
- **Focused**: Just prediction, not a platform

## Future Enhancements

### Near Term
- Integration with CI/CD to predict impact of deployments
- Custom metric support for application-specific predictions
- Webhook support for automated prevention

### Long Term  
- ML-based pattern learning from incident history
- Cross-cluster pattern detection
- Automated prevention execution with approval workflows

## Summary

This feature transforms kubectl-smart from a reactive debugging tool to a proactive incident prevention system. By focusing on mathematically predictable failures and leveraging existing critical path analysis, we can prevent 60-80% of common incidents with minimal complexity.

The key insight: **Most Kubernetes incidents aren't surprises - they're math problems we forgot to solve.**