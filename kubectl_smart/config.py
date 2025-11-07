"""
Configuration management for kubectl-smart

Supports configuration from:
1. Default values (code)
2. Config file (~/.kubectl-smart/config.yaml)
3. Environment variables (KUBECTL_SMART_*)
4. Command-line arguments (highest priority)

Configuration precedence (highest to lowest):
CLI args > ENV vars > Config file > Defaults
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class Config:
    """Configuration manager for kubectl-smart"""

    # Default configuration
    DEFAULTS = {
        # Output settings
        "output": {
            "colors_enabled": True,
            "max_display_issues": 10,
            "max_suggested_actions": 5,
            "default_format": "text",  # text or json
        },
        # Performance settings
        "performance": {
            "max_concurrent_collectors": 5,
            "collector_timeout_seconds": 10.0,
            "cache_ttl_seconds": 300,  # 5 minutes
            "max_retries": 3,
        },
        # Scoring settings
        "scoring": {
            "weights_file": "weights.toml",
            "min_critical_score": 90.0,
            "min_warning_score": 50.0,
        },
        # Forecasting settings
        "forecasting": {
            "forecast_horizon_hours": 48,
            "min_samples_for_forecast": 7,
            "cert_warning_days": 14,
        },
        # Rate limiting
        "rate_limiting": {
            "enabled": True,
            "max_calls_per_minute": 100,
        },
        # Circuit breaker
        "circuit_breaker": {
            "enabled": True,
            "failure_threshold": 5,
            "timeout_seconds": 60.0,
        },
        # Logging
        "logging": {
            "enabled": True,
            "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
            "file": "~/.kubectl-smart/logs/kubectl-smart.log",
            "max_size_mb": 10,
            "backup_count": 3,
        },
        # Health checks
        "health": {
            "check_kubectl_version": True,
            "check_cluster_connectivity": True,
            "warn_on_old_kubectl": True,
        },
    }

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration

        Args:
            config_file: Path to config file (default: ~/.kubectl-smart/config.yaml)
        """
        self.config_file = config_file or self._get_default_config_path()
        self.config = self._load_configuration()

    def _get_default_config_path(self) -> str:
        """Get default config file path"""
        home = Path.home()
        config_dir = home / ".kubectl-smart"
        return str(config_dir / "config.yaml")

    def _load_configuration(self) -> Dict[str, Any]:
        """Load configuration from all sources

        Returns:
            Merged configuration dictionary
        """
        # Start with defaults
        config = self._deep_copy(self.DEFAULTS)

        # Load from file if exists
        file_config = self._load_from_file()
        if file_config:
            config = self._deep_merge(config, file_config)

        # Override with environment variables
        env_config = self._load_from_env()
        config = self._deep_merge(config, env_config)

        return config

    def _load_from_file(self) -> Optional[Dict[str, Any]]:
        """Load configuration from YAML file

        Returns:
            Configuration dictionary or None if file doesn't exist
        """
        config_path = Path(self.config_file)

        if not config_path.exists():
            logger.debug("Config file not found", path=self.config_file)
            return None

        try:
            import yaml

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            logger.info("Loaded configuration from file", path=self.config_file)
            return config or {}

        except ImportError:
            logger.warning(
                "PyYAML not installed, config file support disabled. "
                "Install with: pip install pyyaml"
            )
            return None
        except Exception as e:
            logger.error(
                "Failed to load config file",
                path=self.config_file,
                error=str(e)
            )
            return None

    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables

        Environment variables use the format:
        KUBECTL_SMART_SECTION_KEY=value

        Example: KUBECTL_SMART_OUTPUT_COLORS_ENABLED=false

        Returns:
            Configuration dictionary from environment
        """
        config = {}

        for key, value in os.environ.items():
            if not key.startswith("KUBECTL_SMART_"):
                continue

            # Remove prefix and parse
            config_key = key[14:].lower()  # Remove KUBECTL_SMART_
            parts = config_key.split("_")

            if len(parts) < 2:
                continue

            section = parts[0]
            setting = "_".join(parts[1:])

            # Convert value to appropriate type
            parsed_value = self._parse_env_value(value)

            # Set in config
            if section not in config:
                config[section] = {}
            config[section][setting] = parsed_value

        return config

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type

        Args:
            value: String value from environment

        Returns:
            Parsed value (bool, int, float, or str)
        """
        # Boolean
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False

        # Number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # String
        return value

    def _deep_copy(self, d: Dict) -> Dict:
        """Deep copy a dictionary"""
        import copy
        return copy.deepcopy(d)

    def _deep_merge(self, base: Dict, overlay: Dict) -> Dict:
        """Deep merge two dictionaries (overlay takes precedence)

        Args:
            base: Base dictionary
            overlay: Dictionary to merge on top

        Returns:
            Merged dictionary
        """
        result = self._deep_copy(base)

        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation

        Args:
            key: Configuration key (e.g., "output.colors_enabled")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        """Set configuration value with dot notation

        Args:
            key: Configuration key (e.g., "output.colors_enabled")
            value: Value to set
        """
        keys = key.split(".")
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, path: Optional[str] = None) -> None:
        """Save configuration to file

        Args:
            path: Path to save to (default: self.config_file)
        """
        save_path = Path(path or self.config_file)

        # Create directory if it doesn't exist
        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            import yaml

            with open(save_path, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

            logger.info("Saved configuration to file", path=str(save_path))

        except ImportError:
            logger.error("PyYAML not installed, cannot save config file")
        except Exception as e:
            logger.error("Failed to save config file", path=str(save_path), error=str(e))

    def create_default_config(self) -> None:
        """Create default config file with comments"""
        config_path = Path(self.config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        content = """# kubectl-smart Configuration File
# This file allows you to customize kubectl-smart behavior
# See documentation: https://github.com/srijanshukla18/kubectl-smart

# Output settings
output:
  colors_enabled: true
  max_display_issues: 10
  max_suggested_actions: 5
  default_format: text  # text or json

# Performance settings
performance:
  max_concurrent_collectors: 5
  collector_timeout_seconds: 10.0
  cache_ttl_seconds: 300  # 5 minutes
  max_retries: 3

# Scoring settings
scoring:
  weights_file: weights.toml
  min_critical_score: 90.0
  min_warning_score: 50.0

# Forecasting settings
forecasting:
  forecast_horizon_hours: 48
  min_samples_for_forecast: 7
  cert_warning_days: 14

# Rate limiting (prevent API abuse)
rate_limiting:
  enabled: true
  max_calls_per_minute: 100

# Circuit breaker (prevent cascading failures)
circuit_breaker:
  enabled: true
  failure_threshold: 5
  timeout_seconds: 60.0

# Logging
logging:
  enabled: true
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  file: ~/.kubectl-smart/logs/kubectl-smart.log
  max_size_mb: 10
  backup_count: 3

# Health checks
health:
  check_kubectl_version: true
  check_cluster_connectivity: true
  warn_on_old_kubectl: true
"""

        with open(config_path, "w") as f:
            f.write(content)

        logger.info("Created default config file", path=str(config_path))


# Global config instance
_global_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance

    Returns:
        Global Config instance
    """
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config


def reload_config() -> Config:
    """Reload configuration from all sources

    Returns:
        Reloaded Config instance
    """
    global _global_config
    _global_config = Config()
    return _global_config
