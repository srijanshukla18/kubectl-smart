"""Tests for kubectl_smart/cli/main.py"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from kubectl_smart.cli.main import ResourceType, _resolve_context, app, version_callback


runner = CliRunner()


class TestVersionCallback:
    """Tests for version callback"""

    def test_version_callback_true(self):
        """Test version callback exits when True"""
        import typer

        with pytest.raises(typer.Exit):
            version_callback(True)

    def test_version_callback_false(self):
        """Test version callback does nothing when False"""
        result = version_callback(False)
        assert result is None

    def test_version_callback_none(self):
        """Test version callback does nothing when None"""
        result = version_callback(None)
        assert result is None

    @patch.dict(os.environ, {"KUBECTL_SMART_CONTEXT": "kind-demo"}, clear=False)
    def test_resolve_context_from_env(self):
        """Test context resolver uses KUBECTL_SMART_CONTEXT as fallback."""
        assert _resolve_context(None) == "kind-demo"
        assert _resolve_context("explicit-context") == "explicit-context"


class TestResourceType:
    """Tests for ResourceType enum"""

    def test_resource_type_values(self):
        """Test ResourceType enum values"""
        assert ResourceType.POD.value == "pod"
        assert ResourceType.DEPLOYMENT.value == "deploy"
        assert ResourceType.DEPLOYMENT_FULL.value == "deployment"
        assert ResourceType.STATEFULSET.value == "sts"
        assert ResourceType.STATEFULSET_FULL.value == "statefulset"
        assert ResourceType.JOB.value == "job"
        assert ResourceType.SERVICE.value == "svc"
        assert ResourceType.SERVICE_FULL.value == "service"
        assert ResourceType.INGRESS.value == "ingress"
        assert ResourceType.REPLICASET.value == "rs"
        assert ResourceType.REPLICASET_FULL.value == "replicaset"
        assert ResourceType.DAEMONSET.value == "ds"
        assert ResourceType.DAEMONSET_FULL.value == "daemonset"


class TestMainCallback:
    """Tests for main callback"""

    def test_help(self):
        """Test --help shows help"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "kubectl-smart" in result.stdout
        assert "diag" in result.stdout
        assert "graph" in result.stdout
        assert "top" in result.stdout

    def test_version(self):
        """Test --version shows version"""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout


