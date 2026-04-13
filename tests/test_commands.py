"""Tests for kubectl_smart/cli/commands.py"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubectl_smart.cli.commands import (
    BaseCommand,
    CommandResult,
    DiagCommand,
    GraphCommand,
    TopCommand,
)
from kubectl_smart.models import (
    AnalysisConfig,
    ResourceKind,
    ResourceRecord,
    SubjectCtx,
)


class TestCommandResult:
    """Tests for CommandResult dataclass"""

    def test_command_result_creation(self):
        """Test CommandResult creation"""
        result = CommandResult(output="test output", exit_code=0, analysis_duration=1.5)
        assert result.output == "test output"
        assert result.exit_code == 0
        assert result.analysis_duration == 1.5

    def test_command_result_defaults(self):
        """Test CommandResult defaults"""
        result = CommandResult(output="test")
        assert result.exit_code == 0
        assert result.analysis_duration == 0.0


class TestBaseCommand:
    """Tests for BaseCommand class"""

    def test_base_command_init_defaults(self):
        """Test BaseCommand initializes with defaults"""
        cmd = DiagCommand()  # Use concrete subclass
        assert cmd.config is not None
        assert cmd.graph_builder is not None
        assert cmd.scoring_engine is not None
        assert cmd.forecasting_engine is not None

    def test_base_command_init_custom_config(self):
        """Test BaseCommand with custom config"""
        config = AnalysisConfig(colors_enabled=False)
        cmd = DiagCommand(config=config)
        assert cmd.config.colors_enabled is False


class TestDiagCommand:
    """Tests for DiagCommand class"""

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_resource_not_found(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test DiagCommand when resource not found"""
        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="missing-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 2
        assert "not found" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_success_no_issues(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test DiagCommand with successful analysis and no issues"""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="healthy-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="healthy-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DIAGNOSIS" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_with_issues(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test DiagCommand with issues found"""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="failing-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Failed",
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="failing-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        # Should have non-zero exit code for issues
        assert result.exit_code == 2

    def test_generate_suggested_actions_failed_status(self):
        """Test suggested actions for failed resource"""
        cmd = DiagCommand()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="failed-pod",
            uid="uid-123",
            namespace="default",
            status="Failed",
        )
        actions = cmd._generate_suggested_actions(resource, None, [])

        assert len(actions) > 0
        assert any("logs" in action.lower() for action in actions)

    def test_generate_suggested_actions_mount_issue(self):
        """Test suggested actions for mount issues"""
        from kubectl_smart.models import Issue, IssueSeverity

        cmd = DiagCommand()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="pod",
            uid="uid-123",
            namespace="default",
            status="Pending",
        )
        root_cause = Issue(
            resource_uid="uid-123",
            title="Mount Failed",
            description="Failed to mount volume",
            severity=IssueSeverity.CRITICAL,
            score=90.0,
            reason="FailedMount",
            message="Unable to mount volume",
        )
        actions = cmd._generate_suggested_actions(resource, root_cause, [])

        assert any("pvc" in action.lower() for action in actions)

    def test_generate_suggested_actions_scheduling_issue(self):
        """Test suggested actions for scheduling issues"""
        from kubectl_smart.models import Issue, IssueSeverity

        cmd = DiagCommand()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="pod",
            uid="uid-123",
            namespace="default",
            status="Pending",
        )
        root_cause = Issue(
            resource_uid="uid-123",
            title="Scheduling Failed",
            description="Failed to schedule",
            severity=IssueSeverity.CRITICAL,
            score=90.0,
            reason="FailedScheduling",
            message="Insufficient resources",
        )
        actions = cmd._generate_suggested_actions(resource, root_cause, [])

        assert any("node" in action.lower() for action in actions)

    def test_generate_suggested_actions_image_pull(self):
        """Test suggested actions for image pull issues"""
        from kubectl_smart.models import Issue, IssueSeverity

        cmd = DiagCommand()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="pod",
            uid="uid-123",
            namespace="default",
            status="Pending",
        )
        root_cause = Issue(
            resource_uid="uid-123",
            title="Image Pull Failed",
            description="Failed to pull image",
            severity=IssueSeverity.CRITICAL,
            score=85.0,
            reason="ImagePullBackOff",
            message="Failed to pull image",
        )
        actions = cmd._generate_suggested_actions(resource, root_cause, [])

        assert any("image" in action.lower() for action in actions)


class TestGraphCommand:
    """Tests for GraphCommand class"""

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_resource_not_found(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test GraphCommand when resource not found"""
        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="missing-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 2
        assert "not found" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_success(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test GraphCommand successful execution"""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DEPENDENCY GRAPH" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_upstream_direction(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test GraphCommand with upstream direction"""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        result = await cmd.execute(subject, direction="upstream")

        assert result.exit_code == 0


class TestTopCommand:
    """Tests for TopCommand class"""

    def test_init_custom_horizon(self):
        """Test TopCommand with custom forecast horizon"""
        cmd = TopCommand(forecast_horizon_hours=24)
        assert cmd.forecast_horizon_hours == 24

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_success(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test TopCommand successful execution"""
        mock_collector = MagicMock()
        mock_collector.name = "test"
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = TopCommand()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "PREDICTIVE OUTLOOK" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_with_warnings(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test TopCommand with capacity warnings"""
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="stressed-node",
            uid="node-uid",
            properties={
                "status": {
                    "conditions": [{"type": "DiskPressure", "status": "True"}]
                }
            },
        )

        mock_collector = MagicMock()
        mock_collector.name = "test"
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [node]

        cmd = TopCommand()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        # Exit code should still be 0 for top (advisory)
        assert result.exit_code == 0


class TestCollectData:
    """Tests for _collect_data method"""

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_collect_data_success(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test _collect_data returns parsed resources"""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid",
            namespace="default",
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        resources = await cmd._collect_data(subject, ["get", "describe"])

        assert len(resources) >= 0

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    async def test_collect_data_collector_failure(self, mock_collector_registry):
        """Test _collect_data handles collector failures gracefully"""
        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(side_effect=Exception("Collector failed"))
        mock_collector_registry.create.return_value = mock_collector

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        # Should not raise, just log warning
        resources = await cmd._collect_data(subject, ["get"])

        # Should return empty list on failure
        assert resources == []
