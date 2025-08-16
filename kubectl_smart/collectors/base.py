"""
Base collector classes and interfaces

Collectors are responsible for gathering raw data from kubectl commands
in an async, time-bounded manner as specified in the technical requirements.
"""

import asyncio
import json
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from async_timeout import timeout

from ..models import RawBlob, SubjectCtx

logger = structlog.get_logger(__name__)


class CollectorError(Exception):
    """Base exception for collector errors"""
    pass


class TimeoutError(CollectorError):
    """Raised when collector operation times out"""
    pass


class KubectlError(CollectorError):
    """Raised when kubectl command fails"""
    pass


class RBACError(CollectorError):
    """Raised when RBAC permissions are insufficient"""
    pass


class Collector(ABC):
    """Abstract base class for all collectors
    
    Collectors must be time-bounded, async, and return raw data blobs
    without parsing them (parsing is handled by the parsers module).
    """
    
    name: str = "base"
    
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self._kubectl_path: Optional[str] = None
    
    @property
    def kubectl_path(self) -> str:
        """Find and cache kubectl executable path"""
        if self._kubectl_path is None:
            try:
                result = subprocess.run(
                    ['which', 'kubectl'], 
                    capture_output=True, 
                    text=True,
                    check=True
                )
                self._kubectl_path = result.stdout.strip()
            except subprocess.CalledProcessError:
                raise CollectorError("kubectl not found in PATH")
        
        return self._kubectl_path
    
    @abstractmethod
    async def collect(self, subject: SubjectCtx) -> RawBlob:
        """Collect raw data for the given subject
        
        Args:
            subject: The subject context to collect data for
            
        Returns:
            RawBlob containing the raw collected data
            
        Raises:
            CollectorError: When collection fails
            TimeoutError: When collection times out
        """
        pass
    
    async def _run_kubectl(
        self, 
        args: List[str], 
        subject: SubjectCtx,
        output_format: str = "json"
    ) -> Dict[str, any]:
        """Run kubectl command with proper error handling and timeouts
        
        Args:
            args: kubectl command arguments
            subject: Subject context for namespace/context
            output_format: Output format (json, yaml, etc.)
            
        Returns:
            Parsed command output
            
        Raises:
            TimeoutError: When command times out
            KubectlError: When kubectl command fails
            RBACError: When RBAC permissions are insufficient
        """
        cmd = [self.kubectl_path] + args + subject.kubectl_args()
        
        if output_format:
            cmd.extend(['-o', output_format])
        
        logger.debug("Running kubectl command", cmd=cmd, timeout=self.timeout_seconds)
        
        # Simple retry with backoff for transient network/permission glitches
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt < 3:
            try:
                async with timeout(self.timeout_seconds):
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    if process.returncode != 0:
                        error_msg = stderr.decode() if stderr else "Unknown error"
                        lower = error_msg.lower()
                        if any(phrase in lower for phrase in ['forbidden', 'unauthorized', 'access denied', 'rbac', 'permission denied']):
                            raise RBACError(f"RBAC permission denied: {error_msg}")
                        # Retry on transient network/http errors
                        if any(x in lower for x in ['timeout', 'temporarily unavailable', 'i/o timeout', 'connection refused']):
                            raise KubectlError(error_msg)
                        # Non-retryable
                        raise KubectlError(error_msg)
                    output_str = stdout.decode()
                    if output_format == "json" and output_str.strip():
                        try:
                            return json.loads(output_str)
                        except json.JSONDecodeError as e:
                            raise CollectorError(f"Failed to parse kubectl JSON output: {e}")
                    return {"raw": output_str}
            except (KubectlError, asyncio.TimeoutError) as e:
                last_error = e
                attempt += 1
                await asyncio.sleep(0.5 * attempt)
                continue
            except (CollectorError, RBACError):
                raise
        # Exhausted retries
        if isinstance(last_error, asyncio.TimeoutError):
            raise TimeoutError(f"kubectl command timed out after {self.timeout_seconds}s (retries exhausted)")
        if isinstance(last_error, KubectlError):
            raise last_error
        raise CollectorError("kubectl command failed (retries exhausted)")
    
    def _create_blob(self, data: any, content_type: str = "application/json") -> RawBlob:
        """Create a RawBlob from collected data"""
        return RawBlob(
            data=data,
            source=self.name,
            content_type=content_type,
            timestamp=datetime.utcnow()
        )


