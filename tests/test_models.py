"""Tests for kubectl_smart/models.py"""

import os
from datetime import datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from kubectl_smart.models import (
    AnalysisConfig,
    DiagnosisResult,
    GraphResult,
    Issue,
    IssueSeverity,
    RawBlob,
    ResourceKind,
    ResourceRecord,
    SubjectCtx,
    TopResult,
)


class TestResourceKind:
    """Tests for ResourceKind enum"""

    def test_all_resource_kinds_defined(self):
        """Test that all expected resource kinds are defined"""
        expected_kinds = [
            "Pod",
            "Deployment",
            "ReplicaSet",
            "StatefulSet",
            "DaemonSet",
            "Job",
            "CronJob",
            "Service",
            "Ingress",
            "ConfigMap",
            "Secret",
            "PersistentVolumeClaim",
            "PersistentVolume",
            "StorageClass",
            "Node",
            "Namespace",
            "ServiceAccount",
            "Role",
            "RoleBinding",
            "ClusterRole",
            "ClusterRoleBinding",
            "NetworkPolicy",
            "HorizontalPodAutoscaler",
            "VerticalPodAutoscaler",
            "Endpoints",
            "Event",
        ]
        for kind in expected_kinds:
            assert ResourceKind(kind) is not None

    def test_resource_kind_value(self):
        """Test ResourceKind values match expected strings"""
        assert ResourceKind.POD.value == "Pod"
        assert ResourceKind.DEPLOYMENT.value == "Deployment"
        assert ResourceKind.SERVICE.value == "Service"

    def test_resource_kind_is_string_enum(self):
        """Test ResourceKind behaves as string enum"""
        assert str(ResourceKind.POD) == "Pod"
        assert ResourceKind.POD == "Pod"


class TestIssueSeverity:
    """Tests for IssueSeverity enum"""

    def test_severity_values(self):
        """Test severity enum values"""
        assert IssueSeverity.CRITICAL.value == "critical"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"

    def test_severity_from_string(self):
        """Test creating severity from string"""
        assert IssueSeverity("critical") == IssueSeverity.CRITICAL
        assert IssueSeverity("warning") == IssueSeverity.WARNING
        assert IssueSeverity("info") == IssueSeverity.INFO


class TestRawBlob:
    """Tests for RawBlob model"""

    def test_raw_blob_creation_with_dict(self):
        """Test creating RawBlob with dict data"""
        blob = RawBlob(
            data={"key": "value"},
            source="test_collector",
        )
        assert blob.data == {"key": "value"}
        assert blob.source == "test_collector"
        assert blob.content_type == "application/json"

    def test_raw_blob_creation_with_string(self):
        """Test creating RawBlob with string data"""
        blob = RawBlob(
            data="raw string data",
            source="logs_collector",
            content_type="text/plain",
        )
        assert blob.data == "raw string data"
        assert blob.content_type == "text/plain"

    def test_raw_blob_creation_with_bytes(self):
        """Test creating RawBlob with bytes data"""
        blob = RawBlob(
            data=b"binary data",
            source="binary_collector",
        )
        assert blob.data == b"binary data"

    def test_raw_blob_timestamp_auto_generated(self):
        """Test RawBlob timestamp is auto-generated"""
        blob = RawBlob(data={}, source="test")
        assert blob.timestamp is not None
        assert isinstance(blob.timestamp, datetime)

    def test_raw_blob_metadata(self):
        """Test RawBlob metadata field"""
        blob = RawBlob(
            data={},
            source="test",
            metadata={"extra": "info"},
        )
        assert blob.metadata == {"extra": "info"}


