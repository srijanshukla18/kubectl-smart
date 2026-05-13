"""Tests for kubectl_smart/parsers/base.py"""

import json

import pytest

from kubectl_smart.models import RawBlob, ResourceKind
from kubectl_smart.parsers.base import (
    EventParser,
    KubernetesResourceParser,
    LogParser,
    MetricsParser,
    Parser,
    ParserError,
    ParserRegistry,
    PrometheusTextParser,
    TextParser,
    registry,
)


class TestParserError:
    """Tests for ParserError exception"""

    def test_parser_error(self):
        """Test ParserError is raised properly"""
        with pytest.raises(ParserError):
            raise ParserError("Test error")


class TestParserBase:
    """Tests for base Parser class"""

    def test_safe_get_simple(self):
        """Test _safe_get with simple key"""
        parser = KubernetesResourceParser()
        data = {"key": "value"}
        assert parser._safe_get(data, "key") == "value"

    def test_safe_get_nested(self):
        """Test _safe_get with nested key"""
        parser = KubernetesResourceParser()
        data = {"level1": {"level2": {"level3": "deep_value"}}}
        assert parser._safe_get(data, "level1.level2.level3") == "deep_value"

    def test_safe_get_missing_returns_default(self):
        """Test _safe_get returns default for missing key"""
        parser = KubernetesResourceParser()
        data = {"key": "value"}
        assert parser._safe_get(data, "missing") is None
        assert parser._safe_get(data, "missing", "default") == "default"

    def test_safe_get_list_index(self):
        """Test _safe_get with list index"""
        parser = KubernetesResourceParser()
        data = {"items": ["first", "second", "third"]}
        assert parser._safe_get(data, "items.0") == "first"
        assert parser._safe_get(data, "items.2") == "third"

    def test_safe_get_invalid_path(self):
        """Test _safe_get with invalid path"""
        parser = KubernetesResourceParser()
        data = {"key": "not_a_dict"}
        assert parser._safe_get(data, "key.nested") is None

    def test_parse_timestamp_rfc3339(self):
        """Test _parse_timestamp with RFC3339 format"""
        parser = KubernetesResourceParser()
        ts = parser._parse_timestamp("2024-01-15T12:30:45Z")
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15

    def test_parse_timestamp_with_nanoseconds(self):
        """Test _parse_timestamp with nanoseconds"""
        parser = KubernetesResourceParser()
        ts = parser._parse_timestamp("2024-01-15T12:30:45.123456789Z")
        assert ts is not None
        assert ts.year == 2024

    def test_parse_timestamp_none(self):
        """Test _parse_timestamp with None"""
        parser = KubernetesResourceParser()
        assert parser._parse_timestamp(None) is None

    def test_parse_timestamp_empty(self):
        """Test _parse_timestamp with empty string"""
        parser = KubernetesResourceParser()
        assert parser._parse_timestamp("") is None

    def test_parse_timestamp_invalid(self):
        """Test _parse_timestamp with invalid format"""
        parser = KubernetesResourceParser()
        assert parser._parse_timestamp("not-a-timestamp") is None


