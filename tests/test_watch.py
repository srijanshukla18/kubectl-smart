"""Tests for kubectl_smart/watch.py."""

import asyncio
from datetime import datetime

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
from kubectl_smart.watch import ResourceWatcher, WatchEvent


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


def test_watch_state_preserves_data_gaps():
    """Watch state should track analysis completeness, not just issues."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    resource = ResourceRecord(
        kind=ResourceKind.POD,
        name="api",
        uid="api-uid",
        namespace="default",
        status="Running",
    )
    result = DiagnosisResult(
        subject=subject,
        resource=resource,
        data_gaps=["events events unavailable (rbac): forbidden"],
        analysis_duration=0.1,
    )

    state = ResourceWatcher(subject)._extract_state(result)

    assert state.data_gap_count == 1
    assert state.data_gaps == ["events events unavailable (rbac): forbidden"]


def test_watch_detects_data_gap_changes(capsys):
    """Watch mode should announce when evidence sources appear or disappear."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject)
    previous = watcher._extract_state(
        DiagnosisResult(
            subject=subject,
            resource=ResourceRecord(
                kind=ResourceKind.POD,
                name="api",
                uid="api-uid",
                namespace="default",
                status="Running",
            ),
            analysis_duration=0.1,
        )
    )
    current = watcher._extract_state(
        DiagnosisResult(
            subject=subject,
            resource=ResourceRecord(
                kind=ResourceKind.POD,
                name="api",
                uid="api-uid",
                namespace="default",
                status="Running",
            ),
            data_gaps=["logs pods unavailable (rbac): forbidden"],
            analysis_duration=0.1,
        )
    )

    changes = watcher._detect_changes(previous, current, object())
    watcher._print_changes(changes)
    output = capsys.readouterr().out

    assert any(change.event_type == "data_gap_change" for change in changes)
    assert any(change.event_type == "data_gap_detected" for change in changes)
    assert "Data gaps: 0" in output
    assert "Data gap detected: logs pods unavailable" in output


def test_watch_print_changes_sanitizes_control_sequences(capsys):
    """Watch change lines should not emit terminal control sequences."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject)
    watcher._print_changes(
        [
            WatchEvent(
                timestamp=datetime.now(),
                event_type="new_issue",
                resource=subject.full_name,
                details={"issue": "Log \x1b[31mErrors\x1b[0m\rInjected"},
            ),
            WatchEvent(
                timestamp=datetime.now(),
                event_type="data_gap_detected",
                resource=subject.full_name,
                details={"gap": "logs \x1b[31mblocked\x1b[0m\a"},
            ),
        ]
    )

    output = capsys.readouterr().out

    assert "\x1b" not in output
    assert "Log \\x1b[31mErrors\\x1b[0m\\rInjected" in output
    assert "logs \\x1b[31mblocked\\x1b[0m\\a" in output


def test_watch_initial_command_output_sanitizes_control_sequences(capsys):
    """Legacy CommandResult output should be literal evidence, not terminal effects."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject)

    watcher._print_initial_state(
        CommandResult(output="rendered \x1b[31mred\x1b[0m\rnow", exit_code=1),
        renderer=object(),
        output_format="text",
    )
    output = capsys.readouterr().out

    assert "\x1b" not in output
    assert "rendered \\x1b[31mred\\x1b[0m\\rnow" in output


@pytest.mark.asyncio
async def test_check_resource_uses_raw_diagnosis_for_change_detection(
    monkeypatch,
    capsys,
):
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
        def __init__(self, *args, **kwargs):
            pass

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
    initial_output = capsys.readouterr().out
    await watcher._check_resource(FakeRenderer(), "text")

    assert calls == {"execute": 0, "execute_raw": 2}
    assert "rendered CrashLoopBackOff" in initial_output
    assert watcher.previous_state is not None
    assert watcher.previous_state.root_cause_title == "Log Errors"
    assert any(change.event_type == "root_cause_change" for change in changes)


