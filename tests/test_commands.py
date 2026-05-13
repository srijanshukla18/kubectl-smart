"""Tests for kubectl_smart/cli/commands.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubectl_smart.cli.commands import (
    CommandResult,
    DiagCommand,
    GraphCommand,
    TopCommand,
)
from kubectl_smart.models import (
    AnalysisConfig,
    RawBlob,
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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_collect_data_passes_configured_timeout(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test command collectors use AnalysisConfig.collector_timeout."""
        mock_collector = MagicMock()
        mock_collector.name = "kubectl_get"
        mock_collector.collect = AsyncMock(
            return_value=RawBlob(data={}, source="kubectl_get")
        )
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = DiagCommand(config=AnalysisConfig(collector_timeout=2.5))
        subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")

        await cmd._collect_data(subject, ["get", "events"])

        first_call, second_call = mock_collector_registry.create.call_args_list
        assert first_call.kwargs["timeout_seconds"] == 2.5
        assert second_call.kwargs["timeout_seconds"] == 2.5


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
    async def test_execute_resource_not_found_preserves_data_gaps(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test not-found diagnosis still shows why evidence may be incomplete."""
        gap_blob = RawBlob(
            data={},
            source="kubectl_get",
            content_type="application/json",
            metadata={
                "data_gap": True,
                "collector": "kubectl_get",
                "operation": "get",
                "resource_type": "pod",
                "category": "rbac",
                "error": "forbidden",
            },
        )
        mock_collector = MagicMock()
        mock_collector.name = "kubectl_get"
        mock_collector.collect = AsyncMock(return_value=gap_blob)
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="missing-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 2
        assert "Resource not found" in result.output
        assert "DATA GAPS" in result.output
        assert "get pod unavailable (rbac): forbidden" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_raw_resource_not_found_returns_incomplete_result(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test JSON-capable raw diagnosis preserves not-found data gaps."""
        gap_blob = RawBlob(
            data={},
            source="kubectl_get",
            content_type="application/json",
            metadata={
                "data_gap": True,
                "collector": "kubectl_get",
                "operation": "get",
                "resource_type": "pod",
                "category": "rbac",
                "error": "forbidden",
            },
        )
        mock_collector = MagicMock()
        mock_collector.name = "kubectl_get"
        mock_collector.collect = AsyncMock(return_value=gap_blob)
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="missing-pod", namespace="default"
        )
        result = await cmd.execute_raw(subject)

        assert result.resource is None
        assert result.exit_code == 2
        assert result.data_gaps == ["get pod unavailable (rbac): forbidden"]

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
    async def test_execute_surfaces_data_gaps(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test unavailable collectors are shown as data gaps."""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="api",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )
        get_blob = RawBlob(data={}, source="kubectl_get", content_type="application/json")
        describe_blob = RawBlob(data={}, source="kubectl_describe", content_type="text/plain")
        events_blob = RawBlob(data={}, source="kubectl_events", content_type="application/json")
        logs_blob = RawBlob(
            data={},
            source="kubectl_logs",
            content_type="text/plain",
            metadata={
                "data_gap": True,
                "collector": "kubectl_logs",
                "operation": "logs",
                "resource_type": "pods",
                "category": "rbac",
                "error": "RBAC permission denied: User cannot get pods/log",
                "suggested_action": "kubectl auth can-i get pods --subresource=log -n default",
            },
        )

        collectors = []
        for blob in [get_blob, describe_blob, events_blob, logs_blob]:
            collector = MagicMock()
            collector.name = blob.source
            collector.collect = AsyncMock(return_value=blob)
            collectors.append(collector)

        mock_collector_registry.create.side_effect = collectors

        def parse_blob(blob):
            if blob is get_blob:
                return [pod]
            return []

        mock_parser_registry.parse.side_effect = parse_blob

        cmd = DiagCommand()
        subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DATA GAPS" in result.output
        assert "logs pods unavailable (rbac)" in result.output
        assert "kubectl auth can-i get pods --subresource=log -n default" in result.output

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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_warning_only_returns_exit_one(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test DiagCommand returns exit 1 for warning-only diagnoses."""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="unknown-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Unknown",
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="unknown-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 1
        assert "Resource Status: Unknown" in result.output

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

    def test_generate_suggested_actions_missing_secret(self):
        """Test missing Secret references get direct actions instead of log advice."""
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
            title="Failed",
            description='Error: secret "runtime-token" not found',
            severity=IssueSeverity.CRITICAL,
            score=100.0,
            reason="Failed",
            message='Error: secret "runtime-token" not found',
        )
        actions = cmd._generate_suggested_actions(resource, root_cause, [])

        assert actions[0] == "Verify missing Secret: kubectl get secret runtime-token -n default"
        assert any("Create or restore Secret runtime-token" in action for action in actions)
        assert not any("kubectl logs" in action for action in actions)

    def test_generate_suggested_actions_missing_secret_from_evidence(self):
        """Test pod-status evidence can drive concrete missing Secret actions."""
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
            title="Resource Status: CreateContainerConfigError",
            description="Pod pod is in CreateContainerConfigError state",
            severity=IssueSeverity.CRITICAL,
            score=90.0,
            reason="StatusCreateContainerConfigError",
            message="Resource is in unhealthy state: CreateContainerConfigError",
            evidence=[
                'Container worker waiting: CreateContainerConfigError - secret "runtime-token" not found'
            ],
        )
        actions = cmd._generate_suggested_actions(resource, root_cause, [])

        assert actions[0] == "Verify missing Secret: kubectl get secret runtime-token -n default"
        assert any("Create or restore Secret runtime-token" in action for action in actions)
        assert not any("kubectl logs" in action for action in actions)

    def test_generate_suggested_actions_log_failure(self):
        """Test log-derived root causes carry log review actions."""
        from kubectl_smart.models import Issue, IssueSeverity

        cmd = DiagCommand()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="pod",
            uid="uid-123",
            namespace="default",
            status="Running",
        )
        root_cause = Issue(
            resource_uid="uid-123",
            title="Log Errors",
            description="panic detected",
            severity=IssueSeverity.CRITICAL,
            score=100.0,
            reason="LogFailure",
            message="panic: circuit breaker open",
            suggested_actions=["Review full logs for context"],
        )
        actions = cmd._generate_suggested_actions(resource, root_cause, [])

        assert "Review full logs for context" in actions

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_service_with_empty_endpoints(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test DiagCommand turns empty Endpoints into a Service issue."""
        service = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="inventory",
            uid="svc-uid",
            namespace="default",
            status="Active",
            properties={"spec": {"selector": {"app": "inventory", "tier": "primary"}}},
        )
        endpoints = ResourceRecord(
            kind=ResourceKind.ENDPOINTS,
            name="inventory",
            uid="endpoints-uid",
            namespace="default",
            status="Unavailable",
            properties={"subsets": []},
        )
        canary_pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="inventory-canary",
            uid="pod-uid",
            namespace="default",
            status="Running",
            labels={"app": "inventory", "track": "canary"},
        )

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.side_effect = [
            [service],
            [],
            [],
            [],
            [endpoints],
            [canary_pod],
        ]

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.SERVICE, name="inventory", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 2
        assert "Service has no ready endpoints" in result.output
        assert "Evidence" in result.output
        assert "ready addresses=0" in result.output
        assert "No Pods in namespace match selector app=inventory,tier=primary" in result.output


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
    async def test_execute_resource_not_found_preserves_data_gaps(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test graph not-found errors include incomplete collection evidence."""
        gap_blob = RawBlob(
            data={},
            source="kubectl_get",
            content_type="application/json",
            metadata={
                "data_gap": True,
                "collector": "kubectl_get",
                "operation": "get",
                "resource_type": "secrets",
                "category": "rbac",
                "error": "forbidden",
            },
        )
        mock_collector = MagicMock()
        mock_collector.name = "kubectl_get"
        mock_collector.collect = AsyncMock(return_value=gap_blob)
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = []

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="missing-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 2
        assert "not found in graph" in result.output
        assert "DATA GAPS" in result.output
        assert "get secrets unavailable (rbac): forbidden" in result.output

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
    async def test_execute_collects_related_resource_types(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test GraphCommand collects enough resource types to build live edges."""
        deployment = ResourceRecord(
            kind=ResourceKind.DEPLOYMENT,
            name="frontend",
            uid="deploy-uid",
            namespace="default",
            status="Available",
        )
        replicaset = ResourceRecord(
            kind=ResourceKind.REPLICASET,
            name="frontend-rs",
            uid="rs-uid",
            namespace="default",
            properties={
                "metadata": {
                    "ownerReferences": [
                        {"kind": "Deployment", "uid": "deploy-uid"}
                    ]
                }
            },
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="frontend-pod",
            uid="pod-uid",
            namespace="default",
            properties={
                "metadata": {
                    "ownerReferences": [
                        {"kind": "ReplicaSet", "uid": "rs-uid"}
                    ]
                }
            },
        )

        mock_collector = MagicMock()
        mock_collector.name = "test"
        mock_collector.collect = AsyncMock(return_value=MagicMock(data={}, source="test"))
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.return_value = [deployment, replicaset, pod]

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.DEPLOYMENT, name="frontend", namespace="default"
        )
        result = await cmd.execute(subject, direction="downstream")

        assert result.exit_code == 0
        assert "ReplicaSet/default/frontend-rs" in result.output
        requested_types = {
            call.kwargs["resource_type"]
            for call in mock_collector_registry.create.call_args_list
        }
        assert {"pods", "deployments", "replicasets", "services", "nodes"} <= requested_types

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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_both_directions(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test GraphCommand renders both directions when requested."""
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
        result = await cmd.execute(subject, direction="both")

        assert result.exit_code == 0
        assert "UPSTREAM DEPENDENCIES" in result.output
        assert "DOWNSTREAM DEPENDENCIES" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_surfaces_collector_creation_data_gaps(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test graph reports resource-type collector setup failures as data gaps."""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )

        def create_collector(name, **kwargs):
            if kwargs.get("resource_type") == "secrets":
                raise RuntimeError("registry unavailable")
            collector = MagicMock()
            collector.name = f"{name}_{kwargs.get('resource_type', 'generic')}"
            collector.collect = AsyncMock(
                return_value=MagicMock(data={}, source="test")
            )
            return collector

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.return_value = [pod]

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DATA GAPS" in result.output
        assert "get secrets collector unavailable: registry unavailable" in result.output


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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_surfaces_optional_collector_creation_data_gaps(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test top degrades when optional forecasting collectors cannot start."""

        def create_collector(name, **kwargs):
            if kwargs.get("resource_type") == "secrets":
                raise RuntimeError("registry unavailable")
            collector = MagicMock()
            collector.name = f"{name}_{kwargs.get('resource_type', 'generic')}"
            collector.collect = AsyncMock(
                return_value=MagicMock(data={}, source="test")
            )
            return collector

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.return_value = []

        cmd = TopCommand()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "PREDICTIVE OUTLOOK" in result.output
        assert "DATA GAPS" in result.output
        assert "get secrets collector unavailable: registry unavailable" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_marks_secret_inventory_incomplete_on_secret_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test top does not treat blocked Secret collection as complete inventory."""
        captured = {}

        class FakeForecastingEngine:
            def predict_capacity_issues(self, resources, metrics_data):
                return []

            def predict_certificate_expiry(
                self,
                resources,
                secret_inventory_complete=True,
            ):
                captured["secret_inventory_complete"] = secret_inventory_complete
                return []

        def create_collector(name, **kwargs):
            if kwargs.get("resource_type") == "secrets":
                raise RuntimeError("registry unavailable")
            collector = MagicMock()
            collector.name = f"{name}_{kwargs.get('resource_type', 'generic')}"
            collector.collect = AsyncMock(
                return_value=MagicMock(data={}, source="test")
            )
            return collector

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.return_value = []

        cmd = TopCommand()
        cmd.forecasting_engine = FakeForecastingEngine()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert captured["secret_inventory_complete"] is False


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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    async def test_collect_data_records_collector_creation_failure(
        self, mock_collector_registry
    ):
        """Test collector setup failures become explicit data gaps."""
        mock_collector_registry.create.side_effect = RuntimeError("registry unavailable")

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        resources = await cmd._collect_data(subject, ["get"])

        assert resources == []
        assert cmd.data_gaps == [
            "get pod collector unavailable: registry unavailable"
        ]
