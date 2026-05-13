"""Tests for kubectl_smart/batch.py."""

import pytest

from kubectl_smart.batch import BatchAnalyzer
from kubectl_smart.models import ResourceKind


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