class TestResourceRecord:
    """Tests for ResourceRecord model"""

    def test_resource_record_creation(self, sample_resource_record):
        """Test basic ResourceRecord creation"""
        record = sample_resource_record
        assert record.kind == ResourceKind.POD
        assert record.name == "test-pod"
        assert record.uid == "test-pod-uid-123"
        assert record.namespace == "default"

    def test_full_name_with_namespace(self):
        """Test full_name property with namespace"""
        record = ResourceRecord(
            kind=ResourceKind.POD,
            name="my-pod",
            uid="uid-123",
            namespace="production",
        )
        assert record.full_name == "Pod/production/my-pod"

    def test_full_name_without_namespace(self):
        """Test full_name property without namespace (cluster-scoped)"""
        record = ResourceRecord(
            kind=ResourceKind.NODE,
            name="worker-1",
            uid="node-uid-123",
        )
        assert record.full_name == "Node/worker-1"

    def test_short_name(self):
        """Test short_name property"""
        record = ResourceRecord(
            kind=ResourceKind.DEPLOYMENT,
            name="my-deploy",
            uid="uid-123",
        )
        assert record.short_name == "deployment/my-deploy"

    def test_get_property_simple(self):
        """Test get_property with simple key"""
        record = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="uid-123",
            properties={"simple": "value"},
        )
        assert record.get_property("simple") == "value"

    def test_get_property_nested(self):
        """Test get_property with nested key"""
        record = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="uid-123",
            properties={"spec": {"nodeName": "worker-1", "nested": {"deep": "value"}}},
        )
        assert record.get_property("spec.nodeName") == "worker-1"
        assert record.get_property("spec.nested.deep") == "value"

    def test_get_property_default(self):
        """Test get_property returns default for missing key"""
        record = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="uid-123",
            properties={},
        )
        assert record.get_property("missing") is None
        assert record.get_property("missing", "default") == "default"

    def test_get_property_invalid_path(self):
        """Test get_property with invalid nested path"""
        record = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="uid-123",
            properties={"spec": "not_a_dict"},
        )
        assert record.get_property("spec.nodeName") is None


class TestIssue:
    """Tests for Issue model"""

    def test_issue_creation(self, sample_issue):
        """Test basic Issue creation"""
        issue = sample_issue
        assert issue.title == "Container failed to start"
        assert issue.severity == IssueSeverity.CRITICAL
        assert issue.score == 85.0

    def test_issue_score_validation(self):
        """Test Issue score must be between 0 and 100"""
        with pytest.raises(ValidationError):
            Issue(
                resource_uid="test",
                title="Test",
                description="Test",
                severity=IssueSeverity.INFO,
                score=150.0,  # Invalid
                reason="Test",
                message="Test",
            )

        with pytest.raises(ValidationError):
            Issue(
                resource_uid="test",
                title="Test",
                description="Test",
                severity=IssueSeverity.INFO,
                score=-10.0,  # Invalid
                reason="Test",
                message="Test",
            )

    def test_issue_severity_auto_from_score_critical(self):
        """Test severity is auto-determined from score >= 90"""
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity="critical",
            score=95.0,
            reason="Test",
            message="Test",
        )
        assert issue.severity == IssueSeverity.CRITICAL

    def test_issue_severity_auto_from_score_warning(self):
        """Test severity is auto-determined from score >= 50"""
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity="warning",
            score=60.0,
            reason="Test",
            message="Test",
        )
        assert issue.severity == IssueSeverity.WARNING

    def test_issue_severity_auto_from_score_info(self):
        """Test severity is auto-determined from score < 50"""
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity="info",
            score=30.0,
            reason="Test",
            message="Test",
        )
        assert issue.severity == IssueSeverity.INFO

    def test_issue_to_display_dict(self, sample_issue):
        """Test Issue to_display_dict method"""
        display_dict = sample_issue.to_display_dict()
        assert "title" in display_dict
        assert "severity" in display_dict
        assert "score" in display_dict
        assert "evidence" in display_dict
        assert display_dict["severity"] == "critical"

    def test_issue_evidence_default(self):
        """Test Issue evidence defaults to an empty list."""
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=10.0,
            reason="Test",
            message="Test",
        )
        assert issue.evidence == []

    def test_issue_critical_path_default(self):
        """Test Issue critical_path defaults to False"""
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=10.0,
            reason="Test",
            message="Test",
        )
        assert issue.critical_path is False


