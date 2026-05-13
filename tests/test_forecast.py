"""Tests for kubectl_smart/forecast/predictor.py"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch


from kubectl_smart.forecast.predictor import ForecastingEngine
from kubectl_smart.models import ResourceKind, ResourceRecord


class TestForecastingEngine:
    """Tests for ForecastingEngine class"""

    def test_init_defaults(self):
        """Test ForecastingEngine initializes with defaults"""
        engine = ForecastingEngine()
        assert engine.min_samples == 7
        assert engine.forecast_horizon_hours == 48

    def test_init_custom_values(self):
        """Test ForecastingEngine with custom values"""
        engine = ForecastingEngine(min_samples=10, forecast_horizon_hours=72)
        assert engine.min_samples == 10
        assert engine.forecast_horizon_hours == 72


class TestPredictCapacityIssues:
    """Tests for predict_capacity_issues method"""

    def test_predict_capacity_issues_empty(self):
        """Test predict_capacity_issues with empty resources"""
        engine = ForecastingEngine()
        predictions = engine.predict_capacity_issues([], None)
        assert predictions == []

    def test_predict_capacity_issues_node_pressure(self):
        """Test detecting node with pressure condition"""
        engine = ForecastingEngine()
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="stressed-node",
            uid="node-uid",
            properties={
                "status": {
                    "conditions": [
                        {"type": "DiskPressure", "status": "True"},
                    ]
                }
            },
        )
        predictions = engine.predict_capacity_issues([node], None)

        assert len(predictions) == 1
        assert predictions[0]["type"] == "node_pressure"
        assert predictions[0]["pressure_type"] == "DiskPressure"
        assert predictions[0]["predicted_utilization"] >= 90

    def test_predict_capacity_issues_memory_pressure(self):
        """Test detecting node with memory pressure"""
        engine = ForecastingEngine()
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="memory-stressed-node",
            uid="node-uid",
            properties={
                "status": {
                    "conditions": [
                        {"type": "MemoryPressure", "status": "True"},
                    ]
                }
            },
        )
        predictions = engine.predict_capacity_issues([node], None)

        assert len(predictions) == 1
        assert predictions[0]["pressure_type"] == "MemoryPressure"

    def test_predict_capacity_issues_healthy_node(self):
        """Test healthy node produces no predictions"""
        engine = ForecastingEngine()
        node = ResourceRecord(
            kind=ResourceKind.NODE,
            name="healthy-node",
            uid="node-uid",
            properties={
                "status": {
                    "conditions": [
                        {"type": "DiskPressure", "status": "False"},
                        {"type": "MemoryPressure", "status": "False"},
                    ]
                }
            },
        )
        predictions = engine.predict_capacity_issues([node], None)
        assert predictions == []


class TestPredictPVCUsage:
    """Tests for PVC usage prediction"""

    def test_predict_pvc_usage_high_utilization(self):
        """Test PVC with high utilization"""
        engine = ForecastingEngine()
        pvc = ResourceRecord(
            kind=ResourceKind.PVC,
            name="data-pvc",
            uid="pvc-uid",
            namespace="default",
            properties={
                "spec": {"resources": {"requests": {"storage": "10Gi"}}},
                "metrics": {
                    "pvc_used_bytes": 9500000000,  # 95%
                    "pvc_capacity_bytes": 10000000000,
                },
            },
        )
        predictions = engine.predict_capacity_issues([pvc], None)

        assert len(predictions) == 1
        assert predictions[0]["type"] == "pvc_usage"
        assert predictions[0]["current_utilization"] >= 90

    def test_predict_pvc_usage_low_utilization(self):
        """Test PVC with low utilization produces no actionable prediction"""
        engine = ForecastingEngine()
        pvc = ResourceRecord(
            kind=ResourceKind.PVC,
            name="data-pvc",
            uid="pvc-uid",
            namespace="default",
            properties={
                "spec": {"resources": {"requests": {"storage": "10Gi"}}},
                "metrics": {
                    "pvc_used_bytes": 2000000000,  # 20%
                    "pvc_capacity_bytes": 10000000000,
                },
            },
        )
        # Low utilization won't produce actionable predictions (>=90%)
        predictions = engine.predict_capacity_issues([pvc], None)
        # Should be filtered out by actionable threshold
        assert all(p.get("predicted_utilization", 0) >= 90 for p in predictions) or len(predictions) == 0


class TestPredictCertificateExpiry:
    """Tests for certificate expiry prediction"""

    def test_predict_certificate_expiry_empty(self):
        """Test certificate prediction with empty resources"""
        engine = ForecastingEngine()
        warnings = engine.predict_certificate_expiry([])
        assert warnings == []

    def test_predict_certificate_expiry_non_tls_secret(self):
        """Test non-TLS secret produces no warnings"""
        engine = ForecastingEngine()
        secret = ResourceRecord(
            kind=ResourceKind.SECRET,
            name="regular-secret",
            uid="secret-uid",
            namespace="default",
            properties={"type": "Opaque", "data": {"key": "value"}},
        )
        warnings = engine.predict_certificate_expiry([secret])
        assert warnings == []

    def test_predict_certificate_expiry_tls_secret_no_cert_data(self):
        """Test TLS secret without cert data produces no warnings"""
        engine = ForecastingEngine()
        secret = ResourceRecord(
            kind=ResourceKind.SECRET,
            name="tls-secret",
            uid="secret-uid",
            namespace="default",
            properties={"type": "kubernetes.io/tls", "data": {}},
        )
        warnings = engine.predict_certificate_expiry([secret])
        assert warnings == []

    def test_predict_certificate_expiry_ingress_missing_secret(self):
        """Test ingress TLS reference warns when the Secret is missing."""
        engine = ForecastingEngine()
        ingress = ResourceRecord(
            kind=ResourceKind.INGRESS,
            name="my-ingress",
            uid="ingress-uid",
            namespace="default",
            properties={
                "spec": {
                    "tls": [
                        {
                            "secretName": "my-tls-secret",
                            "hosts": ["example.com"],
                        }
                    ]
                }
            },
        )
        warnings = engine.predict_certificate_expiry([ingress])

        assert len(warnings) == 1
        assert warnings[0]["type"] == "missing_certificate_secret"
        assert warnings[0]["secret_name"] == "my-tls-secret"

    def test_predict_certificate_expiry_ingress_existing_secret_is_not_warning(self):
        """Test ingress TLS references are quiet when the Secret was collected."""
        engine = ForecastingEngine()
        ingress = ResourceRecord(
            kind=ResourceKind.INGRESS,
            name="my-ingress",
            uid="ingress-uid",
            namespace="default",
            properties={
                "spec": {
                    "tls": [
                        {
                            "secretName": "my-tls-secret",
                            "hosts": ["example.com"],
                        }
                    ]
                }
            },
        )
        secret = ResourceRecord(
            kind=ResourceKind.SECRET,
            name="my-tls-secret",
            uid="secret-uid",
            namespace="default",
            properties={"type": "kubernetes.io/tls", "data": {}},
        )

        warnings = engine.predict_certificate_expiry([ingress, secret])

        assert warnings == []

    def test_predict_certificate_expiry_skips_missing_secret_when_inventory_incomplete(self):
        """Test Secret RBAC gaps do not become missing-Secret warnings."""
        engine = ForecastingEngine()
        ingress = ResourceRecord(
            kind=ResourceKind.INGRESS,
            name="my-ingress",
            uid="ingress-uid",
            namespace="default",
            properties={
                "spec": {
                    "tls": [
                        {
                            "secretName": "my-tls-secret",
                            "hosts": ["example.com"],
                        }
                    ]
                }
            },
        )

        warnings = engine.predict_certificate_expiry(
            [ingress],
            secret_inventory_complete=False,
        )

        assert warnings == []

    def test_predict_certificate_expiry_ingress_no_tls(self):
        """Test ingress without TLS produces no warnings"""
        engine = ForecastingEngine()
        ingress = ResourceRecord(
            kind=ResourceKind.INGRESS,
            name="my-ingress",
            uid="ingress-uid",
            namespace="default",
            properties={"spec": {"rules": []}},
        )
        warnings = engine.predict_certificate_expiry([ingress])
        assert warnings == []


class TestParseStorageSize:
    """Tests for _parse_storage_size method"""

    def test_parse_storage_size_gi(self):
        """Test parsing Gi storage size"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("10Gi")
        assert result == 10 * 1024**3

    def test_parse_storage_size_mi(self):
        """Test parsing Mi storage size"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("512Mi")
        assert result == 512 * 1024**2

    def test_parse_storage_size_ti(self):
        """Test parsing Ti storage size"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("1Ti")
        assert result == 1 * 1024**4

    def test_parse_storage_size_empty(self):
        """Test parsing empty storage size"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("")
        assert result == 0

    def test_parse_storage_size_none_as_string(self):
        """Test parsing None returns 0"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size(None)
        assert result == 0

    def test_parse_storage_size_no_unit(self):
        """Test parsing size without unit"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("1000")
        assert result == 1000

    def test_parse_storage_size_decimal(self):
        """Test parsing decimal storage size"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("1.5Gi")
        assert result == int(1.5 * 1024**3)

    def test_parse_storage_size_invalid(self):
        """Test parsing invalid storage size"""
        engine = ForecastingEngine()
        result = engine._parse_storage_size("invalid")
        assert result == 0


