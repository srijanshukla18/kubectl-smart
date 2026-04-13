"""Pytest configuration and fixtures for kubectl-smart tests"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


@pytest.fixture
def sample_pod_json() -> Dict[str, Any]:
    """Sample pod JSON data"""
    return {
        "kind": "Pod",
        "apiVersion": "v1",
        "metadata": {
            "name": "test-pod",
            "namespace": "default",
            "uid": "test-pod-uid-123",
            "creationTimestamp": "2024-01-01T12:00:00Z",
            "labels": {"app": "test", "env": "dev"},
            "annotations": {"note": "test annotation"},
            "ownerReferences": [
                {"kind": "ReplicaSet", "name": "test-rs", "uid": "test-rs-uid"}
            ],
        },
        "spec": {
            "nodeName": "test-node",
            "serviceAccountName": "default",
            "containers": [
                {
                    "name": "main",
                    "image": "nginx:latest",
                    "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}},
                }
            ],
            "volumes": [
                {"name": "data", "persistentVolumeClaim": {"claimName": "test-pvc"}},
                {"name": "config", "configMap": {"name": "test-cm"}},
                {"name": "secrets", "secret": {"secretName": "test-secret"}},
            ],
        },
        "status": {"phase": "Running", "conditions": []},
    }


@pytest.fixture
def sample_deployment_json() -> Dict[str, Any]:
    """Sample deployment JSON data"""
    return {
        "kind": "Deployment",
        "apiVersion": "apps/v1",
        "metadata": {
            "name": "test-deploy",
            "namespace": "default",
            "uid": "test-deploy-uid-123",
            "creationTimestamp": "2024-01-01T10:00:00Z",
            "labels": {"app": "test"},
        },
        "spec": {
            "replicas": 3,
            "selector": {"matchLabels": {"app": "test"}},
            "template": {
                "metadata": {"labels": {"app": "test"}},
                "spec": {"containers": [{"name": "main", "image": "nginx"}]},
            },
        },
        "status": {
            "replicas": 3,
            "availableReplicas": 3,
            "conditions": [{"type": "Available", "status": "True"}],
        },
    }


@pytest.fixture
def sample_node_json() -> Dict[str, Any]:
    """Sample node JSON data"""
    return {
        "kind": "Node",
        "apiVersion": "v1",
        "metadata": {
            "name": "test-node",
            "uid": "test-node-uid-123",
            "creationTimestamp": "2024-01-01T00:00:00Z",
        },
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True"},
                {"type": "DiskPressure", "status": "False"},
                {"type": "MemoryPressure", "status": "False"},
            ],
            "allocatable": {"cpu": "4", "memory": "8Gi"},
            "capacity": {"cpu": "4", "memory": "8Gi"},
        },
    }


@pytest.fixture
def sample_event_json() -> Dict[str, Any]:
    """Sample event JSON data"""
    return {
        "kind": "Event",
        "apiVersion": "v1",
        "metadata": {
            "name": "test-pod.12345",
            "namespace": "default",
            "uid": "event-uid-123",
        },
        "involvedObject": {
            "kind": "Pod",
            "name": "test-pod",
            "namespace": "default",
            "uid": "test-pod-uid-123",
        },
        "reason": "Failed",
        "message": "Container failed to start",
        "type": "Warning",
        "firstTimestamp": "2024-01-01T12:00:00Z",
        "lastTimestamp": "2024-01-01T12:05:00Z",
        "count": 3,
    }


@pytest.fixture
def sample_pvc_json() -> Dict[str, Any]:
    """Sample PVC JSON data"""
    return {
        "kind": "PersistentVolumeClaim",
        "apiVersion": "v1",
        "metadata": {
            "name": "test-pvc",
            "namespace": "default",
            "uid": "test-pvc-uid-123",
        },
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": "10Gi"}},
            "storageClassName": "standard",
        },
        "status": {"phase": "Bound", "capacity": {"storage": "10Gi"}},
    }


@pytest.fixture
def sample_secret_json() -> Dict[str, Any]:
    """Sample secret JSON data"""
    return {
        "kind": "Secret",
        "apiVersion": "v1",
        "metadata": {
            "name": "test-secret",
            "namespace": "default",
            "uid": "test-secret-uid-123",
        },
        "type": "kubernetes.io/tls",
        "data": {"tls.crt": "", "tls.key": ""},
    }


@pytest.fixture
def sample_service_json() -> Dict[str, Any]:
    """Sample service JSON data"""
    return {
        "kind": "Service",
        "apiVersion": "v1",
        "metadata": {
            "name": "test-svc",
            "namespace": "default",
            "uid": "test-svc-uid-123",
        },
        "spec": {
            "selector": {"app": "test"},
            "ports": [{"port": 80, "targetPort": 8080}],
            "type": "ClusterIP",
        },
    }


@pytest.fixture
def sample_resource_record() -> ResourceRecord:
    """Sample ResourceRecord for testing"""
    return ResourceRecord(
        kind=ResourceKind.POD,
        name="test-pod",
        uid="test-pod-uid-123",
        namespace="default",
        status="Running",
        labels={"app": "test"},
        properties={
            "spec": {"nodeName": "test-node"},
            "status": {"phase": "Running"},
        },
    )


@pytest.fixture
def sample_failed_pod_record() -> ResourceRecord:
    """Sample failed pod for testing"""
    return ResourceRecord(
        kind=ResourceKind.POD,
        name="failed-pod",
        uid="failed-pod-uid-123",
        namespace="default",
        status="Failed",
        labels={"app": "broken"},
        properties={
            "spec": {},
            "status": {"phase": "Failed"},
        },
    )


@pytest.fixture
def sample_issue() -> Issue:
    """Sample Issue for testing"""
    return Issue(
        resource_uid="test-pod-uid-123",
        title="Container failed to start",
        description="The container main failed to start due to image pull error",
        severity=IssueSeverity.CRITICAL,
        score=85.0,
        reason="ImagePullBackOff",
        message="Failed to pull image nginx:latest",
        critical_path=True,
        suggested_actions=["Check image name", "Verify registry access"],
    )


@pytest.fixture
def sample_subject_ctx() -> SubjectCtx:
    """Sample SubjectCtx for testing"""
    return SubjectCtx(
        kind=ResourceKind.POD,
        name="test-pod",
        namespace="default",
        context=None,
        scope="resource",
    )


@pytest.fixture
def sample_raw_blob() -> RawBlob:
    """Sample RawBlob for testing"""
    return RawBlob(
        data={"kind": "Pod", "metadata": {"name": "test", "uid": "uid-123"}},
        source="kubectl_get",
        content_type="application/json",
    )


@pytest.fixture
def sample_analysis_config() -> AnalysisConfig:
    """Sample AnalysisConfig for testing"""
    return AnalysisConfig(
        colors_enabled=False,
        max_display_issues=5,
        max_suggested_actions=3,
    )


@pytest.fixture
def sample_events_list_json() -> Dict[str, Any]:
    """Sample events list JSON"""
    return {
        "kind": "List",
        "items": [
            {
                "kind": "Event",
                "metadata": {
                    "name": "event-1",
                    "namespace": "default",
                    "uid": "event-1-uid",
                },
                "involvedObject": {
                    "kind": "Pod",
                    "name": "test-pod",
                    "uid": "test-pod-uid-123",
                },
                "reason": "FailedMount",
                "message": "Unable to attach or mount volumes",
                "type": "Warning",
                "count": 5,
            }
        ],
    }


@pytest.fixture
def sample_resources_list_json(
    sample_pod_json, sample_deployment_json, sample_node_json
) -> Dict[str, Any]:
    """Sample resources list JSON"""
    return {"kind": "List", "items": [sample_pod_json, sample_deployment_json]}


@pytest.fixture
def mock_kubectl_output() -> MagicMock:
    """Mock for kubectl subprocess output"""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = b'{"kind": "Pod", "metadata": {"name": "test", "uid": "123"}}'
    mock.stderr = b""
    return mock


@pytest.fixture
def metrics_server_output() -> str:
    """Sample metrics server output"""
    return """NAME       CPU(cores)   MEMORY(bytes)
test-pod   100m         256Mi
other-pod  200m         512Mi"""


@pytest.fixture
def node_metrics_output() -> str:
    """Sample node metrics output"""
    return """NAME        CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
test-node   2000m        50%    4096Mi          50%"""
