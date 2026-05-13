"""
JSON renderer for machine-readable output

Outputs diagnosis results in JSON format for automation,
scripting, and integration with other tools.

Usage:
    kubectl-smart diag pod my-pod -o json
    kubectl-smart diag pod my-pod -o json | jq '.root_cause'
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models import (
    DiagnosisResult,
    GraphResult,
    Issue,
    ResourceRecord,
    TopResult,
)


class JsonRenderer:
    """JSON renderer for kubectl-smart output

    Produces structured JSON output suitable for:
    - Automation and scripting
    - Integration with monitoring systems
    - CI/CD pipelines
    - Custom tooling
    """

    def __init__(self, pretty: bool = False):
        """Initialize JSON renderer

        Args:
            pretty: If True, output pretty-printed JSON
        """
        self.pretty = pretty
        self.indent = 2 if pretty else None

    def render_diagnosis(self, result: DiagnosisResult) -> str:
        """Render diagnosis result as JSON"""
        output = {
            "type": "diagnosis",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "context": result.subject.context,
            },
            "resource": self._serialize_resource(result.resource) if result.resource else None,
            "status": result.resource.status if result.resource else None,
            "root_cause": self._serialize_issue(result.root_cause) if result.root_cause else None,
            "contributing_factors": [
                self._serialize_issue(f) for f in result.contributing_factors
            ],
            "issues": [self._serialize_issue(i) for i in result.issues],
            "issue_summary": {
                "total": len(result.diagnostic_issues),
                "critical": len(result.critical_issues),
                "warning": len(result.warning_issues),
            },
            "suggested_actions": result.suggested_actions,
            "recent_events": [
                self._serialize_event(e) for e in result.recent_events
            ],
            "data_gaps": result.data_gaps,
            "analysis_duration_seconds": result.analysis_duration,
            "timestamp": result.timestamp.isoformat(),
            "exit_code": result.exit_code,
        }

        return json.dumps(output, indent=self.indent, default=str)

    def render_graph(self, result: GraphResult) -> str:
        """Render graph result as JSON"""
        output = {
            "type": "graph",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
            },
            "nodes": [self._serialize_resource(n) for n in result.nodes],
            "edges": result.edges,
            "statistics": {
                "total_nodes": len(result.nodes),
                "total_edges": len(result.edges),
                "upstream_count": result.upstream_count,
                "downstream_count": result.downstream_count,
            },
            "ascii_graph": result.ascii_graph,
            "data_gaps": result.data_gaps,
            "analysis_duration_seconds": result.analysis_duration,
            "timestamp": result.timestamp.isoformat(),
        }

        return json.dumps(output, indent=self.indent, default=str)

    def render_top(self, result: TopResult) -> str:
        """Render top result as JSON"""
        output = {
            "type": "top",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
            },
            "forecast_horizon_hours": result.forecast_horizon_hours,
            "capacity_warnings": result.capacity_warnings,
            "certificate_warnings": result.certificate_warnings,
            "warning_summary": {
                "capacity_issues": len(result.capacity_warnings),
                "certificate_issues": len(result.certificate_warnings),
                "total": len(result.capacity_warnings) + len(result.certificate_warnings),
            },
            "data_gaps": result.data_gaps,
            "analysis_duration_seconds": result.analysis_duration,
            "timestamp": result.timestamp.isoformat(),
        }

        return json.dumps(output, indent=self.indent, default=str)

    def render_batch(self, results: List[DiagnosisResult], batch_info: Dict[str, Any]) -> str:
        """Render batch diagnosis results as JSON"""
        failed = batch_info.get("failed", 0)
        exit_code = batch_info.get("exit_code")
        if exit_code is None:
            if failed or any(r.critical_issues for r in results):
                exit_code = 2
            elif any(r.warning_issues for r in results):
                exit_code = 1
            else:
                exit_code = 0
        critical_count = sum(len(r.critical_issues) for r in results)
        warning_count = sum(len(r.warning_issues) for r in results)

        output = {
            "type": "batch_diagnosis",
            "summary": {
                "total_resources": batch_info.get("total", len(results)),
                "successful": batch_info.get("successful", len(results)),
                "failed": failed,
                "critical": critical_count,
                "warning": warning_count,
                "duration_seconds": batch_info.get("duration", 0),
                "data_gaps": sum(len(r.data_gaps) for r in results),
                "max_concurrent": batch_info.get("max_concurrent"),
                "exit_code": exit_code,
            },
            "results": [
                {
                    "subject": {
                        "kind": r.subject.kind.value,
                        "name": r.subject.name,
                        "namespace": r.subject.namespace,
                    },
                    "status": r.resource.status if r.resource else None,
                    "root_cause": self._serialize_issue(r.root_cause) if r.root_cause else None,
                    "issue_count": len(r.diagnostic_issues),
                    "critical_count": len(r.critical_issues),
                    "warning_count": len(r.warning_issues),
                    "suggested_actions": r.suggested_actions,
                    "data_gaps": r.data_gaps,
                    "data_gap_count": len(r.data_gaps),
                    "exit_code": r.exit_code,
                }
                for r in results
            ],
            "errors": batch_info.get("errors", []),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return json.dumps(output, indent=self.indent, default=str)

    def render_error(
        self,
        error_msg: str,
        details: Optional[str] = None,
        exit_code: int = 2,
    ) -> str:
        """Render error as JSON"""
        output = {
            "type": "error",
            "error": error_msg,
            "details": details,
            "exit_code": exit_code,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return json.dumps(output, indent=self.indent, default=str)

    def _serialize_resource(self, resource: ResourceRecord) -> Dict[str, Any]:
        """Serialize ResourceRecord to dict"""
        return {
            "kind": resource.kind.value,
            "name": resource.name,
            "namespace": resource.namespace,
            "uid": resource.uid,
            "status": resource.status,
            "creation_timestamp": resource.creation_timestamp.isoformat() if resource.creation_timestamp else None,
            "labels": resource.labels,
            "annotations": {k: v for k, v in resource.annotations.items() if not k.startswith("kubectl.kubernetes.io")},
        }

    def _serialize_issue(self, issue: Issue) -> Dict[str, Any]:
        """Serialize Issue to dict"""
        return {
            "title": issue.title,
            "description": issue.description,
            "severity": issue.severity.value,
            "score": issue.score,
            "reason": issue.reason,
            "message": issue.message,
            "critical_path": issue.critical_path,
            "timestamp": issue.timestamp.isoformat() if issue.timestamp else None,
            "suggested_actions": issue.suggested_actions,
            "evidence": issue.evidence,
        }

    def _serialize_event(self, event: ResourceRecord) -> Dict[str, Any]:
        """Serialize event ResourceRecord to dict"""
        return {
            "type": event.properties.get("type", "Normal"),
            "reason": event.properties.get("reason", "Unknown"),
            "message": event.properties.get("message", ""),
            "first_timestamp": event.properties.get("firstTimestamp"),
            "last_timestamp": event.properties.get("lastTimestamp"),
            "count": event.properties.get("count", 1),
        }
