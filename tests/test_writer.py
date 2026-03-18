"""Tests for the D2 file writer."""

from pathlib import Path

from diagram_update.writer import D2_HEADER, write_diagram


def test_creates_output_directory(tmp_path: Path) -> None:
    """Writer creates docs/diagrams/ if it doesn't exist."""
    output = write_diagram("a -> b", "architecture", tmp_path)
    assert output.parent.exists()
    assert output.parent == tmp_path / "docs" / "diagrams"


def test_architecture_filename(tmp_path: Path) -> None:
    """Architecture diagram produces correct filename."""
    output = write_diagram("a -> b", "architecture", tmp_path)
    assert output.name == "architecture.d2"


def test_dependencies_filename(tmp_path: Path) -> None:
    """Dependencies diagram produces correct filename."""
    output = write_diagram("a -> b", "dependencies", tmp_path)
    assert output.name == "dependencies.d2"


def test_flow_filename(tmp_path: Path) -> None:
    """Sequence diagrams use flow-{name}.d2 naming."""
    output = write_diagram("a -> b", "sequence", tmp_path, flow_name="login")
    assert output.name == "flow-login.d2"


def test_contains_d2_config_header(tmp_path: Path) -> None:
    """Written files contain the D2 config header."""
    write_diagram("a -> b", "architecture", tmp_path)
    content = (tmp_path / "docs" / "diagrams" / "architecture.d2").read_text()
    assert "layout-engine: elk" in content
    assert "direction: right" in content
    assert "vars:" in content


def test_content_after_header(tmp_path: Path) -> None:
    """D2 content appears after the header."""
    d2_code = "api -> db: reads from"
    write_diagram(d2_code, "architecture", tmp_path)
    content = (tmp_path / "docs" / "diagrams" / "architecture.d2").read_text()
    assert content.startswith(D2_HEADER)
    assert d2_code in content


def test_overwrites_existing_file(tmp_path: Path) -> None:
    """Writing to an existing file overwrites it."""
    write_diagram("old -> content", "architecture", tmp_path)
    write_diagram("new -> content", "architecture", tmp_path)
    content = (tmp_path / "docs" / "diagrams" / "architecture.d2").read_text()
    assert "new -> content" in content
    assert "old -> content" not in content


def test_unknown_diagram_type_uses_type_as_filename(tmp_path: Path) -> None:
    """Unknown diagram types use the type string as the filename."""
    output = write_diagram("a -> b", "custom", tmp_path)
    assert output.name == "custom.d2"