class TestDiagCommand:
    """Tests for diag command"""

    def test_diag_help(self):
        """Test diag --help shows help"""
        result = runner.invoke(app, ["diag", "--help"])
        assert result.exit_code == 0
        assert "Root-cause analysis" in result.stdout

    @patch("kubectl_smart.cli.commands.DiagCommand.execute")
    def test_diag_basic(self, mock_execute):
        """Test basic diag command execution"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Diagnosis output", exit_code=0)
        result = runner.invoke(app, ["diag", "pod", "test-pod"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.DiagCommand.execute")
    def test_diag_with_namespace(self, mock_execute):
        """Test diag command with namespace"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(app, ["diag", "pod", "test-pod", "-n", "production"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.DiagCommand.execute")
    def test_diag_with_context(self, mock_execute):
        """Test diag command with context"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(
            app, ["diag", "deploy", "my-app", "--context", "my-cluster"]
        )

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    def test_diag_invalid_resource_type(self):
        """Test diag with invalid resource type"""
        result = runner.invoke(app, ["diag", "invalid", "test"])
        assert result.exit_code != 0

    @patch("kubectl_smart.batch.BatchAnalyzer.diagnose_all")
    def test_diag_all_text_output_includes_data_gaps(self, mock_diagnose_all):
        """Test batch text output surfaces partial-evidence data gaps."""
        from kubectl_smart.batch import BatchResult
        from kubectl_smart.models import (
            DiagnosisResult,
            ResourceKind,
            ResourceRecord,
            SubjectCtx,
        )

        subject = SubjectCtx(
            kind=ResourceKind.POD,
            name="test-pod",
            namespace="default",
        )
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid",
            namespace="default",
            status="Running",
        )
        mock_diagnose_all.return_value = BatchResult(
            total_resources=1,
            successful=1,
            failed=0,
            results=[
                DiagnosisResult(
                    subject=subject,
                    resource=resource,
                    data_gaps=["events events unavailable (rbac): forbidden"],
                    analysis_duration=0.1,
                )
            ],
            duration=0.1,
        )

        result = runner.invoke(app, ["diag", "pod", "--all", "-n", "default"])

        assert result.exit_code == 0
        assert "Data gaps: 1 | Concurrency: 5" in result.stdout
        assert "test-pod: Running | ✅ healthy | data gaps: 1" in result.stdout

    @patch("kubectl_smart.batch.BatchAnalyzer")
    def test_diag_all_passes_max_concurrent(self, mock_batch_analyzer):
        """Test --max-concurrent is passed to batch analysis."""
        from kubectl_smart.batch import BatchResult

        analyzer = mock_batch_analyzer.return_value
        analyzer.diagnose_all = AsyncMock(
            return_value=BatchResult(
                total_resources=0,
                successful=0,
                failed=0,
                errors=[{"message": "No Pods found"}],
                duration=0.1,
            )
        )

        result = runner.invoke(
            app,
            ["diag", "pod", "--all", "-n", "default", "--max-concurrent", "2"],
        )

        assert result.exit_code == 0
        assert mock_batch_analyzer.call_args.kwargs["max_concurrent"] == 2
        assert "Concurrency: 2" in result.stdout

    def test_diag_all_rejects_invalid_max_concurrent(self):
        """Test --max-concurrent must be positive."""
        result = runner.invoke(
            app,
            ["diag", "pod", "--all", "--max-concurrent", "0"],
        )

        assert result.exit_code == 2
        assert "--max-concurrent must be >= 1" in result.output

    @patch("kubectl_smart.batch.BatchAnalyzer.diagnose_all")
    def test_diag_all_exits_nonzero_on_batch_errors(self, mock_diagnose_all):
        """Test batch-level failures are not reported as successful CLI runs."""
        from kubectl_smart.batch import BatchResult

        mock_diagnose_all.return_value = BatchResult(
            total_resources=0,
            successful=0,
            failed=1,
            errors=[{"message": "Timed out after 0.1s listing pods"}],
            duration=0.1,
        )

        result = runner.invoke(app, ["diag", "pod", "--all", "-n", "default"])

        assert result.exit_code == 2
        assert "Failed: 1" in result.stdout
        assert "Timed out after 0.1s listing pods" in result.stdout
        assert "None: None" not in result.stdout

    @patch("kubectl_smart.batch.BatchAnalyzer.diagnose_all")
    def test_diag_all_json_exits_nonzero_on_batch_errors(self, mock_diagnose_all):
        """Test JSON batch output carries nonzero exit code for batch failures."""
        from kubectl_smart.batch import BatchResult

        mock_diagnose_all.return_value = BatchResult(
            total_resources=0,
            successful=0,
            failed=1,
            errors=[{"message": "Failed to list pods: forbidden"}],
            duration=0.1,
        )

        result = runner.invoke(
            app,
            ["diag", "pod", "--all", "-n", "default", "-o", "json"],
        )

        assert result.exit_code == 2
        assert '"failed": 1' in result.stdout
        assert '"exit_code": 2' in result.stdout
        assert "Failed to list pods: forbidden" in result.stdout

    @patch("kubectl_smart.cli.commands.DiagCommand.execute_raw")
    def test_diag_json_warning_only_exits_one(self, mock_execute_raw):
        """Test JSON diag honors documented warning-only exit code."""
        from kubectl_smart.models import (
            DiagnosisResult,
            Issue,
            IssueSeverity,
            ResourceKind,
            ResourceRecord,
            SubjectCtx,
        )

        subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="api",
            uid="api-uid",
            namespace="default",
            status="Unknown",
        )
        issue = Issue(
            resource_uid="api-uid",
            title="Resource Status: Unknown",
            description="Pod api is in Unknown state",
            severity=IssueSeverity.WARNING,
            score=70,
            reason="StatusUnknown",
            message="Resource is in unhealthy state: Unknown",
        )
        mock_execute_raw.return_value = DiagnosisResult(
            subject=subject,
            resource=resource,
            issues=[issue],
            analysis_duration=0.1,
        )

        result = runner.invoke(
            app,
            ["diag", "pod", "api", "-n", "default", "-o", "json"],
        )

        assert result.exit_code == 1
        assert '"warning": 1' in result.stdout
        assert '"exit_code": 1' in result.stdout


class TestGraphCommand:
    """Tests for graph command"""

    def test_graph_help(self):
        """Test graph --help shows help"""
        result = runner.invoke(app, ["graph", "--help"])
        assert result.exit_code == 0
        assert "Dependency visualization" in result.stdout

    @patch("kubectl_smart.cli.commands.GraphCommand.execute")
    def test_graph_basic(self, mock_execute):
        """Test basic graph command execution"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Graph output", exit_code=0)
        result = runner.invoke(app, ["graph", "pod", "test-pod"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.GraphCommand.execute")
    def test_graph_upstream(self, mock_execute):
        """Test graph command with --upstream"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(app, ["graph", "pod", "test-pod", "--upstream"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.GraphCommand.execute")
    def test_graph_downstream(self, mock_execute):
        """Test graph command with --downstream"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(app, ["graph", "deploy", "my-app", "--downstream"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.GraphCommand.execute")
    def test_graph_both_directions(self, mock_execute):
        """Test graph command with --upstream and --downstream."""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(
            app, ["graph", "deployment", "my-app", "--upstream", "--downstream"]
        )

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.GraphCommand.execute")
    def test_graph_ingress(self, mock_execute):
        """Test graph supports Ingress as a starting resource."""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(app, ["graph", "ingress", "checkout", "--upstream"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1


class TestTopCommand:
    """Tests for top command"""

    def test_top_help(self):
        """Test top --help shows help"""
        result = runner.invoke(app, ["top", "--help"])
        assert result.exit_code == 0
        assert "Predictive" in result.stdout

    @patch("kubectl_smart.cli.commands.TopCommand.execute")
    def test_top_basic(self, mock_execute):
        """Test basic top command execution"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Top output", exit_code=0)
        result = runner.invoke(app, ["top", "default"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.TopCommand.execute")
    def test_top_with_horizon(self, mock_execute):
        """Test top command with custom horizon"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(app, ["top", "production", "--horizon", "24"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1

    @patch("kubectl_smart.cli.commands.TopCommand.execute")
    def test_top_with_context(self, mock_execute):
        """Test top command with context"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)
        result = runner.invoke(app, ["top", "staging", "--context", "staging-cluster"])

        assert result.exit_code == 0
        assert mock_execute.await_count == 1


class TestLegacyCommands:
    """Tests for legacy/deprecated commands"""

    def test_describe_deprecated(self):
        """Test describe command shows deprecation warning"""
        result = runner.invoke(app, ["describe", "pod", "test"])
        assert result.exit_code == 1
        assert "deprecated" in result.stdout.lower()

    def test_deps_deprecated(self):
        """Test deps command shows deprecation warning"""
        result = runner.invoke(app, ["deps", "pod", "test"])
        assert result.exit_code == 1
        assert "deprecated" in result.stdout.lower()

    def test_events_deprecated(self):
        """Test events command shows deprecation warning"""
        result = runner.invoke(app, ["events"])
        assert result.exit_code == 1
        assert "deprecated" in result.stdout.lower()


class TestDebugMode:
    """Tests for debug mode"""

    @patch("kubectl_smart.cli.commands.DiagCommand.execute")
    def test_debug_flag(self, mock_execute):
        """Test --debug flag sets debug logging"""
        from kubectl_smart.cli.commands import CommandResult

        mock_execute.return_value = CommandResult(output="Output", exit_code=0)

        # Clear any existing debug env var
        os.environ.pop("KUBECTL_SMART_DEBUG", None)

        result = runner.invoke(app, ["--debug", "diag", "pod", "test"])

        # After command runs with --debug, env var should be set
        # (This is set in main callback)
        assert result.exit_code == 0
        assert os.environ["KUBECTL_SMART_DEBUG"] == "1"
