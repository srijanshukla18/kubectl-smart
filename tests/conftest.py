"""
Pytest configuration and shared fixtures for kubectl-smart tests
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


@pytest.fixture
def sample_pod_resource():
    """Create a sample pod ResourceRecord for testing"""
    return ResourceRecord(
        kind=ResourceKind.POD,
        name="test-pod",
        uid="pod-123-uid",
        namespace="default",
        status="Running",
        labels={"app": "test", "env": "dev"},
        annotations={"description": "Test pod"},
        creation_timestamp=datetime.utcnow(),
        properties={
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "image": "nginx:latest"
                    }
                ],
                "nodeName": "node-1"
            },
            "status": {
                "phase": "Running"
            }
        }
    )


@pytest.fixture
def sample_critical_issue():
    """Create a sample critical issue for testing"""
    return Issue(
        resource_uid="pod-123-uid",
        title="CrashLoopBackOff",
        description="Pod is crash looping",
        severity=IssueSeverity.CRITICAL,
        score=95.0,
        reason="CrashLoopBackOff",
        message="Container failed to start",
        critical_path=True,
    )


@pytest.fixture
def sample_warning_issue():
    """Create a sample warning issue for testing"""
    return Issue(
        resource_uid="pod-123-uid",
        title="ImagePullBackOff",
        description="Failed to pull container image",
        severity=IssueSeverity.WARNING,
        score=75.0,
        reason="ImagePullBackOff",
        message="Failed to pull image: invalid-registry.com/app:latest",
        critical_path=False,
    )


@pytest.fixture
def sample_subject():
    """Create a sample SubjectCtx for testing"""
    return SubjectCtx(
        kind=ResourceKind.POD,
        name="test-pod",
        namespace="default",
        context=None,
        scope="resource",
    )
