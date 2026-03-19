"""Configuration loading from .diagram-update.yml."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .models import ConfigError, DiagramConfig

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".diagram-update.yml"

VALID_GRANULARITIES = {"directory", "package", "module"}

_KNOWN_KEYS = {"include", "exclude", "granularity", "entry_points", "model", "token_budget"}


def load_config(project_root: Path) -> DiagramConfig:
    """Load .diagram-update.yml from project_root.

    Returns DiagramConfig with defaults applied.
    Raises ConfigError if file exists but is invalid.
    If no config file exists, returns default config.
    """
    config_path = project_root / CONFIG_FILENAME

    if not config_path.exists():
        return DiagramConfig()

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read {config_path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    if data is None:
        return DiagramConfig()

    if not isinstance(data, dict):
        raise ConfigError(
            f"Expected a YAML mapping in {config_path}, got {type(data).__name__}"
        )

    unknown = set(data.keys()) - _KNOWN_KEYS
    for key in sorted(unknown):
        logger.warning("Unknown config key %r in %s (ignored)", key, config_path)

    return _build_config(data, config_path)


def _build_config(data: dict, config_path: Path) -> DiagramConfig:
    """Validate fields and construct DiagramConfig from parsed YAML dict."""
    kwargs: dict = {}

    if "include" in data:
        kwargs["include"] = _expect_list_of_str(data["include"], "include", config_path)

    if "exclude" in data:
        kwargs["exclude"] = _expect_list_of_str(data["exclude"], "exclude", config_path)

    if "granularity" in data:
        val = data["granularity"]
        if not isinstance(val, str) or val not in VALID_GRANULARITIES:
            raise ConfigError(
                f"Invalid granularity {val!r} in {config_path}; "
                f"must be one of {sorted(VALID_GRANULARITIES)}"
            )
        kwargs["granularity"] = val

    if "entry_points" in data:
        kwargs["entry_points"] = _expect_list_of_str(
            data["entry_points"], "entry_points", config_path
        )

    if "model" in data:
        val = data["model"]
        if not isinstance(val, str):
            raise ConfigError(
                f"Invalid model {val!r} in {config_path}; must be a string"
            )
        kwargs["model"] = val

    if "token_budget" in data:
        val = data["token_budget"]
        if not isinstance(val, int) or val < 1000:
            raise ConfigError(
                f"Invalid token_budget {val!r} in {config_path}; "
                f"must be an integer >= 1000"
            )
        kwargs["token_budget"] = val

    return DiagramConfig(**kwargs)


def _expect_list_of_str(value: object, field_name: str, config_path: Path) -> list[str]:
    """Validate that value is a list of strings."""
    if not isinstance(value, list):
        raise ConfigError(
            f"Field {field_name!r} in {config_path} must be a list, "
            f"got {type(value).__name__}"
        )
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(
                f"Field {field_name!r}[{i}] in {config_path} must be a string, "
                f"got {type(item).__name__}"
            )
    return value
