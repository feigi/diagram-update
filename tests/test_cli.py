"""Tests for the CLI entry point."""

from pathlib import Path
from unittest.mock import patch

from diagram_update.cli import main


def test_nonexistent_directory(capsys) -> None:
    """CLI errors on nonexistent directory."""
    result = main(["/nonexistent/path/that/does/not/exist"])
    assert result == 1
    assert "not a directory" in capsys.readouterr().err


def test_config_error(tmp_path: Path, capsys) -> None:
    """CLI handles config errors gracefully."""
    config_file = tmp_path / ".diagram-update.yml"
    config_file.write_text("granularity: invalid_value")
    result = main([str(tmp_path)])
    assert result == 1
    assert "Config error" in capsys.readouterr().err


def test_missing_gh_binary(tmp_path: Path, capsys) -> None:
    """CLI handles missing gh binary gracefully."""
    # Create a minimal Python file so analysis produces something
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "app.py").write_text("import os\n")

    with patch("diagram_update.llm.shutil.which", return_value=None):
        result = main([str(tmp_path)])
    assert result == 1
    assert "GitHub CLI" in capsys.readouterr().err


def test_full_pipeline_success(tmp_path: Path, capsys) -> None:
    """CLI runs full pipeline generating all diagram types."""
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "app.py").write_text("import os\n")

    fake_components = "COMPONENTS:\n- id: api, label: API, type: service"
    fake_d2 = "api: API\ndb: Database\napi -> db: queries"

    with patch("diagram_update.llm._check_gh_available"):
        with patch(
            "diagram_update.llm._call_gh_copilot",
            side_effect=[
                fake_components, fake_d2,  # architecture
                fake_components, fake_d2,  # dependencies
                fake_components, fake_d2,  # sequence
            ],
        ):
            result = main([str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "architecture.d2" in output
    assert "dependencies.d2" in output
    assert "sequence.d2" in output

    diagrams_dir = tmp_path / "docs" / "diagrams"
    assert (diagrams_dir / "architecture.d2").exists()
    assert (diagrams_dir / "dependencies.d2").exists()
    assert (diagrams_dir / "sequence.d2").exists()

    content = (diagrams_dir / "architecture.d2").read_text()
    assert "api -> db" in content
    assert "layout-engine: elk" in content


def test_partial_failure_continues(tmp_path: Path, capsys) -> None:
    """CLI continues generating other diagrams if one fails."""
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "app.py").write_text("import os\n")

    fake_components = "COMPONENTS:\n- id: api"
    fake_d2 = "api: API"

    with patch("diagram_update.llm._check_gh_available"):
        with patch(
            "diagram_update.llm._call_gh_copilot",
            side_effect=[
                fake_components, fake_d2,  # architecture succeeds
                "",  # dependencies pass1 fails (empty)
                fake_components, fake_d2,  # sequence succeeds
            ],
        ):
            result = main([str(tmp_path)])

    assert result == 0  # partial success
    output = capsys.readouterr()
    assert "architecture.d2" in output.out
    assert "Error (dependencies)" in output.err


def test_all_diagrams_fail(tmp_path: Path, capsys) -> None:
    """CLI returns error code when all diagram types fail."""
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "app.py").write_text("import os\n")

    with patch("diagram_update.llm._check_gh_available"):
        with patch("diagram_update.llm._call_gh_copilot", return_value=""):
            result = main([str(tmp_path)])

    assert result == 1


def test_verbose_flag(tmp_path: Path) -> None:
    """CLI accepts -v flag without error."""
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "app.py").write_text("x = 1\n")

    fake_components = "COMPONENTS:\n- id: a"
    fake_d2 = "a: A"
    with patch("diagram_update.llm._check_gh_available"):
        with patch(
            "diagram_update.llm._call_gh_copilot",
            side_effect=[fake_components, fake_d2] * 3,
        ):
            result = main([str(tmp_path), "-v"])
    assert result == 0
