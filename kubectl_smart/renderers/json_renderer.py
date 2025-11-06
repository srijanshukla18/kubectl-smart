"""
JSON output renderer for automation and scripting

This renderer provides machine-readable output that can be processed
by scripts, stored in databases, or piped to other tools.
"""

import json
from datetime import datetime
from typing import Any, Dict, List

from ..models import DiagnosisResult, GraphResult, TopResult, Issue


class JSONRenderer:
    """Renders analysis results as JSON for automation"""

    def render_diagnosis(self, result: DiagnosisResult) -> str:
        """Render diagnosis result as JSON

        Args:
            result: Diagnosis result to render

        Returns:
            JSON string
        """
        output = {
            "command": "diag",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "context": result.subject.context,
            },
            "resource": self._serialize_resource(result.resource) if result.resource else None,
            "summary": {
                "total_issues": len(result.issues),
                "critical_issues": len(result.critical_issues),
                "warning_issues": len(result.warning_issues),
                "has_root_cause": result.root_cause is not None,
            },
            "root_cause": self._serialize_issue(result.root_cause) if result.root_cause else None,
            "contributing_factors": [
                self._serialize_issue(issue) for issue in result.contributing_factors
            ],
            "suggested_actions": result.suggested_actions,
            "all_issues": [self._serialize_issue(issue) for issue in result.issues],
            "analysis_duration_seconds": result.analysis_duration,
            "exit_code": 2 if (result.critical_issues or result.warning_issues) else 0,
        }

        return json.dumps(output, indent=2, default=str)

    def render_graph(self, result: GraphResult) -> str:
        """Render graph result as JSON

        Args:
            result: Graph result to render

        Returns:
            JSON string
        """
        output = {
            "command": "graph",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "context": result.subject.context,
            },
            "summary": {
                "total_nodes": len(result.nodes),
                "total_edges": len(result.edges),
                "upstream_count": result.upstream_count,
                "downstream_count": result.downstream_count,
            },
            "nodes": [self._serialize_resource(node) for node in result.nodes],
            "edges": result.edges,
            "ascii_graph": result.ascii_graph,
            "analysis_duration_seconds": result.analysis_duration,
        }

        return json.dumps(output, indent=2, default=str)

    def render_top(self, result: TopResult) -> str:
        """Render top result as JSON

        Args:
            result: Top result to render

        Returns:
            JSON string
        """
        output = {
            "command": "top",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "subject": {
                "kind": result.subject.kind.value,
                "name": result.subject.name,
                "namespace": result.subject.namespace,
                "context": result.subject.context,
            },
            "forecast_horizon_hours": result.forecast_horizon_hours,
            "summary": {
                "capacity_warnings_count": len(result.capacity_warnings),
                "certificate_warnings_count": len(result.certificate_warnings),
                "total_warnings": len(result.capacity_warnings) + len(result.certificate_warnings),
            },
            "capacity_warnings": result.capacity_warnings,
            "certificate_warnings": result.certificate_warnings,
            "analysis_duration_seconds": result.analysis_duration,
        }

        return json.dumps(output, indent=2, default=str)

    def render_error(self, error_message: str) -> str:
        """Render error as JSON

        Args:
            error_message: Error message

        Returns:
            JSON string
        """
        output = {
            "error": True,
            "message": error_message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        return json.dumps(output, indent=2)

    def _serialize_issue(self, issue: Issue) -> Dict[str, Any]:
        """Serialize an Issue to JSON-compatible dict

        Args:
            issue: Issue to serialize

        Returns:
            Dictionary representation
        """
        return {
            "title": issue.title,
            "severity": issue.severity.value,
            "score": issue.score,
            "reason": issue.reason,
            "description": issue.description,
            "message": issue.message,
            "timestamp": issue.timestamp.isoformat() + "Z" if issue.timestamp else None,
            "critical_path": issue.critical_path,
            "suggested_actions": issue.suggested_actions,
            "metadata": issue.metadata,
        }

    def _serialize_resource(self, resource) -> Dict[str, Any]:
        """Serialize a ResourceRecord to JSON-compatible dict

        Args:
            resource: Resource to serialize

        Returns:
            Dictionary representation
        """
        if not resource:
            return None

        return {
            "kind": resource.kind.value,
            "name": resource.name,
            "namespace": resource.namespace,
            "uid": resource.uid,
            "status": resource.status,
            "labels": resource.labels,
            "annotations": resource.annotations,
            "creation_timestamp": resource.creation_timestamp.isoformat() + "Z" if resource.creation_timestamp else None,
            "full_name": resource.full_name,
            "properties": resource.properties,
        }
