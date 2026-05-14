"""Tests for kubectl_smart/renderers/terminal.py"""

import json

from kubectl_smart.models import (
    DiagnosisResult,
    GraphResult,
    Issue,
    IssueSeverity,
    ResourceKind,
    ResourceRecord,
    TopResult,
)
from kubectl_smart.renderers.json_renderer import JsonRenderer
from kubectl_smart.renderers.terminal import TerminalRenderer


class TestTerminalRenderer:
    """Tests for TerminalRenderer class"""

    def test_init_defaults(self):
        """Test TerminalRenderer initializes with defaults"""
        renderer = TerminalRenderer()
        assert renderer.colors_enabled is True
        assert renderer.console is not None

    def test_init_colors_disabled(self):
        """Test TerminalRenderer with colors disabled"""
        renderer = TerminalRenderer(colors_enabled=False)
        assert renderer.colors_enabled is False

    def test_init_custom_width(self):
        """Test TerminalRenderer with custom width"""
        renderer = TerminalRenderer(width=80)
        assert renderer.console.size.width == 80


class TestRenderDiagnosis:
    """Tests for render_diagnosis method"""

    def test_render_diagnosis_basic(self, sample_subject_ctx, sample_resource_record):
        """Test basic diagnosis rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            analysis_duration=1.5,
        )
        output = renderer.render_diagnosis(result)

        assert "DIAGNOSIS" in output
        assert sample_resource_record.name in output
        assert "1.5" in output

    def test_render_diagnosis_with_root_cause(
        self, sample_subject_ctx, sample_resource_record, sample_issue
    ):
        """Test diagnosis rendering with root cause"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=sample_issue,
            analysis_duration=1.0,
        )
        output = renderer.render_diagnosis(result)

        assert "LIKELY ROOT CAUSE" in output
        assert sample_issue.title in output

    def test_render_diagnosis_escapes_issue_markup(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test issue evidence is rendered literally, not as Rich markup."""
        renderer = TerminalRenderer(colors_enabled=False)
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Log [red]Errors[/red]",
            description="Saw [yellow]panic[/yellow]",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="LogFailure",
            message="panic",
            evidence=["Log line: [red]panic[/red]"],
            suggested_actions=["Inspect [blue]logs[/blue]"],
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=issue,
            suggested_actions=["Run [green]kubectl logs[/green]"],
            analysis_duration=1.0,
        )

        output = renderer.render_diagnosis(result)

        assert "[red]Errors[/red]" in output
        assert "[yellow]panic[/yellow]" in output
        assert "[red]panic[/red]" in output
        assert "[blue]logs[/blue]" in output
        assert "[green]kubectl logs[/green]" in output

    def test_render_diagnosis_root_cause_only_is_nonzero(
        self, sample_subject_ctx, sample_resource_record, sample_issue
    ):
        """Test surfaced root causes affect JSON summary and exit code."""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=sample_issue,
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_diagnosis(result)

        assert '"total": 1' in output
        assert '"critical": 1' in output
        assert '"exit_code": 2' in output
        parsed = json.loads(output)
        assert parsed["issues"] == []
        assert len(parsed["diagnostic_issues"]) == 1
        assert parsed["diagnostic_issues"][0]["title"] == sample_issue.title

    def test_render_diagnosis_root_cause_header_uses_issue_severity(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test root cause section header does not overstate warning severity."""
        renderer = TerminalRenderer(colors_enabled=False)
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Resource Status: Unknown",
            description="Pod test-pod is in Unknown state",
            severity=IssueSeverity.WARNING,
            score=70.0,
            reason="StatusUnknown",
            message="Resource is in unhealthy state: Unknown",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=issue,
            issues=[issue],
            analysis_duration=1.0,
        )

        output = renderer.render_diagnosis(result)

        assert "🟡 LIKELY ROOT CAUSE" in output
        assert "🔴 LIKELY ROOT CAUSE" not in output

    def test_render_diagnosis_with_root_cause_evidence(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test root cause rendering includes supporting evidence."""
        renderer = TerminalRenderer(colors_enabled=False)
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Missing Secret",
            description="Secret token is not found",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="Failed",
            message="secret token not found",
            evidence=['Event Warning/Failed: Error: secret "token" not found'],
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=issue,
            analysis_duration=1.0,
        )
        output = renderer.render_diagnosis(result)

        assert "Evidence" in output
        assert 'secret "token" not found' in output

    def test_render_diagnosis_with_contributing_factors(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test diagnosis rendering with contributing factors"""
        renderer = TerminalRenderer(colors_enabled=False)
        factor = Issue(
            resource_uid="test",
            title="Contributing Factor",
            description="A contributing factor",
            severity=IssueSeverity.WARNING,
            score=60.0,
            reason="FactorReason",
            message="Factor message",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            contributing_factors=[factor],
            analysis_duration=1.0,
        )
        output = renderer.render_diagnosis(result)

        assert "CONTRIBUTING FACTORS" in output
        assert "Contributing Factor" in output

    def test_render_diagnosis_with_contributing_factor_evidence(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test contributing factors include supporting evidence."""
        renderer = TerminalRenderer(colors_enabled=False)
        factor = Issue(
            resource_uid="test",
            title="Scheduling Failed",
            description="Pod could not be scheduled",
            severity=IssueSeverity.WARNING,
            score=65.0,
            reason="FailedScheduling",
            message="0/3 nodes are available",
            evidence=[
                "Event Warning/FailedScheduling: 0/3 nodes are available: insufficient cpu"
            ],
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            contributing_factors=[factor],
            analysis_duration=1.0,
        )
        output = renderer.render_diagnosis(result)

        assert "CONTRIBUTING FACTORS" in output
        assert "Evidence" in output
        assert "insufficient cpu" in output

    def test_render_diagnosis_with_suggested_actions(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test diagnosis rendering with suggested actions"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            suggested_actions=["Check logs", "Restart pod"],
            analysis_duration=1.0,
        )
        output = renderer.render_diagnosis(result)

        assert "SUGGESTED ACTIONS" in output
        assert "Check logs" in output
        assert "Restart pod" in output

    def test_render_diagnosis_with_data_gaps(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test diagnosis rendering shows unavailable signals."""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            data_gaps=[
                "logs pods unavailable (rbac): User cannot get pods/log | Check: kubectl auth can-i get pods --subresource=log -n default"
            ],
            analysis_duration=1.0,
        )
        output = renderer.render_diagnosis(result)

        assert "DATA GAPS" in output
        assert "pods/log" in output

    def test_render_diagnosis_notes_truncated_data_gaps(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test diagnosis rendering does not silently hide extra gaps."""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            data_gaps=[f"collector {index} unavailable" for index in range(7)],
            analysis_duration=1.0,
        )

        output = renderer.render_diagnosis(result)

        assert "DATA GAPS (7)" in output
        assert "collector 0 unavailable" in output
        assert "collector 4 unavailable" in output
        assert "collector 5 unavailable" not in output
        assert "... 2 more data gaps not shown" in output

    def test_render_diagnosis_escapes_data_gap_markup(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test data gaps are rendered literally, not as Rich markup."""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            data_gaps=["collector unavailable: before [red]not literal[/red] after"],
            analysis_duration=1.0,
        )

        output = renderer.render_diagnosis(result)

        assert "[red]not literal[/red]" in output

    def test_render_diagnosis_escapes_status_and_event_markup(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test status and event evidence are rendered literally."""
        renderer = TerminalRenderer(colors_enabled=False, width=160)
        resource = sample_resource_record.model_copy(
            update={"status": "Running[red]mutated[/red]"}
        )
        event = ResourceRecord(
            kind=ResourceKind.EVENT,
            name="test-event",
            uid="event-uid",
            namespace="default",
            properties={
                "lastTimestamp": "2026-05-14T10:11:12Z",
                "type": "Warning",
                "reason": "Failed[red]Reason[/red]",
                "message": "before [yellow]message[/yellow] after",
            },
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=resource,
            recent_events=[event],
            analysis_duration=1.0,
        )

        output = renderer.render_diagnosis(result)

        assert "Running[red]mutated[/red]" in output
        assert "Failed[red]Reason[/red]" in output
        assert "before [yellow]message[/yellow] after" in output

    def test_render_diagnosis_folds_recent_events_without_ellipsis(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test recent events preserve full messages in narrow terminals."""
        renderer = TerminalRenderer(colors_enabled=False, width=72)
        event = ResourceRecord(
            kind=ResourceKind.EVENT,
            name="test-event",
            uid="event-uid",
            namespace="default",
            properties={
                "lastTimestamp": "2026-05-14T10:11:12Z",
                "type": "Warning",
                "reason": "BackOff",
                "message": (
                    "Back-off restarting failed container api in pod "
                    "checkout-api-0_kubectl-smart-complex"
                ),
            },
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            recent_events=[event],
            analysis_duration=1.0,
        )

        output = renderer.render_diagnosis(result)

        assert "…" not in output
        assert "checkout-api-0" in output
        assert "kubectl-smart-complex" in output

    def test_render_diagnosis_resource_not_found(self, sample_subject_ctx):
        """Test diagnosis rendering when resource not found"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=None,
            data_gaps=[
                'get pod unavailable (not_found): pods "test-pod" not found'
            ],
            analysis_duration=0.5,
        )
        output = renderer.render_diagnosis(result)

        assert "Status: Resource not found" in output

    def test_render_diagnosis_missing_resource_with_visibility_gap(
        self, sample_subject_ctx
    ):
        """Test missing resources are not overclaimed when evidence is blocked."""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=None,
            data_gaps=["get pod unavailable (rbac): forbidden"],
            analysis_duration=0.5,
        )
        output = renderer.render_diagnosis(result)

        assert "Status: Resource not present in collected data" in output
        assert "get pod unavailable (rbac): forbidden" in output

    def test_render_diagnosis_status_style(self, sample_subject_ctx):
        """Test diagnosis applies status styling"""
        renderer = TerminalRenderer(colors_enabled=True)
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="failed-pod",
            uid="uid-123",
            status="Failed",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=resource,
            analysis_duration=0.5,
        )
        output = renderer.render_diagnosis(result)

        assert "Failed" in output


class TestRenderGraph:
    """Tests for render_graph method"""

    def test_render_graph_basic(self, sample_subject_ctx):
        """Test basic graph rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = GraphResult(
            subject=sample_subject_ctx,
            ascii_graph="Root\n  └── Child",
            upstream_count=2,
            downstream_count=5,
            analysis_duration=0.3,
        )
        output = renderer.render_graph(result)

        assert "DEPENDENCY GRAPH" in output
        assert "Root" in output
        assert "Child" in output
        assert "GRAPH STATISTICS" in output

    def test_render_graph_statistics(self, sample_subject_ctx, sample_resource_record):
        """Test graph statistics are shown"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = GraphResult(
            subject=sample_subject_ctx,
            nodes=[sample_resource_record],
            edges=[{"source": "a", "target": "b"}],
            upstream_count=3,
            downstream_count=7,
            analysis_duration=0.5,
        )
        output = renderer.render_graph(result)

        assert "Resources: 1" in output
        assert "Dependencies: 1" in output
        assert "Upstream: 3" in output
        assert "Downstream: 7" in output

    def test_render_graph_empty(self, sample_subject_ctx):
        """Test empty graph rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = GraphResult(
            subject=sample_subject_ctx,
            ascii_graph="",
            data_gaps=["get nodes unavailable (rbac): forbidden"],
            analysis_duration=0.1,
        )
        output = renderer.render_graph(result)

        assert "DEPENDENCY GRAPH" in output
        assert "DATA GAPS" in output

    def test_render_graph_escapes_ascii_markup(self, sample_subject_ctx):
        """Test graph lines are rendered literally, not as Rich markup."""
        renderer = TerminalRenderer(colors_enabled=False)
        result = GraphResult(
            subject=sample_subject_ctx,
            ascii_graph="Pod/test-pod [red]hidden[/red]",
            analysis_duration=0.1,
        )

        output = renderer.render_graph(result)

        assert "Pod/test-pod [red]hidden[/red]" in output


class TestRenderTop:
    """Tests for render_top method"""

    def test_render_top_basic(self, sample_subject_ctx):
        """Test basic top rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = TopResult(
            subject=sample_subject_ctx,
            forecast_horizon_hours=48,
            analysis_duration=2.0,
        )
        output = renderer.render_top(result)

        assert "PREDICTIVE OUTLOOK" in output
        assert "48" in output
        assert "✅ No capacity or certificate issues predicted" in output

    def test_render_top_with_capacity_warnings(self, sample_subject_ctx):
        """Test top rendering with capacity warnings"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = TopResult(
            subject=sample_subject_ctx,
            capacity_warnings=[
                {
                    "resource": "Node/worker-1",
                    "type": "node_pressure",
                    "current_utilization": 85.0,
                    "predicted_utilization": 95.0,
                    "suggested_action": "Add nodes",
                }
            ],
            forecast_horizon_hours=48,
            analysis_duration=1.0,
        )
        output = renderer.render_top(result)

        assert "CAPACITY WARNINGS" in output
        assert "worker-1" in output
        assert "95.0%" in output

    def test_render_top_escapes_capacity_warning_markup(self, sample_subject_ctx):
        """Test capacity warning values are rendered literally."""
        renderer = TerminalRenderer(colors_enabled=False, width=180)
        result = TopResult(
            subject=sample_subject_ctx,
            capacity_warnings=[
                {
                    "resource": "Node/[red]worker-1[/red]",
                    "type": "node_[yellow]pressure[/yellow]",
                    "current_utilization": 85.0,
                    "predicted_utilization": 95.0,
                    "suggested_action": "Add [green]nodes[/green]",
                }
            ],
            forecast_horizon_hours=48,
            analysis_duration=1.0,
        )

        output = renderer.render_top(result)

        assert "Node/[red]worker-1[/red]" in output
        assert "node_[yellow]pressure[/yellow]" in output
        assert "Add [green]nodes[/green]" in output

    def test_render_top_with_certificate_warnings(self, sample_subject_ctx):
        """Test top rendering with certificate warnings"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = TopResult(
            subject=sample_subject_ctx,
            certificate_warnings=[
                {
                    "resource": "Secret/tls-cert",
                    "certificate_type": "tls_secret",
                    "expiry_date": "2024-02-01T00:00:00Z",
                    "days_until_expiry": 10,
                    "suggested_action": "Renew certificate",
                }
            ],
            forecast_horizon_hours=48,
            analysis_duration=1.0,
        )
        output = renderer.render_top(result)

        assert "CERTIFICATE WARNINGS" in output
        assert "tls-cert" in output
        assert "10" in output

    def test_render_top_escapes_certificate_warning_markup(self, sample_subject_ctx):
        """Test certificate warning values are rendered literally."""
        renderer = TerminalRenderer(colors_enabled=False, width=200)
        result = TopResult(
            subject=sample_subject_ctx,
            certificate_warnings=[
                {
                    "resource": "Secret/[red]tls-cert[/red]",
                    "certificate_type": "tls_[yellow]secret[/yellow]",
                    "expiry_date": "2026-[blue]05[/blue]-15",
                    "days_until_expiry": 1,
                    "suggested_action": "Renew [green]certificate[/green]",
                }
            ],
            forecast_horizon_hours=48,
            analysis_duration=1.0,
        )

        output = renderer.render_top(result)

        assert "Secret/[red]tls-cert[/red]" in output
        assert "tls_[yellow]secret[/yellow]" in output
        assert "2026-[blue]05[/blue]-15" in output
        assert "Renew [green]certificate[/green]" in output

    def test_render_top_shows_warning_values_without_ellipsis(self, sample_subject_ctx):
        """Test top warnings preserve inspectable resource identifiers."""
        renderer = TerminalRenderer(colors_enabled=False, width=100)
        result = TopResult(
            subject=sample_subject_ctx,
            certificate_warnings=[
                {
                    "resource": "Secret/kubectl-smart-complex/checkout-demo-tls",
                    "certificate_type": "tls_secret",
                    "expiry_date": "2026-05-16T18:30:00Z",
                    "days_until_expiry": 2,
                    "suggested_action": "Renew certificate for secret checkout-demo-tls",
                }
            ],
            forecast_horizon_hours=72,
            analysis_duration=1.0,
        )

        output = renderer.render_top(result)

        assert "…" not in output
        assert "checkout-demo-tls" in output
        assert "2026-05-16" in output

    def test_render_top_no_warnings_with_data_gaps_is_qualified(
        self, sample_subject_ctx
    ):
        """Test partial top rendering does not look like a clean forecast."""
        renderer = TerminalRenderer(colors_enabled=False)
        result = TopResult(
            subject=sample_subject_ctx,
            data_gaps=["metrics pods unavailable (rbac): forbidden"],
            forecast_horizon_hours=48,
            analysis_duration=1.0,
        )
        output = renderer.render_top(result)

        assert "No capacity or certificate issues predicted from available signals" in output
        assert "Review DATA GAPS below" in output
        assert "✅ No capacity or certificate issues predicted" not in output
        assert "DATA GAPS" in output


class TestRenderError:
    """Tests for render_error method"""

    def test_render_error_basic(self):
        """Test basic error rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_error("Something went wrong")

        assert "Error" in output
        assert "Something went wrong" in output

    def test_render_error_with_details(self):
        """Test error rendering with details"""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_error("Main error", "Additional details here")

        assert "Main error" in output
        assert "Additional details here" in output

    def test_render_error_with_data_gaps(self):
        """Test error rendering can preserve incomplete evidence context."""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_error(
            "Graph analysis failed",
            data_gaps=["get secrets unavailable (rbac): forbidden"],
        )

        assert "Graph analysis failed" in output
        assert "DATA GAPS" in output
        assert "get secrets unavailable (rbac): forbidden" in output

    def test_render_error_escapes_markup(self):
        """Test error messages and details are rendered literally."""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_error(
            "Main [red]error[/red]",
            "Detail [yellow]context[/yellow]",
        )

        assert "Main [red]error[/red]" in output
        assert "Detail [yellow]context[/yellow]" in output


class TestRenderRbacError:
    """Tests for render_rbac_error method"""

    def test_render_rbac_error_basic(self):
        """Test basic RBAC error rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_rbac_error(["get pods", "list secrets"])

        assert "RBAC" in output
        assert "get pods" in output
        assert "list secrets" in output

    def test_render_rbac_error_includes_guidance(self):
        """Test RBAC error includes guidance"""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_rbac_error(["get pods"])

        assert "cluster admin" in output
        assert "kubectl auth can-i" in output

    def test_render_rbac_error_escapes_permission_markup(self):
        """Test RBAC permission strings are rendered literally."""
        renderer = TerminalRenderer(colors_enabled=False)
        output = renderer.render_rbac_error(["get pods [red]secret[/red]"])

        assert "get pods [red]secret[/red]" in output


class TestHelperMethods:
    """Tests for helper methods"""

    def test_get_severity_style_critical(self):
        """Test severity style for critical"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_severity_style(IssueSeverity.CRITICAL)
        assert "red" in style
        assert "bold" in style

    def test_get_severity_style_warning(self):
        """Test severity style for warning"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_severity_style(IssueSeverity.WARNING)
        assert "yellow" in style

    def test_get_severity_style_info(self):
        """Test severity style for info"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_severity_style(IssueSeverity.INFO)
        assert "blue" in style

    def test_get_severity_style_colors_disabled(self):
        """Test severity style when colors disabled"""
        renderer = TerminalRenderer(colors_enabled=False)
        style = renderer._get_severity_style(IssueSeverity.CRITICAL)
        assert style == "white"

    def test_get_severity_icon_critical(self):
        """Test severity icon for critical"""
        renderer = TerminalRenderer()
        icon = renderer._get_severity_icon(IssueSeverity.CRITICAL)
        assert icon == "🔴"

    def test_get_severity_icon_warning(self):
        """Test severity icon for warning"""
        renderer = TerminalRenderer()
        icon = renderer._get_severity_icon(IssueSeverity.WARNING)
        assert icon == "🟡"

    def test_get_severity_icon_info(self):
        """Test severity icon for info"""
        renderer = TerminalRenderer()
        icon = renderer._get_severity_icon(IssueSeverity.INFO)
        assert icon == "🔵"

    def test_get_status_style_running(self):
        """Test status style for running"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_status_style("Running")
        assert style == "green"

    def test_get_status_style_failed(self):
        """Test status style for failed"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_status_style("Failed")
        assert style == "red"

    def test_get_status_style_pending(self):
        """Test status style for pending"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_status_style("Pending")
        assert style == "yellow"

    def test_get_status_style_unknown(self):
        """Test status style for unknown status"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_status_style("SomeOther")
        assert style == "white"

    def test_get_status_style_none(self):
        """Test status style for None"""
        renderer = TerminalRenderer(colors_enabled=True)
        style = renderer._get_status_style(None)
        assert style == "white"

    def test_get_status_style_colors_disabled(self):
        """Test status style when colors disabled"""
        renderer = TerminalRenderer(colors_enabled=False)
        style = renderer._get_status_style("Failed")
        assert style == "white"


class TestRenderIssue:
    """Tests for _render_issue method"""

    def test_render_issue_basic(self, sample_issue):
        """Test basic issue rendering"""
        renderer = TerminalRenderer(colors_enabled=False)
        from rich.console import Console

        console = Console(file=None)
        with console.capture() as capture:
            renderer._render_issue(console, sample_issue)
        output = capture.get()

        assert sample_issue.title in output
        assert str(sample_issue.score) in output

    def test_render_issue_with_critical_path(self):
        """Test issue rendering shows critical path indicator"""
        renderer = TerminalRenderer(colors_enabled=False)
        issue = Issue(
            resource_uid="test",
            title="Critical Path Issue",
            description="On critical path",
            severity=IssueSeverity.CRITICAL,
            score=90.0,
            reason="Error",
            message="Error",
            critical_path=True,
        )
        from rich.console import Console

        console = Console(file=None)
        with console.capture() as capture:
            renderer._render_issue(console, issue)
        output = capture.get()

        assert "critical dependency path" in output

    def test_render_issue_with_details(self):
        """Test issue rendering with details and suggested actions"""
        renderer = TerminalRenderer(colors_enabled=False)
        issue = Issue(
            resource_uid="test",
            title="Issue With Actions",
            description="Has suggested actions",
            severity=IssueSeverity.WARNING,
            score=70.0,
            reason="Warning",
            message="Warning",
            suggested_actions=["Action 1", "Action 2", "Action 3", "Action 4"],
        )
        from rich.console import Console

        console = Console(file=None)
        with console.capture() as capture:
            renderer._render_issue(console, issue, show_details=True)
        output = capture.get()

        assert "Suggested actions" in output
        assert "Action 1" in output
        # Should show max 3 actions
        assert "Action 3" in output

    def test_render_issue_with_details_without_evidence_is_explicit(self):
        """Test detailed high-severity issues do not silently omit evidence."""
        renderer = TerminalRenderer(colors_enabled=False)
        issue = Issue(
            resource_uid="test",
            title="Warning Without Evidence",
            description="A warning issue",
            severity=IssueSeverity.WARNING,
            score=70.0,
            reason="Warning",
            message="Warning",
        )
        from rich.console import Console

        console = Console(file=None)
        with console.capture() as capture:
            renderer._render_issue(console, issue, show_details=True)
        output = capture.get()

        assert "Evidence: no supporting evidence attached" in output


class TestJsonRenderer:
    """Tests for JsonRenderer class."""

    def test_render_error_includes_exit_code(self):
        """Test JSON errors are automation-friendly."""
        output = JsonRenderer().render_error("Something went wrong")

        assert '"type": "error"' in output
        assert '"exit_code": 2' in output
        assert "Something went wrong" in output
        assert '"analysis_complete": false' in output

    def test_render_error_includes_data_gaps(self):
        """Test JSON errors preserve partial-analysis gaps."""
        output = JsonRenderer().render_error(
            "Something went wrong",
            data_gaps=["events events unavailable (rbac): forbidden"],
        )

        assert '"data_gap_count": 1' in output
        assert "events events unavailable" in output

    def test_render_diagnosis_includes_issue_evidence(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON diagnosis preserves evidence for automation."""
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Missing Secret",
            description="Secret token is not found",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="Failed",
            message="secret token not found",
            evidence=['Event Warning/Failed: Error: secret "token" not found'],
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            issues=[issue],
            root_cause=issue,
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_diagnosis(result)
        parsed = json.loads(output)

        assert '"evidence"' in output
        assert 'secret \\"token\\" not found' in output
        assert '"data_gaps"' in output
        assert parsed["analysis_complete"] is True
        assert parsed["root_cause"]["evidence_count"] == 1
        assert parsed["root_cause"]["evidence_complete"] is True

    def test_render_diagnosis_marks_json_issue_without_evidence_incomplete(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test automation can detect root-cause claims without attached evidence."""
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Warning Without Evidence",
            description="Warning issue",
            severity=IssueSeverity.WARNING,
            score=70.0,
            reason="Warning",
            message="Warning",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=issue,
            analysis_duration=1.0,
        )

        parsed = json.loads(JsonRenderer().render_diagnosis(result))

        assert parsed["root_cause"]["evidence"] == []
        assert parsed["root_cause"]["evidence_count"] == 0
        assert parsed["root_cause"]["evidence_complete"] is False
        assert parsed["analysis_complete"] is False

    def test_render_diagnosis_includes_issue_metadata(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON diagnosis keeps structured issue metadata for automation."""
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Child pod failed",
            description="Deployment child pod is unhealthy",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="ChildLogFailure",
            message="Pod/default/api-abc: panic",
            metadata={
                "child_resource": "Pod/default/api-abc",
                "source_issue_resource_uid": "pod-uid",
            },
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            issues=[issue],
            root_cause=issue,
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_diagnosis(result)

        assert '"metadata"' in output
        assert '"child_resource": "Pod/default/api-abc"' in output
        assert '"source_issue_resource_uid": "pod-uid"' in output

    def test_render_diagnosis_includes_data_gap_summary(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON diagnosis exposes machine-readable completeness."""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            data_gaps=["events unavailable (rbac): forbidden"],
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_diagnosis(result)

        assert '"data_gap_count": 1' in output
        assert '"analysis_complete": false' in output

    def test_render_diagnosis_marks_missing_resource_incomplete(self, sample_subject_ctx):
        """Test JSON diagnosis completeness is false without target resource data."""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=None,
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_diagnosis(result)

        parsed = json.loads(output)
        assert parsed["resource"] is None
        assert parsed["data_gap_count"] == 0
        assert parsed["analysis_complete"] is False
        assert parsed["exit_code"] == 2

    def test_render_graph_includes_data_gap_summary(self, sample_subject_ctx):
        """Test JSON graph exposes machine-readable completeness."""
        result = GraphResult(
            subject=sample_subject_ctx,
            data_gaps=["get secrets unavailable (rbac): forbidden"],
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_graph(result)

        assert '"data_gap_count": 1' in output
        assert '"analysis_complete": false' in output

    def test_render_top_includes_data_gap_summary(self, sample_subject_ctx):
        """Test JSON top exposes machine-readable completeness."""
        result = TopResult(
            subject=sample_subject_ctx,
            data_gaps=["metrics pods unavailable (rbac): forbidden"],
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_top(result)

        assert '"data_gap_count": 1' in output
        assert '"analysis_complete": false' in output

    def test_render_batch_includes_per_resource_data_gap_summary(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON batch output preserves per-resource completeness."""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            data_gaps=["events events unavailable (rbac): forbidden"],
            suggested_actions=["kubectl auth can-i list events -n default"],
            analysis_duration=1.0,
        )
        complete_result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_batch(
            [result, complete_result],
            {
                "total": 2,
                "successful": 2,
                "failed": 0,
                "duration": 1.0,
                "max_concurrent": 2,
            },
        )

        assert '"data_gaps": 1' in output
        assert '"analysis_complete": false' in output
        assert '"max_concurrent": 2' in output
        assert '"data_gap_count": 1' in output
        assert "events events unavailable" in output
        assert "kubectl auth can-i list events" in output
        parsed = json.loads(output)
        assert parsed["results"][0]["data_gap_count"] == 1
        assert parsed["results"][0]["analysis_complete"] is False
        assert parsed["results"][1]["data_gap_count"] == 0
        assert parsed["results"][1]["analysis_complete"] is True

    def test_render_batch_summary_includes_exit_code(self):
        """Test JSON batch summary exposes the aggregate exit code."""
        output = JsonRenderer().render_batch(
            [],
            {
                "total": 0,
                "successful": 0,
                "failed": 1,
                "duration": 0.1,
                "errors": [{"message": "Failed to list pods: forbidden"}],
                "exit_code": 2,
            },
        )

        assert '"exit_code": 2' in output
        assert "Failed to list pods: forbidden" in output

    def test_render_batch_summary_includes_label_selector(self):
        """Test JSON batch summary preserves filtered batch scope."""
        output = JsonRenderer().render_batch(
            [],
            {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "duration": 0.1,
                "label_selector": "app=checkout",
            },
        )

        assert '"label_selector": "app=checkout"' in output

    def test_render_batch_preserves_non_error_messages(self):
        """Test JSON batch output separates empty-selection notes from errors."""
        output = JsonRenderer().render_batch(
            [],
            {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "duration": 0.1,
                "messages": [{"message": "No Pods found"}],
            },
        )

        assert '"errors": []' in output
        assert '"messages"' in output
        assert "No Pods found" in output
        assert '"exit_code": 0' in output

    def test_render_batch_infers_warning_exit_code(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON batch summary infers warning-only exit code."""
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Resource Status: Unknown",
            description="Pod test-pod is in Unknown state",
            severity=IssueSeverity.WARNING,
            score=70,
            reason="StatusUnknown",
            message="Resource is in unhealthy state: Unknown",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            issues=[issue],
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_batch(
            [result],
            {"total": 1, "successful": 1, "failed": 0},
        )

        assert '"critical": 0' in output
        assert '"warning": 1' in output
        assert '"warning_count": 1' in output
        parsed = json.loads(output)
        assert len(parsed["results"][0]["diagnostic_issues"]) == 1
        assert parsed["results"][0]["diagnostic_issues"][0]["title"] == issue.title
        assert '"exit_code": 1' in output

    def test_render_batch_infers_not_found_exit_code(self, sample_subject_ctx):
        """Test JSON batch summary honors per-resource not-found failures."""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=None,
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_batch(
            [result],
            {"total": 1, "successful": 1, "failed": 0},
        )

        parsed = json.loads(output)
        assert parsed["summary"]["exit_code"] == 2
        assert parsed["summary"]["analysis_complete"] is False
        assert parsed["summary"]["not_found"] == 1
        assert parsed["results"][0]["status"] is None
        assert parsed["results"][0]["analysis_complete"] is False
        assert parsed["results"][0]["exit_code"] == 2

    def test_render_batch_marks_unsupported_issue_evidence_incomplete(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test batch completeness reflects unsupported root-cause evidence."""
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Warning Without Evidence",
            description="Warning issue",
            severity=IssueSeverity.WARNING,
            score=70.0,
            reason="Warning",
            message="Warning",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            root_cause=issue,
            analysis_duration=1.0,
        )

        parsed = json.loads(
            JsonRenderer().render_batch(
                [result],
                {
                    "total": 1,
                    "successful": 1,
                    "failed": 0,
                    "duration": 1.0,
                },
            )
        )

        assert parsed["summary"]["analysis_complete"] is False
        assert parsed["results"][0]["analysis_complete"] is False

    def test_render_diagnosis_uses_warning_exit_code(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON diagnosis distinguishes warning-only results."""
        issue = Issue(
            resource_uid=sample_resource_record.uid,
            title="Resource Status: Unknown",
            description="Pod test-pod is in Unknown state",
            severity=IssueSeverity.WARNING,
            score=70,
            reason="StatusUnknown",
            message="Resource is in unhealthy state: Unknown",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            issues=[issue],
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_diagnosis(result)

        assert '"warning": 1' in output
        assert '"exit_code": 1' in output
