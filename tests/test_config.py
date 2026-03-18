"""Tests for config loader."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from diagram_update.config import load_config
from diagram_update.models import ConfigError, DiagramConfig


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    return tmp_path


def _write_config(project_dir: Path, content: str) -> Path:
    cfg = project_dir / ".diagram-update.yml"
    cfg.write_text(content, encoding="utf-8")
    return cfg


class TestLoadConfigDefaults:
    def test_missing_file_returns_defaults(self, project_dir: Path) -> None:
        cfg = load_config(project_dir)
        assert cfg == DiagramConfig()
        assert cfg.granularity == "package"
        assert cfg.include == ["**/*"]
        assert cfg.model == "claude-sonnet-4.6"

    def test_empty_file_returns_defaults(self, project_dir: Path) -> None:
        _write_config(project_dir, "")
        cfg = load_config(project_dir)
        assert cfg == DiagramConfig()

    def test_empty_mapping_returns_defaults(self, project_dir: Path) -> None:
        _write_config(project_dir, "{}")
        cfg = load_config(project_dir)
        assert cfg == DiagramConfig()


class TestLoadConfigAllFields:
    def test_all_fields_specified(self, project_dir: Path) -> None:
        _write_config(
            project_dir,
            """\
include:
  - "src/**/*"
exclude:
  - "src/generated/**"
granularity: module
entry_points:
  - "src/main.py:main"
model: claude-sonnet-4-6
""",
        )
        cfg = load_config(project_dir)
        assert cfg.include == ["src/**/*"]
        assert cfg.exclude == ["src/generated/**"]
        assert cfg.granularity == "module"
        assert cfg.entry_points == ["src/main.py:main"]
        assert cfg.model == "claude-sonnet-4-6"


class TestLoadConfigPartial:
    def test_only_granularity(self, project_dir: Path) -> None:
        _write_config(project_dir, "granularity: directory\n")
        cfg = load_config(project_dir)
        assert cfg.granularity == "directory"
        assert cfg.include == ["**/*"]  # default preserved
        assert cfg.entry_points == []

    def test_only_include(self, project_dir: Path) -> None:
        _write_config(project_dir, 'include:\n  - "lib/**"\n')
        cfg = load_config(project_dir)
        assert cfg.include == ["lib/**"]
        assert cfg.granularity == "package"  # default preserved


class TestLoadConfigValidation:
    def test_invalid_yaml_raises_config_error(self, project_dir: Path) -> None:
        _write_config(project_dir, "include: [unterminated")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(project_dir)

    def test_non_mapping_raises_config_error(self, project_dir: Path) -> None:
        _write_config(project_dir, "- item1\n- item2\n")
        with pytest.raises(ConfigError, match="Expected a YAML mapping"):
            load_config(project_dir)

    def test_invalid_granularity_raises_config_error(self, project_dir: Path) -> None:
        _write_config(project_dir, "granularity: foobar\n")
        with pytest.raises(ConfigError, match="Invalid granularity"):
            load_config(project_dir)

    def test_include_not_list_raises_config_error(self, project_dir: Path) -> None:
        _write_config(project_dir, "include: not-a-list\n")
        with pytest.raises(ConfigError, match="must be a list"):
            load_config(project_dir)

    def test_include_non_string_item_raises_config_error(
        self, project_dir: Path
    ) -> None:
        _write_config(project_dir, "include:\n  - 42\n")
        with pytest.raises(ConfigError, match="must be a string"):
            load_config(project_dir)

    def test_model_non_string_raises_config_error(self, project_dir: Path) -> None:
        _write_config(project_dir, "model: 123\n")
        with pytest.raises(ConfigError, match="must be a string"):
            load_config(project_dir)


class TestLoadConfigUnknownKeys:
    def test_unknown_keys_warn_but_succeed(
        self, project_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_config(
            project_dir,
            "granularity: package\nfoo: bar\nbaz: 1\n",
        )
        with caplog.at_level(logging.WARNING):
            cfg = load_config(project_dir)
        assert cfg.granularity == "package"
        assert "Unknown config key 'baz'" in caplog.text
        assert "Unknown config key 'foo'" in caplog.text


class TestGranularityValues:
    @pytest.mark.parametrize("value", ["directory", "package", "module"])
    def test_valid_granularities(self, project_dir: Path, value: str) -> None:
        _write_config(project_dir, f"granularity: {value}\n")
        cfg = load_config(project_dir)
        assert cfg.granularity == value