class KubectlGet(Collector):
    """Collector for kubectl get commands"""
    
    name = "kubectl_get"
    
    def __init__(self, resource_type: str, timeout_seconds: float = 10.0):
        super().__init__(timeout_seconds)
        self.resource_type = resource_type
    
    async def collect(self, subject: SubjectCtx) -> RawBlob:
        """Collect resource data using kubectl get"""
        try:
            list_types = {'secrets', 'ingresses', 'persistentvolumeclaims', 'persistentvolumes'}
            if self.resource_type in list_types:
                # Namespace/cluster scope listing for forecasting needs
                args = ['get', self.resource_type]
            else:
                if subject.name:
                    # Get specific resource
                    args = ['get', self.resource_type, subject.name]
                else:
                    # Get all resources of this type
                    args = ['get', self.resource_type]
            
            data = await self._run_kubectl(args, subject)
            return self._create_blob(data)
            
        except Exception as e:
            logger.warning(
                "Failed to collect resource data",
                resource_type=self.resource_type,
                subject=subject.full_name,
                error=str(e)
            )
            # Return empty blob on failure for graceful degradation
            return self._create_blob({}, "application/json")


class KubectlDescribe(Collector):
    """Collector for kubectl describe commands"""
    
    name = "kubectl_describe"
    
    def __init__(self, resource_type: str, timeout_seconds: float = 10.0):
        super().__init__(timeout_seconds)
        self.resource_type = resource_type
    
    async def collect(self, subject: SubjectCtx) -> RawBlob:
        """Collect detailed resource description"""
        try:
            args = ['describe', self.resource_type, subject.name]
            # describe output is not JSON, so get raw text
            data = await self._run_kubectl(args, subject, output_format="")
            return self._create_blob(data, "text/plain")
            
        except Exception as e:
            logger.warning(
                "Failed to describe resource",
                resource_type=self.resource_type,
                subject=subject.full_name,
                error=str(e)
            )
            return self._create_blob({}, "text/plain")


class KubectlEvents(Collector):
    """Collector for kubectl events"""
    
    name = "kubectl_events"
    
    async def collect(self, subject: SubjectCtx) -> RawBlob:
        """Collect events, optionally filtered by resource"""
        try:
            args = ['get', 'events', '--sort-by=.lastTimestamp']
            
            # Add field selector for specific resource if provided
            if subject.name and subject.kind:
                field_selector = f"involvedObject.name={subject.name},involvedObject.kind={subject.kind.value}"
                args.extend(['--field-selector', field_selector])
            
            data = await self._run_kubectl(args, subject)
            return self._create_blob(data)
            
        except Exception as e:
            logger.warning(
                "Failed to collect events",
                subject=subject.full_name,
                error=str(e)
            )
            return self._create_blob({}, "application/json")


class KubectlLogs(Collector):
    """Collector for kubectl logs"""
    
    name = "kubectl_logs"
    
    def __init__(self, tail_lines: int = 100, timeout_seconds: float = 10.0):
        super().__init__(timeout_seconds)
        self.tail_lines = tail_lines
    
    async def collect(self, subject: SubjectCtx) -> RawBlob:
        """Collect pod logs"""
        try:
            # Only works for pods
            if subject.kind.value != "Pod":
                return self._create_blob({}, "text/plain")
            
            args = ['logs', subject.name, f'--tail={self.tail_lines}']
            data = await self._run_kubectl(args, subject, output_format="")
            return self._create_blob(data, "text/plain")
            
        except Exception as e:
            logger.warning(
                "Failed to collect logs",
                subject=subject.full_name,
                error=str(e)
            )
            return self._create_blob({}, "text/plain")


