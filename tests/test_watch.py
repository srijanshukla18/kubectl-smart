"""Tests for kubectl_smart/watch.py."""

import pytest

from kubectl_smart.cli.commands import CommandResult
from kubectl_smart.models import (
    DiagnosisResult,
    Issue,
    IssueSeverity,
    ResourceKind,
    ResourceRecord,
    SubjectCtx,
)
from kubectl_smart.watch import ResourceWatcher


def test_watch_state_preserves_warning_exit_code():
    """Watch mode should not flatten warnings into critical errors."""
    watcher = ResourceWatcher(
        SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    )

    warning = watcher._extract_state(CommandResult(output="", exit_code=1))
    critical = watcher._extract_state(CommandResult(output="", exit_code=2))

    assert warning.status == "warning"
    assert critical.status == "critical_or_error"


def test_watch_status_from_unknown_exit_code():
    """Unexpected exit codes should remain visible in watch state."""
    watcher = ResourceWatcher(
        SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    )

    state = watcher._extract_state(CommandResult(output="", exit_code=7))

    assert state.status == "exit_7"


@pytest.mark.asyncio
async def test_check_resource_uses_raw_diagnosis_for_change_detection(monkeypatch):
    """Watch mode should compare diagnosis details, not only exit-code labels."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    resource = ResourceRecord(
        kind=ResourceKind.POD,
        name="api",
        uid="api-uid",
        namespace="default",
        status="CrashLoopBackOff",
    )
    crash_issue = Issue(
        resource_uid="api-uid",
        title="CrashLoopBackOff",
        description="Container is restarting",
        severity=IssueSeverity.CRITICAL,
        score=85.0,
        reason="BackOff",
        message="Back-off restarting failed container",
    )
    log_issue = Issue(
        resource_uid="api-uid",
        title="Log Errors",
        description="Application emitted fatal startup errors",
        severity=IssueSeverity.CRITICAL,
        score=95.0,
        reason="LogFailure",
        message="panic: database connection refused",
    )
    results = [
        DiagnosisResult(
            subject=subject,
            resource=resource,
            issues=[crash_issue],
            root_cause=crash_issue,
            analysis_duration=0.1,
        ),
        DiagnosisResult(
            subject=subject,
            resource=resource,
            issues=[log_issue],
            root_cause=log_issue,
            analysis_duration=0.1,
        ),
    ]
    calls = {"execute": 0, "execute_raw": 0}

    class FakeDiagCommand:
        async def execute(self, received_subject):
            calls["execute"] += 1
            raise AssertionError("watch mode should not use rendered diagnosis")

        async def execute_raw(self, received_subject):
            calls["execute_raw"] += 1
            assert received_subject == subject
            return results.pop(0)

    class FakeRenderer:
        def render_diagnosis(self, result):
            return f"rendered {result.root_cause.title}"

    changes = []
    watcher = ResourceWatcher(subject, on_change=changes.append)

    monkeypatch.setattr(
        "kubectl_smart.cli.commands.DiagCommand",
        FakeDiagCommand,
    )

    await watcher._check_resource(FakeRenderer(), "text")
    await watcher._check_resource(FakeRenderer(), "text")

    assert calls == {"execute": 0, "execute_raw": 2}
    assert watcher.previous_state is not None
    assert watcher.previous_state.root_cause_title == "Log Errors"
    assert any(change.event_type == "root_cause_change" for change in changes)
