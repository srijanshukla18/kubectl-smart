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

        if subject.kind == ResourceKind.SERVICE:
            endpoints_collector = self._create_collector('get', resource_type='endpoints')
            endpoints_blob = await endpoints_collector.collect(subject)
            self._record_blob_gap(endpoints_blob)
            try:
                all_resources.extend(parser_registry.parse(endpoints_blob))
            except Exception as e:
                logger.warning("Failed to parse service endpoint data", error=str(e))
                self._add_data_gap(f"endpoints output could not be parsed: {str(e).splitlines()[0]}")

            pods_collector = self._create_collector('get', resource_type='pods')
            pods_blob = await pods_collector.collect(subject.model_copy(update={"name": ""}))
            self._record_blob_gap(pods_blob)
            try:
                all_resources.extend(parser_registry.parse(pods_blob))
            except Exception as e:
                logger.warning("Failed to parse service pod data", error=str(e))
                self._add_data_gap(f"pods output could not be parsed: {str(e).splitlines()[0]}")

        return all_resources

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
            target_resource = None
            for resource in all_resources:
                if (resource.kind == subject.kind and 
                    resource.name == subject.name and
                    resource.namespace == subject.namespace):
                    target_resource = resource
                    break
            
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
            service_endpoint_issue = self._service_endpoint_issue(target_resource, all_resources)
            if service_endpoint_issue:
                target_issues.append(service_endpoint_issue)
                target_issues.sort(key=self.scoring_engine._issue_sort_key)
            
            # Identify root cause and contributing factors
            root_cause = self.scoring_engine.get_root_cause(target_issues)
            contributing_factors = self.scoring_engine.get_contributing_factors(target_issues, root_cause)
            
            # Generate suggested actions
            suggested_actions = self._generate_suggested_actions(target_resource, root_cause, contributing_factors)
            
            analysis_duration = time.time() - start_time
            
            # Create result
            result = DiagnosisResult(
                subject=subject,
                resource=target_resource,
                issues=target_issues,
                root_cause=root_cause,
                contributing_factors=contributing_factors,
                suggested_actions=suggested_actions,
                recent_events=events[:5], # Top 5 recent events
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
            output = renderer.render_error(f"Diagnosis failed: {e}")
            
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
        target_resource = None
        for resource in all_resources:
            if (resource.kind == subject.kind and
                resource.name == subject.name and
                resource.namespace == subject.namespace):
                target_resource = resource
                break

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
        service_endpoint_issue = self._service_endpoint_issue(target_resource, all_resources)
        if service_endpoint_issue:
            target_issues.append(service_endpoint_issue)
            target_issues.sort(key=self.scoring_engine._issue_sort_key)

        # Identify root cause and contributing factors
        root_cause = self.scoring_engine.get_root_cause(target_issues)
        contributing_factors = self.scoring_engine.get_contributing_factors(target_issues, root_cause)

        # Generate suggested actions
        suggested_actions = self._generate_suggested_actions(target_resource, root_cause, contributing_factors)

        analysis_duration = time.time() - start_time

        return DiagnosisResult(
            subject=subject,
            resource=target_resource,
            issues=target_issues,
            root_cause=root_cause,
            contributing_factors=contributing_factors,
            suggested_actions=suggested_actions,
            recent_events=events[:5],
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
        if resource.status in ['Failed', 'Pending', 'Unknown'] and not missing_config_ref:
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
        
        # Actions based on resource type
        if resource.kind.value == "Pod":
            actions.append(f"Get detailed info: kubectl describe pod {resource.name}")
            if resource.namespace:
                actions[-1] += f" -n {resource.namespace}"
        
        return actions[:self.config.max_suggested_actions]


class GraphCommand(BaseCommand):
    """Implementation of the graph command
    
    As specified in the technical requirements:
    - Uses graph built during last diag run in same process; else re-collect minimal data
    - Provides ASCII tree visualization with health indicators
    """

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
        subjects = []
        list_subject = subject.model_copy(update={"name": ""})
        cluster_subject = subject.model_copy(update={"name": "", "namespace": None})

        for resource_type in namespace_resource_types:
            try:
                collectors.append(self._create_collector("get", resource_type=resource_type))
                subjects.append(list_subject)
            except Exception as e:
                logger.warning("Failed to create graph collector", resource_type=resource_type, error=str(e))
                self._record_collector_creation_gap("get", e, resource_type)

        for resource_type in cluster_resource_types:
            try:
                collectors.append(self._create_collector("get", resource_type=resource_type))
                subjects.append(cluster_subject)
            except Exception as e:
                logger.warning("Failed to create graph collector", resource_type=resource_type, error=str(e))
                self._record_collector_creation_gap("get", e, resource_type)

        blobs = await asyncio.gather(
            *[collector.collect(collector_subject) for collector, collector_subject in zip(collectors, subjects)],
            return_exceptions=True,
        )

        resources = []
        for i, blob in enumerate(blobs):
            if isinstance(blob, Exception):
                logger.warning("Graph collector failed", collector=collectors[i].name, error=str(blob))
                self._record_exception_gap(collectors[i].name, blob)
                continue
            self._record_blob_gap(blob)
            try:
                resources.extend(parser_registry.parse(blob))
            except Exception as e:
                logger.warning("Failed to parse graph data", collector=collectors[i].name, error=str(e))
                self._add_data_gap(f"{collectors[i].name} output could not be parsed: {str(e).splitlines()[0]}")

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
                output = renderer.render_error(f"Resource {subject.full_name} not found in graph")
                
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
            output = renderer.render_error(f"Graph analysis failed: {e}")
                
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
    
    async def execute(self, subject: SubjectCtx) -> CommandResult:
        """Execute top command"""
        start_time = time.time()
        self._reset_data_gaps()
        
        try:
            # Collect data for namespace analysis
            collector_names = ['get', 'metrics', 'kubelet']
            all_resources = await self._collect_data(subject, collector_names)

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
                    extra_collectors.append(
                        self._create_collector('get', resource_type=resource_type)
                    )
                except Exception as e:
                    logger.info(
                        "Optional collector unavailable",
                        resource_type=resource_type,
                        error=str(e),
                    )
                    self._record_collector_creation_gap('get', e, resource_type)
            import asyncio as _asyncio
            extra_blobs = await _asyncio.gather(*[c.collect(subject) for c in extra_collectors], return_exceptions=True)
            for i, blob in enumerate(extra_blobs):
                if isinstance(blob, Exception):
                    logger.info("Optional collector failed", collector=extra_collectors[i].name, error=str(blob))
                    self._record_exception_gap(extra_collectors[i].name, blob)
                    continue
                self._record_blob_gap(blob)
                try:
                    parsed = parser_registry.parse(blob)
                    all_resources.extend(parsed)
                except Exception as e:
                    logger.info("Optional parser failed", collector=extra_collectors[i].name, error=str(e))
                    self._add_data_gap(f"{extra_collectors[i].name} output could not be parsed: {str(e).splitlines()[0]}")
            
            # Filter to namespace resources
            namespace_resources = [
                r for r in all_resources 
                if r.namespace == subject.name or r.kind.value in ['Node', 'PersistentVolume']
            ]
            
            # Get metrics data for forecasting
            metrics_data = [r for r in all_resources if r.properties.get('metrics')]
            
            # Predict capacity issues (nodes + PVCs)
            capacity_warnings = self.forecasting_engine.predict_capacity_issues(
                namespace_resources, metrics_data
            )
            
            # Predict certificate expiry
            certificate_warnings = self.forecasting_engine.predict_certificate_expiry(
                namespace_resources
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
            output = renderer.render_error(f"Predictive analysis failed: {e}")
                
            # All errors return exit_code=2
            return CommandResult(output=output, exit_code=2, analysis_duration=analysis_duration)