class MetricsServer(Collector):
    """Collector for metrics-server data"""
    
    name = "metrics_server"
    
    async def collect(self, subject: SubjectCtx) -> RawBlob:
        """Collect metrics from metrics-server"""
        try:
            if subject.kind.value == "Pod":
                args = ['top', 'pod', subject.name]
            elif subject.kind.value == "Node":
                args = ['top', 'node', subject.name]
            else:
                # For other resources, collect namespace-wide metrics
                args = ['top', 'pods']
            
            data = await self._run_kubectl(args, subject, output_format="")
            return self._create_blob(data, "text/plain")
            
        except Exception as e:
            logger.info(
                "Metrics server not available or accessible",
                subject=subject.full_name,
                error=str(e)
            )
            # Metrics server is optional, return empty blob
            return self._create_blob({}, "text/plain")


class KubeletMetricsScrape(Collector):
    """Collector that scrapes kubelet Prometheus metrics via kubectl raw proxy
    
    Targets per-node endpoint: /api/v1/nodes/<node>/proxy/metrics
    Returns concatenated Prometheus text for parsing.
    """

    name = "kubelet_metrics"

    async def collect(self, subject: SubjectCtx) -> RawBlob:
        try:
            # First get list of nodes; avoid namespace/context flags interfering with --raw
            from ..models import SubjectCtx as _SC
            subject_no_ns = _SC(kind=subject.kind, name=subject.name, context=subject.context, scope=subject.scope)
            # list nodes cluster-wide
            nodes_json = await self._run_kubectl(['get', 'nodes'], subject_no_ns, output_format="json")
            items = nodes_json.get('items', []) if isinstance(nodes_json, dict) else []

            combined = []
            for item in items:
                node_name = item.get('metadata', {}).get('name')
                if not node_name:
                    continue
                # Use kubectl raw to fetch kubelet metrics
                # Note: --raw returns plain text
                try:
                    data = await self._run_kubectl(['get', '--raw', f"/api/v1/nodes/{node_name}/proxy/metrics"], subject_no_ns, output_format="")
                    raw_text = data.get('raw', '') if isinstance(data, dict) else ''
                    if raw_text:
                        combined.append(f"# node={node_name}\n" + raw_text)
                except RBACError:
                    # Skip quietly when forbidden
                    continue
                except Exception as e:
                    logger.info("Failed to scrape kubelet metrics for node", node=node_name, error=str(e))

            return self._create_blob("\n".join(combined), "text/plain")

        except Exception as e:
            logger.info("Kubelet metrics scrape unavailable", error=str(e))
            return self._create_blob("", "text/plain")

class CollectorRegistry:
    """Registry for managing and creating collectors"""
    
    def __init__(self):
        self._collectors = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """Register default collectors"""
        self._collectors.update({
            'get': KubectlGet,
            'describe': KubectlDescribe,
            'events': KubectlEvents,
            'logs': KubectlLogs,
            'metrics': MetricsServer,
            'kubelet': KubeletMetricsScrape,
        })
    
    def register(self, name: str, collector_class: type):
        """Register a custom collector"""
        self._collectors[name] = collector_class
    
    def create(self, name: str, **kwargs) -> Collector:
        """Create a collector instance"""
        if name not in self._collectors:
            raise ValueError(f"Unknown collector: {name}")
        
        return self._collectors[name](**kwargs)
    
    def get_collectors_for_command(self, command: str) -> List[str]:
        """Get recommended collectors for a specific command"""
        collectors_map = {
            'diag': ['get', 'describe', 'events', 'logs'],
            'graph': ['get', 'describe'],
            'top': ['get', 'metrics'],
        }
        return collectors_map.get(command, ['get'])


# Global registry instance
registry = CollectorRegistry()