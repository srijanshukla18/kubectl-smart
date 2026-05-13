"""
Batch operations for analyzing multiple resources at once

Enables kubectl-smart to analyze multiple resources in parallel,
significantly improving efficiency for cluster-wide analysis.

Usage:
    kubectl-smart diag pod --all -n production
    kubectl-smart diag deploy --all --context staging
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

from .models import DiagnosisResult, ResourceKind, SubjectCtx

logger = structlog.get_logger(__name__)  # type: ignore[attr-defined]


@dataclass
class BatchResult:
    """Result of batch operation"""
    total_resources: int
    successful: int
    failed: int
    results: list[DiagnosisResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    duration: float = 0.0


class BatchAnalyzer:
    """Batch analyzer for processing multiple resources concurrently"""

    def __init__(self, max_concurrent: int = 5):
        """Initialize batch analyzer

        Args:
            max_concurrent: Maximum number of concurrent diagnoses
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def diagnose_all(
        self,
        kind: ResourceKind,
        namespace: Optional[str] = None,
        context: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> BatchResult:
        """Diagnose all resources of a given kind

        Args:
            kind: Resource kind (Pod, Deployment, etc.)
            namespace: Namespace to analyze (None = current namespace)
            context: kubectl context
            label_selector: Label selector (e.g., "app=nginx")

        Returns:
            BatchResult with all diagnoses
        """
        start_time = time.time()

        # Get list of resources
        resources = await self._get_resources(kind, namespace, context, label_selector)

        if not resources:
            return BatchResult(
                total_resources=0,
                successful=0,
                failed=0,
                results=[],
                errors=[{"message": f"No {kind.value}s found"}],
                duration=time.time() - start_time,
            )

        logger.info(f"Found {len(resources)} {kind.value}s to analyze")

        # Analyze resources concurrently with semaphore limiting
        tasks = [
            self._diagnose_resource(name, kind, namespace, context)
            for name in resources
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful_results: list[DiagnosisResult] = []
        errors: list[dict[str, str]] = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append({
                    "resource": resources[i],
                    "error": str(result)
                })
            elif result is not None:
                successful_results.append(result)

        duration = time.time() - start_time

        return BatchResult(
            total_resources=len(resources),
            successful=len(successful_results),
            failed=len(errors),
            results=successful_results,
            errors=errors,
            duration=duration,
        )

    async def _get_resources(
        self,
        kind: ResourceKind,
        namespace: Optional[str],
        context: Optional[str],
        label_selector: Optional[str],
    ) -> list[str]:
        """Get list of resource names"""
        # Map ResourceKind to kubectl resource type
        kind_to_kubectl = {
            ResourceKind.POD: "pods",
            ResourceKind.DEPLOYMENT: "deployments",
            ResourceKind.STATEFULSET: "statefulsets",
            ResourceKind.DAEMONSET: "daemonsets",
            ResourceKind.JOB: "jobs",
            ResourceKind.SERVICE: "services",
            ResourceKind.REPLICASET: "replicasets",
        }

        resource_type = kind_to_kubectl.get(kind, kind.value.lower() + "s")

        cmd = ["kubectl", "get", resource_type, "-o", "jsonpath={.items[*].metadata.name}"]

        if namespace:
            cmd.extend(["-n", namespace])
        if context:
            cmd.extend(["--context", context])
        if label_selector:
            cmd.extend(["-l", label_selector])

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.warning(f"kubectl get failed: {result.stderr}")
                return []

            names = result.stdout.strip().split()
            return [n for n in names if n]  # Filter empty strings

        except subprocess.TimeoutExpired:
            logger.error("kubectl get timed out")
            return []
        except Exception as e:
            logger.error(f"Failed to get resources: {e}")
            return []

    async def _diagnose_resource(
        self,
        name: str,
        kind: ResourceKind,
        namespace: Optional[str],
        context: Optional[str],
    ) -> Optional[DiagnosisResult]:
        """Diagnose a single resource with concurrency limiting"""
        async with self.semaphore:
            try:
                subject = SubjectCtx(
                    kind=kind,
                    name=name,
                    namespace=namespace,
                    context=context,
                    scope="resource",
                )

                return await self._execute_diagnosis(subject)

            except Exception as e:
                logger.warning(f"Failed to diagnose {name}: {e}")
                raise

    async def _execute_diagnosis(self, subject: SubjectCtx) -> DiagnosisResult:
        """Execute diagnosis and return DiagnosisResult directly"""
        from .collectors.base import registry as collector_registry
        from .graph.builder import GraphBuilder
        from .parsers.base import registry as parser_registry
        from .scoring.engine import ScoringEngine

        graph_builder = GraphBuilder()
        scoring_engine = ScoringEngine()

        start_time = time.time()

        # Collect data
        collector_names = ['get', 'describe', 'events', 'logs']
        all_resources = []

        for name in collector_names:
            try:
                if name in ('describe', 'get'):
                    collector = collector_registry.create(name, resource_type=subject.kind.value.lower())
                else:
                    collector = collector_registry.create(name)

                blob = await collector.collect(subject)
                resources = parser_registry.parse(blob)
                all_resources.extend(resources)
            except Exception as e:
                logger.debug(f"Collector {name} failed: {e}")

        # Build graph
        graph_builder.add_resources(all_resources)

        # Find target resource
        target_resource = None
        for resource in all_resources:
            if (resource.kind == subject.kind and
                resource.name == subject.name and
                resource.namespace == subject.namespace):
                target_resource = resource
                break

        if not target_resource:
            raise ValueError(f"Resource {subject.full_name} not found")

        # Extract events
        events = [r for r in all_resources if r.kind.value == "Event"]
        events.sort(key=lambda x: x.creation_timestamp.timestamp() if x.creation_timestamp else 0, reverse=True)

        # Analyze issues
        issues = scoring_engine.analyze_issues(all_resources, events, graph_builder)
        target_issues = [
            issue for issue in issues
            if issue.resource_uid == target_resource.uid
        ]

        # Get root cause and contributing factors
        root_cause = scoring_engine.get_root_cause(target_issues)
        contributing_factors = scoring_engine.get_contributing_factors(target_issues, root_cause)

        analysis_duration = time.time() - start_time

        return DiagnosisResult(
            subject=subject,
            resource=target_resource,
            issues=target_issues,
            root_cause=root_cause,
            contributing_factors=contributing_factors,
            suggested_actions=[],
            recent_events=events[:5],
            analysis_duration=analysis_duration,
        )
