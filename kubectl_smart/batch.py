"""
Batch operations for analyzing multiple resources at once

This module enables kubectl-smart to analyze multiple resources in parallel,
significantly improving efficiency for cluster-wide analysis.
"""

import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import structlog

from .models import SubjectCtx, ResourceKind, DiagnosisResult
from .cli.commands import DiagCommand

logger = structlog.get_logger(__name__)


@dataclass
class BatchResult:
    """Result of batch operation"""
    total_resources: int
    successful: int
    failed: int
    results: List[Any]
    errors: List[Dict[str, str]]
    duration: float


class BatchAnalyzer:
    """Batch analyzer for processing multiple resources"""

    def __init__(self, max_concurrent: int = 10):
        """Initialize batch analyzer

        Args:
            max_concurrent: Maximum number of concurrent operations
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def diagnose_all_pods(
        self,
        namespace: Optional[str] = None,
        context: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> BatchResult:
        """Diagnose all pods in namespace

        Args:
            namespace: Namespace to analyze (None = all namespaces)
            context: kubectl context
            label_selector: Label selector (e.g., "app=nginx")

        Returns:
            BatchResult with all diagnoses
        """
        import time
        start_time = time.time()

        # Get list of pods
        pods = await self._get_pods(namespace, context, label_selector)

        if not pods:
            return BatchResult(
                total_resources=0,
                successful=0,
                failed=0,
                results=[],
                errors=[{"message": "No pods found"}],
                duration=time.time() - start_time,
            )

        # Analyze pods concurrently
        tasks = [
            self._diagnose_pod(pod, namespace, context)
            for pod in pods
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        successful = []
        errors = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append({
                    "resource": pods[i],
                    "error": str(result),
                })
            else:
                successful.append(result)

        duration = time.time() - start_time

        return BatchResult(
            total_resources=len(pods),
            successful=len(successful),
            failed=len(errors),
            results=successful,
            errors=errors,
            duration=duration,
        )

    async def _get_pods(
        self,
        namespace: Optional[str],
        context: Optional[str],
        label_selector: Optional[str],
    ) -> List[str]:
        """Get list of pod names

        Args:
            namespace: Namespace
            context: kubectl context
            label_selector: Label selector

        Returns:
            List of pod names
        """
        import json

        cmd = ["kubectl", "get", "pods"]

        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")

        if label_selector:
            cmd.extend(["-l", label_selector])

        cmd.extend(["-o", "json"])

        if context:
            cmd.extend(["--context", context])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error("Failed to get pods", error=stderr.decode())
                return []

            data = json.loads(stdout.decode())
            items = data.get("items", [])

            pod_names = []
            for item in items:
                name = item.get("metadata", {}).get("name")
                if name:
                    pod_names.append(name)

            return pod_names

        except Exception as e:
            logger.error("Failed to get pods", error=str(e))
            return []

    async def _diagnose_pod(
        self,
        pod_name: str,
        namespace: Optional[str],
        context: Optional[str],
    ) -> DiagnosisResult:
        """Diagnose a single pod

        Args:
            pod_name: Pod name
            namespace: Namespace
            context: kubectl context

        Returns:
            DiagnosisResult
        """
        async with self.semaphore:
            subject = SubjectCtx(
                kind=ResourceKind.POD,
                name=pod_name,
                namespace=namespace,
                context=context,
                scope="resource",
            )

            command = DiagCommand()
            result = await command.execute(subject)

            return result.result_data


def format_batch_summary(batch_result: BatchResult) -> str:
    """Format batch result summary for display

    Args:
        batch_result: Batch result to format

    Returns:
        Formatted summary string
    """
    lines = [
        f"\n📊 BATCH ANALYSIS SUMMARY",
        f"=" * 60,
        f"Total Resources: {batch_result.total_resources}",
        f"✅ Successful: {batch_result.successful}",
        f"❌ Failed: {batch_result.failed}",
        f"⏱️  Duration: {batch_result.duration:.2f}s",
    ]

    if batch_result.results:
        critical_count = sum(
            1 for r in batch_result.results
            if r and len(r.critical_issues) > 0
        )
        warning_count = sum(
            1 for r in batch_result.results
            if r and len(r.warning_issues) > 0
        )

        lines.append(f"\n🔍 ISSUE SUMMARY:")
        lines.append(f"🔴 Resources with critical issues: {critical_count}")
        lines.append(f"🟡 Resources with warnings: {warning_count}")
        lines.append(f"✅ Healthy resources: {batch_result.successful - critical_count - warning_count}")

    if batch_result.errors:
        lines.append(f"\n❌ ERRORS:")
        for error in batch_result.errors[:5]:  # Show first 5
            lines.append(f"  • {error.get('resource', 'Unknown')}: {error.get('error', 'Unknown error')}")

        if len(batch_result.errors) > 5:
            lines.append(f"  ... and {len(batch_result.errors) - 5} more errors")

    lines.append("=" * 60)

    return "\n".join(lines)