class TestKubernetesResourceParser:
    """Tests for KubernetesResourceParser"""

    def test_feed_single_pod(self, sample_pod_json):
        """Test parsing a single pod resource"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_pod_json, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)

        assert len(resources) == 1
        pod = resources[0]
        assert pod.kind == ResourceKind.POD
        assert pod.name == "test-pod"
        assert pod.namespace == "default"
        assert pod.uid == "test-pod-uid-123"

    def test_feed_resource_list(self, sample_pod_json, sample_deployment_json):
        """Test parsing a list of resources"""
        parser = KubernetesResourceParser()
        list_data = {"kind": "List", "items": [sample_pod_json, sample_deployment_json]}
        blob = RawBlob(
            data=list_data, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)

        assert len(resources) == 2
        kinds = [r.kind for r in resources]
        assert ResourceKind.POD in kinds
        assert ResourceKind.DEPLOYMENT in kinds

    def test_feed_non_json_returns_empty(self):
        """Test parsing non-JSON content returns empty list"""
        parser = KubernetesResourceParser()
        blob = RawBlob(data="plain text", source="test", content_type="text/plain")
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_string_json(self, sample_pod_json):
        """Test parsing JSON string data"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=json.dumps(sample_pod_json),
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert len(resources) == 1

    def test_feed_invalid_json_returns_empty(self):
        """Test parsing invalid JSON returns empty list"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data="{invalid json", source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_unknown_kind_skipped(self):
        """Test resources with unknown kind are skipped"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data={
                "kind": "UnknownResource",
                "metadata": {"name": "test", "uid": "123"},
            },
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_missing_name_skipped(self):
        """Test resources missing name are skipped"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data={"kind": "Pod", "metadata": {"uid": "123"}},
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_missing_uid_skipped(self):
        """Test resources missing UID are skipped"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data={"kind": "Pod", "metadata": {"name": "test"}},
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources == []

    def test_extract_pod_status(self, sample_pod_json):
        """Test Pod status extraction"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_pod_json, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Running"

    def test_extract_pod_waiting_container_status(self, sample_pod_json):
        """Test Pod status prefers container waiting reason over phase."""
        parser = KubernetesResourceParser()
        sample_pod_json["status"] = {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "api",
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off restarting failed container",
                        }
                    },
                }
            ],
        }
        blob = RawBlob(
            data=sample_pod_json,
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)

        assert resources[0].status == "CrashLoopBackOff"

    def test_extract_node_status(self, sample_node_json):
        """Test Node status extraction"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_node_json, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Ready"

    def test_extract_node_not_ready_status(self):
        """Test Node NotReady status extraction"""
        parser = KubernetesResourceParser()
        data = {
            "kind": "Node",
            "metadata": {"name": "bad-node", "uid": "node-123"},
            "status": {
                "conditions": [{"type": "Ready", "status": "False"}],
            },
        }
        blob = RawBlob(
            data=data, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources[0].status == "NotReady"

    def test_extract_deployment_status(self, sample_deployment_json):
        """Test Deployment status extraction"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_deployment_json,
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Available"

    def test_extract_pvc_status(self, sample_pvc_json):
        """Test PVC status extraction"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_pvc_json, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Bound"

    def test_extract_service_status(self, sample_service_json):
        """Test Service status extraction"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_service_json,
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Active"

    def test_extract_empty_endpoints_status(self):
        """Test empty Endpoints are marked unavailable for service diagnosis."""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data={
                "kind": "Endpoints",
                "metadata": {
                    "name": "api",
                    "namespace": "default",
                    "uid": "endpoints-uid",
                },
                "subsets": [],
            },
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources[0].kind == ResourceKind.ENDPOINTS
        assert resources[0].status == "Unavailable"
        assert resources[0].properties["subsets"] == []

    def test_extract_ready_endpoints_status(self):
        """Test Endpoints with addresses are active."""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data={
                "kind": "Endpoints",
                "metadata": {
                    "name": "api",
                    "namespace": "default",
                    "uid": "endpoints-uid",
                },
                "subsets": [{"addresses": [{"ip": "10.0.0.10"}]}],
            },
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Active"
        assert resources[0].properties["subsets"] == [{"addresses": [{"ip": "10.0.0.10"}]}]

    def test_extract_job_complete_status(self):
        """Test Job Complete status extraction"""
        parser = KubernetesResourceParser()
        data = {
            "kind": "Job",
            "metadata": {"name": "test-job", "uid": "job-123"},
            "status": {"conditions": [{"type": "Complete", "status": "True"}]},
        }
        blob = RawBlob(
            data=data, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Complete"

    def test_extract_job_failed_status(self):
        """Test Job Failed status extraction"""
        parser = KubernetesResourceParser()
        data = {
            "kind": "Job",
            "metadata": {"name": "test-job", "uid": "job-123"},
            "status": {"conditions": [{"type": "Failed", "status": "True"}]},
        }
        blob = RawBlob(
            data=data, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)
        assert resources[0].status == "Failed"

    def test_labels_and_annotations_extracted(self, sample_pod_json):
        """Test labels and annotations are extracted"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_pod_json, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)

        assert resources[0].labels == {"app": "test", "env": "dev"}
        assert resources[0].annotations == {"note": "test annotation"}

    def test_properties_include_spec_status(self, sample_pod_json):
        """Test properties include spec and status"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_pod_json, source="kubectl_get", content_type="application/json"
        )
        resources = parser.feed(blob)

        assert "spec" in resources[0].properties
        assert "status" in resources[0].properties
        assert "metadata" in resources[0].properties

    def test_secret_data_included(self, sample_secret_json):
        """Test secret data field is included in properties"""
        parser = KubernetesResourceParser()
        blob = RawBlob(
            data=sample_secret_json,
            source="kubectl_get",
            content_type="application/json",
        )
        resources = parser.feed(blob)

        assert "data" in resources[0].properties
        assert "type" in resources[0].properties


class TestEventParser:
    """Tests for EventParser"""

    def test_feed_events(self, sample_events_list_json):
        """Test parsing events list"""
        parser = EventParser()
        blob = RawBlob(
            data=sample_events_list_json,
            source="kubectl_events",
            content_type="application/json",
        )
        resources = parser.feed(blob)

        assert len(resources) == 1
        event = resources[0]
        assert event.kind == ResourceKind.EVENT
        assert event.properties["reason"] == "FailedMount"

    def test_feed_single_event(self, sample_event_json):
        """Test parsing a single event"""
        parser = EventParser()
        blob = RawBlob(
            data={"kind": "List", "items": [sample_event_json]},
            source="kubectl_events",
            content_type="application/json",
        )
        resources = parser.feed(blob)

        assert len(resources) == 1
        event = resources[0]
        assert event.properties["reason"] == "Failed"
        assert event.properties["message"] == "Container failed to start"
        assert event.properties["type"] == "Warning"
        assert event.properties["count"] == 3
        assert event.creation_timestamp.isoformat() == "2024-01-01T12:05:00+00:00"

    def test_feed_event_without_uid_skipped(self):
        """Test events without UID are skipped"""
        parser = EventParser()
        blob = RawBlob(
            data={
                "kind": "List",
                "items": [
                    {
                        "metadata": {"name": "event-1"},
                        "involvedObject": {},
                        "reason": "Test",
                    }
                ],
            },
            source="kubectl_events",
            content_type="application/json",
        )
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_non_json_returns_empty(self):
        """Test parsing non-JSON returns empty list"""
        parser = EventParser()
        blob = RawBlob(data="plain text", source="test", content_type="text/plain")
        resources = parser.feed(blob)
        assert resources == []

    def test_event_involved_object_stored(self, sample_event_json):
        """Test involvedObject is stored in properties"""
        parser = EventParser()
        blob = RawBlob(
            data={"kind": "List", "items": [sample_event_json]},
            source="kubectl_events",
            content_type="application/json",
        )
        resources = parser.feed(blob)

        assert "involvedObject" in resources[0].properties
        assert resources[0].properties["involvedObject"]["name"] == "test-pod"


class TestTextParser:
    """Tests for TextParser"""

    def test_feed_returns_empty(self):
        """Test TextParser always returns empty list"""
        parser = TextParser()
        blob = RawBlob(
            data="Some log output\nMore logs", source="kubectl_logs", content_type="text/plain"
        )
        resources = parser.feed(blob)
        assert resources == []


class TestMetricsParser:
    """Tests for MetricsParser"""

    def test_feed_pod_metrics(self, metrics_server_output):
        """Test parsing pod metrics"""
        parser = MetricsParser()
        blob = RawBlob(
            data={"raw": metrics_server_output},
            source="metrics_server",
            content_type="text/plain",
        )
        resources = parser.feed(blob)

        assert len(resources) == 2
        assert resources[0].kind == ResourceKind.POD
        assert resources[0].name == "test-pod"
        assert resources[0].properties["metrics"]["cpu"] == "100m"
        assert resources[0].properties["metrics"]["memory"] == "256Mi"

    def test_feed_node_metrics(self, node_metrics_output):
        """Test parsing node metrics"""
        parser = MetricsParser()
        blob = RawBlob(
            data={"raw": node_metrics_output},
            source="metrics_server",
            content_type="text/plain",
        )
        resources = parser.feed(blob)

        assert len(resources) == 1
        assert resources[0].kind == ResourceKind.NODE
        assert resources[0].name == "test-node"
        assert resources[0].properties["metrics"]["cpu_percent"] == "50"
        assert resources[0].properties["metrics"]["memory_percent"] == "50"

    def test_feed_non_text_returns_empty(self):
        """Test parsing non-text content returns empty"""
        parser = MetricsParser()
        blob = RawBlob(data={}, source="test", content_type="application/json")
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_empty_output_returns_empty(self):
        """Test parsing empty output returns empty"""
        parser = MetricsParser()
        blob = RawBlob(data={"raw": ""}, source="metrics_server", content_type="text/plain")
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_single_header_line_returns_empty(self):
        """Test parsing output with only header returns empty"""
        parser = MetricsParser()
        blob = RawBlob(
            data={"raw": "NAME       CPU(cores)   MEMORY(bytes)"},
            source="metrics_server",
            content_type="text/plain",
        )
        resources = parser.feed(blob)
        assert resources == []


class TestPrometheusTextParser:
    """Tests for PrometheusTextParser"""

    def test_feed_pvc_metrics(self):
        """Test parsing PVC metrics from Prometheus format"""
        parser = PrometheusTextParser()
        prometheus_text = """# HELP kubelet_volume_stats_used_bytes
kubelet_volume_stats_used_bytes{namespace="default",persistentvolumeclaim="my-pvc"} 5000000000
kubelet_volume_stats_capacity_bytes{namespace="default",persistentvolumeclaim="my-pvc"} 10000000000
"""
        blob = RawBlob(
            data=prometheus_text, source="kubelet_metrics", content_type="text/plain"
        )
        resources = parser.feed(blob)

        assert len(resources) == 1
        assert resources[0].kind == ResourceKind.PVC
        assert resources[0].name == "my-pvc"
        assert resources[0].namespace == "default"
        assert resources[0].properties["metrics"]["pvc_used_bytes"] == 5000000000
        assert resources[0].properties["metrics"]["pvc_capacity_bytes"] == 10000000000

    def test_feed_non_text_returns_empty(self):
        """Test parsing non-text returns empty"""
        parser = PrometheusTextParser()
        blob = RawBlob(data={}, source="test", content_type="application/json")
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_no_pvc_metrics_returns_empty(self):
        """Test parsing metrics without PVC data returns empty"""
        parser = PrometheusTextParser()
        prometheus_text = """# HELP some_other_metric
some_other_metric{label="value"} 100
"""
        blob = RawBlob(
            data=prometheus_text, source="kubelet_metrics", content_type="text/plain"
        )
        resources = parser.feed(blob)
        assert resources == []

    def test_feed_incomplete_pvc_metrics_skipped(self):
        """Test incomplete PVC metrics (missing used or capacity) are skipped"""
        parser = PrometheusTextParser()
        prometheus_text = """# HELP kubelet_volume_stats_used_bytes
kubelet_volume_stats_used_bytes{namespace="default",persistentvolumeclaim="my-pvc"} 5000000000
"""
        blob = RawBlob(
            data=prometheus_text, source="kubelet_metrics", content_type="text/plain"
        )
        resources = parser.feed(blob)
        assert resources == []


class TestParserRegistry:
    """Tests for ParserRegistry"""

    def test_registry_default_parsers(self):
        """Test registry has default parsers"""
        reg = ParserRegistry()
        assert "kubernetes" in reg._parsers
        assert "events" in reg._parsers
        assert "text" in reg._parsers
        assert "metrics" in reg._parsers
        assert "prom" in reg._parsers

    def test_registry_register_custom_parser(self):
        """Test registering custom parser"""
        reg = ParserRegistry()

        class CustomParser(Parser):
            def feed(self, blob):
                return []

        reg.register("custom", CustomParser())
        assert "custom" in reg._parsers

    def test_get_parser_for_events(self):
        """Test get_parser returns events parser for events source"""
        reg = ParserRegistry()
        blob = RawBlob(data={}, source="kubectl_events", content_type="application/json")
        parser = reg.get_parser(blob)
        assert isinstance(parser, EventParser)

    def test_get_parser_for_metrics(self):
        """Test get_parser returns metrics parser for metrics source"""
        reg = ParserRegistry()
        blob = RawBlob(data={}, source="metrics_server", content_type="text/plain")
        parser = reg.get_parser(blob)
        assert isinstance(parser, MetricsParser)

    def test_get_parser_for_kubelet_metrics(self):
        """Test get_parser returns prometheus parser for kubelet source"""
        reg = ParserRegistry()
        blob = RawBlob(data={}, source="kubelet_metrics", content_type="text/plain")
        parser = reg.get_parser(blob)
        assert isinstance(parser, PrometheusTextParser)

    def test_get_parser_for_logs(self):
        """Test get_parser returns log parser for kubectl logs output"""
        reg = ParserRegistry()
        blob = RawBlob(data={}, source="kubectl_logs", content_type="text/plain")
        parser = reg.get_parser(blob)
        assert isinstance(parser, LogParser)

    def test_get_parser_for_json(self):
        """Test get_parser returns kubernetes parser for JSON"""
        reg = ParserRegistry()
        blob = RawBlob(data={}, source="kubectl_get", content_type="application/json")
        parser = reg.get_parser(blob)
        assert isinstance(parser, KubernetesResourceParser)

    def test_parse_uses_correct_parser(self, sample_pod_json):
        """Test parse method uses appropriate parser"""
        reg = ParserRegistry()
        blob = RawBlob(
            data=sample_pod_json, source="kubectl_get", content_type="application/json"
        )
        resources = reg.parse(blob)
        assert len(resources) == 1
        assert resources[0].kind == ResourceKind.POD


class TestGlobalRegistry:
    """Tests for global parser registry instance"""

    def test_global_registry_exists(self):
        """Test global registry is available"""
        assert registry is not None
        assert isinstance(registry, ParserRegistry)
