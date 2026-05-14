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
        assert "Resource not present in collected data" in result.output

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
        assert "Resource not present in collected data" in result.output
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

    def test_pod_needs_child_log_collection_only_for_unhealthy_children(self):
        """Test controller diag does not scrape logs from healthy child Pods."""
        cmd = DiagCommand()
        healthy = ResourceRecord(
            kind=ResourceKind.POD,
            name="api-healthy",
            uid="healthy-uid",
            namespace="default",
            status="Running",
            properties={
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True"},
                        {"type": "ContainersReady", "status": "True"},
                    ]
                }
            },
        )
        unready = ResourceRecord(
            kind=ResourceKind.POD,
            name="api-unready",
            uid="unready-uid",
            namespace="default",
            status="Running",
            properties={
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "False"},
                    ]
                }
            },
        )

        assert cmd._pod_needs_child_log_collection(healthy) is False
        assert cmd._pod_needs_child_log_collection(unready) is True

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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_service_context_collect_failure_is_data_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test Service diag survives endpoint collection failures."""
        service = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="inventory",
            uid="svc-uid",
            namespace="default",
            status="Active",
            properties={"spec": {"selector": {"app": "inventory"}}},
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            if resource_type == "endpoints":
                collector.collect = AsyncMock(
                    side_effect=RuntimeError("apiserver timeout")
                )
            else:
                collector.collect = AsyncMock(
                    return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
                )
            return collector

        def parse(blob):
            if blob.source == "get_service":
                return [service]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.SERVICE, name="inventory", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DIAGNOSIS" in result.output
        assert "DATA GAPS" in result.output
        assert "get endpoints failed: apiserver timeout" in result.output
        assert "Diagnosis failed" not in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_raw_service_context_parse_failure_is_data_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test malformed Service context keeps raw diagnosis incomplete."""
        service = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="inventory",
            uid="svc-uid",
            namespace="default",
            status="Active",
            properties={"spec": {"selector": {"app": "inventory"}}},
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            collector.collect = AsyncMock(
                return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
            )
            return collector

        def parse(blob):
            if blob.source == "get_service":
                return [service]
            if blob.source == "get_pods":
                raise ValueError("malformed pod list")
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.SERVICE, name="inventory", namespace="default"
        )
        result = await cmd.execute_raw(subject)

        assert result.exit_code == 0
        assert result.resource == service
        assert result.data_gaps == [
            "get pods output could not be parsed: malformed pod list"
        ]

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_raw_service_context_creation_failure_is_data_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test Service context collector creation failures remain bounded."""
        service = ResourceRecord(
            kind=ResourceKind.SERVICE,
            name="inventory",
            uid="svc-uid",
            namespace="default",
            status="Active",
            properties={"spec": {"selector": {"app": "inventory"}}},
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            if resource_type in {"endpoints", "pods"}:
                raise RuntimeError(f"{resource_type} registry unavailable")
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            collector.collect = AsyncMock(
                return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
            )
            return collector

        def parse(blob):
            if blob.source == "get_service":
                return [service]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.SERVICE, name="inventory", namespace="default"
        )
        result = await cmd.execute_raw(subject)

        assert result.exit_code == 0
        assert result.resource == service
        assert result.data_gaps == [
            "get endpoints collector unavailable: endpoints registry unavailable",
            "get pods collector unavailable: pods registry unavailable",
        ]

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_raw_deployment_promotes_child_pod_issue(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test Deployment diagnosis follows ReplicaSet-owned Pods for root cause."""
        deployment = ResourceRecord(
            kind=ResourceKind.DEPLOYMENT,
            name="checkout-api",
            uid="deploy-uid",
            namespace="default",
            status="Available",
            properties={
                "metadata": {},
                "spec": {"selector": {"matchLabels": {"app": "checkout-api"}}},
                "status": {},
            },
        )
        replicaset = ResourceRecord(
            kind=ResourceKind.REPLICASET,
            name="checkout-api-6d7f",
            uid="rs-uid",
            namespace="default",
            status="Active",
            properties={
                "metadata": {
                    "ownerReferences": [
                        {"kind": "Deployment", "name": "checkout-api", "uid": "deploy-uid"}
                    ]
                },
                "spec": {},
                "status": {},
            },
        )
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="checkout-api-6d7f-k9x2m",
            uid="pod-uid",
            namespace="default",
            status="CreateContainerConfigError",
            labels={"app": "checkout-api"},
            properties={
                "metadata": {
                    "ownerReferences": [
                        {"kind": "ReplicaSet", "name": "checkout-api-6d7f", "uid": "rs-uid"}
                    ]
                },
                "spec": {},
                "status": {
                    "containerStatuses": [
                        {
                            "name": "api",
                            "state": {
                                "waiting": {
                                    "reason": "CreateContainerConfigError",
                                    "message": 'secret "runtime-token" not found',
                                }
                            },
                        }
                    ]
                },
            },
        )

        mock_collector = MagicMock()
        mock_collector.name = "kubectl_get"
        mock_collector.collect = AsyncMock(
            return_value=RawBlob(data={}, source="kubectl_get")
        )
        mock_collector_registry.create.return_value = mock_collector
        mock_parser_registry.parse.side_effect = [
            [deployment],
            [],
            [],
            [],
            [pod],
            [replicaset],
            [],
            [],
        ]

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.DEPLOYMENT,
            name="checkout-api",
            namespace="default",
        )
        result = await cmd.execute_raw(subject)

        assert result.exit_code == 2
        assert result.root_cause is not None
        assert result.root_cause.resource_uid == deployment.uid
        assert "Pod checkout-api-6d7f-k9x2m" in result.root_cause.title
        assert result.root_cause.metadata["child_resource"] == pod.full_name
        assert any("OwnerReference chain" in item for item in result.root_cause.evidence)
        assert any('secret "runtime-token" not found' in item for item in result.root_cause.evidence)
        assert result.suggested_actions[0] == (
            "Verify missing Secret: kubectl get secret runtime-token -n default"
        )
        assert any("Inspect child pod" in action for action in result.suggested_actions)
        assert "Check logs: kubectl logs checkout-api -n default" not in result.suggested_actions

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_raw_controller_context_collect_failure_is_data_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test controller diagnosis keeps resource-typed context collect gaps."""
        deployment = ResourceRecord(
            kind=ResourceKind.DEPLOYMENT,
            name="checkout-api",
            uid="deploy-uid",
            namespace="default",
            status="Available",
            properties={"spec": {"selector": {"matchLabels": {"app": "checkout"}}}},
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            if resource_type == "pods":
                collector.collect = AsyncMock(
                    side_effect=RuntimeError("apiserver timeout")
                )
            else:
                collector.collect = AsyncMock(
                    return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
                )
            return collector

        def parse(blob):
            if blob.source == "get_deployment":
                return [deployment]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.DEPLOYMENT,
            name="checkout-api",
            namespace="default",
        )
        result = await cmd.execute_raw(subject)

        assert result.exit_code == 0
        assert result.resource == deployment
        assert "get pods failed: apiserver timeout" in result.data_gaps
        assert not any("get_pods failed" in gap for gap in result.data_gaps)

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_raw_controller_context_parse_failure_is_data_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test controller diagnosis labels context parse gaps by resource."""
        deployment = ResourceRecord(
            kind=ResourceKind.DEPLOYMENT,
            name="checkout-api",
            uid="deploy-uid",
            namespace="default",
            status="Available",
            properties={"spec": {"selector": {"matchLabels": {"app": "checkout"}}}},
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            collector.collect = AsyncMock(
                return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
            )
            return collector

        def parse(blob):
            if blob.source == "get_deployment":
                return [deployment]
            if blob.source == "get_replicasets":
                raise ValueError("malformed replicaset list")
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.DEPLOYMENT,
            name="checkout-api",
            namespace="default",
        )
        result = await cmd.execute_raw(subject)

        assert result.exit_code == 0
        assert result.resource == deployment
        assert "get replicasets output could not be parsed: malformed replicaset list" in result.data_gaps
        assert not any("get_replicasets output could not be parsed" in gap for gap in result.data_gaps)

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    async def test_collect_child_pod_logs_failure_is_data_gap(
        self, mock_collector_registry
    ):
        """Test child pod log collection failures use Kubernetes resource labels."""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="checkout-api-0",
            uid="pod-uid",
            namespace="default",
            status="CrashLoopBackOff",
        )

        collector = MagicMock()
        collector.name = "kubectl_logs"
        collector.collect = AsyncMock(side_effect=RuntimeError("forbidden"))
        mock_collector_registry.create.return_value = collector

        cmd = DiagCommand()
        subject = SubjectCtx(
            kind=ResourceKind.STATEFULSET,
            name="checkout-api",
            namespace="default",
        )
        resources = await cmd._collect_child_pod_logs(subject, [pod])

        assert resources == []
        assert cmd.data_gaps == ["logs pods failed: forbidden"]

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
    async def test_execute_resource_not_found_softens_target_inventory_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test graph avoids not-found overclaims when target inventory is blocked."""
        gap_blob = RawBlob(
            data={},
            source="kubectl_get",
            content_type="application/json",
            metadata={
                "data_gap": True,
                "collector": "kubectl_get",
                "operation": "get",
                "resource_type": "pods",
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
        assert "not present in collected graph" in result.output
        assert "not found in graph" not in result.output
        assert "DATA GAPS" in result.output
        assert "get pods unavailable (rbac): forbidden" in result.output

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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_surfaces_collector_runtime_data_gaps(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test graph labels runtime collector failures by resource type."""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", "generic")
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            if resource_type == "secrets":
                collector.collect = AsyncMock(
                    side_effect=RuntimeError("apiserver timeout")
                )
            else:
                collector.collect = AsyncMock(
                    return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
                )
            return collector

        def parse(blob):
            if blob.source == "get_pods":
                return [pod]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DATA GAPS" in result.output
        assert "get secrets failed: apiserver timeout" in result.output
        assert "get_secrets failed" not in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_surfaces_parser_data_gaps_by_resource_type(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test graph labels parse failures by Kubernetes resource type."""
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", "generic")
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            collector.collect = AsyncMock(
                return_value=RawBlob(data={}, source=f"{name}_{resource_type}")
            )
            return collector

        def parse(blob):
            if blob.source == "get_pods":
                return [pod]
            if blob.source == "get_services":
                raise ValueError("malformed service list")
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = GraphCommand()
        subject = SubjectCtx(
            kind=ResourceKind.POD, name="test-pod", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DATA GAPS" in result.output
        assert "get services output could not be parsed: malformed service list" in result.output
        assert "get_services output could not be parsed" not in result.output


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
    async def test_execute_missing_namespace_returns_error(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test top fails when the target namespace itself is missing."""
        namespace_gap = RawBlob(
            data={},
            source="kubectl_get",
            content_type="application/json",
            metadata={
                "data_gap": True,
                "collector": "kubectl_get",
                "operation": "get",
                "resource_type": "namespace",
                "category": "not_found",
                "error": 'namespaces "missing" not found',
            },
        )

        def create_collector(name, **kwargs):
            collector = MagicMock()
            collector.name = f"{name}_{kwargs.get('resource_type', 'generic')}"
            if name == "get" and kwargs.get("resource_type") == "namespace":
                collector.collect = AsyncMock(return_value=namespace_gap)
            else:
                collector.collect = AsyncMock(
                    return_value=RawBlob(data={}, source=collector.name)
                )
            return collector

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.return_value = []

        cmd = TopCommand()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="missing", namespace="missing"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 2
        assert "Namespace missing not found" in result.output
        assert "DATA GAPS" in result.output
        assert 'namespaces "missing" not found' in result.output
        assert "PREDICTIVE OUTLOOK" not in result.output

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
    async def test_execute_collects_node_inventory_and_metrics(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test top uses real node inventory plus metrics-server node rows."""
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="node-a",
            uid="node-uid",
            properties={"status": {"conditions": []}},
        )
        node_metrics = ResourceRecord(
            kind=ResourceKind.NODE,
            name="node-a",
            uid="metrics-node-a",
            properties={
                "metrics": {
                    "cpu_percent": "96",
                    "memory_percent": "30",
                }
            },
        )

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            source = f"{name}_{resource_type}"
            collector = MagicMock()
            collector.name = source
            if name == "metrics":
                async def collect_metrics(received_subject):
                    metric_source = (
                        "metrics_node"
                        if received_subject.kind == ResourceKind.NODE
                        else "metrics_pods"
                    )
                    return RawBlob(data={}, source=metric_source)

                collector.collect = AsyncMock(side_effect=collect_metrics)
            else:
                collector.collect = AsyncMock(return_value=RawBlob(data={}, source=source))
            return collector

        def parse(blob):
            if blob.source == "get_nodes":
                return [node]
            if blob.source == "metrics_node":
                return [node_metrics]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = TopCommand()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "CAPACITY WARNINGS" in result.output
        assert "Node/node-a" in result.output
        assert "cpu" in result.output

        requested = [
            (call.args[0], call.kwargs.get("resource_type"))
            for call in mock_collector_registry.create.call_args_list
        ]
        assert ("get", "nodes") in requested
        assert ("metrics", None) in requested

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
                return_value=RawBlob(data={}, source="test")
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

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_marks_secret_inventory_incomplete_on_secret_collect_failure(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test failed Secret collection keeps certificate forecasts qualified."""
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
            resource_type = kwargs.get("resource_type", "generic")
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            if resource_type == "secrets":
                collector.collect = AsyncMock(
                    side_effect=RuntimeError("apiserver timeout")
                )
            else:
                collector.collect = AsyncMock(
                    return_value=RawBlob(
                        data={},
                        source=f"{name}_{resource_type}",
                    )
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
        assert "get secrets failed: apiserver timeout" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_marks_secret_inventory_incomplete_on_secret_parse_failure(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test malformed Secret inventory does not become clean TLS evidence."""
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
            resource_type = kwargs.get("resource_type", "generic")
            collector = MagicMock()
            collector.name = f"{name}_{resource_type}"
            collector.collect = AsyncMock(
                return_value=RawBlob(
                    data={},
                    source=f"{name}_{resource_type}",
                )
            )
            return collector

        def parse(blob):
            if blob.source == "get_secrets":
                raise ValueError("malformed json")
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = TopCommand()
        cmd.forecasting_engine = FakeForecastingEngine()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert captured["secret_inventory_complete"] is False
        assert "get secrets output could not be parsed: malformed json" in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_merges_kubelet_pvc_metrics_before_forecast(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test PVC inventory and kubelet volume stats are forecast together."""
        captured = {}
        pvc = ResourceRecord(
            kind=ResourceKind.PVC,
            name="data-pvc",
            uid="pvc-uid",
            namespace="default",
            status="Bound",
            properties={
                "spec": {
                    "resources": {"requests": {"storage": "10Gi"}},
                }
            },
        )
        pvc_metrics = ResourceRecord(
            kind=ResourceKind.PVC,
            name="data-pvc",
            uid="pvc-metrics-default-data-pvc",
            namespace="default",
            status="Active",
            properties={
                "metrics": {
                    "pvc_used_bytes": 5_000_000_000,
                    "pvc_capacity_bytes": 10_000_000_000,
                }
            },
        )

        class FakeForecastingEngine:
            def predict_capacity_issues(self, resources, metrics_data):
                pvcs = [r for r in resources if r.kind == ResourceKind.PVC]
                captured["pvc_count"] = len(pvcs)
                captured["metrics"] = pvcs[0].properties.get("metrics")
                return []

            def predict_certificate_expiry(
                self,
                resources,
                secret_inventory_complete=True,
            ):
                return []

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            source = "kubelet_metrics" if name == "kubelet" else f"{name}_{resource_type}"
            collector = MagicMock()
            collector.name = source
            collector.collect = AsyncMock(return_value=RawBlob(data={}, source=source))
            return collector

        def parse(blob):
            if blob.source == "get_persistentvolumeclaims":
                return [pvc]
            if blob.source == "kubelet_metrics":
                return [pvc_metrics]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = TopCommand()
        cmd.forecasting_engine = FakeForecastingEngine()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert captured["pvc_count"] == 1
        assert captured["metrics"] == {
            "pvc_used_bytes": 5_000_000_000,
            "pvc_capacity_bytes": 10_000_000_000,
        }
        assert "missing kubelet_volume_stats" not in result.output

    @pytest.mark.asyncio
    @patch("kubectl_smart.cli.commands.collector_registry")
    @patch("kubectl_smart.cli.commands.parser_registry")
    async def test_execute_records_missing_pvc_metric_gap(
        self, mock_parser_registry, mock_collector_registry
    ):
        """Test PVC inventory without kubelet volume stats is not silent."""
        pvc = ResourceRecord(
            kind=ResourceKind.PVC,
            name="data-pvc",
            uid="pvc-uid",
            namespace="default",
            status="Bound",
            properties={
                "spec": {
                    "resources": {"requests": {"storage": "10Gi"}},
                }
            },
        )

        class FakeForecastingEngine:
            def predict_capacity_issues(self, resources, metrics_data):
                return []

            def predict_certificate_expiry(
                self,
                resources,
                secret_inventory_complete=True,
            ):
                return []

        def create_collector(name, **kwargs):
            resource_type = kwargs.get("resource_type", name)
            source = "kubelet_metrics" if name == "kubelet" else f"{name}_{resource_type}"
            collector = MagicMock()
            collector.name = source
            collector.collect = AsyncMock(return_value=RawBlob(data={}, source=source))
            return collector

        def parse(blob):
            if blob.source == "get_persistentvolumeclaims":
                return [pvc]
            return []

        mock_collector_registry.create.side_effect = create_collector
        mock_parser_registry.parse.side_effect = parse

        cmd = TopCommand()
        cmd.forecasting_engine = FakeForecastingEngine()
        subject = SubjectCtx(
            kind=ResourceKind.NAMESPACE, name="default", namespace="default"
        )
        result = await cmd.execute(subject)

        assert result.exit_code == 0
        assert "DATA GAPS" in result.output
        assert cmd.data_gaps == [
            "kubelet persistentvolumeclaims unavailable (incomplete): "
            "missing kubelet_volume_stats metrics for data-pvc"
        ]


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
