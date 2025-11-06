"""
Comprehensive logging configuration for kubectl-smart

Features:
- Structured logging with structlog
- File rotation with size limits
- Multiple log levels
- Context-aware logging
- Performance metrics
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import structlog


def configure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_size_mb: int = 10,
    backup_count: int = 3,
    enable_colors: bool = True,
) -> None:
    """Configure comprehensive logging for kubectl-smart

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (None = stdout only)
        max_size_mb: Max log file size in MB before rotation
        backup_count: Number of backup files to keep
        enable_colors: Enable colored console output
    """
    # Map string level to logging constant
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    log_level = level_map.get(level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # File handler (if log_file specified)
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_size_mb * 1024 * 1024,  # Convert MB to bytes
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add colored output for console if enabled
    if enable_colors and sys.stderr.isatty():
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class PerformanceLogger:
    """Context manager for logging performance metrics"""

    def __init__(self, operation: str, logger: Optional[structlog.BoundLogger] = None):
        """Initialize performance logger

        Args:
            operation: Name of operation being measured
            logger: Logger instance (creates one if None)
        """
        self.operation = operation
        self.logger = logger or get_logger("performance")
        self.start_time = None

    def __enter__(self):
        """Start timing"""
        import time
        self.start_time = time.time()
        self.logger.debug("Operation started", operation=self.operation)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and log"""
        import time
        duration = time.time() - self.start_time

        if exc_type is None:
            self.logger.info(
                "Operation completed",
                operation=self.operation,
                duration_seconds=round(duration, 3),
            )
        else:
            self.logger.error(
                "Operation failed",
                operation=self.operation,
                duration_seconds=round(duration, 3),
                error=str(exc_val),
            )


def log_command_execution(
    command: str,
    args: dict,
    logger: Optional[structlog.BoundLogger] = None,
) -> None:
    """Log command execution for audit trail

    Args:
        command: Command name (diag, graph, top)
        args: Command arguments
        logger: Logger instance
    """
    log = logger or get_logger("audit")

    # Sanitize args (remove sensitive data if any)
    safe_args = {k: v for k, v in args.items() if k not in ["token", "password"]}

    log.info(
        "Command executed",
        command=command,
        args=safe_args,
        user=os.getenv("USER", "unknown"),
        pwd=os.getcwd(),
    )


def log_error_with_context(
    error: Exception,
    context: dict,
    logger: Optional[structlog.BoundLogger] = None,
) -> None:
    """Log error with rich context for debugging

    Args:
        error: Exception that occurred
        context: Additional context (resource, namespace, etc.)
        logger: Logger instance
    """
    log = logger or get_logger("error")

    log.error(
        "Error occurred",
        error_type=type(error).__name__,
        error_message=str(error),
        **context,
        exc_info=True,
    )


def setup_logging_from_config(config: dict) -> None:
    """Setup logging from configuration dict

    Args:
        config: Configuration dictionary
    """
    logging_config = config.get("logging", {})

    if not logging_config.get("enabled", True):
        # Disable logging
        logging.disable(logging.CRITICAL)
        return

    configure_logging(
        level=logging_config.get("level", "INFO"),
        log_file=logging_config.get("file"),
        max_size_mb=logging_config.get("max_size_mb", 10),
        backup_count=logging_config.get("backup_count", 3),
        enable_colors=config.get("output", {}).get("colors_enabled", True),
    )


# Initialize logging with defaults
# This will be reconfigured when config is loaded
configure_logging()