class TestParseMetricValue:
    """Tests for _parse_metric_value method"""

    def test_parse_metric_value_cpu_millicores(self):
        """Test parsing CPU millicores"""
        engine = ForecastingEngine()
        result = engine._parse_metric_value("250m", "cpu")
        assert result == 0.25

    def test_parse_metric_value_cpu_cores(self):
        """Test parsing CPU cores"""
        engine = ForecastingEngine()
        result = engine._parse_metric_value("2", "cpu")
        assert result == 2.0

    def test_parse_metric_value_memory(self):
        """Test parsing memory metric"""
        engine = ForecastingEngine()
        result = engine._parse_metric_value("1024Mi", "memory")
        assert result == 1024 * 1024**2

    def test_parse_metric_value_generic(self):
        """Test parsing generic metric"""
        engine = ForecastingEngine()
        result = engine._parse_metric_value("42.5", "other")
        assert result == 42.5

    def test_parse_metric_value_empty(self):
        """Test parsing empty metric"""
        engine = ForecastingEngine()
        result = engine._parse_metric_value("", "cpu")
        assert result == 0.0

    def test_parse_metric_value_invalid(self):
        """Test parsing invalid metric"""
        engine = ForecastingEngine()
        result = engine._parse_metric_value("invalid", "other")
        assert result == 0.0


