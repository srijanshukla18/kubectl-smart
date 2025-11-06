"""
Input validation and sanitization for kubectl-smart

This module provides comprehensive input validation to ensure robust operation
and prevent command injection or other security issues.
"""

import re
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class ValidationError(Exception):
    """Raised when input validation fails"""
    pass


class InputValidator:
    """Validates all user inputs before processing"""

    # Kubernetes naming rules (RFC 1123 DNS label)
    # - lowercase alphanumeric + hyphens
    # - start with alphanumeric
    # - end with alphanumeric
    # - max 253 characters for names
    # - max 63 characters for labels

    RESOURCE_NAME_PATTERN = re.compile(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
    NAMESPACE_PATTERN = re.compile(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
    CONTEXT_PATTERN = re.compile(r'^[a-zA-Z0-9]([-a-zA-Z0-9._]*[a-zA-Z0-9])?$')

    MAX_RESOURCE_NAME_LENGTH = 253
    MAX_NAMESPACE_LENGTH = 63
    MAX_CONTEXT_LENGTH = 253

    @classmethod
    def validate_resource_name(cls, name: str) -> str:
        """Validate and sanitize a Kubernetes resource name

        Args:
            name: Resource name to validate

        Returns:
            Validated name

        Raises:
            ValidationError: If name is invalid
        """
        if not name:
            raise ValidationError("Resource name cannot be empty")

        if len(name) > cls.MAX_RESOURCE_NAME_LENGTH:
            raise ValidationError(
                f"Resource name too long: {len(name)} chars "
                f"(max {cls.MAX_RESOURCE_NAME_LENGTH})"
            )

        if not cls.RESOURCE_NAME_PATTERN.match(name):
            raise ValidationError(
                f"Invalid resource name '{name}': must match pattern "
                f"{cls.RESOURCE_NAME_PATTERN.pattern}"
            )

        return name

    @classmethod
    def validate_namespace(cls, namespace: Optional[str]) -> Optional[str]:
        """Validate and sanitize a Kubernetes namespace

        Args:
            namespace: Namespace to validate (can be None)

        Returns:
            Validated namespace or None

        Raises:
            ValidationError: If namespace is invalid
        """
        if namespace is None:
            return None

        if not namespace:
            raise ValidationError("Namespace cannot be empty string")

        if len(namespace) > cls.MAX_NAMESPACE_LENGTH:
            raise ValidationError(
                f"Namespace too long: {len(namespace)} chars "
                f"(max {cls.MAX_NAMESPACE_LENGTH})"
            )

        if not cls.NAMESPACE_PATTERN.match(namespace):
            raise ValidationError(
                f"Invalid namespace '{namespace}': must match pattern "
                f"{cls.NAMESPACE_PATTERN.pattern}"
            )

        return namespace

    @classmethod
    def validate_context(cls, context: Optional[str]) -> Optional[str]:
        """Validate and sanitize a kubectl context name

        Args:
            context: Context name to validate (can be None)

        Returns:
            Validated context or None

        Raises:
            ValidationError: If context is invalid
        """
        if context is None:
            return None

        if not context:
            raise ValidationError("Context cannot be empty string")

        if len(context) > cls.MAX_CONTEXT_LENGTH:
            raise ValidationError(
                f"Context name too long: {len(context)} chars "
                f"(max {cls.MAX_CONTEXT_LENGTH})"
            )

        if not cls.CONTEXT_PATTERN.match(context):
            raise ValidationError(
                f"Invalid context '{context}': must match pattern "
                f"{cls.CONTEXT_PATTERN.pattern}"
            )

        return context

    @classmethod
    def validate_horizon(cls, horizon: int) -> int:
        """Validate forecast horizon parameter

        Args:
            horizon: Horizon in hours

        Returns:
            Validated horizon

        Raises:
            ValidationError: If horizon is invalid
        """
        if not isinstance(horizon, int):
            raise ValidationError(f"Horizon must be an integer, got {type(horizon)}")

        if horizon < 1:
            raise ValidationError(f"Horizon must be >= 1 hour, got {horizon}")

        if horizon > 720:  # 30 days
            raise ValidationError(
                f"Horizon too large: {horizon} hours (max 720 hours / 30 days)"
            )

        return horizon

    @classmethod
    def validate_depth(cls, depth: int) -> int:
        """Validate graph depth parameter

        Args:
            depth: Graph traversal depth

        Returns:
            Validated depth

        Raises:
            ValidationError: If depth is invalid
        """
        if not isinstance(depth, int):
            raise ValidationError(f"Depth must be an integer, got {type(depth)}")

        if depth < 1:
            raise ValidationError(f"Depth must be >= 1, got {depth}")

        if depth > 10:
            raise ValidationError(
                f"Depth too large: {depth} (max 10, consider lower for performance)"
            )

        return depth

    @classmethod
    def sanitize_for_shell(cls, value: str) -> str:
        """Sanitize a value for safe shell execution

        This is a defense-in-depth measure. We should never pass
        user input directly to shell, but this adds an extra layer.

        Args:
            value: Value to sanitize

        Returns:
            Sanitized value
        """
        # Remove characters that could be dangerous in shell context
        dangerous_chars = [';', '&', '|', '$', '`', '\\', '\n', '\r']

        sanitized = value
        for char in dangerous_chars:
            if char in sanitized:
                logger.warning(
                    "Removed dangerous character from input",
                    char=char,
                    original=value
                )
                sanitized = sanitized.replace(char, '')

        return sanitized

    @classmethod
    def validate_output_format(cls, format: str) -> str:
        """Validate output format parameter

        Args:
            format: Output format (json, yaml, text)

        Returns:
            Validated format

        Raises:
            ValidationError: If format is invalid
        """
        valid_formats = ['json', 'yaml', 'text', 'table']

        if format not in valid_formats:
            raise ValidationError(
                f"Invalid output format '{format}'. "
                f"Valid options: {', '.join(valid_formats)}"
            )

        return format


def validate_inputs(
    name: str,
    namespace: Optional[str] = None,
    context: Optional[str] = None,
    horizon: Optional[int] = None,
    depth: Optional[int] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    """Convenience function to validate common inputs

    Args:
        name: Resource name
        namespace: Optional namespace
        context: Optional context
        horizon: Optional forecast horizon
        depth: Optional graph depth

    Returns:
        Tuple of (validated_name, validated_namespace, validated_context)

    Raises:
        ValidationError: If any input is invalid
    """
    try:
        validated_name = InputValidator.validate_resource_name(name)
        validated_namespace = InputValidator.validate_namespace(namespace)
        validated_context = InputValidator.validate_context(context)

        if horizon is not None:
            InputValidator.validate_horizon(horizon)

        if depth is not None:
            InputValidator.validate_depth(depth)

        return validated_name, validated_namespace, validated_context

    except ValidationError as e:
        logger.error("Input validation failed", error=str(e))
        raise
