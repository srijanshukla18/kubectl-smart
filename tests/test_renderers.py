"""Tests for kubectl_smart/renderers/terminal.py"""



from kubectl_smart.models import (
    DiagnosisResult,
    GraphResult,
    Issue,
    IssueSeverity,
    ResourceKind,
    ResourceRecord,
    TopResult,
)
from kubectl_smart.renderers.terminal import TerminalRenderer
from kubectl_smart.renderers.json_renderer import JsonRenderer


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

    def test_render_diagnosis_resource_not_found(self, sample_subject_ctx):
        """Test diagnosis rendering when resource not found"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=None,
            analysis_duration=0.5,
        )
        output = renderer.render_diagnosis(result)

        assert "not found" in output

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

    def test_render_top_no_warnings(self, sample_subject_ctx):
        """Test top rendering with no warnings"""
        renderer = TerminalRenderer(colors_enabled=False)
        result = TopResult(
            subject=sample_subject_ctx,
            data_gaps=["metrics pods unavailable (rbac): forbidden"],
            forecast_horizon_hours=48,
            analysis_duration=1.0,
        )
        output = renderer.render_top(result)

        assert "No capacity or certificate issues predicted" in output
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


class TestJsonRenderer:
    """Tests for JsonRenderer class."""

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

        assert '"evidence"' in output
        assert 'secret \\"token\\" not found' in output
        assert '"data_gaps"' in output

    def test_render_batch_includes_data_gaps(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test JSON batch output preserves per-resource data gaps."""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            data_gaps=["events events unavailable (rbac): forbidden"],
            suggested_actions=["kubectl auth can-i list events -n default"],
            analysis_duration=1.0,
        )

        output = JsonRenderer().render_batch(
            [result],
            {
                "total": 1,
                "successful": 1,
                "failed": 0,
                "duration": 1.0,
                "max_concurrent": 2,
            },
        )

        assert '"data_gaps": 1' in output
        assert '"max_concurrent": 2' in output
        assert '"data_gap_count": 1' in output
        assert "events events unavailable" in output
        assert "kubectl auth can-i list events" in output

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

        assert '"warning_count": 1' in output
        assert '"exit_code": 1' in output

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
