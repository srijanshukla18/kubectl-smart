"""
Unit tests for kubectl-smart data models

Tests the Pydantic models and their validators.
"""

import pytest
from datetime import datetime

from kubectl_smart.models import (
    ResourceKind,
    ResourceRecord,
    Issue,
    IssueSeverity,
    SubjectCtx,
)


class TestResourceRecord:
    """Tests for ResourceRecord model"""

    def test_full_name_with_namespace(self, sample_pod_resource):
        """Test full_name property includes namespace"""
        assert sample_pod_resource.full_name == "Pod/default/test-pod"

    def test_full_name_without_namespace(self):
        """Test full_name property without namespace"""
        resource = ResourceRecord(
            kind=ResourceKind.NODE,
            name="node-1",
            uid="node-123",
            namespace=None,
        )
        assert resource.full_name == "Node/node-1"

    def test_short_name(self, sample_pod_resource):
        """Test short_name property"""
        assert sample_pod_resource.short_name == "pod/test-pod"

    def test_get_property_nested(self, sample_pod_resource):
        """Test get_property with dot notation"""
        node_name = sample_pod_resource.get_property("spec.nodeName")
        assert node_name == "node-1"

    def test_get_property_missing_returns_default(self, sample_pod_resource):
        """Test get_property returns default for missing keys"""
        result = sample_pod_resource.get_property("spec.missing.key", default="fallback")
        assert result == "fallback"


class TestIssue:
    """Tests for Issue model"""

    def test_severity_auto_determined_from_score(self):
        """Test that severity is automatically determined from score"""
        critical_issue = Issue(
            resource_uid="test-uid",
            title="Test",
            description="Test issue",
            reason="TestReason",
            message="Test message",
            score=95.0,
            severity=IssueSeverity.INFO,  # Will be overridden
        )
        assert critical_issue.severity == IssueSeverity.CRITICAL

    def test_warning_severity_threshold(self):
        """Test warning severity threshold (50-89)"""
        warning_issue = Issue(
            resource_uid="test-uid",
            title="Test",
            description="Test issue",
            reason="TestReason",
            message="Test message",
            score=75.0,
            severity=IssueSeverity.INFO,  # Will be overridden
        )
        assert warning_issue.severity == IssueSeverity.WARNING

    def test_info_severity_threshold(self):
        """Test info severity threshold (<50)"""
        info_issue = Issue(
            resource_uid="test-uid",
            title="Test",
            description="Test issue",
            reason="TestReason",
            message="Test message",
            score=30.0,
            severity=IssueSeverity.CRITICAL,  # Will be overridden
        )
        assert info_issue.severity == IssueSeverity.INFO


class TestSubjectCtx:
    """Tests for SubjectCtx model"""

    def test_full_name_with_namespace(self, sample_subject):
        """Test full_name includes namespace"""
        assert sample_subject.full_name == "Pod/default/test-pod"

    def test_kubectl_args_with_namespace_and_context(self):
        """Test kubectl_args generation"""
        subject = SubjectCtx(
            kind=ResourceKind.POD,
            name="test-pod",
            namespace="production",
            context="prod-cluster",
        )
        args = subject.kubectl_args()
        assert "--context" in args
        assert "prod-cluster" in args
        assert "--namespace" in args
        assert "production" in args

    def test_kubectl_args_without_options(self):
        """Test kubectl_args with no context or namespace"""
        subject = SubjectCtx(
            kind=ResourceKind.POD,
            name="test-pod",
        )
        args = subject.kubectl_args()
        assert len(args) == 0


def test_resource_kind_enum_values():
    """Test ResourceKind enum has expected values"""
    assert ResourceKind.POD.value == "Pod"
    assert ResourceKind.DEPLOYMENT.value == "Deployment"
    assert ResourceKind.SERVICE.value == "Service"


def test_issue_severity_enum_values():
    """Test IssueSeverity enum has expected values"""
    assert IssueSeverity.CRITICAL.value == "critical"
    assert IssueSeverity.WARNING.value == "warning"
    assert IssueSeverity.INFO.value == "info"
