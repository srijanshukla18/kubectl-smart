"""
Unit tests for input validation

Tests the InputValidator class and all validation functions.
"""

import pytest

from kubectl_smart.validation import InputValidator, ValidationError


class TestResourceNameValidation:
    """Tests for resource name validation"""

    def test_valid_resource_names(self):
        """Test that valid resource names pass validation"""
        valid_names = [
            "my-pod",
            "app-123",
            "nginx",
            "my-app-v2",
            "a",  # Single char
            "123-app",  # Starting with number is ok
        ]
        for name in valid_names:
            # Should not raise
            result = InputValidator.validate_resource_name(name)
            assert result == name

    def test_invalid_resource_names(self):
        """Test that invalid resource names raise ValidationError"""
        invalid_names = [
            "",  # Empty
            "my_pod",  # Underscore not allowed
            "MY-POD",  # Uppercase not allowed
            "my-pod-",  # Cannot end with hyphen
            "-my-pod",  # Cannot start with hyphen
            "my pod",  # Spaces not allowed
            "my@pod",  # Special chars not allowed
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                InputValidator.validate_resource_name(name)

    def test_resource_name_too_long(self):
        """Test that names exceeding max length are rejected"""
        too_long = "a" * 254  # Max is 253
        with pytest.raises(ValidationError, match="too long"):
            InputValidator.validate_resource_name(too_long)


class TestNamespaceValidation:
    """Tests for namespace validation"""

    def test_valid_namespaces(self):
        """Test that valid namespaces pass validation"""
        valid_namespaces = [
            "default",
            "kube-system",
            "production",
            "my-app-v2",
        ]
        for ns in valid_namespaces:
            result = InputValidator.validate_namespace(ns)
            assert result == ns

    def test_none_namespace_is_valid(self):
        """Test that None namespace is allowed"""
        result = InputValidator.validate_namespace(None)
        assert result is None

    def test_invalid_namespaces(self):
        """Test that invalid namespaces raise ValidationError"""
        invalid_namespaces = [
            "MY-NS",  # Uppercase
            "my_ns",  # Underscore
            "my ns",  # Space
        ]
        for ns in invalid_namespaces:
            with pytest.raises(ValidationError):
                InputValidator.validate_namespace(ns)


class TestContextValidation:
    """Tests for context validation"""

    def test_valid_contexts(self):
        """Test that valid context names pass validation"""
        valid_contexts = [
            "minikube",
            "prod-cluster",
            "my-context.internal",
            "ctx_with_underscore",  # Context allows more chars
        ]
        for ctx in valid_contexts:
            result = InputValidator.validate_context(ctx)
            assert result == ctx

    def test_none_context_is_valid(self):
        """Test that None context is allowed"""
        result = InputValidator.validate_context(None)
        assert result is None


class TestHorizonValidation:
    """Tests for forecast horizon validation"""

    def test_valid_horizons(self):
        """Test that valid horizons pass validation"""
        valid_horizons = [1, 24, 48, 168, 720]
        for horizon in valid_horizons:
            result = InputValidator.validate_horizon(horizon)
            assert result == horizon

    def test_horizon_too_small(self):
        """Test that horizon < 1 is rejected"""
        with pytest.raises(ValidationError, match="must be >= 1"):
            InputValidator.validate_horizon(0)

    def test_horizon_too_large(self):
        """Test that horizon > 720 is rejected"""
        with pytest.raises(ValidationError, match="too large"):
            InputValidator.validate_horizon(721)

    def test_horizon_must_be_int(self):
        """Test that non-integer horizon is rejected"""
        with pytest.raises(ValidationError, match="must be an integer"):
            InputValidator.validate_horizon(24.5)


class TestDepthValidation:
    """Tests for graph depth validation"""

    def test_valid_depths(self):
        """Test that valid depths pass validation"""
        valid_depths = [1, 3, 5, 10]
        for depth in valid_depths:
            result = InputValidator.validate_depth(depth)
            assert result == depth

    def test_depth_too_small(self):
        """Test that depth < 1 is rejected"""
        with pytest.raises(ValidationError, match="must be >= 1"):
            InputValidator.validate_depth(0)

    def test_depth_too_large(self):
        """Test that depth > 10 is rejected"""
        with pytest.raises(ValidationError, match="too large"):
            InputValidator.validate_depth(11)


class TestShellSanitization:
    """Tests for shell command sanitization"""

    def test_sanitize_removes_dangerous_chars(self):
        """Test that dangerous shell characters are removed"""
        dangerous = "pod-name; rm -rf /"
        sanitized = InputValidator.sanitize_for_shell(dangerous)
        assert ";" not in sanitized
        assert sanitized == "pod-name rm -rf /"

    def test_sanitize_removes_all_dangerous_chars(self):
        """Test all dangerous characters are removed"""
        dangerous = "test&|$`\\\n\r"
        sanitized = InputValidator.sanitize_for_shell(dangerous)
        for char in ['&', '|', '$', '`', '\\', '\n', '\r']:
            assert char not in sanitized