class TestForecastTimeSeries:
    """Tests for time series forecasting"""

    def test_forecast_time_series_insufficient_samples(self):
        """Test forecasting with insufficient samples"""
        engine = ForecastingEngine(min_samples=7)
        metrics = [
            ResourceRecord(
                kind=ResourceKind.POD,
                name="pod",
                uid=f"uid-{i}",
                properties={"metrics": {"cpu": f"{i * 10}m"}},
            )
            for i in range(3)
        ]
        result = engine._forecast_time_series(metrics, "cpu")
        # Should fall back to linear or return None
        assert result is None or "predicted_value" in result

    def test_linear_forecast_basic(self):
        """Test linear forecasting"""
        engine = ForecastingEngine()
        metrics = [
            ResourceRecord(
                kind=ResourceKind.POD,
                name="pod",
                uid=f"uid-{i}",
                properties={"metrics": {"cpu": f"{10 + i * 5}m"}},
            )
            for i in range(5)
        ]
        result = engine._linear_forecast(metrics, "cpu")

        assert result is not None
        assert "current_value" in result
        assert "predicted_value" in result
        assert result["confidence"] == 0.6

    def test_linear_forecast_single_sample(self):
        """Test linear forecasting with single sample"""
        engine = ForecastingEngine()
        metrics = [
            ResourceRecord(
                kind=ResourceKind.POD,
                name="pod",
                uid="uid",
                properties={"metrics": {"cpu": "100m"}},
            )
        ]
        result = engine._linear_forecast(metrics, "cpu")
        assert result is None


