"""Tests for kubectl_smart/batch.py."""

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