class TestSubjectCtx:
    """Tests for SubjectCtx model"""

    def test_subject_ctx_creation(self, sample_subject_ctx):
        """Test SubjectCtx creation"""
        ctx = sample_subject_ctx
        assert ctx.kind == ResourceKind.POD
        assert ctx.name == "test-pod"
        assert ctx.namespace == "default"

    def test_subject_ctx_full_name_with_namespace(self):
        """Test SubjectCtx full_name with namespace"""
        ctx = SubjectCtx(
            kind=ResourceKind.DEPLOYMENT,
            name="my-deploy",
            namespace="production",
        )
        assert ctx.full_name == "Deployment/production/my-deploy"

    def test_subject_ctx_full_name_without_namespace(self):
        """Test SubjectCtx full_name without namespace"""
        ctx = SubjectCtx(
            kind=ResourceKind.NODE,
            name="worker-1",
        )
        assert ctx.full_name == "Node/worker-1"

    def test_subject_ctx_kubectl_args_with_context(self):
        """Test kubectl_args with context"""
        ctx = SubjectCtx(
            kind=ResourceKind.POD,
            name="test",
            context="my-cluster",
        )
        args = ctx.kubectl_args()
        assert "--context" in args
        assert "my-cluster" in args

    def test_subject_ctx_kubectl_args_with_namespace(self):
        """Test kubectl_args with namespace"""
        ctx = SubjectCtx(
            kind=ResourceKind.POD,
            name="test",
            namespace="kube-system",
        )
        args = ctx.kubectl_args()
        assert "--namespace" in args
        assert "kube-system" in args

    def test_subject_ctx_kubectl_args_empty(self):
        """Test kubectl_args with no context or namespace"""
        ctx = SubjectCtx(
            kind=ResourceKind.NODE,
            name="test",
        )
        args = ctx.kubectl_args()
        assert args == []

    def test_subject_ctx_depth_validation(self):
        """Test SubjectCtx depth validation (1-5)"""
        ctx = SubjectCtx(kind=ResourceKind.POD, name="test", depth=3)
        assert ctx.depth == 3

        with pytest.raises(ValidationError):
            SubjectCtx(kind=ResourceKind.POD, name="test", depth=0)

        with pytest.raises(ValidationError):
            SubjectCtx(kind=ResourceKind.POD, name="test", depth=10)


class TestDiagnosisResult:
    """Tests for DiagnosisResult model"""

    def test_diagnosis_result_creation(self, sample_subject_ctx, sample_resource_record):
        """Test DiagnosisResult creation"""
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            analysis_duration=1.5,
        )
        assert result.subject == sample_subject_ctx
        assert result.analysis_duration == 1.5

    def test_diagnosis_result_critical_issues(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test DiagnosisResult critical_issues property"""
        critical_issue = Issue(
            resource_uid="test",
            title="Critical",
            description="Critical issue",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="CriticalError",
            message="Critical message",
        )
        warning_issue = Issue(
            resource_uid="test",
            title="Warning",
            description="Warning issue",
            severity=IssueSeverity.WARNING,
            score=60.0,
            reason="WarningError",
            message="Warning message",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            issues=[critical_issue, warning_issue],
            analysis_duration=1.0,
        )
        assert len(result.critical_issues) == 1
        assert result.critical_issues[0].severity == IssueSeverity.CRITICAL

    def test_diagnosis_result_warning_issues(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test DiagnosisResult warning_issues property"""
        warning_issue = Issue(
            resource_uid="test",
            title="Warning",
            description="Warning issue",
            severity=IssueSeverity.WARNING,
            score=60.0,
            reason="WarningError",
            message="Warning message",
        )
        info_issue = Issue(
            resource_uid="test",
            title="Info",
            description="Info issue",
            severity=IssueSeverity.INFO,
            score=20.0,
            reason="Info",
            message="Info message",
        )
        result = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            issues=[warning_issue, info_issue],
            analysis_duration=1.0,
        )
        assert len(result.warning_issues) == 1
        assert result.warning_issues[0].severity == IssueSeverity.WARNING

    def test_diagnosis_result_exit_code_uses_highest_severity(
        self, sample_subject_ctx, sample_resource_record
    ):
        """Test diagnosis exit code follows documented severity levels."""
        warning_issue = Issue(
            resource_uid="test",
            title="Warning",
            description="Warning issue",
            severity=IssueSeverity.WARNING,
            score=60.0,
            reason="WarningError",
            message="Warning message",
        )
        critical_issue = warning_issue.model_copy(
            update={
                "severity": IssueSeverity.CRITICAL,
                "score": 95.0,
                "reason": "CriticalError",
            }
        )

        healthy = DiagnosisResult(
            subject=sample_subject_ctx,
            resource=sample_resource_record,
            analysis_duration=1.0,
        )
        warning = healthy.model_copy(update={"issues": [warning_issue]})
        critical = healthy.model_copy(update={"issues": [warning_issue, critical_issue]})

        assert healthy.exit_code == 0
        assert warning.exit_code == 1
        assert critical.exit_code == 2


