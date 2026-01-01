"""
Signal scorer for issue prioritization

This module implements the heuristic scoring system as specified in the technical
requirements, with configurable weights and deterministic output.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import structlog

# Handle tomli import for Python < 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from ..graph.builder import GraphBuilder
from ..models import Issue, IssueSeverity, ResourceKind, ResourceRecord

logger = structlog.get_logger(__name__)


class ScoringEngine:
    """Heuristic scoring engine for issue prioritization
    
    As specified in the technical requirements:
    - Heuristic matrix defined in weights.toml
    - Severity thresholds: Critical ≥90, Warning ≥50, Info <50
    - score_issue(issue: Issue) -> int must be pure
    """
    
    def __init__(self, weights_file: Optional[str] = None):
        self.weights = self._load_weights(weights_file)
        self.base_scores = self.weights.get('base_scores', {})
        self.multipliers = self.weights.get('multipliers', {})
        self.keywords = self.weights.get('keywords', {})
        
    def _load_weights(self, weights_file: Optional[str] = None) -> Dict:
        """Load scoring weights from TOML file"""
        package_dir = Path(__file__).parent.parent.resolve()
        if not weights_file:
            # Look for weights.toml in package directory
            weights_file = package_dir / "weights.toml"
        
        weights_path = Path(weights_file).resolve()
        # Prevent path traversal / arbitrary file reads
        try:
            weights_path.relative_to(package_dir)
        except Exception:
            logger.warning("Weights file rejected: outside package directory", path=weights_path)
            return self._get_default_weights()
        
        if not weights_path.exists():
            logger.warning("Weights file not found, using defaults", path=weights_path)
            return self._get_default_weights()
        
        if tomllib is None:
            logger.warning("tomli not available, using default weights")
            return self._get_default_weights()
        
        try:
            with open(weights_path, 'rb') as f:
                weights = tomllib.load(f)
            logger.debug("Loaded weights from file", path=weights_path)
            return weights
        except Exception as e:
            logger.warning("Failed to load weights file, using defaults", 
                          error=str(e), path=weights_path)
            return self._get_default_weights()
    
    def _get_default_weights(self) -> Dict:
        """Get default scoring weights when weights.toml is not available"""
        return {
            'base_scores': {
                # Event reasons
                'Failed': 50.0,
                'FailedMount': 80.0,
                'FailedScheduling': 85.0,
                'ImagePullBackOff': 75.0,
                'ErrImagePull': 75.0,
                'Unhealthy': 70.0,
                'NetworkNotReady': 60.0,
                'BackOff': 30.0,
                'Pulling': 10.0,
                'Created': 5.0,
                'Started': 5.0,
                'Killing': 40.0,
                'Preempting': 45.0,
                
                # Resource statuses
                'status_Failed': 90.0,
                'status_Pending': 40.0,
                'status_Unknown': 70.0,
                'status_NotReady': 80.0,
                'status_Unavailable': 75.0,
                'status_Running': 0.0,
                'status_Active': 0.0,
                'status_Ready': 0.0,
                'status_Available': 0.0,
                'status_Bound': 0.0,
            },
            
            'multipliers': {
                # Resource type criticality
                'resource_type': {
                    'Node': 2.0,
                    'PersistentVolume': 1.8,
                    'PersistentVolumeClaim': 1.6,
                    'Pod': 1.2,
                    'Deployment': 1.4,
                    'StatefulSet': 1.5,
                    'DaemonSet': 1.4,
                    'Service': 1.3,
                    'ConfigMap': 1.1,
                    'Secret': 1.2,
                },
                
                # Event type severity
                'event_type': {
                    'Warning': 2.0,
                    'Normal': 1.0,
                },
                
                # Critical path bonus
                'critical_path': 1.5,
                
                # Age factors (older events are less critical)
                'age_hours': {
                    '0-1': 1.0,      # Very recent
                    '1-6': 0.9,      # Recent
                    '6-24': 0.7,     # Several hours old
                    '24-168': 0.5,   # Days old
                    '168+': 0.3,     # Week+ old
                },
            },
            
            'keywords': {
                # Critical keywords in messages
                'critical': {
                    'patterns': [
                        'failed', 'error', 'timeout', 'unable', 'cannot', 'denied',
                        'not found', 'no space', 'disk full', 'out of memory',
                        'connection refused', 'network unreachable', 'permission denied'
                    ],
                    'score': 15.0
                },
                
                'warning': {
                    'patterns': [
                        'warning', 'deprecated', 'retry', 'backoff', 'slow',
                        'degraded', 'limited', 'throttled'
                    ],
                    'score': 8.0
                },
                
                'resource_specific': {
                    'patterns': [
                        'insufficient', 'exceeded', 'quota', 'limit', 'capacity',
                        'evicted', 'preempted', 'oomkilled'
                    ],
                    'score': 12.0
                }
            }
        }
    
    def score_issue(self, issue: Issue) -> float:
        """Score an issue based on heuristic weights (pure function)
        
        Args:
            issue: Issue to score
            
        Returns:
            Score from 0-100
        """
        score = 0.0
        
        # Base score from reason
        reason_score = self.base_scores.get(issue.reason, 20.0)
        score += reason_score
        
        # Keyword scoring from message
        message_lower = issue.message.lower()
        for category, config in self.keywords.items():
            for pattern in config['patterns']:
                if pattern in message_lower:
                    score += config['score']
                    break  # Only count once per category
        
        # Critical path multiplier
        if issue.critical_path:
            score *= self.multipliers.get('critical_path', 1.5)
        
        # Timestamp-based aging (if available)
        if issue.timestamp:
            age_multiplier = self._get_age_multiplier(issue.timestamp)
            score *= age_multiplier
        
        # Clamp to 0-100 range
        return max(0.0, min(100.0, score))
    
    def score_resource_status(self, resource: ResourceRecord) -> float:
        """Score a resource based on its status"""
        if not resource.status:
            return 0.0
        
        status_key = f"status_{resource.status}"
        return self.base_scores.get(status_key, 0.0)
    
    def create_issue_from_event(
        self, 
        event_resource: ResourceRecord, 
        target_resource: ResourceRecord,
        is_critical_path: bool = False
    ) -> Issue:
        """Create an Issue from an event ResourceRecord"""
        properties = event_resource.properties
        
        reason = properties.get('reason', 'Unknown')
        message = properties.get('message', '')
        event_type = properties.get('type', 'Normal')
        
        # Create base issue
        issue = Issue(
            resource_uid=target_resource.uid,
            title=f"{reason}: {target_resource.name}",
            description=message,
            reason=reason,
            message=message,
            timestamp=event_resource.creation_timestamp,
            critical_path=is_critical_path,
            severity=IssueSeverity.INFO,  # Will be updated by scoring
            score=0.0,  # Will be calculated
        )
        
        # Calculate score
        base_score = self.score_issue(issue)
        
        # Apply resource type multiplier
        resource_multiplier = self.multipliers.get('resource_type', {}).get(
            target_resource.kind.value, 1.0
        )
        base_score *= resource_multiplier
        
        # Apply event type multiplier
        event_multiplier = self.multipliers.get('event_type', {}).get(
            event_type, 1.0
        )
        base_score *= event_multiplier
        
        # Set final score and severity
        final_score = max(0.0, min(100.0, base_score))
        issue.score = final_score
        
        if final_score >= 90:
            issue.severity = IssueSeverity.CRITICAL
        elif final_score >= 50:
            issue.severity = IssueSeverity.WARNING
        else:
            issue.severity = IssueSeverity.INFO
        
        return issue
    
    def create_issue_from_resource_status(
        self, 
        resource: ResourceRecord,
        is_critical_path: bool = False
    ) -> Optional[Issue]:
        """Create an Issue from a resource's unhealthy status"""
        status_score = self.score_resource_status(resource)
        
        # Only create issues for problematic statuses
        if status_score < 30.0:
            return None
        
        issue = Issue(
            resource_uid=resource.uid,
            title=f"Resource Status: {resource.status}",
            description=f"{resource.kind.value} {resource.name} is in {resource.status} state",
            reason=f"Status{resource.status}",
            message=f"Resource is in unhealthy state: {resource.status}",
            timestamp=resource.creation_timestamp,
            critical_path=is_critical_path,
            severity=IssueSeverity.INFO,
            score=status_score,
        )
        
        # Set severity based on score
        if status_score >= 90:
            issue.severity = IssueSeverity.CRITICAL
        elif status_score >= 50:
            issue.severity = IssueSeverity.WARNING
        else:
            issue.severity = IssueSeverity.INFO
        
        return issue
    
    def create_issue_from_logs(
        self,
        log_record: ResourceRecord,
        target_resource: ResourceRecord
    ) -> Optional[Issue]:
        """Create an Issue from log analysis"""
        errors = log_record.properties.get('errors', [])
        if not errors:
            return None
            
        # Create a summary message
        error_count = len(errors)
        last_error = errors[-1]
        if len(last_error) > 80:
            last_error = last_error[:77] + "..."
            
        return Issue(
            resource_uid=target_resource.uid,
            title=f"Log Errors: Found {error_count} error(s)",
            description=f"Log analysis detected {error_count} unique error patterns. Recent: {last_error}",
            reason="LogFailure",
            message="\n".join([f"- {e}" for e in errors]),
            timestamp=datetime.utcnow(),
            critical_path=True, # Logs are usually critical if we are diagnosing
            severity=IssueSeverity.WARNING, # Will be rescored
            score=85.0, # High base score for log errors
            suggested_actions=["Review full logs for context", "Check application configuration"]
        )

    def _get_age_multiplier(self, timestamp) -> float:
        """Get age-based score multiplier"""
        if not timestamp:
            return 1.0
        
        try:
            from datetime import datetime, timezone
            
            if isinstance(timestamp, str):
                # Parse timestamp if it's a string
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            
            now = datetime.now(timezone.utc)
            age_hours = (now - timestamp).total_seconds() / 3600
            
            age_multipliers = self.multipliers.get('age_hours', {})
            
            if age_hours < 1:
                return age_multipliers.get('0-1', 1.0)
            elif age_hours < 6:
                return age_multipliers.get('1-6', 0.9)
            elif age_hours < 24:
                return age_multipliers.get('6-24', 0.7)
            elif age_hours < 168:  # 1 week
                return age_multipliers.get('24-168', 0.5)
            else:
                return age_multipliers.get('168+', 0.3)
                
        except Exception as e:
            logger.debug("Failed to calculate age multiplier", error=str(e))
            return 1.0
    
    def analyze_issues(
        self, 
        resources: List[ResourceRecord], 
        events: List[ResourceRecord],
        graph: Optional[GraphBuilder] = None
    ) -> List[Issue]:
        """Analyze resources and events to create scored issues
        
        Args:
            resources: List of all resources
            events: List of event resources
            graph: Optional graph for critical path analysis
            
        Returns:
            List of scored issues sorted by severity and score
        """
        issues = []
        resource_map = {r.uid: r for r in resources}
        
        # Identify the primary target resource (heuristic: usually the one being diagnosed)
        # In a list of resources, we often want to attach log issues to the "subject".
        # For now, we'll attach log issues to the first Pod found, or if none, leave generic.
        # A better way is if the caller passed the target, but we are inside the engine.
        target_pod = next((r for r in resources if r.kind == ResourceKind.POD), None)
        
        # Process LogAnalysis records
        for resource in resources:
            if resource.kind == ResourceKind.LOGANALYSIS and target_pod:
                log_issue = self.create_issue_from_logs(resource, target_pod)
                if log_issue:
                    issues.append(log_issue)

        # Process events
        for event in events:
            if event.kind != ResourceKind.EVENT:
                continue
            
            properties = event.properties
            involved_object = properties.get('involvedObject', {})
            
            # Find the target resource
            target_resource = None
            involved_name = involved_object.get('name')
            involved_kind = involved_object.get('kind')
            involved_namespace = involved_object.get('namespace', event.namespace)
            
            # Try to find by UID first
            involved_uid = involved_object.get('uid')
            if involved_uid and involved_uid in resource_map:
                target_resource = resource_map[involved_uid]
            else:
                # Fallback: find by name, kind, namespace
                for resource in resources:
                    if (resource.name == involved_name and 
                        resource.kind.value == involved_kind and
                        resource.namespace == involved_namespace):
                        target_resource = resource
                        break
            
            if not target_resource:
                logger.debug("Could not find target resource for event", 
                           event_name=event.name, involved_object=involved_object)
                continue
            
            # Check if this is on a critical path
            is_critical_path = False
            if graph:
                # Simple critical path detection: check if resource has failed dependencies
                deps = graph.get_dependencies(target_resource.uid, "upstream")
                for dep_uid in deps:
                    dep_resource = resource_map.get(dep_uid)
                    if dep_resource and dep_resource.status in ['Failed', 'NotReady', 'Unavailable']:
                        is_critical_path = True
                        break
            
            # Create issue from event
            issue = self.create_issue_from_event(event, target_resource, is_critical_path)
            issues.append(issue)
        
        # Process resource statuses
        for resource in resources:
            if resource.kind == ResourceKind.EVENT:
                continue
            
            # Check if this resource is on a critical path
            is_critical_path = False
            if graph:
                deps = graph.get_dependencies(resource.uid, "downstream")
                # If this resource has many dependents, it's more critical
                is_critical_path = len(deps) > 2
            
            status_issue = self.create_issue_from_resource_status(resource, is_critical_path)
            if status_issue:
                issues.append(status_issue)
        
        # Sort by severity and score
        issues.sort(key=lambda i: (i.severity.value, -i.score))
        
        return issues
    
    def get_root_cause(self, issues: List[Issue]) -> Optional[Issue]:
        """Identify the root cause from a list of issues
        
        Args:
            issues: List of issues sorted by priority
            
        Returns:
            The issue most likely to be the root cause
        """
        if not issues:
            return None
        
        # Filter to critical issues first
        critical_issues = [i for i in issues if i.severity == IssueSeverity.CRITICAL]
        
        if critical_issues:
            # Return highest scoring critical issue on critical path
            critical_path_issues = [i for i in critical_issues if i.critical_path]
            if critical_path_issues:
                return critical_path_issues[0]
            else:
                return critical_issues[0]
        
        # Fallback to highest scoring issue
        return issues[0] if issues else None
    
    def get_contributing_factors(self, issues: List[Issue], root_cause: Optional[Issue] = None) -> List[Issue]:
        """Get contributing factors (top 2 issues excluding root cause)
        
        Args:
            issues: List of all issues
            root_cause: The identified root cause
            
        Returns:
            List of up to 2 contributing factor issues
        """
        filtered_issues = issues.copy()
        
        # Remove root cause from consideration
        if root_cause:
            filtered_issues = [i for i in filtered_issues if i.resource_uid != root_cause.resource_uid or i.reason != root_cause.reason]
        
        # Return top 2 issues with score >= 50
        contributing = [i for i in filtered_issues if i.score >= 50.0]
        return contributing[:2]
