"""
Batch operations for analyzing multiple resources at once

Enables kubectl-smart to analyze multiple resources in parallel,
significantly improving efficiency for cluster-wide analysis.

Usage:
    kubectl-smart diag pod --all -n production
    kubectl-smart diag deploy --all --context staging
"""

import asyncio
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

from .models import DiagnosisResult, ResourceKind, SubjectCtx

logger = structlog.get_logger(__name__)  # type: ignore[attr-defined]

DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def kubectl_resource_type(kind: ResourceKind) -> str:
    """Return the kubectl plural resource type for a supported kind."""
    kind_to_kubectl = {
        ResourceKind.POD: "pods",
        ResourceKind.DEPLOYMENT: "deployments",
        ResourceKind.STATEFULSET: "statefulsets",
        ResourceKind.DAEMONSET: "daemonsets",
        ResourceKind.JOB: "jobs",
        ResourceKind.SERVICE: "services",
        ResourceKind.REPLICASET: "replicasets",
        ResourceKind.INGRESS: "ingresses",
    }
    return kind_to_kubectl.get(kind, kind.value.lower() + "s")


@dataclass
class BatchResult:
    """Result of batch operation"""
    total_resources: int
    successful: int
    failed: int
    results: list[DiagnosisResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)
    duration: float = 0.0

    @property
    def exit_code(self) -> int:
        """Return CLI exit code for aggregate batch diagnosis."""
        if self.failed or any(result.exit_code == 2 for result in self.results):
            return 2
        if any(result.exit_code == 1 for result in self.results):
            return 1
        return 0


class BatchAnalyzer:
    """Batch analyzer for processing multiple resources concurrently"""

    def __init__(
        self,
        max_concurrent: int = 5,
        kubectl_timeout: Optional[float] = None,
        collector_timeout: Optional[float] = None,
    ):
        """Initialize batch analyzer

        Args:
            max_concurrent: Maximum number of concurrent diagnoses
            kubectl_timeout: Timeout for the initial kubectl resource list
            collector_timeout: Timeout for per-resource diagnosis collectors
        """
        from .models import AnalysisConfig

        default_timeout = AnalysisConfig().collector_timeout
        self.max_concurrent = max_concurrent
        self.kubectl_timeout = kubectl_timeout if kubectl_timeout is not None else default_timeout
        self.collector_timeout = collector_timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._resource_list_error: Optional[str] = None

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
            resource_label = kubectl_resource_type(kind).capitalize()
            message = self._resource_list_error or f"No {resource_label} found"
            return BatchResult(
                total_resources=0,
                successful=0,
                failed=1 if self._resource_list_error else 0,
                results=[],
                errors=[{"message": message}] if self._resource_list_error else [],
                messages=[] if self._resource_list_error else [{"message": message}],
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
        self._resource_list_error = None

        resource_type = kubectl_resource_type(kind)

        cmd = ["kubectl", "get", resource_type, "-o", "jsonpath={.items[*].metadata.name}"]

        if namespace and (len(namespace) > 63 or not DNS_LABEL.fullmatch(namespace)):
            self._resource_list_error = "Invalid namespace supplied"
            logger.warning(self._resource_list_error)
            return []
        if context and any(ord(char) < 32 or ord(char) == 127 for char in context):
            self._resource_list_error = "Invalid context supplied"
            logger.warning(self._resource_list_error)
            return []
        if label_selector is not None:
            if not label_selector.strip():
                self._resource_list_error = "Invalid label selector supplied"
                logger.warning(self._resource_list_error)
                return []
            if any(ord(char) < 32 or ord(char) == 127 for char in label_selector):
                self._resource_list_error = "Invalid label selector supplied"
                logger.warning(self._resource_list_error)
                return []

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
                timeout=self.kubectl_timeout,
            )

            if result.returncode != 0:
                error = result.stderr.strip() or "kubectl get failed"
                self._resource_list_error = f"Failed to list {resource_type}: {error}"
                logger.warning(self._resource_list_error)
                return []

            names = result.stdout.strip().split()
            return [n for n in names if n]  # Filter empty strings

        except subprocess.TimeoutExpired:
            self._resource_list_error = (
                f"Timed out after {self.kubectl_timeout}s listing {resource_type}"
            )
            logger.error(self._resource_list_error)
            return []
        except Exception as e:
            self._resource_list_error = f"Failed to list {resource_type}: {e}"
            logger.error(self._resource_list_error)
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
        from .cli.commands import DiagCommand
        from .models import AnalysisConfig

        config = (
            AnalysisConfig(collector_timeout=self.collector_timeout)
            if self.collector_timeout is not None
            else None
        )
        return await DiagCommand(config=config).execute_raw(subject)