class TestGraphResult:
    """Tests for GraphResult model"""

    def test_graph_result_creation(self, sample_subject_ctx):
        """Test GraphResult creation"""
        result = GraphResult(
            subject=sample_subject_ctx,
            ascii_graph="Root\n  └── Child",
            upstream_count=2,
            downstream_count=5,
            analysis_duration=0.5,
        )
        assert result.upstream_count == 2
        assert result.downstream_count == 5
        assert "Child" in result.ascii_graph


class TestTopResult:
    """Tests for TopResult model"""

    def test_top_result_creation(self, sample_subject_ctx):
        """Test TopResult creation"""
        result = TopResult(
            subject=sample_subject_ctx,
            capacity_warnings=[{"resource": "test", "utilization": 95}],
            certificate_warnings=[{"secret": "tls-cert", "days_left": 10}],
            forecast_horizon_hours=48,
            analysis_duration=2.0,
        )
        assert len(result.capacity_warnings) == 1
        assert len(result.certificate_warnings) == 1
        assert result.forecast_horizon_hours == 48


class TestAnalysisConfig:
    """Tests for AnalysisConfig model"""

    def test_analysis_config_defaults(self):
        """Test AnalysisConfig default values"""
        config = AnalysisConfig()
        assert config.max_concurrent_collectors == 5
        assert config.collector_timeout == 10.0
        assert config.cache_ttl_seconds == 300
        assert config.min_critical_score == 90.0
        assert config.min_warning_score == 50.0
        assert config.colors_enabled is True

    def test_analysis_config_custom_values(self):
        """Test AnalysisConfig with custom values"""
        config = AnalysisConfig(
            max_concurrent_collectors=10,
            collector_timeout=30.0,
            colors_enabled=False,
        )
        assert config.max_concurrent_collectors == 10
        assert config.collector_timeout == 30.0
        assert config.colors_enabled is False

    def test_analysis_config_env_colors(self):
        """Test AnalysisConfig reads KUBECTL_SMART_COLORS env var"""
        with patch.dict(os.environ, {"KUBECTL_SMART_COLORS": "false"}):
            config = AnalysisConfig()
            assert config.colors_enabled is False

    def test_analysis_config_env_cache_ttl(self):
        """Test AnalysisConfig reads KUBECTL_SMART_CACHE_TTL env var"""
        with patch.dict(os.environ, {"KUBECTL_SMART_CACHE_TTL": "600"}):
            config = AnalysisConfig()
            assert config.cache_ttl_seconds == 600

    def test_analysis_config_env_timeout(self):
        """Test AnalysisConfig reads KUBECTL_SMART_TIMEOUT env var"""
        with patch.dict(os.environ, {"KUBECTL_SMART_TIMEOUT": "20.0"}):
            config = AnalysisConfig()
            assert config.collector_timeout == 20.0

    def test_analysis_config_env_invalid_values(self):
        """Test AnalysisConfig handles invalid env var values gracefully"""
        with patch.dict(
            os.environ,
            {
                "KUBECTL_SMART_CACHE_TTL": "invalid",
                "KUBECTL_SMART_TIMEOUT": "not_a_number",
            },
        ):
            config = AnalysisConfig()
            # Should use defaults when parsing fails
            assert config.cache_ttl_seconds == 300
            assert config.collector_timeout == 10.0
