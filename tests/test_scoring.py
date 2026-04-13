"""Tests for kubectl_smart/scoring/engine.py"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from kubectl_smart.graph.builder import GraphBuilder
from kubectl_smart.models import Issue, IssueSeverity, ResourceKind, ResourceRecord
from kubectl_smart.scoring.engine import ScoringEngine


class TestScoringEngine:
    """Tests for ScoringEngine class"""

    def test_scoring_engine_init_defaults(self):
        """Test ScoringEngine initialization with defaults"""
        engine = ScoringEngine()
        assert engine.weights is not None
        assert "base_scores" in engine.weights
        assert "multipliers" in engine.weights
        assert "keywords" in engine.weights

    def test_scoring_engine_init_custom_weights(self, tmp_path):
        """Test ScoringEngine with custom weights file"""
        weights_file = tmp_path / "weights.toml"
        weights_file.write_text("""
[base_scores]
TestReason = 75.0

[multipliers]
critical_path = 2.0

[multipliers.resource_type]
Pod = 1.5

[keywords.critical]
patterns = ["error"]
score = 20.0
""")
        engine = ScoringEngine(weights_file=str(weights_file))
        assert engine.base_scores.get("TestReason") == 75.0

    def test_scoring_engine_missing_weights_file(self, tmp_path):
        """Test ScoringEngine uses defaults for missing weights file"""
        engine = ScoringEngine(weights_file=str(tmp_path / "nonexistent.toml"))
        assert engine.base_scores is not None
        assert "Failed" in engine.base_scores

    def test_get_default_weights(self):
        """Test _get_default_weights returns complete structure"""
        engine = ScoringEngine()
        defaults = engine._get_default_weights()

        assert "base_scores" in defaults
        assert "multipliers" in defaults
        assert "keywords" in defaults
        assert defaults["base_scores"]["Failed"] == 50.0
        assert defaults["base_scores"]["FailedMount"] == 80.0


class TestScoreIssue:
    """Tests for score_issue method"""

    def test_score_issue_base_score(self):
        """Test scoring uses base score for reason"""
        engine = ScoringEngine()
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=0.0,
            reason="Failed",
            message="",
        )
        score = engine.score_issue(issue)
        assert score >= 50.0  # Base score for Failed

    def test_score_issue_keyword_scoring(self):
        """Test scoring adds keyword scores"""
        engine = ScoringEngine()
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=0.0,
            reason="Unknown",
            message="error occurred during timeout",
        )
        score = engine.score_issue(issue)
        # Should have keyword bonuses for "error" and "timeout"
        assert score > 20.0  # Default reason score

    def test_score_issue_critical_path_multiplier(self):
        """Test critical path multiplier is applied"""
        engine = ScoringEngine()
        issue_normal = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=0.0,
            reason="Failed",
            message="",
            critical_path=False,
        )
        issue_critical = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=0.0,
            reason="Failed",
            message="",
            critical_path=True,
        )
        score_normal = engine.score_issue(issue_normal)
        score_critical = engine.score_issue(issue_critical)
        assert score_critical > score_normal

    def test_score_issue_clamps_to_100(self):
        """Test score is clamped to maximum 100"""
        engine = ScoringEngine()
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.CRITICAL,
            score=0.0,
            reason="FailedScheduling",
            message="failed error timeout unable cannot denied",
            critical_path=True,
        )
        score = engine.score_issue(issue)
        assert score <= 100.0

    def test_score_issue_clamps_to_zero(self):
        """Test score is clamped to minimum 0"""
        engine = ScoringEngine()
        issue = Issue(
            resource_uid="test",
            title="Test",
            description="Test",
            severity=IssueSeverity.INFO,
            score=0.0,
            reason="UnknownReason",
            message="",
        )
        score = engine.score_issue(issue)
        assert score >= 0.0


class TestScoreResourceStatus:
    """Tests for score_resource_status method"""

    def test_score_resource_status_failed(self):
        """Test scoring Failed status"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="test-uid",
            status="Failed",
        )
        score = engine.score_resource_status(resource)
        assert score >= 90.0

    def test_score_resource_status_pending(self):
        """Test scoring Pending status"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="test-uid",
            status="Pending",
        )
        score = engine.score_resource_status(resource)
        assert score >= 40.0

    def test_score_resource_status_running(self):
        """Test scoring Running status returns 0"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="test-uid",
            status="Running",
        )
        score = engine.score_resource_status(resource)
        assert score == 0.0

    def test_score_resource_status_none(self):
        """Test scoring None status returns 0"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="test",
            uid="test-uid",
            status=None,
        )
        score = engine.score_resource_status(resource)
        assert score == 0.0


class TestCreateIssueFromEvent:
    """Tests for create_issue_from_event method"""

    def test_create_issue_from_event(self):
        """Test creating issue from event"""
        engine = ScoringEngine()
        event = ResourceRecord(
            kind=ResourceKind.EVENT,
            name="event-1",
            uid="event-uid",
            namespace="default",
            properties={
                "reason": "FailedMount",
                "message": "Unable to attach volume",
                "type": "Warning",
            },
        )
        target = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid",
            namespace="default",
        )
        issue = engine.create_issue_from_event(event, target)

        assert issue.resource_uid == target.uid
        assert "FailedMount" in issue.title
        assert issue.reason == "FailedMount"
        assert issue.score > 0

    def test_create_issue_from_event_critical_path(self):
        """Test creating issue from event with critical path"""
        engine = ScoringEngine()
        event = ResourceRecord(
            kind=ResourceKind.EVENT,
            name="event-1",
            uid="event-uid",
            namespace="default",
            properties={
                "reason": "Failed",
                "message": "Container failed",
                "type": "Warning",
            },
        )
        target = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid",
            namespace="default",
        )
        issue = engine.create_issue_from_event(event, target, is_critical_path=True)

        assert issue.critical_path is True

    def test_create_issue_from_event_severity_threshold(self):
        """Test issue severity is set based on score thresholds"""
        engine = ScoringEngine()
        event = ResourceRecord(
            kind=ResourceKind.EVENT,
            name="event-1",
            uid="event-uid",
            namespace="default",
            properties={
                "reason": "FailedScheduling",
                "message": "failed to schedule",
                "type": "Warning",
            },
        )
        target = ResourceRecord(
            kind=ResourceKind.NODE,
            name="test-node",
            uid="node-uid",
        )
        issue = engine.create_issue_from_event(event, target, is_critical_path=True)

        # With high base score, resource multiplier, and event type multiplier
        # should be at least WARNING
        assert issue.severity in [IssueSeverity.CRITICAL, IssueSeverity.WARNING]


class TestCreateIssueFromResourceStatus:
    """Tests for create_issue_from_resource_status method"""

    def test_create_issue_from_resource_status_failed(self):
        """Test creating issue from failed resource"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="failed-pod",
            uid="pod-uid",
            namespace="default",
            status="Failed",
        )
        issue = engine.create_issue_from_resource_status(resource)

        assert issue is not None
        assert issue.resource_uid == resource.uid
        assert issue.severity == IssueSeverity.CRITICAL

    def test_create_issue_from_resource_status_running_returns_none(self):
        """Test creating issue from running resource returns None"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="healthy-pod",
            uid="pod-uid",
            namespace="default",
            status="Running",
        )
        issue = engine.create_issue_from_resource_status(resource)

        assert issue is None

    def test_create_issue_from_resource_status_pending(self):
        """Test creating issue from pending resource"""
        engine = ScoringEngine()
        resource = ResourceRecord(
            kind=ResourceKind.POD,
            name="pending-pod",
            uid="pod-uid",
            namespace="default",
            status="Pending",
        )
        issue = engine.create_issue_from_resource_status(resource)

        assert issue is not None
        assert issue.severity == IssueSeverity.INFO


class TestAgeMultiplier:
    """Tests for age-based score multiplier"""

    def test_get_age_multiplier_recent(self):
        """Test age multiplier for recent events"""
        engine = ScoringEngine()
        recent_timestamp = datetime.now(timezone.utc) - timedelta(minutes=30)
        multiplier = engine._get_age_multiplier(recent_timestamp)
        assert multiplier == 1.0

    def test_get_age_multiplier_few_hours(self):
        """Test age multiplier for events a few hours old"""
        engine = ScoringEngine()
        timestamp = datetime.now(timezone.utc) - timedelta(hours=3)
        multiplier = engine._get_age_multiplier(timestamp)
        assert multiplier == 0.9

    def test_get_age_multiplier_day_old(self):
        """Test age multiplier for day-old events"""
        engine = ScoringEngine()
        timestamp = datetime.now(timezone.utc) - timedelta(hours=12)
        multiplier = engine._get_age_multiplier(timestamp)
        assert multiplier == 0.7

    def test_get_age_multiplier_week_old(self):
        """Test age multiplier for week-old events"""
        engine = ScoringEngine()
        timestamp = datetime.now(timezone.utc) - timedelta(days=3)
        multiplier = engine._get_age_multiplier(timestamp)
        assert multiplier == 0.5

    def test_get_age_multiplier_very_old(self):
        """Test age multiplier for very old events"""
        engine = ScoringEngine()
        timestamp = datetime.now(timezone.utc) - timedelta(days=14)
        multiplier = engine._get_age_multiplier(timestamp)
        assert multiplier == 0.3

    def test_get_age_multiplier_none(self):
        """Test age multiplier with None timestamp"""
        engine = ScoringEngine()
        multiplier = engine._get_age_multiplier(None)
        assert multiplier == 1.0

    def test_get_age_multiplier_string_timestamp(self):
        """Test age multiplier with string timestamp"""
        engine = ScoringEngine()
        timestamp_str = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        multiplier = engine._get_age_multiplier(timestamp_str)
        assert multiplier == 0.9


class TestAnalyzeIssues:
    """Tests for analyze_issues method"""

    def test_analyze_issues_from_events(self):
        """Test analyzing issues from events"""
        engine = ScoringEngine()
        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Running",
        )
        event = ResourceRecord(
            kind=ResourceKind.EVENT,
            name="event-1",
            uid="event-uid",
            namespace="default",
            properties={
                "reason": "FailedMount",
                "message": "Unable to mount volume",
                "type": "Warning",
                "involvedObject": {
                    "kind": "Pod",
                    "name": "test-pod",
                    "namespace": "default",
                    "uid": "pod-uid-123",
                },
            },
        )

        issues = engine.analyze_issues([pod], [event])
        assert len(issues) >= 1

    def test_analyze_issues_from_resource_status(self):
        """Test analyzing issues from resource status"""
        engine = ScoringEngine()
        failed_pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="failed-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Failed",
        )

        issues = engine.analyze_issues([failed_pod], [])
        assert len(issues) >= 1
        assert any(i.resource_uid == failed_pod.uid for i in issues)

    def test_analyze_issues_sorted_by_severity(self):
        """Test issues are sorted by severity and score"""
        engine = ScoringEngine()
        resources = [
            ResourceRecord(
                kind=ResourceKind.POD,
                name="critical-pod",
                uid="critical-uid",
                namespace="default",
                status="Failed",
            ),
            ResourceRecord(
                kind=ResourceKind.POD,
                name="pending-pod",
                uid="pending-uid",
                namespace="default",
                status="Pending",
            ),
        ]

        issues = engine.analyze_issues(resources, [])
        # Issues should be sorted by severity
        if len(issues) >= 2:
            first_severity = issues[0].severity.value
            assert first_severity in ["critical", "warning"]

    def test_analyze_issues_with_graph(self):
        """Test analyzing issues with dependency graph"""
        engine = ScoringEngine()
        graph = GraphBuilder()

        pod = ResourceRecord(
            kind=ResourceKind.POD,
            name="test-pod",
            uid="pod-uid-123",
            namespace="default",
            status="Failed",
        )
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="test-node",
            uid="node-uid-123",
            status="NotReady",
        )

        graph.add_resources([pod, node])
        issues = engine.analyze_issues([pod, node], [], graph)
        assert len(issues) >= 1


class TestRootCauseAnalysis:
    """Tests for root cause analysis methods"""

    def test_get_root_cause_empty(self):
        """Test get_root_cause with empty list"""
        engine = ScoringEngine()
        result = engine.get_root_cause([])
        assert result is None

    def test_get_root_cause_critical_first(self):
        """Test get_root_cause returns critical issue first"""
        engine = ScoringEngine()
        critical = Issue(
            resource_uid="critical",
            title="Critical Issue",
            description="Critical",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="CriticalError",
            message="Critical error",
        )
        warning = Issue(
            resource_uid="warning",
            title="Warning Issue",
            description="Warning",
            severity=IssueSeverity.WARNING,
            score=60.0,
            reason="WarningError",
            message="Warning error",
        )
        result = engine.get_root_cause([warning, critical])
        assert result.severity == IssueSeverity.CRITICAL

    def test_get_root_cause_prefers_critical_path(self):
        """Test get_root_cause prefers critical path issue"""
        engine = ScoringEngine()
        critical_not_path = Issue(
            resource_uid="critical1",
            title="Critical Issue 1",
            description="Critical",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="Error",
            message="Error",
            critical_path=False,
        )
        critical_on_path = Issue(
            resource_uid="critical2",
            title="Critical Issue 2",
            description="Critical",
            severity=IssueSeverity.CRITICAL,
            score=90.0,
            reason="Error",
            message="Error",
            critical_path=True,
        )
        result = engine.get_root_cause([critical_not_path, critical_on_path])
        assert result.critical_path is True

    def test_get_contributing_factors(self):
        """Test get_contributing_factors returns top 2 issues"""
        engine = ScoringEngine()
        root = Issue(
            resource_uid="root",
            title="Root Cause",
            description="Root",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="RootError",
            message="Root error",
        )
        factor1 = Issue(
            resource_uid="factor1",
            title="Factor 1",
            description="Factor",
            severity=IssueSeverity.WARNING,
            score=70.0,
            reason="Factor1Error",
            message="Factor 1",
        )
        factor2 = Issue(
            resource_uid="factor2",
            title="Factor 2",
            description="Factor",
            severity=IssueSeverity.WARNING,
            score=60.0,
            reason="Factor2Error",
            message="Factor 2",
        )
        factor3 = Issue(
            resource_uid="factor3",
            title="Factor 3",
            description="Factor",
            severity=IssueSeverity.INFO,
            score=30.0,
            reason="Factor3Error",
            message="Factor 3",
        )

        factors = engine.get_contributing_factors([root, factor1, factor2, factor3], root)
        assert len(factors) <= 2
        # Should not include low-score issues
        assert all(f.score >= 50.0 for f in factors)
        # Should not include root cause
        assert all(f.resource_uid != root.resource_uid for f in factors)

    def test_get_contributing_factors_excludes_root(self):
        """Test get_contributing_factors excludes root cause"""
        engine = ScoringEngine()
        root = Issue(
            resource_uid="root",
            title="Root Cause",
            description="Root",
            severity=IssueSeverity.CRITICAL,
            score=95.0,
            reason="RootError",
            message="Root error",
        )

        factors = engine.get_contributing_factors([root], root)
        assert len(factors) == 0
