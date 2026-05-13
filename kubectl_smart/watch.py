"""
Watch mode for continuous monitoring of Kubernetes resources

Provides real-time monitoring with change detection, alerting when
issues appear or resolve.

Usage:
    kubectl-smart diag pod my-pod --watch
    kubectl-smart diag deploy my-app -n production --watch --interval 10
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

import structlog

from .models import SubjectCtx

logger = structlog.get_logger(__name__)  # type: ignore[attr-defined]


@dataclass
class WatchEvent:
    """Event detected during watch"""
    timestamp: datetime
    event_type: str  # "new_issue", "issue_resolved", "status_change", "score_change"
    resource: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchState:
    """Current watch state for comparison"""
    status: Optional[str] = None
    root_cause_title: Optional[str] = None
    root_cause_score: float = 0.0
    issue_count: int = 0
    issue_titles: List[str] = field(default_factory=list)


class ResourceWatcher:
    """Watches a resource for changes and issues"""

    def __init__(
        self,
        subject: SubjectCtx,
        interval_seconds: float = 5.0,
        on_change: Optional[Callable[[WatchEvent], None]] = None,
    ):
        """Initialize resource watcher

        Args:
            subject: Resource to watch
            interval_seconds: Polling interval
            on_change: Optional callback for change events
        """
        self.subject = subject
        self.interval_seconds = interval_seconds
        self.on_change = on_change
        self.running = False
        self.previous_state: Optional[WatchState] = None
        self.events: List[WatchEvent] = []
        self.iteration_count = 0

    async def start(self, renderer=None, output_format: str = "text") -> None:
        """Start watching the resource

        Args:
            renderer: Renderer to use for output
            output_format: Output format (text or json)
        """
        if renderer is None:
            from .renderers.terminal import TerminalRenderer

            renderer = TerminalRenderer()

        self.running = True
        logger.info("Started watching resource", resource=self.subject.full_name)

        print(f"\n👁️  WATCH MODE: Monitoring {self.subject.full_name}")
        print(f"Polling interval: {self.interval_seconds}s")
        print("Press Ctrl+C to stop\n")
        print("=" * 60)

        try:
            while self.running:
                await self._check_resource(renderer, output_format)
                self.iteration_count += 1
                await asyncio.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            print("\n\n⏹️  Watch stopped by user")
            self._print_summary()
            self.stop()
        except Exception as e:
            logger.error("Watch failed", error=str(e))
            print(f"\n❌ Watch error: {e}")
            self.stop()

    def stop(self) -> None:
        """Stop watching"""
        self.running = False
        logger.info("Stopped watching resource", resource=self.subject.full_name)

    async def _check_resource(self, renderer, output_format: str) -> None:
        """Check resource and detect changes"""
        try:
            # Lazy import to avoid circular dependency
            from .cli.commands import DiagCommand

            command = DiagCommand()
            result = await command.execute_raw(self.subject)

            # Build current state
            current_state = self._extract_state(result)

            # Detect changes
            if self.previous_state:
                changes = self._detect_changes(self.previous_state, current_state, result)
                if changes:
                    self._print_changes(changes)
            else:
                # First iteration - print full diagnosis
                self._print_initial_state(result, renderer, output_format)

            self.previous_state = current_state

        except Exception as e:
            logger.warning(f"Check failed: {e}")
            print(f"\n⚠️  [{datetime.now().strftime('%H:%M:%S')}] Check failed: {e}")

    def _extract_state(self, result) -> WatchState:
        """Extract comparable state from diagnosis result"""
        # Handle CommandResult vs DiagnosisResult
        if hasattr(result, 'output'):
            # It's a CommandResult, need to parse state from it
            # For simplicity, we'll track based on exit code
            return WatchState(
                status=self._status_from_exit_code(result.exit_code),
                root_cause_title=None,
                root_cause_score=0.0,
                issue_count=0,
                issue_titles=[],
            )

        # It's a DiagnosisResult
        return WatchState(
            status=result.resource.status if result.resource else None,
            root_cause_title=result.root_cause.title if result.root_cause else None,
            root_cause_score=result.root_cause.score if result.root_cause else 0.0,
            issue_count=len(result.issues),
            issue_titles=[i.title for i in result.issues],
        )

    def _status_from_exit_code(self, exit_code: int) -> str:
        """Map diagnosis exit codes to watch state labels."""
        if exit_code == 0:
            return "healthy"
        if exit_code == 1:
            return "warning"
        if exit_code == 2:
            return "critical_or_error"
        return f"exit_{exit_code}"

    def _detect_changes(
        self,
        prev: WatchState,
        curr: WatchState,
        result
    ) -> List[WatchEvent]:
        """Detect changes between states"""
        changes: List[WatchEvent] = []
        now = datetime.now()

        # Status change
        if prev.status != curr.status:
            event = WatchEvent(
                timestamp=now,
                event_type="status_change",
                resource=self.subject.full_name,
                details={
                    "previous": prev.status,
                    "current": curr.status
                }
            )
            changes.append(event)
            self.events.append(event)

        # Root cause change
        if prev.root_cause_title != curr.root_cause_title:
            if curr.root_cause_title and not prev.root_cause_title:
                event_type = "new_issue"
            elif prev.root_cause_title and not curr.root_cause_title:
                event_type = "issue_resolved"
            else:
                event_type = "root_cause_change"

            event = WatchEvent(
                timestamp=now,
                event_type=event_type,
                resource=self.subject.full_name,
                details={
                    "previous": prev.root_cause_title,
                    "current": curr.root_cause_title,
                    "score": curr.root_cause_score
                }
            )
            changes.append(event)
            self.events.append(event)

        # Score change (significant threshold: 10 points)
        if abs(prev.root_cause_score - curr.root_cause_score) >= 10:
            event = WatchEvent(
                timestamp=now,
                event_type="score_change",
                resource=self.subject.full_name,
                details={
                    "previous_score": prev.root_cause_score,
                    "current_score": curr.root_cause_score,
                    "delta": curr.root_cause_score - prev.root_cause_score
                }
            )
            changes.append(event)
            self.events.append(event)

        # New issues detected
        new_issues = set(curr.issue_titles) - set(prev.issue_titles)
        for issue_title in new_issues:
            event = WatchEvent(
                timestamp=now,
                event_type="new_issue",
                resource=self.subject.full_name,
                details={"issue": issue_title}
            )
            changes.append(event)
            self.events.append(event)

        # Resolved issues
        resolved_issues = set(prev.issue_titles) - set(curr.issue_titles)
        for issue_title in resolved_issues:
            event = WatchEvent(
                timestamp=now,
                event_type="issue_resolved",
                resource=self.subject.full_name,
                details={"issue": issue_title}
            )
            changes.append(event)
            self.events.append(event)

        return changes

    def _print_initial_state(self, result, renderer, output_format: str) -> None:
        """Print initial diagnosis state"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{timestamp}] Initial diagnosis:")

        if hasattr(result, 'output'):
            # CommandResult
            print(result.output)
        elif renderer:
            print(renderer.render_diagnosis(result))

    def _print_changes(self, changes: List[WatchEvent]) -> None:
        """Print detected changes"""
        for change in changes:
            timestamp = change.timestamp.strftime('%H:%M:%S')
            icon = self._get_event_icon(change.event_type)

            if change.event_type == "status_change":
                print(f"\n{icon} [{timestamp}] Status: {change.details['previous']} → {change.details['current']}")

            elif change.event_type == "new_issue":
                issue = change.details.get('issue') or change.details.get('current')
                score = change.details.get('score', '')
                score_str = f" (score: {score:.1f})" if score else ""
                print(f"\n{icon} [{timestamp}] New issue: {issue}{score_str}")

            elif change.event_type == "issue_resolved":
                issue = change.details.get('issue') or change.details.get('previous')
                print(f"\n{icon} [{timestamp}] Resolved: {issue}")

            elif change.event_type == "score_change":
                delta = change.details['delta']
                direction = "↑" if delta > 0 else "↓"
                print(f"\n{icon} [{timestamp}] Score: {change.details['previous_score']:.1f} → {change.details['current_score']:.1f} ({direction}{abs(delta):.1f})")

            elif change.event_type == "root_cause_change":
                print(f"\n{icon} [{timestamp}] Root cause changed: {change.details['previous']} → {change.details['current']}")

            # Trigger callback if registered
            if self.on_change:
                self.on_change(change)

    def _print_summary(self) -> None:
        """Print watch session summary"""
        print("\n" + "=" * 60)
        print("📊 WATCH SUMMARY")
        print(f"  Duration: {self.iteration_count * self.interval_seconds:.0f}s ({self.iteration_count} checks)")
        print(f"  Events detected: {len(self.events)}")

        if self.events:
            print("\n  Event breakdown:")
            event_types = {}
            for event in self.events:
                event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

            for event_type, count in sorted(event_types.items()):
                icon = self._get_event_icon(event_type)
                print(f"    {icon} {event_type}: {count}")

    def _get_event_icon(self, event_type: str) -> str:
        """Get icon for event type"""
        icons = {
            "status_change": "🔄",
            "new_issue": "🔴",
            "issue_resolved": "✅",
            "score_change": "📈",
            "root_cause_change": "⚠️",
        }
        return icons.get(event_type, "📌")

    def _get_event_color(self, event_type: str) -> str:
        """Get color for event type"""
        colors = {
            "status_change": "yellow",
            "new_issue": "red",
            "issue_resolved": "green",
            "score_change": "cyan",
            "root_cause_change": "yellow",
        }
        return colors.get(event_type, "white")
