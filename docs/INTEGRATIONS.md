# kubectl-smart Integrations

Integration guides for CI/CD pipelines, monitoring systems, and automation workflows.

## Table of Contents

- [CI/CD Integrations](#cicd-integrations)
- [Monitoring Integrations](#monitoring-integrations)
- [Alerting Integrations](#alerting-integrations)
- [Automation Workflows](#automation-workflows)
- [Custom Integrations](#custom-integrations)

---

## CI/CD Integrations

### GitHub Actions

**Use case**: Validate deployments in pull requests

**.github/workflows/k8s-validation.yml**:
```yaml
name: Kubernetes Deployment Validation

on:
  pull_request:
    paths:
      - 'k8s/**'
      - 'manifests/**'

jobs:
  validate-deployment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install kubectl-smart
        run: |
          pip install kubectl-smart

      - name: Configure kubectl
        env:
          KUBECONFIG_DATA: ${{ secrets.KUBECONFIG_STAGING }}
        run: |
          mkdir -p ~/.kube
          echo "$KUBECONFIG_DATA" | base64 -d > ~/.kube/config

      - name: Apply manifests to staging
        run: |
          kubectl apply -f k8s/ --namespace=staging-pr-${{ github.event.pull_request.number }}

      - name: Wait for rollout
        run: |
          kubectl rollout status deployment/my-app --namespace=staging-pr-${{ github.event.pull_request.number }}
          sleep 30  # Allow time for issues to surface

      - name: Run kubectl-smart diagnosis
        id: diagnosis
        run: |
          kubectl-smart diag deploy my-app \
            --namespace=staging-pr-${{ github.event.pull_request.number }} \
            -o json > diagnosis.json

          # Check for critical issues
          CRITICAL=$(jq '.summary.critical_issues' diagnosis.json)
          echo "critical_issues=$CRITICAL" >> $GITHUB_OUTPUT

          if [ "$CRITICAL" -gt 0 ]; then
            echo "❌ Critical issues detected!"
            kubectl-smart diag deploy my-app \
              --namespace=staging-pr-${{ github.event.pull_request.number }}
            exit 1
          fi

      - name: Run capacity forecast
        run: |
          kubectl-smart top staging-pr-${{ github.event.pull_request.number }} \
            --horizon=48 -o json > capacity.json

          WARNINGS=$(jq '.capacity_warnings | length' capacity.json)
          if [ "$WARNINGS" -gt 0 ]; then
            echo "⚠️ Capacity warnings detected"
            kubectl-smart top staging-pr-${{ github.event.pull_request.number }}
          fi

      - name: Comment PR with results
        uses: actions/github-script@v6
        if: always()
        with:
          script: |
            const fs = require('fs');
            const diagnosis = JSON.parse(fs.readFileSync('diagnosis.json', 'utf8'));

            const comment = `## Kubernetes Deployment Validation

            **Summary**:
            - Total Issues: ${diagnosis.summary.total_issues}
            - Critical: ${diagnosis.summary.critical_issues}
            - Warnings: ${diagnosis.summary.warning_issues}

            ${diagnosis.summary.critical_issues > 0 ? '❌ **FAILED** - Critical issues detected' : '✅ **PASSED** - No critical issues'}

            <details>
            <summary>View full diagnosis</summary>

            \`\`\`json
            ${JSON.stringify(diagnosis, null, 2)}
            \`\`\`
            </details>
            `;

            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: comment
            });

      - name: Upload diagnosis artifacts
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: kubectl-smart-reports
          path: |
            diagnosis.json
            capacity.json

      - name: Cleanup staging environment
        if: always()
        run: |
          kubectl delete namespace staging-pr-${{ github.event.pull_request.number }} --ignore-not-found=true
```

---

### GitLab CI/CD

**Use case**: Post-deployment validation

**.gitlab-ci.yml**:
```yaml
stages:
  - build
  - deploy
  - validate

variables:
  NAMESPACE: production
  DEPLOYMENT_NAME: my-app

deploy_production:
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - kubectl config use-context production
    - kubectl apply -f k8s/
    - kubectl rollout status deployment/$DEPLOYMENT_NAME -n $NAMESPACE
  only:
    - main

validate_deployment:
  stage: validate
  image: python:3.11
  before_script:
    - pip install kubectl-smart
  script:
    # Diagnosis
    - kubectl-smart diag deploy $DEPLOYMENT_NAME -n $NAMESPACE -o json > diagnosis.json

    # Check exit code
    - |
      EXIT_CODE=$?
      if [ $EXIT_CODE -eq 2 ]; then
        echo "❌ Critical issues detected!"
        kubectl-smart diag deploy $DEPLOYMENT_NAME -n $NAMESPACE
        exit 1
      fi

    # Capacity check
    - kubectl-smart top $NAMESPACE --horizon=168 -o json > capacity.json

    # Alert on capacity warnings
    - |
      WARNINGS=$(jq '.capacity_warnings | length' capacity.json)
      if [ "$WARNINGS" -gt 0 ]; then
        echo "⚠️ Capacity warnings detected"
        kubectl-smart top $NAMESPACE
        # Send Slack alert
        curl -X POST -H 'Content-type: application/json' \
          --data "{\"text\":\"Capacity warnings in $NAMESPACE\"}" \
          $SLACK_WEBHOOK_URL
      fi

  artifacts:
    paths:
      - diagnosis.json
      - capacity.json
    reports:
      junit: diagnosis.json
  only:
    - main
```

---

### Jenkins Pipeline

**Use case**: Continuous deployment with validation

**Jenkinsfile**:
```groovy
pipeline {
    agent any

    environment {
        NAMESPACE = 'production'
        DEPLOYMENT = 'my-app'
    }

    stages {
        stage('Install kubectl-smart') {
            steps {
                sh 'pip install kubectl-smart'
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    kubectl apply -f k8s/ --namespace=$NAMESPACE
                    kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE
                '''
            }
        }

        stage('Validate Deployment') {
            steps {
                script {
                    // Run diagnosis
                    def exitCode = sh(
                        script: "kubectl-smart diag deploy $DEPLOYMENT -n $NAMESPACE -o json > diagnosis.json",
                        returnStatus: true
                    )

                    // Parse results
                    def diagnosis = readJSON file: 'diagnosis.json'

                    // Check for critical issues
                    if (diagnosis.summary.critical_issues > 0) {
                        error("Deployment has critical issues!")
                    }

                    // Capacity check
                    sh 'kubectl-smart top $NAMESPACE --horizon=168 -o json > capacity.json'
                    def capacity = readJSON file: 'capacity.json'

                    if (capacity.capacity_warnings.size() > 0) {
                        echo "WARNING: Capacity issues detected"
                        // Send alert but don't fail build
                        slackSend(
                            color: 'warning',
                            message: "Capacity warnings in ${NAMESPACE}"
                        )
                    }
                }
            }
        }

        stage('Post-Deployment Health Check') {
            steps {
                sh '''
                    # Wait 5 minutes, then re-check
                    sleep 300
                    kubectl-smart diag deploy $DEPLOYMENT -n $NAMESPACE -o json > post-deploy.json
                '''

                script {
                    def postDeploy = readJSON file: 'post-deploy.json'

                    if (postDeploy.summary.critical_issues > 0) {
                        error("Post-deployment check failed!")
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: '*.json', fingerprint: true
        }

        failure {
            sh 'kubectl-smart diag deploy $DEPLOYMENT -n $NAMESPACE'
        }
    }
}
```

---

### ArgoCD

**Use case**: Post-sync health check

**argocd-hook.yaml**:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: kubectl-smart-postsync
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      serviceAccountName: kubectl-smart
      containers:
      - name: kubectl-smart
        image: python:3.11
        command:
        - /bin/bash
        - -c
        - |
          pip install kubectl-smart

          # Diagnose deployment
          kubectl-smart diag deploy my-app -n production -o json > /tmp/diagnosis.json

          # Check for critical issues
          CRITICAL=$(jq '.summary.critical_issues' /tmp/diagnosis.json)

          if [ "$CRITICAL" -gt 0 ]; then
            echo "❌ Deployment has critical issues!"
            kubectl-smart diag deploy my-app -n production
            exit 1
          fi

          echo "✅ Deployment healthy"
      restartPolicy: Never
  backoffLimit: 1
```

---

## Monitoring Integrations

### Prometheus

**Use case**: Export kubectl-smart metrics to Prometheus

**prometheus-exporter.sh**:
```bash
#!/bin/bash
# Export kubectl-smart metrics to Prometheus Pushgateway

NAMESPACES="production staging"
PUSHGATEWAY="http://pushgateway:9091"

for ns in $NAMESPACES; do
  echo "Collecting metrics for namespace: $ns"

  # Diagnose all pods
  kubectl-smart diag pod --all -n $ns -o json > /tmp/$ns-diagnosis.json

  # Extract metrics
  TOTAL=$(jq '.total' /tmp/$ns-diagnosis.json)
  WITH_ISSUES=$(jq '.with_issues' /tmp/$ns-diagnosis.json)
  HEALTHY=$(jq '.healthy' /tmp/$ns-diagnosis.json)

  # Push to Pushgateway
  cat <<EOF | curl --data-binary @- $PUSHGATEWAY/metrics/job/kubectl_smart/namespace/$ns
# TYPE kubectl_smart_total_resources gauge
kubectl_smart_total_resources{namespace="$ns"} $TOTAL

# TYPE kubectl_smart_resources_with_issues gauge
kubectl_smart_resources_with_issues{namespace="$ns"} $WITH_ISSUES

# TYPE kubectl_smart_healthy_resources gauge
kubectl_smart_healthy_resources{namespace="$ns"} $HEALTHY
EOF

  # Capacity metrics
  kubectl-smart top $ns --horizon=48 -o json > /tmp/$ns-capacity.json

  CAPACITY_WARNINGS=$(jq '.capacity_warnings | length' /tmp/$ns-capacity.json)
  CERT_WARNINGS=$(jq '.certificate_warnings | length' /tmp/$ns-capacity.json)

  cat <<EOF | curl --data-binary @- $PUSHGATEWAY/metrics/job/kubectl_smart/namespace/$ns
# TYPE kubectl_smart_capacity_warnings gauge
kubectl_smart_capacity_warnings{namespace="$ns"} $CAPACITY_WARNINGS

# TYPE kubectl_smart_certificate_warnings gauge
kubectl_smart_certificate_warnings{namespace="$ns"} $CERT_WARNINGS
EOF
done
```

**Crontab** (run every 5 minutes):
```bash
*/5 * * * * /usr/local/bin/prometheus-exporter.sh
```

**Prometheus queries**:
```promql
# Total resources with issues
sum(kubectl_smart_resources_with_issues)

# Health rate by namespace
kubectl_smart_healthy_resources / kubectl_smart_total_resources

# Capacity warnings
sum(kubectl_smart_capacity_warnings)
```

---

### Grafana Dashboard

**Use case**: Visualize kubectl-smart metrics

**dashboard.json** (excerpt):
```json
{
  "dashboard": {
    "title": "kubectl-smart Health Overview",
    "panels": [
      {
        "title": "Resources with Issues",
        "targets": [
          {
            "expr": "sum by (namespace) (kubectl_smart_resources_with_issues)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Health Score",
        "targets": [
          {
            "expr": "kubectl_smart_healthy_resources / kubectl_smart_total_resources * 100"
          }
        ],
        "type": "gauge"
      },
      {
        "title": "Capacity Warnings",
        "targets": [
          {
            "expr": "sum(kubectl_smart_capacity_warnings)"
          }
        ],
        "type": "stat"
      }
    ]
  }
}
```

---

### Datadog

**Use case**: Send kubectl-smart events to Datadog

**datadog-integration.sh**:
```bash
#!/bin/bash
# Send kubectl-smart diagnosis to Datadog

DD_API_KEY="your-api-key"
NAMESPACE="production"

# Run diagnosis
kubectl-smart diag pod --all -n $NAMESPACE -o json > diagnosis.json

# Extract issues
jq -c '.issues[]' diagnosis.json | while read issue; do
  RESOURCE=$(echo $issue | jq -r '.resource')
  SEVERITY=$(echo $issue | jq -r '.severity')
  REASON=$(echo $issue | jq -r '.reason')
  MESSAGE=$(echo $issue | jq -r '.message')

  # Send event to Datadog
  curl -X POST "https://api.datadoghq.com/api/v1/events" \
    -H "DD-API-KEY: $DD_API_KEY" \
    -H "Content-Type: application/json" \
    -d @- <<EOF
{
  "title": "kubectl-smart: $SEVERITY issue in $RESOURCE",
  "text": "$REASON: $MESSAGE",
  "priority": "normal",
  "tags": [
    "namespace:$NAMESPACE",
    "severity:$SEVERITY",
    "tool:kubectl-smart"
  ],
  "alert_type": "$([ "$SEVERITY" == "critical" ] && echo "error" || echo "warning")"
}
EOF
done
```

---

## Alerting Integrations

### Slack

**Use case**: Send alerts for critical issues

**slack-alert.sh**:
```bash
#!/bin/bash
# Send kubectl-smart alerts to Slack

SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
NAMESPACE="production"

# Run diagnosis
kubectl-smart diag pod --all -n $NAMESPACE -o json > diagnosis.json

# Check for critical issues
CRITICAL=$(jq '.with_issues' diagnosis.json)

if [ "$CRITICAL" -gt 0 ]; then
  # Build Slack message
  MESSAGE=$(cat <<EOF
{
  "text": "🚨 kubectl-smart Alert: Critical Issues Detected",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "🚨 Kubernetes Health Alert"
      }
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "*Namespace:*\n$NAMESPACE"
        },
        {
          "type": "mrkdwn",
          "text": "*Resources with Issues:*\n$CRITICAL"
        }
      ]
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "\`\`\`$(kubectl-smart diag pod --all -n $NAMESPACE | head -20)\`\`\`"
      }
    }
  ]
}
EOF
)

  # Send to Slack
  curl -X POST -H 'Content-type: application/json' \
    --data "$MESSAGE" \
    $SLACK_WEBHOOK
fi
```

---

### PagerDuty

**Use case**: Create incidents for critical issues

**pagerduty-alert.sh**:
```bash
#!/bin/bash
# Create PagerDuty incidents for critical issues

PD_ROUTING_KEY="your-routing-key"
NAMESPACE="production"

# Run diagnosis
kubectl-smart diag pod --all -n $NAMESPACE -o json > diagnosis.json

# Check for critical issues
CRITICAL=$(jq -r '.issues[] | select(.severity == "critical")' diagnosis.json)

if [ -n "$CRITICAL" ]; then
  # Create PagerDuty event
  curl -X POST https://events.pagerduty.com/v2/enqueue \
    -H 'Content-Type: application/json' \
    -d @- <<EOF
{
  "routing_key": "$PD_ROUTING_KEY",
  "event_action": "trigger",
  "payload": {
    "summary": "kubectl-smart: Critical issues in $NAMESPACE",
    "severity": "critical",
    "source": "kubectl-smart",
    "custom_details": $(cat diagnosis.json)
  }
}
EOF
fi
```

---

### Email

**Use case**: Daily health reports

**email-report.sh**:
```bash
#!/bin/bash
# Send daily kubectl-smart report via email

EMAIL="team@example.com"
NAMESPACES="production staging"
REPORT_FILE="/tmp/kubectl-smart-report.txt"

echo "kubectl-smart Daily Health Report" > $REPORT_FILE
echo "Date: $(date)" >> $REPORT_FILE
echo "======================================" >> $REPORT_FILE

for ns in $NAMESPACES; do
  echo "" >> $REPORT_FILE
  echo "Namespace: $ns" >> $REPORT_FILE
  echo "---" >> $REPORT_FILE

  # Diagnosis
  kubectl-smart diag pod --all -n $ns >> $REPORT_FILE

  # Capacity forecast
  echo "" >> $REPORT_FILE
  kubectl-smart top $ns --horizon=168 >> $REPORT_FILE
done

# Send email
mail -s "kubectl-smart Daily Health Report" $EMAIL < $REPORT_FILE
```

**Crontab** (daily at 8 AM):
```bash
0 8 * * * /usr/local/bin/email-report.sh
```

---

## Automation Workflows

### Auto-Remediation (Future)

**Use case**: Automated fixes with approval workflow

**auto-remediate.sh**:
```bash
#!/bin/bash
# Auto-remediation with approval (FUTURE FEATURE)

NAMESPACE="production"
APPROVAL_WEBHOOK="https://approval-system.example.com/api/approve"

# Run diagnosis
kubectl-smart diag pod --all -n $NAMESPACE -o json > diagnosis.json

# Check for remediable issues
REMEDIATIONS=$(jq -r '.remediations[] | select(.automated == true)' diagnosis.json)

if [ -n "$REMEDIATIONS" ]; then
  # Request approval
  APPROVAL_ID=$(curl -X POST $APPROVAL_WEBHOOK \
    -H 'Content-Type: application/json' \
    -d "{\"namespace\": \"$NAMESPACE\", \"remediations\": $REMEDIATIONS}" | \
    jq -r '.approval_id')

  echo "Approval requested: $APPROVAL_ID"

  # Wait for approval (polling)
  while true; do
    STATUS=$(curl -s "$APPROVAL_WEBHOOK/$APPROVAL_ID" | jq -r '.status')

    if [ "$STATUS" == "approved" ]; then
      echo "Approval granted. Applying remediations..."
      # kubectl-smart diag pod --all -n $NAMESPACE --apply
      break
    elif [ "$STATUS" == "rejected" ]; then
      echo "Approval rejected. Skipping remediation."
      break
    fi

    sleep 60
  done
fi
```

---

### Scheduled Health Checks

**Use case**: Periodic cluster health monitoring

**health-check.sh**:
```bash
#!/bin/bash
# Comprehensive health check script

NAMESPACES="production staging development"
LOG_DIR="/var/log/kubectl-smart"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p $LOG_DIR

for ns in $NAMESPACES; do
  echo "Checking namespace: $ns"

  # Diagnosis
  kubectl-smart diag pod --all -n $ns -o json > \
    $LOG_DIR/$ns-diagnosis-$TIMESTAMP.json

  # Capacity forecast
  kubectl-smart top $ns --horizon=168 -o json > \
    $LOG_DIR/$ns-capacity-$TIMESTAMP.json

  # Generate summary
  CRITICAL=$(jq '.with_issues' $LOG_DIR/$ns-diagnosis-$TIMESTAMP.json)
  CAP_WARNINGS=$(jq '.capacity_warnings | length' $LOG_DIR/$ns-capacity-$TIMESTAMP.json)

  echo "  Critical issues: $CRITICAL"
  echo "  Capacity warnings: $CAP_WARNINGS"

  # Alert if thresholds exceeded
  if [ "$CRITICAL" -gt 5 ] || [ "$CAP_WARNINGS" -gt 3 ]; then
    # Send alert
    echo "Alert triggered for $ns"
    # send_alert "$ns has $CRITICAL critical issues"
  fi
done

# Cleanup old logs (keep 30 days)
find $LOG_DIR -name "*.json" -mtime +30 -delete
```

**Crontab** (every 6 hours):
```bash
0 */6 * * * /usr/local/bin/health-check.sh
```

---

## Custom Integrations

### REST API Wrapper

**Use case**: Expose kubectl-smart via REST API

**api-server.py**:
```python
#!/usr/bin/env python3
"""
Simple Flask API wrapper for kubectl-smart
"""
from flask import Flask, jsonify, request
import subprocess
import json

app = Flask(__name__)

@app.route('/api/v1/diag/<namespace>/<resource_type>/<name>', methods=['GET'])
def diagnose(namespace, resource_type, name):
    """Diagnose a resource"""
    try:
        result = subprocess.run(
            ['kubectl-smart', 'diag', resource_type, name, '-n', namespace, '-o', 'json'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0 or result.returncode == 1 or result.returncode == 2:
            return jsonify(json.loads(result.stdout))
        else:
            return jsonify({'error': result.stderr}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Diagnosis timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/top/<namespace>', methods=['GET'])
def capacity(namespace):
    """Get capacity forecast"""
    horizon = request.args.get('horizon', default=48, type=int)

    try:
        result = subprocess.run(
            ['kubectl-smart', 'top', namespace, '--horizon', str(horizon), '-o', 'json'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return jsonify(json.loads(result.stdout))
        else:
            return jsonify({'error': result.stderr}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

**Usage**:
```bash
# Start server
python api-server.py

# Query API
curl http://localhost:8080/api/v1/diag/production/pod/my-pod

curl http://localhost:8080/api/v1/top/production?horizon=168
```

---

### Kubernetes Operator

**Use case**: Automated diagnosis as CRD

**kubectl-smart-operator** (concept):
```yaml
apiVersion: kubectl-smart.io/v1
kind: DiagnosisSchedule
metadata:
  name: production-health-check
  namespace: production
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  resourceType: pod
  all: true
  alerting:
    slack:
      webhook: https://hooks.slack.com/...
    pagerduty:
      routingKey: ...
  thresholds:
    criticalIssues: 5
    capacityWarnings: 3
```

---

## Summary

kubectl-smart integrates seamlessly with:

- **CI/CD**: GitHub Actions, GitLab CI, Jenkins, ArgoCD
- **Monitoring**: Prometheus, Grafana, Datadog
- **Alerting**: Slack, PagerDuty, Email
- **Automation**: Custom scripts, cron jobs, operators

**Key integration patterns**:
1. **JSON output** for machine parsing
2. **Exit codes** for automation decisions
3. **Scheduled execution** for proactive monitoring
4. **Event-driven** for reactive diagnosis

See [Best Practices](BEST_PRACTICES.md) for recommended usage patterns.
