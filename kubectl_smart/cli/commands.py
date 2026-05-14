"""
Command implementations for the three core commands

This module implements the business logic for diag, graph, and top commands
as specified in the technical requirements.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog

from ..batch import kubectl_resource_type
from ..collectors.base import registry as collector_registry
from ..forecast.predictor import ForecastingEngine
from ..graph.builder import GraphBuilder
from ..models import (
    AnalysisConfig,
    DiagnosisResult,
    GraphResult,
    Issue,
    IssueSeverity,
    ResourceKind,
    ResourceRecord,
    SubjectCtx,
    TopResult,
)
from ..parsers.base import registry as parser_registry
from ..renderers.terminal import TerminalRenderer
from ..scoring.engine import ScoringEngine

logger = structlog.get_logger(__name__)


@dataclass
class CommandResult:
    """Result of command execution"""
    output: str
    exit_code: int = 0
    analysis_duration: float = 0.0


class BaseCommand:
    """Base class for all commands"""
    
    def __init__(self, config: Optional[AnalysisConfig] = None):
        self.config = config or AnalysisConfig()
        self.graph_builder = GraphBuilder()
        self.scoring_engine = ScoringEngine()
        self.forecasting_engine = ForecastingEngine(
            forecast_horizon_hours=self.config.forecast_horizon_hours
        )
        self.data_gaps: List[str] = []

    def _reset_data_gaps(self) -> None:
        self.data_gaps = []

    def _add_data_gap(self, message: str) -> None:
        if message and message not in self.data_gaps:
            self.data_gaps.append(message)

    def _record_blob_gap(self, blob) -> None:
        metadata = getattr(blob, "metadata", {}) or {}
        if not metadata.get("data_gap"):
            return

        operation = metadata.get("operation") or metadata.get("collector") or "collector"
        resource_type = metadata.get("resource_type")
        category = metadata.get("category")
        error = (metadata.get("error") or "").splitlines()[0]
        suggested_action = metadata.get("suggested_action")

        label = f"{operation}"
        if resource_type:
            label += f" {resource_type}"
        if category:
            label += f" unavailable ({category})"
        else:
            label += " unavailable"
        if error:
            label += f": {error}"
        if suggested_action:
            label += f" | Check: {suggested_action}"

        self._add_data_gap(label)

    def _record_exception_gap(self, collector_name: str, error: Exception) -> None:
        self._add_data_gap(f"{collector_name} failed: {str(error).splitlines()[0]}")

    def _record_collector_creation_gap(
        self,
        collector_name: str,
        error: Exception,
        resource_type: Optional[str] = None,
    ) -> None:
        label = collector_name
        if resource_type:
            label += f" {resource_type}"
        self._add_data_gap(
            f"{label} collector unavailable: {str(error).splitlines()[0]}"
        )

    def _create_collector(self, name: str, **kwargs):
        """Create a collector using the configured per-kubectl timeout."""
        kwargs.setdefault("timeout_seconds", self.config.collector_timeout)
        return collector_registry.create(name, **kwargs)
    
    async def _collect_data(self, subject: SubjectCtx, collector_names: List[str]) -> List[ResourceRecord]:
        """Collect data using multiple collectors concurrently"""
        start_time = time.time()
        
        # Create collectors
        collectors = []
        for name in collector_names:
            try:
                if name == 'describe':
                    resource_type = subject.kind.value.lower()
                    collector = self._create_collector(name, resource_type=resource_type)
                elif name == 'get':
                    resource_type = subject.kind.value.lower()
                    collector = self._create_collector(name, resource_type=resource_type)
                else:
                    resource_type = None
                    collector = self._create_collector(name)
                collectors.append(collector)
            except Exception as e:
                logger.warning("Failed to create collector", name=name, error=str(e))
                self._record_collector_creation_gap(name, e, resource_type)
        
        # Collect data concurrently
        tasks = [collector.collect(subject) for collector in collectors]
        blobs = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Parse collected data
        all_resources = []
        for i, blob in enumerate(blobs):
            if isinstance(blob, Exception):
                logger.warning("Collector failed", collector=collectors[i].name, error=str(blob))
                self._record_exception_gap(collectors[i].name, blob)
                continue

            self._record_blob_gap(blob)
            
            try:
                resources = parser_registry.parse(blob)
                all_resources.extend(resources)
            except Exception as e:
                logger.warning("Failed to parse data", collector=collectors[i].name, error=str(e))
                self._add_data_gap(f"{collectors[i].name} output could not be parsed: {str(e).splitlines()[0]}")
        
        collection_time = time.time() - start_time
        logger.debug("Data collection completed", 
                    resources=len(all_resources), 
                    duration=collection_time)
        
        return all_resources
    
    


class DiagCommand(BaseCommand):
    """Implementation of the diag command
    
    As specified in the technical requirements:
    - Collectors invoked: Get, Describe, Events, Logs
    - Output sections: Header, Root Cause, Contributing Factors, Suggested Action
    - Exit codes: 0 = no issues ≥50; 1 = warnings; 2 = critical
    """

    async def _collect_diag_data(self, subject: SubjectCtx) -> List[ResourceRecord]:
        """Collect diagnosis data plus targeted related resources for evidence."""
        collector_names = ['get', 'describe', 'events', 'logs']
        all_resources = await self._collect_data(subject, collector_names)

        if self._is_controller_kind(subject.kind):
            all_resources.extend(await self._collect_controller_context(subject))
            all_resources = self._dedupe_resources(all_resources)
            target_resource = self._find_subject_resource(subject, all_resources)
            if target_resource:
                child_pods = [
                    resource for resource in self._controller_child_resources(
                        target_resource,
                        all_resources,
                    )
                    if resource.kind == ResourceKind.POD
                ]
                all_resources.extend(
                    await self._collect_child_pod_logs(subject, child_pods)
                )
                all_resources = self._dedupe_resources(all_resources)

        if subject.kind == ResourceKind.SERVICE:
            all_resources.extend(await self._collect_service_context(subject))

        return all_resources

    async def _collect_service_context(self, subject: SubjectCtx) -> List[ResourceRecord]:
        """Collect endpoint and namespace pod context for Service diagnosis."""
        collector_specs = [
            ("endpoints", subject),
            ("pods", subject.model_copy(update={"name": ""})),
        ]
        collectors = []

        for resource_type, collector_subject in collector_specs:
            try:
                collector = self._create_collector("get", resource_type=resource_type)
                collectors.append((resource_type, collector, collector_subject))
            except Exception as e:
                logger.warning(
                    "Failed to create service context collector",
                    resource_type=resource_type,
                    error=str(e),
                )
                self._record_collector_creation_gap("get", e, resource_type)

        if not collectors:
            return []

        blobs = await asyncio.gather(
            *[
                collector.collect(collector_subject)
                for _, collector, collector_subject in collectors
            ],
            return_exceptions=True,
        )

        resources: List[ResourceRecord] = []
        for (resource_type, collector, _), blob in zip(collectors, blobs):
            collector_label = f"get {resource_type}"
            if isinstance(blob, Exception):
                logger.warning(
                    "Service context collector failed",
                    collector=collector.name,
                    resource_type=resource_type,
                    error=str(blob),
                )
                self._record_exception_gap(collector_label, blob)
                continue

            self._record_blob_gap(blob)
            try:
                resources.extend(parser_registry.parse(blob))
            except Exception as e:
                logger.warning(
                    "Failed to parse service context",
                    collector=collector.name,
                    resource_type=resource_type,
                    error=str(e),
                )
                self._add_data_gap(
                    f"{collector_label} output could not be parsed: {str(e).splitlines()[0]}"
                )

        return resources

    def _is_controller_kind(self, kind: ResourceKind) -> bool:
        return kind in {
            ResourceKind.DEPLOYMENT,
            ResourceKind.REPLICASET,
            ResourceKind.STATEFULSET,
            ResourceKind.DAEMONSET,
            ResourceKind.JOB,
        }

    def _dedupe_resources(self, resources: List[ResourceRecord]) -> List[ResourceRecord]:
        deduped: List[ResourceRecord] = []
        seen: set[tuple[str, str, str, str]] = set()

        for resource in resources:
            key = (
                resource.kind.value,
                resource.namespace or "",
                resource.name,
                resource.uid,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(resource)

        return deduped

    def _find_subject_resource(
        self,
        subject: SubjectCtx,
        all_resources: List[ResourceRecord],
    ) -> Optional[ResourceRecord]:
        for resource in all_resources:
            if (
                resource.kind == subject.kind
                and resource.name == subject.name
                and resource.namespace == subject.namespace
            ):
                return resource
        return None

    async def _collect_controller_context(
        self,
        subject: SubjectCtx,
    ) -> List[ResourceRecord]:
        resource_types = ["pods"]
        if subject.kind == ResourceKind.DEPLOYMENT:
            resource_types.append("replicasets")

        collectors = []
        list_subject = subject.model_copy(update={"name": ""})

        for resource_type in resource_types:
            try:
                collector = self._create_collector("get", resource_type=resource_type)
                collectors.append((f"get {resource_type}", collector, list_subject))
            except Exception as e:
                logger.warning("Failed to create controller context collector", resource_type=resource_type, error=str(e))
                self._record_collector_creation_gap("get", e, resource_type)

        try:
            collector = self._create_collector("events")
            collectors.append(("events events", collector, list_subject))
        except Exception as e:
            logger.warning("Failed to create controller event collector", error=str(e))
            self._record_collector_creation_gap("events", e, "events")

        if not collectors:
            return []

        blobs = await asyncio.gather(
            *[
                collector.collect(collector_subject)
                for _, collector, collector_subject in collectors
            ],
            return_exceptions=True,
        )

        resources = []
        for (collector_label, collector, _), blob in zip(collectors, blobs):
            if isinstance(blob, Exception):
                logger.warning(
                    "Controller context collector failed",
                    collector=collector.name,
                    error=str(blob),
                )
                self._record_exception_gap(collector_label, blob)
                continue

            self._record_blob_gap(blob)
            try:
                resources.extend(parser_registry.parse(blob))
            except Exception as e:
                logger.warning(
                    "Failed to parse controller context",
                    collector=collector.name,
                    error=str(e),
                )
                self._add_data_gap(
                    f"{collector_label} output could not be parsed: {str(e).splitlines()[0]}"
                )

        return resources

    async def _collect_child_pod_logs(
        self,
        subject: SubjectCtx,
        child_pods: List[ResourceRecord],
    ) -> List[ResourceRecord]:
        if not child_pods:
            return []

        log_targets = [
            pod for pod in child_pods
            if self._pod_needs_child_log_collection(pod)
        ]
        if not log_targets:
            return []
        log_targets = log_targets[:3]

        collectors = []
        for pod in log_targets:
            try:
                collector = self._create_collector("logs")
                collectors.append((
                    "logs pods",
                    collector,
                    SubjectCtx(
                        kind=ResourceKind.POD,
                        name=pod.name,
                        namespace=pod.namespace,
                        context=subject.context,
                    ),
                ))
            except Exception as e:
                logger.warning("Failed to create child pod log collector", pod=pod.name, error=str(e))
                self._record_collector_creation_gap("logs", e, "pods")

        if not collectors:
            return []

        blobs = await asyncio.gather(
            *[
                collector.collect(collector_subject)
                for _, collector, collector_subject in collectors
            ],
            return_exceptions=True,
        )

        resources = []
        for (collector_label, collector, _), blob in zip(collectors, blobs):
            if isinstance(blob, Exception):
                logger.warning(
                    "Child pod log collector failed",
                    collector=collector.name,
                    error=str(blob),
                )
                self._record_exception_gap(collector_label, blob)
                continue

            self._record_blob_gap(blob)
            try:
                resources.extend(parser_registry.parse(blob))
            except Exception as e:
                logger.warning(
                    "Failed to parse child pod logs",
                    collector=collector.name,
                    error=str(e),
                )
                self._add_data_gap(
                    f"{collector_label} output could not be parsed: {str(e).splitlines()[0]}"
                )

        return resources

    def _pod_needs_child_log_collection(self, pod: ResourceRecord) -> bool:
        unhealthy_statuses = {
            "Failed",
            "Pending",
            "Unknown",
            "Error",
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "ErrImagePull",
            "CreateContainerConfigError",
        }
        if pod.status in unhealthy_statuses:
            return True

        status = pod.properties.get("status", {})
        if not isinstance(status, dict):
            return False

        for condition in status.get("conditions", []) or []:
            if (
                condition.get("type") in {"Ready", "ContainersReady"}
                and condition.get("status") == "False"
            ):
                return True

        return False

    def _owner_refs(self, resource: ResourceRecord) -> List[Dict[str, str]]:
        owner_refs = resource.get_property("metadata.ownerReferences", [])
        return owner_refs if isinstance(owner_refs, list) else []

    def _is_owned_by(self, resource: ResourceRecord, owner: ResourceRecord) -> bool:
        return any(
            owner_ref.get("kind") == owner.kind.value
            and owner_ref.get("uid") == owner.uid
            for owner_ref in self._owner_refs(resource)
        )

    def _match_label_selector(self, resource: ResourceRecord) -> Dict[str, str]:
        selector = resource.get_property("spec.selector", {}) or {}
        if not isinstance(selector, dict):
            return {}
        match_labels = selector.get("matchLabels")
        if isinstance(match_labels, dict):
            return match_labels
        return selector

    def _controller_child_resources(
        self,
        target_resource: ResourceRecord,
        all_resources: List[ResourceRecord],
    ) -> List[ResourceRecord]:
        if not self._is_controller_kind(target_resource.kind):
            return []

        namespace_resources = [
            resource for resource in all_resources
            if resource.namespace == target_resource.namespace
        ]
        pods = [
            resource for resource in namespace_resources
            if resource.kind == ResourceKind.POD
        ]
        replicasets = [
            resource for resource in namespace_resources
            if resource.kind == ResourceKind.REPLICASET
        ]

        children: List[ResourceRecord] = []
        if target_resource.kind == ResourceKind.DEPLOYMENT:
            owned_replicasets = [
                replicaset for replicaset in replicasets
                if self._is_owned_by(replicaset, target_resource)
            ]
            owned_rs_uids = {replicaset.uid for replicaset in owned_replicasets}
            children.extend(owned_replicasets)
            children.extend(
                pod for pod in pods
                if any(
                    owner_ref.get("kind") == ResourceKind.REPLICASET.value
                    and owner_ref.get("uid") in owned_rs_uids
                    for owner_ref in self._owner_refs(pod)
                )
            )
        else:
            children.extend(
                pod for pod in pods
                if self._is_owned_by(pod, target_resource)
            )

        if not any(child.kind == ResourceKind.POD for child in children):
            selector = self._match_label_selector(target_resource)
            children.extend(
                pod for pod in pods
                if self._pod_matches_selector(pod, selector)
            )

        if target_resource.kind == ResourceKind.STATEFULSET:
            children.extend(
                pod for pod in pods
                if pod.name.startswith(f"{target_resource.name}-")
            )

        return self._dedupe_resources(children)

    def _controller_relationship_evidence(
        self,
        target_resource: ResourceRecord,
        child: ResourceRecord,
        all_resources: List[ResourceRecord],
    ) -> str:
        if self._is_owned_by(child, target_resource):
            return (
                f"OwnerReference: {child.full_name} is owned by "
                f"{target_resource.full_name}"
            )

        if target_resource.kind == ResourceKind.DEPLOYMENT and child.kind == ResourceKind.POD:
            owned_replicasets = [
                resource for resource in all_resources
                if resource.kind == ResourceKind.REPLICASET
                and resource.namespace == target_resource.namespace
                and self._is_owned_by(resource, target_resource)
            ]
            for replicaset in owned_replicasets:
                if self._is_owned_by(child, replicaset):
                    return (
                        f"OwnerReference chain: {target_resource.full_name} -> "
                        f"{replicaset.full_name} -> {child.full_name}"
                    )

        selector = self._selector_string(self._match_label_selector(target_resource))
        return (
            f"Selector relationship: {child.full_name} matches "
            f"{target_resource.full_name} selector {selector}"
        )

    def _child_issue_actions(
        self,
        issue: Issue,
        child: ResourceRecord,
    ) -> List[str]:
        actions = list(issue.suggested_actions)
        if child.kind == ResourceKind.POD:
            if child.namespace:
                actions.append(f"Inspect child pod: kubectl describe pod {child.name} -n {child.namespace}")
                actions.append(f"Inspect child pod logs: kubectl logs {child.name} -n {child.namespace} --previous")
                actions.append(
                    "Check child pod events: "
                    f"kubectl get events -n {child.namespace} "
                    f"--field-selector involvedObject.name={child.name}"
                )
            else:
                actions.append(f"Inspect child pod: kubectl describe pod {child.name}")
                actions.append(f"Inspect child pod logs: kubectl logs {child.name} --previous")

        return list(dict.fromkeys(actions))

    def _promote_controller_child_issues(
        self,
        target_resource: ResourceRecord,
        issues: List[Issue],
        all_resources: List[ResourceRecord],
    ) -> List[Issue]:
        child_resources = self._controller_child_resources(target_resource, all_resources)
        child_by_uid = {resource.uid: resource for resource in child_resources}
        promoted: List[Issue] = []

        for issue in issues:
            child = child_by_uid.get(issue.resource_uid)
            if not child:
                continue

            relationship = self._controller_relationship_evidence(
                target_resource,
                child,
                all_resources,
            )
            promoted.append(
                Issue(
                    resource_uid=target_resource.uid,
                    title=f"{child.kind.value} {child.name}: {issue.title}",
                    description=(
                        f"{target_resource.kind.value} {target_resource.name} has "
                        f"an unhealthy child {child.kind.value} {child.name}: "
                        f"{issue.description}"
                    ),
                    reason=f"Child{issue.reason}",
                    message=f"{child.full_name}: {issue.message}",
                    timestamp=issue.timestamp,
                    critical_path=True,
                    severity=issue.severity,
                    score=issue.score,
                    evidence=[relationship, *issue.evidence],
                    related_events=issue.related_events,
                    suggested_actions=self._child_issue_actions(issue, child),
                    metadata={
                        **issue.metadata,
                        "source_issue_resource_uid": issue.resource_uid,
                        "child_resource": child.full_name,
                    },
                )
            )

        return promoted

    def _events_related_to_resources(
        self,
        events: List[ResourceRecord],
        resources: List[ResourceRecord],
    ) -> List[ResourceRecord]:
        resource_uids = {resource.uid for resource in resources}
        resource_names = {
            (resource.kind.value, resource.name, resource.namespace)
            for resource in resources
        }
        related = []
        for event in events:
            involved = event.properties.get("involvedObject", {})
            involved_uid = involved.get("uid")
            if involved_uid and involved_uid in resource_uids:
                related.append(event)
                continue

            event_name = (
                involved.get("kind"),
                involved.get("name"),
                involved.get("namespace", event.namespace),
            )
            if event_name in resource_names:
                related.append(event)

        return related

    def _selector_string(self, selector: Dict[str, str]) -> str:
        if not selector:
            return "<none>"
        return ",".join(f"{key}={value}" for key, value in sorted(selector.items()))

    def _pod_matches_selector(self, pod: ResourceRecord, selector: Dict[str, str]) -> bool:
        return bool(selector) and all(pod.labels.get(key) == value for key, value in selector.items())

    def _endpoint_address_counts(self, endpoints: ResourceRecord) -> tuple[int, int]:
        ready = 0
        not_ready = 0
        for subset in endpoints.properties.get('subsets', []) or []:
            ready += len(subset.get('addresses') or [])
            not_ready += len(subset.get('notReadyAddresses') or [])
        return ready, not_ready

    def _service_endpoint_evidence(
        self,
        target_resource: ResourceRecord,
        endpoints: ResourceRecord,
        all_resources: List[ResourceRecord],
    ) -> List[str]:
        ready_count, not_ready_count = self._endpoint_address_counts(endpoints)
        evidence = [
            (
                f"Endpoints/{target_resource.namespace}/{target_resource.name}: "
                f"ready addresses={ready_count}, not-ready addresses={not_ready_count}"
            )
        ]

        selector = target_resource.properties.get('spec', {}).get('selector', {}) or {}
        evidence.append(f"Service selector: {self._selector_string(selector)}")

        if selector:
            namespace_pods = [
                resource for resource in all_resources
                if resource.kind == ResourceKind.POD and resource.namespace == target_resource.namespace
            ]
            matching_pods = [
                pod for pod in namespace_pods
                if self._pod_matches_selector(pod, selector)
            ]
            if matching_pods:
                pod_summary = ", ".join(f"{pod.name}({pod.status})" for pod in matching_pods[:5])
                evidence.append(f"Pods matching selector: {pod_summary}")
            else:
                evidence.append(f"No Pods in namespace match selector {self._selector_string(selector)}")

        return evidence

    def _service_endpoint_issue(
        self,
        target_resource: ResourceRecord,
        all_resources: List[ResourceRecord],
    ) -> Optional[Issue]:
        """Create a target Service issue when its Endpoints object is empty."""
        if target_resource.kind != ResourceKind.SERVICE:
            return None

        for resource in all_resources:
            if (
                resource.kind == ResourceKind.ENDPOINTS
                and resource.name == target_resource.name
                and resource.namespace == target_resource.namespace
                and resource.status == 'Unavailable'
            ):
                evidence = self._service_endpoint_evidence(
                    target_resource,
                    resource,
                    all_resources,
                )
                return Issue(
                    resource_uid=target_resource.uid,
                    title="Service has no ready endpoints",
                    description=f"Service {target_resource.name} has no ready Endpoint addresses",
                    reason="ServiceNoEndpoints",
                    message=(
                        f"Endpoints/{target_resource.namespace}/{target_resource.name} "
                        "has no ready addresses. Check Service selector labels and backend pod readiness."
                    ),
                    severity=IssueSeverity.CRITICAL,
                    score=95.0,
                    critical_path=True,
                    evidence=evidence,
                    suggested_actions=[
                        f"kubectl get endpoints {target_resource.name} -n {target_resource.namespace}",
                        f"kubectl describe svc {target_resource.name} -n {target_resource.namespace}",
                        "Compare Service selector labels with backend pod labels",
                    ],
                )

        return None
    
    async def execute(self, subject: SubjectCtx) -> CommandResult:
        """Execute diagnosis command"""
        start_time = time.time()
        self._reset_data_gaps()
        
        try:
            all_resources = await self._collect_diag_data(subject)
            
            # Build dependency graph
            self.graph_builder.add_resources(all_resources)
            
            # Find target resource
            target_resource = self._find_subject_resource(subject, all_resources)
            
            if not target_resource:
                # Resource not found
                analysis_duration = time.time() - start_time
                renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
                result = DiagnosisResult(
                    subject=subject,
                    resource=None,
                    data_gaps=self.data_gaps,
                    analysis_duration=analysis_duration,
                )
                output = renderer.render_diagnosis(result)
                
                # All errors return exit_code=2
                return CommandResult(output=output, exit_code=result.exit_code, analysis_duration=analysis_duration)
            
            # Extract events related to this resource
            events = [r for r in all_resources if r.kind.value == "Event"]
            
            # Sort events by creation_timestamp descending (newest first)
            events.sort(key=lambda x: x.creation_timestamp.timestamp() if x.creation_timestamp else 0, reverse=True)
            
            # Analyze issues
            issues = self.scoring_engine.analyze_issues(all_resources, events, self.graph_builder)
            
            # Filter issues related to target resource
            target_issues = [
                issue for issue in issues 
                if issue.resource_uid == target_resource.uid
            ]
            target_issues.extend(
                self._promote_controller_child_issues(
                    target_resource,
                    issues,
                    all_resources,
                )
            )
            service_endpoint_issue = self._service_endpoint_issue(target_resource, all_resources)
            if service_endpoint_issue:
                target_issues.append(service_endpoint_issue)
            target_issues.sort(key=self.scoring_engine._issue_sort_key)
            
            # Identify root cause and contributing factors
            root_cause = self.scoring_engine.get_root_cause(target_issues)
            contributing_factors = self.scoring_engine.get_contributing_factors(target_issues, root_cause)
            
            # Generate suggested actions
            suggested_actions = self._generate_suggested_actions(target_resource, root_cause, contributing_factors)
            related_resources = [
                target_resource,
                *self._controller_child_resources(target_resource, all_resources),
            ]
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = DiagnosisResult(
                subject=subject,
                resource=target_resource,
                issues=target_issues,
                root_cause=root_cause,
                contributing_factors=contributing_factors,
                suggested_actions=suggested_actions,
                recent_events=self._events_related_to_resources(events, related_resources)[:5],
                data_gaps=self.data_gaps,
                analysis_duration=analysis_duration,
            )
            
            # Render output
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_diagnosis(result)
            
            logger.debug(f"DiagCommand: critical_issues={result.critical_issues}, warning_issues={result.warning_issues}")
            return CommandResult(
                output=output, 
                exit_code=result.exit_code,
                analysis_duration=analysis_duration
            )
            
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise  # Re-raise SystemExit to ensure proper exit code propagation
            analysis_duration = time.time() - start_time
            logger.error("Diagnosis command failed", error=str(e))
            
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_error(
                f"Diagnosis failed: {e}",
                data_gaps=self.data_gaps,
            )
            
            logger.debug(f"DiagCommand returning exit_code=2 due to exception: {e}")
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
    
    async def execute_raw(self, subject: SubjectCtx) -> DiagnosisResult:
        """Execute diagnosis and return raw DiagnosisResult (for JSON output)"""
        start_time = time.time()
        self._reset_data_gaps()

        all_resources = await self._collect_diag_data(subject)

        # Build dependency graph
        self.graph_builder.add_resources(all_resources)

        # Find target resource
        target_resource = self._find_subject_resource(subject, all_resources)

        if not target_resource:
            return DiagnosisResult(
                subject=subject,
                resource=None,
                data_gaps=self.data_gaps,
                analysis_duration=time.time() - start_time,
            )

        # Extract events related to this resource
        events = [r for r in all_resources if r.kind.value == "Event"]
        events.sort(key=lambda x: x.creation_timestamp.timestamp() if x.creation_timestamp else 0, reverse=True)

        # Analyze issues
        issues = self.scoring_engine.analyze_issues(all_resources, events, self.graph_builder)
        target_issues = [
            issue for issue in issues
            if issue.resource_uid == target_resource.uid
        ]
        target_issues.extend(
            self._promote_controller_child_issues(
                target_resource,
                issues,
                all_resources,
            )
        )
        service_endpoint_issue = self._service_endpoint_issue(target_resource, all_resources)
        if service_endpoint_issue:
            target_issues.append(service_endpoint_issue)
        target_issues.sort(key=self.scoring_engine._issue_sort_key)

        # Identify root cause and contributing factors
        root_cause = self.scoring_engine.get_root_cause(target_issues)
        contributing_factors = self.scoring_engine.get_contributing_factors(target_issues, root_cause)

        # Generate suggested actions
        suggested_actions = self._generate_suggested_actions(target_resource, root_cause, contributing_factors)
        related_resources = [
            target_resource,
            *self._controller_child_resources(target_resource, all_resources),
        ]

        analysis_duration = time.time() - start_time

        return DiagnosisResult(
            subject=subject,
            resource=target_resource,
            issues=target_issues,
            root_cause=root_cause,
            contributing_factors=contributing_factors,
            suggested_actions=suggested_actions,
            recent_events=self._events_related_to_resources(events, related_resources)[:5],
            data_gaps=self.data_gaps,
            analysis_duration=analysis_duration,
        )

    def _generate_suggested_actions(self, resource: ResourceRecord, root_cause, contributing_factors) -> List[str]:
        """Generate specific suggested actions based on diagnosis"""
        actions = []
        reason = (root_cause.reason or '').lower() if root_cause else ''
        raw_message = root_cause.message if root_cause and root_cause.message else ''
        evidence_text = "\n".join(root_cause.evidence) if root_cause else ''
        diagnostic_text = f"{raw_message}\n{evidence_text}"
        diagnostic_lower = diagnostic_text.lower()
        message = raw_message.lower()
        missing_config_ref = bool(
            root_cause
            and 'not found' in diagnostic_lower
            and (
                'secret "' in diagnostic_lower
                or 'configmap "' in diagnostic_lower
                or 'config map "' in diagnostic_lower
            )
        )
        
        # Generic actions based on resource status
        if (
            resource.kind == ResourceKind.POD
            and resource.status in ['Failed', 'Pending', 'Unknown']
            and not missing_config_ref
        ):
            actions.append(f"Check logs: kubectl logs {resource.name}")
            if resource.namespace:
                actions[-1] += f" -n {resource.namespace}"
        
        # Actions based on root cause
        if root_cause:
            missing_ref = re.search(r'(secret|configmap|config map) "([^"]+)" not found', diagnostic_text, re.IGNORECASE)
            if missing_ref:
                ref_type = missing_ref.group(1).replace(' ', '').lower()
                ref_name = missing_ref.group(2)
                kubectl_type = 'secret' if ref_type == 'secret' else 'configmap'
                describe = 'Secret' if kubectl_type == 'secret' else 'ConfigMap'
                action = f"Verify missing {describe}: kubectl get {kubectl_type} {ref_name}"
                if resource.namespace:
                    action += f" -n {resource.namespace}"
                actions.append(action)
                actions.append(f"Create or restore {describe} {ref_name}, or update the Pod reference")
            elif 'failedmount' in reason or 'mount' in message:
                actions.append("Check PVC status: kubectl get pvc")
                actions.append("Verify storage class: kubectl get storageclass")
            elif 'failedscheduling' in reason:
                actions.append("Check node resources: kubectl top nodes")
                actions.append("Check pod resource requests vs available capacity")
                if 'taint' in message or 'toleration' in message:
                    actions.append("Review taints/tolerations: kubectl describe nodes | grep -i taint")
                    actions.append("Add appropriate tolerations to Pod spec if needed")
            elif 'imagepullbackoff' in reason or 'errimagepull' in reason:
                actions.append("Verify image name and tag")
                actions.append("Check image pull secrets if using private registry")
            elif 'crashloopbackoff' in reason or 'crash' in message:
                act = f"Inspect previous logs: kubectl logs {resource.name} -p"
                if resource.namespace:
                    act += f" -n {resource.namespace}"
                actions.append(act)
                actions.append("Check container start command, readiness of dependencies, and exit code")
            elif 'readiness' in reason or 'liveness' in reason or 'probe' in message:
                actions.append("Inspect probe config: initialDelaySeconds, timeoutSeconds, periodSeconds")
                actions.append("Manually curl the probe endpoint from within the cluster")
            elif 'dns' in message or 'no such host' in message:
                actions.append("Check CoreDNS health: kubectl -n kube-system get pods -l k8s-app=kube-dns")
                actions.append("Verify Service/ClusterIP and pod resolv.conf")
            elif 'forbidden' in message or 'unauthorized' in message or 'permission' in message or 'rbac' in message:
                actions.append("Check RBAC: kubectl auth can-i --list")
                actions.append("Request missing permissions from cluster admin")
            elif 'networkpolicy' in message or 'deny' in message:
                actions.append("Review NetworkPolicy rules in namespace")
                actions.append("Temporarily relax policy to validate connectivity")
            elif 'servicenoendpoints' in reason:
                actions.extend(root_cause.suggested_actions)
            elif 'logfailure' in reason:
                actions.extend(root_cause.suggested_actions)
            if reason.startswith('child'):
                actions.extend(root_cause.suggested_actions)
        
        # Actions based on resource type
        if resource.kind.value == "Pod":
            actions.append(f"Get detailed info: kubectl describe pod {resource.name}")
            if resource.namespace:
                actions[-1] += f" -n {resource.namespace}"
        
        return list(dict.fromkeys(actions))[:self.config.max_suggested_actions]


class GraphCommand(BaseCommand):
    """Implementation of the graph command
    
    As specified in the technical requirements:
    - Uses graph built during last diag run in same process; else re-collect minimal data
    - Provides ASCII tree visualization with health indicators
    """

    def _target_inventory_incomplete(self, subject: SubjectCtx) -> bool:
        resource_type = kubectl_resource_type(subject.kind)
        return any(
            gap.startswith(f"get {resource_type} unavailable")
            or gap.startswith(f"get {resource_type} collector unavailable")
            for gap in self.data_gaps
        )

    async def _collect_graph_data(self, subject: SubjectCtx) -> List[ResourceRecord]:
        """Collect the namespace resource set needed to build useful relationships."""
        namespace_resource_types = [
            "pods",
            "deployments",
            "replicasets",
            "statefulsets",
            "daemonsets",
            "services",
            "configmaps",
            "secrets",
            "persistentvolumeclaims",
            "serviceaccounts",
            "ingresses",
            "endpoints",
        ]
        cluster_resource_types = ["nodes", "persistentvolumes"]

        collectors = []
        list_subject = subject.model_copy(update={"name": ""})
        cluster_subject = subject.model_copy(update={"name": "", "namespace": None})

        for resource_type in namespace_resource_types:
            try:
                collector = self._create_collector("get", resource_type=resource_type)
                collectors.append((resource_type, collector, list_subject))
            except Exception as e:
                logger.warning("Failed to create graph collector", resource_type=resource_type, error=str(e))
                self._record_collector_creation_gap("get", e, resource_type)

        for resource_type in cluster_resource_types:
            try:
                collector = self._create_collector("get", resource_type=resource_type)
                collectors.append((resource_type, collector, cluster_subject))
            except Exception as e:
                logger.warning("Failed to create graph collector", resource_type=resource_type, error=str(e))
                self._record_collector_creation_gap("get", e, resource_type)

        blobs = await asyncio.gather(
            *[
                collector.collect(collector_subject)
                for _, collector, collector_subject in collectors
            ],
            return_exceptions=True,
        )

        resources = []
        for (resource_type, collector, _), blob in zip(collectors, blobs):
            collector_label = f"get {resource_type}"
            if isinstance(blob, Exception):
                logger.warning(
                    "Graph collector failed",
                    collector=collector.name,
                    resource_type=resource_type,
                    error=str(blob),
                )
                self._record_exception_gap(collector_label, blob)
                continue
            self._record_blob_gap(blob)
            try:
                resources.extend(parser_registry.parse(blob))
            except Exception as e:
                logger.warning(
                    "Failed to parse graph data",
                    collector=collector.name,
                    resource_type=resource_type,
                    error=str(e),
                )
                self._add_data_gap(
                    f"{collector_label} output could not be parsed: {str(e).splitlines()[0]}"
                )

        return resources
    
    async def execute(self, subject: SubjectCtx, direction: str = "downstream") -> CommandResult:
        """Execute graph command"""
        start_time = time.time()
        self._reset_data_gaps()
        
        try:
            # Check if we have an existing graph, otherwise collect minimal data
            if self.graph_builder.graph.vcount() == 0:
                all_resources = await self._collect_graph_data(subject)
                self.graph_builder.add_resources(all_resources)
            
            # Find target resource
            target_uid = None
            target_resource = None
            
            for uid, resource in self.graph_builder.resources.items():
                if (resource.kind == subject.kind and 
                    resource.name == subject.name and
                    resource.namespace == subject.namespace):
                    target_uid = uid
                    target_resource = resource
                    break
            
            if not target_uid:
                analysis_duration = time.time() - start_time
                renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
                message = f"Resource {subject.full_name} not found in graph"
                if self._target_inventory_incomplete(subject):
                    message = (
                        f"Resource {subject.full_name} not present in collected graph"
                    )
                output = renderer.render_error(
                    message,
                    data_gaps=self.data_gaps,
                )
                
                # All errors return exit_code=2
                return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
            
            # Generate ASCII graph
            if direction == "both":
                upstream_graph = self.graph_builder.to_ascii(target_uid, "upstream", max_depth=3)
                downstream_graph = self.graph_builder.to_ascii(target_uid, "downstream", max_depth=3)
                ascii_graph = (
                    "UPSTREAM DEPENDENCIES (what this resource depends on):\n"
                    f"{upstream_graph}\n\n"
                    "DOWNSTREAM DEPENDENCIES (what depends on this resource):\n"
                    f"{downstream_graph}"
                )
                dependencies = list(dict.fromkeys(
                    self.graph_builder.get_dependencies(target_uid, "upstream")
                    + self.graph_builder.get_dependencies(target_uid, "downstream")
                ))
            else:
                ascii_graph = self.graph_builder.to_ascii(target_uid, direction, max_depth=3)
                dependencies = self.graph_builder.get_dependencies(target_uid, direction)
            
            # Build edges list
            edges = []
            for dep_uid in dependencies:
                dep_resource = self.graph_builder.resources.get(dep_uid)
                if dep_resource:
                    edges.append({
                        'source': target_resource.full_name,
                        'target': dep_resource.full_name,
                        'type': direction
                    })
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = GraphResult(
                subject=subject,
                nodes=list(self.graph_builder.resources.values()),
                edges=edges,
                ascii_graph=ascii_graph,
                upstream_count=len(self.graph_builder.get_dependencies(target_uid, "upstream")),
                downstream_count=len(self.graph_builder.get_dependencies(target_uid, "downstream")),
                data_gaps=self.data_gaps,
                analysis_duration=analysis_duration,
            )
            
            # Render output
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_graph(result)
            
            return CommandResult(output=output, exit_code=0, analysis_duration=analysis_duration)
            
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise  # Re-raise SystemExit to ensure proper exit code propagation
            analysis_duration = time.time() - start_time
            logger.error("Graph command failed", error=str(e))
            
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_error(
                f"Graph analysis failed: {e}",
                data_gaps=self.data_gaps,
            )
                
            logger.debug(f"GraphCommand returning exit_code=2 due to exception: {e}")
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)


class TopCommand(BaseCommand):
    """Implementation of the top command
    
    As specified in the technical requirements:
    - Pulls kubectl top pods; groups by PVC and Secret expiries
    - Forecast horizon: 48h; list only issues predicted to cross 90% or expire
    """
    
    def __init__(self, forecast_horizon_hours: int = 48, **kwargs):
        super().__init__(**kwargs)
        self.forecast_horizon_hours = forecast_horizon_hours
        self.forecasting_engine = ForecastingEngine(
            forecast_horizon_hours=forecast_horizon_hours
        )

    def _subject_not_found(self, subject: SubjectCtx) -> bool:
        resource_type = subject.kind.value.lower()
        return any(
            gap.startswith(f"get {resource_type} unavailable (not_found)")
            for gap in self.data_gaps
        )

    def _merge_pvc_metrics(self, resources: List[ResourceRecord]) -> List[ResourceRecord]:
        """Attach kubelet PVC metric records to matching PVC inventory records."""
        metric_by_key: Dict[tuple[Optional[str], str], Dict[str, object]] = {}
        inventory_keys: set[tuple[Optional[str], str]] = set()

        for resource in resources:
            if resource.kind != ResourceKind.PVC:
                continue
            key = (resource.namespace, resource.name)
            if not resource.uid.startswith("pvc-metrics-"):
                inventory_keys.add(key)
            metrics = resource.get_property("metrics", {})
            if (
                isinstance(metrics, dict)
                and "pvc_used_bytes" in metrics
                and "pvc_capacity_bytes" in metrics
            ):
                metric_by_key[key] = metrics

        if not metric_by_key:
            return resources

        merged: List[ResourceRecord] = []
        for resource in resources:
            if resource.kind != ResourceKind.PVC:
                merged.append(resource)
                continue

            key = (resource.namespace, resource.name)
            if resource.uid.startswith("pvc-metrics-") and key in inventory_keys:
                continue

            metrics = metric_by_key.get(key)
            if metrics and not resource.uid.startswith("pvc-metrics-"):
                properties = dict(resource.properties)
                existing_metrics = properties.get("metrics", {})
                if not isinstance(existing_metrics, dict):
                    existing_metrics = {}
                properties["metrics"] = {**existing_metrics, **metrics}
                merged.append(resource.model_copy(update={"properties": properties}))
            else:
                merged.append(resource)

        return merged

    def _record_missing_pvc_metric_gaps(self, resources: List[ResourceRecord]) -> None:
        """Record incomplete PVC usage evidence after kubelet metric merging."""
        missing = []
        for resource in resources:
            if resource.kind != ResourceKind.PVC:
                continue
            if resource.uid.startswith("pvc-metrics-"):
                continue
            storage_request = resource.get_property("spec.resources.requests.storage")
            if not storage_request:
                continue
            metrics = resource.get_property("metrics", {})
            if not (
                isinstance(metrics, dict)
                and metrics.get("pvc_used_bytes") is not None
                and metrics.get("pvc_capacity_bytes") is not None
            ):
                missing.append(resource.name)

        if not missing:
            return

        shown = ", ".join(missing[:5])
        remaining = len(missing) - 5
        if remaining > 0:
            shown += f", ... {remaining} more"
        self._add_data_gap(
            "kubelet persistentvolumeclaims unavailable (incomplete): "
            f"missing kubelet_volume_stats metrics for {shown}"
        )

    async def _collect_node_context(self, subject: SubjectCtx) -> List[ResourceRecord]:
        """Collect cluster node inventory and metrics for capacity outlooks."""
        cluster_subject = SubjectCtx(
            kind=ResourceKind.NODE,
            name="",
            namespace=None,
            context=subject.context,
            scope="cluster",
        )
        collector_specs = [
            ("get nodes", "get", {"resource_type": "nodes"}),
            ("metrics nodes", "metrics", {}),
        ]
        collectors = []

        for collector_label, collector_name, kwargs in collector_specs:
            try:
                collector = self._create_collector(collector_name, **kwargs)
                collectors.append((collector_label, collector, cluster_subject))
            except Exception as e:
                resource_type = collector_label.split(" ", 1)[1]
                logger.info(
                    "Node context collector unavailable",
                    collector=collector_name,
                    resource_type=resource_type,
                    error=str(e),
                )
                self._record_collector_creation_gap(
                    collector_name,
                    e,
                    resource_type,
                )

        if not collectors:
            return []

        blobs = await asyncio.gather(
            *[
                collector.collect(collector_subject)
                for _, collector, collector_subject in collectors
            ],
            return_exceptions=True,
        )

        resources: List[ResourceRecord] = []
        for (collector_label, collector, _), blob in zip(collectors, blobs):
            if isinstance(blob, Exception):
                logger.info(
                    "Node context collector failed",
                    collector=collector.name,
                    error=str(blob),
                )
                self._record_exception_gap(collector_label, blob)
                continue

            self._record_blob_gap(blob)
            try:
                resources.extend(parser_registry.parse(blob))
            except Exception as e:
                logger.info(
                    "Node context parser failed",
                    collector=collector.name,
                    error=str(e),
                )
                self._add_data_gap(
                    f"{collector_label} output could not be parsed: {str(e).splitlines()[0]}"
                )

        return resources
    
    async def execute(self, subject: SubjectCtx) -> CommandResult:
        """Execute top command"""
        start_time = time.time()
        self._reset_data_gaps()
        
        try:
            # Collect data for namespace analysis
            collector_names = ['get', 'metrics', 'kubelet']
            all_resources = await self._collect_data(subject, collector_names)
            if self._subject_not_found(subject):
                analysis_duration = time.time() - start_time
                renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
                output = renderer.render_error(
                    f"Namespace {subject.name} not found",
                    data_gaps=self.data_gaps,
                )
                return CommandResult(
                    output=output,
                    exit_code=2,
                    analysis_duration=analysis_duration,
                )

            all_resources.extend(await self._collect_node_context(subject))

            # Additional targeted gets for resources needed by forecasting
            # Secrets (for TLS), Ingress (TLS references), PVC/PV (storage mapping)
            extra_collectors = []
            for resource_type in [
                'secrets',
                'ingresses',
                'persistentvolumeclaims',
                'persistentvolumes',
            ]:
                try:
                    collector = self._create_collector(
                        'get',
                        resource_type=resource_type,
                    )
                    extra_collectors.append((resource_type, collector))
                except Exception as e:
                    logger.info(
                        "Optional collector unavailable",
                        resource_type=resource_type,
                        error=str(e),
                    )
                    self._record_collector_creation_gap('get', e, resource_type)
            import asyncio as _asyncio
            extra_blobs = await _asyncio.gather(
                *[collector.collect(subject) for _, collector in extra_collectors],
                return_exceptions=True,
            )
            for (resource_type, collector), blob in zip(extra_collectors, extra_blobs):
                collector_label = f"get {resource_type}"
                if isinstance(blob, Exception):
                    logger.info(
                        "Optional collector failed",
                        collector=collector.name,
                        resource_type=resource_type,
                        error=str(blob),
                    )
                    self._record_exception_gap(collector_label, blob)
                    continue
                self._record_blob_gap(blob)
                try:
                    parsed = parser_registry.parse(blob)
                    all_resources.extend(parsed)
                except Exception as e:
                    logger.info(
                        "Optional parser failed",
                        collector=collector.name,
                        resource_type=resource_type,
                        error=str(e),
                    )
                    self._add_data_gap(
                        f"{collector_label} output could not be parsed: {str(e).splitlines()[0]}"
                    )

            all_resources = self._merge_pvc_metrics(all_resources)
            
            # Filter to namespace resources
            namespace_resources = [
                r for r in all_resources 
                if r.namespace == subject.name or r.kind.value in ['Node', 'PersistentVolume']
            ]
            self._record_missing_pvc_metric_gaps(namespace_resources)
            
            # Get metrics data for forecasting
            metrics_data = [r for r in all_resources if r.properties.get('metrics')]
            
            # Predict capacity issues (nodes + PVCs)
            capacity_warnings = self.forecasting_engine.predict_capacity_issues(
                namespace_resources, metrics_data
            )
            
            # Predict certificate expiry
            secret_inventory_complete = not any(
                gap.startswith("get secrets") for gap in self.data_gaps
            )
            certificate_warnings = self.forecasting_engine.predict_certificate_expiry(
                namespace_resources,
                secret_inventory_complete=secret_inventory_complete,
            )
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = TopResult(
                subject=subject,
                capacity_warnings=capacity_warnings,
                certificate_warnings=certificate_warnings,
                forecast_horizon_hours=self.forecast_horizon_hours,
                data_gaps=self.data_gaps,
                analysis_duration=analysis_duration,
            )
            
            # Render output
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_top(result)
            
            # Exit code 0 even if warnings exist; top is advisory
            return CommandResult(output=output, exit_code=0, analysis_duration=analysis_duration)
            
        except Exception as e:
            analysis_duration = time.time() - start_time
            logger.error("Top command failed", error=str(e))
            
            renderer = TerminalRenderer(colors_enabled=self.config.colors_enabled)
            output = renderer.render_error(
                f"Predictive analysis failed: {e}",
                data_gaps=self.data_gaps,
            )
                
            # All errors return exit_code=2
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
