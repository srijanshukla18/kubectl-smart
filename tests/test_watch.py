"""Tests for kubectl_smart/watch.py."""

from kubectl_smart.cli.commands import CommandResult
from kubectl_smart.models import ResourceKind, SubjectCtx
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
