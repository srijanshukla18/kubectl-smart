"""Tests for kubectl_smart/batch.py."""

import subprocess
from types import SimpleNamespace

import pytest

from kubectl_smart.batch import BatchAnalyzer
from kubectl_smart.models import (
    DiagnosisResult,
    ResourceKind,
    ResourceRecord,
    SubjectCtx,
)


@pytest.mark.asyncio
async def test_diagnose_resource_runs_single_diagnosis(monkeypatch):
    """Batch mode should not run the expensive diagnosis path twice."""
    analyzer = BatchAnalyzer()
    calls = []
    expected = object()

    async def fake_execute_diagnosis(subject):
        calls.append(subject.name)
        return expected

    async def fail_cli_execute(self, subject):
        raise AssertionError("DiagCommand.execute should not run in batch mode")

    monkeypatch.setattr(analyzer, "_execute_diagnosis", fake_execute_diagnosis)
    monkeypatch.setattr(
        "kubectl_smart.cli.commands.DiagCommand.execute",
        fail_cli_execute,
    )

    result = await analyzer._diagnose_resource(
        "checkout-api-0",
        ResourceKind.POD,
        "default",
        None,
    )

    assert result is expected
    assert calls == ["checkout-api-0"]


@pytest.mark.asyncio
async def test_execute_diagnosis_uses_diag_raw_path(monkeypatch):
    """Batch mode should preserve single-resource diag behavior and data gaps."""
    calls = {"execute": 0, "execute_raw": 0}
    subject = SubjectCtx(
        kind=ResourceKind.POD,
        name="checkout-api-0",
        namespace="default",
    )
    resource = ResourceRecord(
        kind=ResourceKind.POD,
        name="checkout-api-0",
        uid="pod-uid",
        namespace="default",
        status="CrashLoopBackOff",
    )
    expected = DiagnosisResult(
        subject=subject,
        resource=resource,
        data_gaps=["events events unavailable (rbac): forbidden"],
        analysis_duration=0.1,
    )

    async def fake_execute_raw(self, received_subject):
        calls["execute_raw"] += 1
        assert received_subject == subject
        return expected

    async def fail_execute(self, received_subject):
        calls["execute"] += 1
        raise AssertionError("Batch mode must use execute_raw, not rendered execute")

    monkeypatch.setattr(
        "kubectl_smart.cli.commands.DiagCommand.execute_raw",
        fake_execute_raw,
    )
    monkeypatch.setattr(
        "kubectl_smart.cli.commands.DiagCommand.execute",
        fail_execute,
    )

    result = await BatchAnalyzer()._execute_diagnosis(subject)

    assert result is expected
    assert result.data_gaps == ["events events unavailable (rbac): forbidden"]
    assert calls == {"execute": 0, "execute_raw": 1}


@pytest.mark.asyncio
async def test_get_resources_uses_configured_timeout(monkeypatch):
    """Batch resource discovery should honor the configured kubectl timeout."""
    captured = {}

    async def fake_to_thread(func, cmd, **kwargs):
        captured["cmd"] = cmd
        captured["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stdout="pod-a pod-b", stderr="")

    monkeypatch.setattr("kubectl_smart.batch.asyncio.to_thread", fake_to_thread)

    analyzer = BatchAnalyzer(kubectl_timeout=2.5)
    resources = await analyzer._get_resources(
        ResourceKind.POD,
        namespace="default",
        context="kind-demo",
        label_selector="app=checkout",
    )

    assert resources == ["pod-a", "pod-b"]
    assert captured["timeout"] == 2.5
    assert captured["cmd"] == [
        "kubectl",
        "get",
        "pods",
        "-o",
        "jsonpath={.items[*].metadata.name}",
        "-n",
        "default",
        "--context",
        "kind-demo",
        "-l",
        "app=checkout",
    ]


@pytest.mark.asyncio
async def test_diagnose_all_reports_resource_list_timeout(monkeypatch):
    """Batch mode should not call a list timeout 'no resources found'."""

    async def fake_to_thread(func, cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

    monkeypatch.setattr("kubectl_smart.batch.asyncio.to_thread", fake_to_thread)

    result = await BatchAnalyzer(kubectl_timeout=0.1).diagnose_all(
        ResourceKind.POD,
        namespace="default",
    )

    assert result.total_resources == 0
    assert result.successful == 0
    assert result.failed == 1
    assert result.errors == [{"message": "Timed out after 0.1s listing pods"}]


@pytest.mark.asyncio
async def test_diagnose_all_reports_resource_list_failure(monkeypatch):
    """Batch mode should surface kubectl list failures as errors."""

    async def fake_to_thread(func, cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="forbidden")

    monkeypatch.setattr("kubectl_smart.batch.asyncio.to_thread", fake_to_thread)

    result = await BatchAnalyzer().diagnose_all(ResourceKind.POD, namespace="default")

    assert result.total_resources == 0
    assert result.failed == 1
    assert result.errors == [{"message": "Failed to list pods: forbidden"}]