@pytest.mark.asyncio
async def test_check_resource_records_failures_and_recovery(monkeypatch, capsys):
    """Watch mode should summarize failed checks and recovery."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    resource = ResourceRecord(
        kind=ResourceKind.POD,
        name="api",
        uid="api-uid",
        namespace="default",
        status="Running",
    )
    results = [
        RuntimeError("apiserver timeout"),
        DiagnosisResult(
            subject=subject,
            resource=resource,
            analysis_duration=0.1,
        ),
    ]

    class FakeDiagCommand:
        def __init__(self, *args, **kwargs):
            pass

        async def execute_raw(self, received_subject):
            assert received_subject == subject
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    class FakeRenderer:
        def render_diagnosis(self, result):
            return f"rendered {result.resource.name}"

    changes = []
    watcher = ResourceWatcher(subject, on_change=changes.append)

    monkeypatch.setattr(
        "kubectl_smart.cli.commands.DiagCommand",
        FakeDiagCommand,
    )

    await watcher._check_resource(FakeRenderer(), "text")
    await watcher._check_resource(FakeRenderer(), "text")
    output = capsys.readouterr().out

    assert "Check failed: apiserver timeout" in output
    assert "Check recovered" in output
    assert [event.event_type for event in watcher.events] == [
        "check_failed",
        "check_recovered",
    ]
    assert [event.event_type for event in changes] == [
        "check_failed",
        "check_recovered",
    ]


@pytest.mark.asyncio
async def test_check_resource_passes_collector_timeout(monkeypatch):
    """Watch mode should pass explicit collector timeouts to diag."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    resource = ResourceRecord(
        kind=ResourceKind.POD,
        name="api",
        uid="api-uid",
        namespace="default",
        status="Running",
    )
    captured = {}

    class FakeDiagCommand:
        def __init__(self, config=None):
            captured["timeout"] = config.collector_timeout

        async def execute_raw(self, received_subject):
            assert received_subject == subject
            return DiagnosisResult(
                subject=subject,
                resource=resource,
                analysis_duration=0.1,
            )

    class FakeRenderer:
        def render_diagnosis(self, result):
            return f"rendered {result.resource.name}"

    monkeypatch.setattr(
        "kubectl_smart.cli.commands.DiagCommand",
        FakeDiagCommand,
    )

    watcher = ResourceWatcher(subject, collector_timeout=2.5)
    await watcher._check_resource(FakeRenderer(), "text")

    assert captured["timeout"] == 2.5


@pytest.mark.asyncio
async def test_watch_start_returns_error_code_for_fatal_loop_error(
    monkeypatch,
    capsys,
):
    """Watch mode should not report success after the watch loop crashes."""
    subject = SubjectCtx(
        kind=ResourceKind.POD,
        name="api\x1b[31mred\x1b[0m",
        namespace="default",
    )
    watcher = ResourceWatcher(subject, interval_seconds=1)

    async def fail_check(*_args, **_kwargs):
        raise RuntimeError("terminal \x1b[31mrefresh\x1b[0m failed\rnow")

    monkeypatch.setattr(watcher, "_check_resource", fail_check)

    exit_code = await watcher.start(renderer=object(), output_format="text")
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "\x1b" not in output
    assert "Monitoring Pod/default/api\\x1b[31mred\\x1b[0m" in output
    assert "Watch error: terminal \\x1b[31mrefresh\\x1b[0m failed\\rnow" in output
    assert watcher.running is False


@pytest.mark.asyncio
async def test_watch_start_stops_cleanly_without_extra_sleep(monkeypatch, capsys):
    """A clean stop during a check should exit immediately and print a summary."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject, interval_seconds=30)
    calls = {"check": 0}
    sleeps = []

    async def check_once_then_stop(*_args, **_kwargs):
        calls["check"] += 1
        watcher.stop()

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(watcher, "_check_resource", check_once_then_stop)
    monkeypatch.setattr("kubectl_smart.watch.asyncio.sleep", fake_sleep)

    exit_code = await watcher.start(renderer=object(), output_format="text")
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls["check"] == 1
    assert sleeps == []
    assert watcher.iteration_count == 1
    assert "WATCH SUMMARY" in output
    assert "1 checks" in output


@pytest.mark.asyncio
async def test_watch_start_prints_summary_on_keyboard_interrupt(monkeypatch, capsys):
    """Ctrl+C-style interrupts should keep the existing graceful summary path."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject, interval_seconds=1)

    async def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(watcher, "_check_resource", interrupt)

    exit_code = await watcher.start(renderer=object(), output_format="text")
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Watch stopped by user" in output
    assert "WATCH SUMMARY" in output
    assert watcher.running is False


@pytest.mark.asyncio
async def test_watch_start_cleans_up_on_task_cancellation(monkeypatch, capsys):
    """External asyncio cancellation should stop the watch before propagating."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject, interval_seconds=30)

    async def check_once(*_args, **_kwargs):
        return None

    async def cancel_sleep(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(watcher, "_check_resource", check_once)
    monkeypatch.setattr("kubectl_smart.watch.asyncio.sleep", cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await watcher.start(renderer=object(), output_format="text")
    output = capsys.readouterr().out

    assert "Watch cancelled" in output
    assert "WATCH SUMMARY" in output
    assert "1 checks" in output
    assert watcher.running is False


def test_watch_summary_includes_event_breakdown(capsys):
    """Watch summaries should show event counts for resumable incident notes."""
    subject = SubjectCtx(kind=ResourceKind.POD, name="api", namespace="default")
    watcher = ResourceWatcher(subject, interval_seconds=5)
    watcher.iteration_count = 3
    watcher.events = [
        WatchEvent(
            timestamp=datetime.now(),
            event_type="check_failed",
            resource=subject.full_name,
        ),
        WatchEvent(
            timestamp=datetime.now(),
            event_type="check_failed",
            resource=subject.full_name,
        ),
        WatchEvent(
            timestamp=datetime.now(),
            event_type="check_recovered",
            resource=subject.full_name,
        ),
    ]

    watcher._print_summary()
    output = capsys.readouterr().out

    assert "Events detected: 3" in output
    assert "check_failed: 2" in output
    assert "check_recovered: 1" in output
