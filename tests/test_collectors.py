"""Tests for kubectl_smart/collectors/base.py"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubectl_smart.collectors.base import (
    Collector,
    CollectorError,
    CollectorRegistry,
    KubectlDescribe,
    KubectlError,
    KubectlEvents,
    KubectlGet,
    KubectlLogs,
    KubeletMetricsScrape,
    MetricsServer,
    RBACError,
    TimeoutError,
    TransientKubectlError,
    registry,
)
from kubectl_smart.models import RawBlob, ResourceKind, SubjectCtx


class TestCollectorExceptions:
    """Tests for collector exception classes"""

    def test_collector_error(self):
        """Test CollectorError is raised properly"""
        with pytest.raises(CollectorError):
            raise CollectorError("Test error")

    def test_timeout_error_is_collector_error(self):
        """Test TimeoutError is a subclass of CollectorError"""
        assert issubclass(TimeoutError, CollectorError)

    def test_kubectl_error_is_collector_error(self):
        """Test KubectlError is a subclass of CollectorError"""
        assert issubclass(KubectlError, CollectorError)

    def test_transient_kubectl_error_is_kubectl_error(self):
        """Test transient errors are a retryable KubectlError subclass."""
        assert issubclass(TransientKubectlError, KubectlError)

    def test_rbac_error_is_collector_error(self):
        """Test RBACError is a subclass of CollectorError"""
        assert issubclass(RBACError, CollectorError)


class TestCollectorBase:
    """Tests for base Collector class"""

    def test_collector_init_default_timeout(self):
        """Test Collector initializes with default timeout"""
        collector = KubectlGet(resource_type="pod")
        assert collector.timeout_seconds == 10.0

    def test_collector_init_custom_timeout(self):
        """Test Collector initializes with custom timeout"""
        collector = KubectlGet(resource_type="pod", timeout_seconds=30.0)
        assert collector.timeout_seconds == 30.0

    @patch("subprocess.run")
    def test_collector_kubectl_path_found(self, mock_run):
        """Test kubectl path is found correctly"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        collector = KubectlGet(resource_type="pod")
        path = collector.kubectl_path
        assert path == "/usr/local/bin/kubectl"

    @patch("subprocess.run")
    def test_collector_kubectl_path_not_found(self, mock_run):
        """Test kubectl path not found raises error"""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "which")
        collector = KubectlGet(resource_type="pod")
        with pytest.raises(CollectorError, match="kubectl not found"):
            _ = collector.kubectl_path

    @patch("subprocess.run")
    def test_collector_kubectl_path_cached(self, mock_run):
        """Test kubectl path is cached after first lookup"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        collector = KubectlGet(resource_type="pod")
        path1 = collector.kubectl_path
        path2 = collector.kubectl_path
        assert path1 == path2
        # Should only call subprocess once due to caching
        assert mock_run.call_count == 1

    def test_create_blob(self):
        """Test _create_blob creates proper RawBlob"""
        collector = KubectlGet(resource_type="pod")
        blob = collector._create_blob({"test": "data"})
        assert isinstance(blob, RawBlob)
        assert blob.data == {"test": "data"}
        assert blob.source == "kubectl_get"
        assert blob.content_type == "application/json"

    def test_create_blob_text_content(self):
        """Test _create_blob with text content type"""
        collector = KubectlDescribe(resource_type="pod")
        blob = collector._create_blob("describe output", "text/plain")
        assert blob.content_type == "text/plain"
        assert blob.data == "describe output"

    def test_create_failure_blob_records_rbac_gap(self):
        """Test failures preserve collector and RBAC evidence in metadata."""
        collector = KubectlLogs()
        subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
        blob = collector._create_failure_blob(
            {},
            "text/plain",
            RBACError("User cannot get pods/log"),
            subject,
            operation="logs",
            resource_type="pods",
        )

        assert blob.metadata["data_gap"] is True
        assert blob.metadata["category"] == "rbac"
        assert blob.metadata["collector"] == "kubectl_logs"
        assert blob.metadata["suggested_action"] == (
            "kubectl auth can-i get pods --subresource=log -n default"
        )


class TestKubectlGet:
    """Tests for KubectlGet collector"""

    def test_kubectl_get_name(self):
        """Test KubectlGet has correct name"""
        collector = KubectlGet(resource_type="pod")
        assert collector.name == "kubectl_get"

    def test_kubectl_get_resource_type(self):
        """Test KubectlGet stores resource type"""
        collector = KubectlGet(resource_type="deployment")
        assert collector.resource_type == "deployment"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_kubectl_get_collect_success(self, mock_run, mock_exec):
        """Test KubectlGet collect returns data on success"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b'{"kind": "Pod", "metadata": {"name": "test"}}',
            b"",
        )
        mock_exec.return_value = mock_process

        collector = KubectlGet(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        blob = await collector.collect(subject)

        assert isinstance(blob, RawBlob)
        assert blob.source == "kubectl_get"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_kubectl_get_collect_failure_returns_empty(self, mock_run, mock_exec):
        """Test KubectlGet collect returns empty blob on failure"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"resource not found")
        mock_exec.return_value = mock_process

        collector = KubectlGet(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="missing-pod", namespace="default"
        )
        blob = await collector.collect(subject)

        assert blob.data == {}

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_kubectl_get_list_types(self, mock_run, mock_exec):
        """Test KubectlGet uses list mode for specific resource types"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'{"kind": "List", "items": []}', b"")
        mock_exec.return_value = mock_process

        collector = KubectlGet(resource_type="secrets")
        subject = SubjectCtx(
            kind=ResourceKind.SECRET, name="test-secret", namespace="default"
        )
        await collector.collect(subject)

        # Verify that the command was called (actual args checking would need more setup)
        assert mock_exec.called


class TestKubectlDescribe:
    """Tests for KubectlDescribe collector"""

    def test_kubectl_describe_name(self):
        """Test KubectlDescribe has correct name"""
        collector = KubectlDescribe(resource_type="pod")
        assert collector.name == "kubectl_describe"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_kubectl_describe_collect(self, mock_run, mock_exec):
        """Test KubectlDescribe collect returns text data"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Name: test-pod\nStatus: Running", b"")
        mock_exec.return_value = mock_process

        collector = KubectlDescribe(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        blob = await collector.collect(subject)

        assert blob.content_type == "text/plain"


class TestKubectlEvents:
    """Tests for KubectlEvents collector"""

    def test_kubectl_events_name(self):
        """Test KubectlEvents has correct name"""
        collector = KubectlEvents()
        assert collector.name == "kubectl_events"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_kubectl_events_collect_with_filter(self, mock_run, mock_exec):
        """Test KubectlEvents collect with resource filter"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'{"kind": "List", "items": []}', b"")
        mock_exec.return_value = mock_process

        collector = KubectlEvents()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        blob = await collector.collect(subject)

        assert blob.source == "kubectl_events"


class TestKubectlLogs:
    """Tests for KubectlLogs collector"""

    def test_kubectl_logs_name(self):
        """Test KubectlLogs has correct name"""
        collector = KubectlLogs()
        assert collector.name == "kubectl_logs"

    def test_kubectl_logs_tail_lines(self):
        """Test KubectlLogs stores tail_lines"""
        collector = KubectlLogs(tail_lines=50)
        assert collector.tail_lines == 50

    @pytest.mark.asyncio
    async def test_kubectl_logs_non_pod_returns_empty(self):
        """Test KubectlLogs returns empty for non-pod resources"""
        collector = KubectlLogs()
        subject = SubjectCtx(
            kind=ResourceKind.DEPLOYMENT, name="test-deploy", namespace="default"
        )
        blob = await collector.collect(subject)
        assert blob.data == {}


class TestMetricsServer:
    """Tests for MetricsServer collector"""

    def test_metrics_server_name(self):
        """Test MetricsServer has correct name"""
        collector = MetricsServer()
        assert collector.name == "metrics_server"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_metrics_server_collect_pod(self, mock_run, mock_exec):
        """Test MetricsServer collect for pod"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b"NAME       CPU(cores)   MEMORY(bytes)\ntest-pod   100m         256Mi",
            b"",
        )
        mock_exec.return_value = mock_process

        collector = MetricsServer()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        blob = await collector.collect(subject)

        assert blob.content_type == "text/plain"


class TestKubeletMetricsScrape:
    """Tests for KubeletMetricsScrape collector"""

    def test_kubelet_metrics_name(self):
        """Test KubeletMetricsScrape has correct name"""
        collector = KubeletMetricsScrape()
        assert collector.name == "kubelet_metrics"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_kubelet_metrics_collect_empty_on_failure(self, mock_run, mock_exec):
        """Test KubeletMetricsScrape returns empty on failure"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"error")
        mock_exec.return_value = mock_process

        collector = KubeletMetricsScrape()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        blob = await collector.collect(subject)

        assert blob.content_type == "text/plain"


class TestCollectorRegistry:
    """Tests for CollectorRegistry"""

    def test_registry_default_collectors(self):
        """Test registry has default collectors registered"""
        reg = CollectorRegistry()
        assert "get" in reg._collectors
        assert "describe" in reg._collectors
        assert "events" in reg._collectors
        assert "logs" in reg._collectors
        assert "metrics" in reg._collectors
        assert "kubelet" in reg._collectors

    def test_registry_register_custom_collector(self):
        """Test registering custom collector"""
        reg = CollectorRegistry()

        class CustomCollector(Collector):
            name = "custom"

            async def collect(self, subject):
                return self._create_blob({})

        reg.register("custom", CustomCollector)
        assert "custom" in reg._collectors

    def test_registry_create_collector(self):
        """Test creating collector from registry"""
        reg = CollectorRegistry()
        collector = reg.create("get", resource_type="pod")
        assert isinstance(collector, KubectlGet)
        assert collector.resource_type == "pod"

    def test_registry_create_unknown_raises(self):
        """Test creating unknown collector raises ValueError"""
        reg = CollectorRegistry()
        with pytest.raises(ValueError, match="Unknown collector"):
            reg.create("nonexistent")

    def test_registry_get_collectors_for_command_diag(self):
        """Test get_collectors_for_command for diag"""
        reg = CollectorRegistry()
        collectors = reg.get_collectors_for_command("diag")
        assert "get" in collectors
        assert "describe" in collectors
        assert "events" in collectors
        assert "logs" in collectors

    def test_registry_get_collectors_for_command_graph(self):
        """Test get_collectors_for_command for graph"""
        reg = CollectorRegistry()
        collectors = reg.get_collectors_for_command("graph")
        assert "get" in collectors
        assert "describe" in collectors

    def test_registry_get_collectors_for_command_top(self):
        """Test get_collectors_for_command for top"""
        reg = CollectorRegistry()
        collectors = reg.get_collectors_for_command("top")
        assert "get" in collectors
        assert "metrics" in collectors

    def test_registry_get_collectors_for_unknown_command(self):
        """Test get_collectors_for_command for unknown command"""
        reg = CollectorRegistry()
        collectors = reg.get_collectors_for_command("unknown")
        assert collectors == ["get"]


class TestGlobalRegistry:
    """Tests for global registry instance"""

    def test_global_registry_exists(self):
        """Test global registry is available"""
        assert registry is not None
        assert isinstance(registry, CollectorRegistry)


class TestRunKubectl:
    """Tests for _run_kubectl method"""

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_run_kubectl_rbac_error(self, mock_run, mock_exec):
        """Test _run_kubectl raises RBACError on permission denied"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (
            b"",
            b"Error: forbidden - user cannot list pods",
        )
        mock_exec.return_value = mock_process

        collector = KubectlGet(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )

        with pytest.raises(RBACError):
            await collector._run_kubectl(["get", "pods"], subject)

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_run_kubectl_non_retryable_error_fails_fast(self, mock_run, mock_exec):
        """Test non-transient kubectl failures are not retried."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (
            b"",
            b"Error from server (BadRequest): container is waiting to start",
        )
        mock_exec.return_value = mock_process

        collector = KubectlLogs()
        subject = SubjectCtx(kind=ResourceKind.POD, name="test-pod", namespace="default")

        with pytest.raises(KubectlError):
            await collector._run_kubectl(["logs", "test-pod"], subject, output_format="")
        assert mock_exec.call_count == 1

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_run_kubectl_transient_error_retries(self, mock_run, mock_exec, _mock_sleep):
        """Test transient kubectl failures are retried."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        fail_process = AsyncMock()
        fail_process.returncode = 1
        fail_process.communicate.return_value = (b"", b"i/o timeout")
        ok_process = AsyncMock()
        ok_process.returncode = 0
        ok_process.communicate.return_value = (b'{"kind": "List", "items": []}', b"")
        mock_exec.side_effect = [fail_process, ok_process]

        collector = KubectlGet(resource_type="pods")
        subject = SubjectCtx(kind=ResourceKind.POD, name="", namespace="default")

        result = await collector._run_kubectl(["get", "pods"], subject)
        assert result["kind"] == "List"
        assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_run_kubectl_json_parse_error(self, mock_run, mock_exec):
        """Test _run_kubectl raises error on invalid JSON"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"not json", b"")
        mock_exec.return_value = mock_process

        collector = KubectlGet(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )

        with pytest.raises(CollectorError, match="Failed to parse"):
            await collector._run_kubectl(["get", "pods"], subject)

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_run_kubectl_empty_output(self, mock_run, mock_exec):
        """Test _run_kubectl handles empty output"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")
        mock_exec.return_value = mock_process

        collector = KubectlGet(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )

        result = await collector._run_kubectl(["get", "pods"], subject)
        assert result == {"raw": ""}

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("subprocess.run")
    async def test_run_kubectl_raw_format(self, mock_run, mock_exec):
        """Test _run_kubectl with non-json output format"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/usr/local/bin/kubectl\n", stderr=""
        )
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"plain text output", b"")
        mock_exec.return_value = mock_process

        collector = KubectlDescribe(resource_type="pod")
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )

        result = await collector._run_kubectl(
            ["describe", "pod", "test-pod"], subject, output_format=""
        )
        assert result == {"raw": "plain text output"}
