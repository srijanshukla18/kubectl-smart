"""
Watch mode for continuous monitoring of Kubernetes resources

This module provides real-time monitoring capabilities, alerting on changes
and new issues as they occur.
"""

import asyncio
import time
from typing import Optional, Set, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime

import structlog

from .models import SubjectCtx, DiagnosisResult
from .cli.commands import DiagCommand

logger = structlog.get_logger(__name__)


@dataclass
class WatchEvent:
    """Event detected during watch"""
    timestamp: datetime
    event_type: str  # "new_issue", "issue_resolved", "status_change"
    resource: str
    details: Dict[str, Any]


class ResourceWatcher:
    """Watches a resource for changes and issues"""

    def __init__(
        self,
        subject: SubjectCtx,
        interval_seconds: float = 5.0,
        alert_callback: Optional[Callable] = None,
    ):
        """Initialize resource watcher

        Args:
            subject: Resource to watch
            interval_seconds: Polling interval
            alert_callback: Optional callback for alerts
        """
        self.subject = subject
        self.interval_seconds = interval_seconds
        self.alert_callback = alert_callback
        self.running = False
        self.previous_state: Optional[DiagnosisResult] = None
        self.events: list[WatchEvent] = []

    async def start(self) -> None:
        """Start watching the resource"""
        self.running = True
        logger.info("Started watching resource", resource=self.subject.full_name)

        print(f"\n👁️  WATCH MODE: Monitoring {self.subject.full_name}")
        print(f"Polling interval: {self.interval_seconds}s")
        print(f"Press Ctrl+C to stop\n")
        print("=" * 60)

        try:
            while self.running:
                await self._check_resource()
                await asyncio.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            print("\n\n⏹️  Watch stopped by user")
            self.stop()
        except Exception as e:
            logger.error("Watch failed", error=str(e))
            self.stop()

    def stop(self) -> None:
        """Stop watching"""
        self.running = False
        logger.info("Stopped watching resource", resource=self.subject.full_name)

    async def _check_resource(self) -> None:
        """Check resource state and detect changes"""
        try:
            # Diagnose current state
            command = DiagCommand()
            result = await command.execute(self.subject)
            current_state = result.result_data

            if current_state is None:
                return

            # First check - just store state
            if self.previous_state is None:
                self.previous_state = current_state
                self._print_initial_state(current_state)
                return

            # Compare states and detect changes
            changes = self._detect_changes(self.previous_state, current_state)

            if changes:
                self._print_changes(changes)
                self.events.extend(changes)

                # Alert callback if configured
                if self.alert_callback:
                    for change in changes:
                        await self.alert_callback(change)

            self.previous_state = current_state

        except Exception as e:
            logger.error("Failed to check resource", error=str(e))

    def _print_initial_state(self, state: DiagnosisResult) -> None:
        """Print initial state"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"[{timestamp}] 📸 Initial State:")
        print(f"  Status: {state.resource.status if state.resource else 'Unknown'}")
        print(f"  Issues: {len(state.issues)}")

        if state.critical_issues:
            print(f"  🔴 Critical Issues: {len(state.critical_issues)}")
        if state.warning_issues:
            print(f"  🟡 Warnings: {len(state.warning_issues)}")

        print()

    def _detect_changes(
        self,
        previous: DiagnosisResult,
        current: DiagnosisResult,
    ) -> list[WatchEvent]:
        """Detect changes between states

        Args:
            previous: Previous state
            current: Current state

        Returns:
            List of detected changes
        """
        changes = []
        timestamp = datetime.now()

        # Status change
        if previous.resource and current.resource:
            if previous.resource.status != current.resource.status:
                changes.append(WatchEvent(
                    timestamp=timestamp,
                    event_type="status_change",
                    resource=self.subject.full_name,
                    details={
                        "old_status": previous.resource.status,
                        "new_status": current.resource.status,
                    }
                ))

        # New issues
        previous_issue_keys = {
            (issue.reason, issue.message) for issue in previous.issues
        }
        current_issue_keys = {
            (issue.reason, issue.message) for issue in current.issues
        }

        new_issue_keys = current_issue_keys - previous_issue_keys
        for issue in current.issues:
            if (issue.reason, issue.message) in new_issue_keys:
                changes.append(WatchEvent(
                    timestamp=timestamp,
                    event_type="new_issue",
                    resource=self.subject.full_name,
                    details={
                        "severity": issue.severity.value,
                        "reason": issue.reason,
                        "message": issue.message,
                        "score": issue.score,
                    }
                ))

        # Resolved issues
        resolved_issue_keys = previous_issue_keys - current_issue_keys
        for issue in previous.issues:
            if (issue.reason, issue.message) in resolved_issue_keys:
                changes.append(WatchEvent(
                    timestamp=timestamp,
                    event_type="issue_resolved",
                    resource=self.subject.full_name,
                    details={
                        "severity": issue.severity.value,
                        "reason": issue.reason,
                        "message": issue.message,
                    }
                ))

        return changes

    def _print_changes(self, changes: list[WatchEvent]) -> None:
        """Print detected changes

        Args:
            changes: List of changes to print
        """
        for change in changes:
            timestamp = change.timestamp.strftime("%H:%M:%S")

            if change.event_type == "status_change":
                old = change.details["old_status"]
                new = change.details["new_status"]
                print(f"[{timestamp}] 🔄 Status changed: {old} → {new}")

            elif change.event_type == "new_issue":
                severity = change.details["severity"]
                reason = change.details["reason"]
                score = change.details["score"]

                icon = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "ℹ️"
                print(f"[{timestamp}] {icon} New Issue: {reason} (score: {score})")
                print(f"           {change.details['message'][:80]}")

            elif change.event_type == "issue_resolved":
                severity = change.details["severity"]
                reason = change.details["reason"]

                print(f"[{timestamp}] ✅ Issue Resolved: {reason}")

        print()

    def get_summary(self) -> Dict[str, Any]:
        """Get watch session summary

        Returns:
            Summary dictionary
        """
        return {
            "resource": self.subject.full_name,
            "total_events": len(self.events),
            "event_types": {
                "new_issues": sum(1 for e in self.events if e.event_type == "new_issue"),
                "resolved_issues": sum(1 for e in self.events if e.event_type == "issue_resolved"),
                "status_changes": sum(1 for e in self.events if e.event_type == "status_change"),
            },
            "events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "type": e.event_type,
                    "details": e.details,
                }
                for e in self.events
            ],
        }


async def watch_resource(
    subject: SubjectCtx,
    interval_seconds: float = 5.0,
    duration_seconds: Optional[float] = None,
) -> ResourceWatcher:
    """Watch a resource for changes

    Args:
        subject: Resource to watch
        interval_seconds: Polling interval
        duration_seconds: Optional maximum duration

    Returns:
        ResourceWatcher instance with collected events
    """
    watcher = ResourceWatcher(subject, interval_seconds)

    if duration_seconds:
        # Watch for specified duration
        watch_task = asyncio.create_task(watcher.start())
        await asyncio.sleep(duration_seconds)
        watcher.stop()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass
    else:
        # Watch indefinitely
        await watcher.start()

    return watcher