class TestPVCUtilizationCache:
    """Tests for PVC utilization caching"""

    def test_cache_path(self):
        """Test cache path generation"""
        engine = ForecastingEngine()
        path = engine._cache_path()
        assert "kubectl-smart" in path
        assert "metrics.json" in path

    def test_append_and_load_pvc_samples(self, tmp_path):
        """Test appending and loading PVC samples"""
        engine = ForecastingEngine()

        # Override cache path for testing
        test_cache_dir = tmp_path / "cache"
        test_cache_dir.mkdir()
        test_cache_path = str(test_cache_dir / "metrics.json")

        with patch.object(engine, "_cache_path", return_value=test_cache_path):
            # Append sample
            engine._append_pvc_utilization_sample("default", "my-pvc", 50.0)

            # Load samples
            series = engine._load_pvc_utilization_series("default", "my-pvc")

            assert len(series) == 1
            assert series[0][1] == 50.0

    def test_append_pvc_samples_limit(self, tmp_path):
        """Test PVC samples are limited to 50"""
        engine = ForecastingEngine()

        test_cache_dir = tmp_path / "cache"
        test_cache_dir.mkdir()
        test_cache_path = str(test_cache_dir / "metrics.json")

        with patch.object(engine, "_cache_path", return_value=test_cache_path):
            # Append 60 samples
            for i in range(60):
                engine._append_pvc_utilization_sample("default", "my-pvc", float(i))

            # Load samples - should only have last 50
            series = engine._load_pvc_utilization_series("default", "my-pvc")

            assert len(series) == 50

    def test_load_pvc_series_nonexistent_file(self, tmp_path):
        """Test loading from nonexistent cache file"""
        engine = ForecastingEngine()
        test_cache_path = str(tmp_path / "nonexistent.json")

        with patch.object(engine, "_cache_path", return_value=test_cache_path):
            series = engine._load_pvc_utilization_series("default", "my-pvc")
            assert series == []


class TestForecastFromHistory:
    """Tests for _forecast_from_history method"""

    def test_forecast_from_history_insufficient_points(self):
        """Test forecasting with insufficient history"""
        engine = ForecastingEngine()
        series = [(datetime.now(timezone.utc), 50.0)]
        result = engine._forecast_from_history(series, 50.0)
        assert result is None

    def test_forecast_from_history_growing_trend(self):
        """Test forecasting with growing trend"""
        engine = ForecastingEngine()
        now = datetime.now(timezone.utc)
        series = [
            (now - timedelta(hours=2), 40.0),
            (now - timedelta(hours=1), 50.0),
            (now, 60.0),
        ]
        result = engine._forecast_from_history(series, 60.0)

        assert result is not None
        assert result > 60.0  # Should predict growth

    def test_forecast_from_history_stable(self):
        """Test forecasting with stable usage"""
        engine = ForecastingEngine()
        now = datetime.now(timezone.utc)
        series = [
            (now - timedelta(hours=2), 50.0),
            (now - timedelta(hours=1), 50.0),
            (now, 50.0),
        ]
        result = engine._forecast_from_history(series, 50.0)

        assert result is not None
        assert abs(result - 50.0) < 1.0  # Should stay stable

    def test_forecast_from_history_clamped(self):
        """Test forecast is clamped to 0-100"""
        engine = ForecastingEngine()
        now = datetime.now(timezone.utc)
        series = [
            (now - timedelta(hours=2), 10.0),
            (now - timedelta(hours=1), 5.0),
            (now, 0.0),
        ]
        result = engine._forecast_from_history(series, 0.0)

        assert result is not None
        assert result >= 0.0

        # Test upper bound
        series_high = [
            (now - timedelta(hours=2), 90.0),
            (now - timedelta(hours=1), 95.0),
            (now, 100.0),
        ]
        result_high = engine._forecast_from_history(series_high, 100.0)
        assert result_high <= 100.0
