"""D2 file writer: write generated diagrams to docs/diagrams/."""

from __future__ import annotations

from pathlib import Path

# D2 config header applied to all generated files
D2_HEADER = """\
vars: {
  d2-config: {
    layout-engine: elk
  }
}

direction: right
"""

# Map diagram type to output filename
_FILENAME_MAP = {
    "architecture": "architecture.d2",
    "dependencies": "dependencies.d2",
}


def write_diagram(
    d2_content: str,
    diagram_type: str,
    project_root: Path,
    flow_name: str | None = None,
) -> Path:
    """Write D2 content to docs/diagrams/.

    Creates the directory if it doesn't exist.
    Prepends the D2 config header (ELK layout, direction: right).
    Returns the path to the written file.
    """
    output_dir = project_root / "docs" / "diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = _get_filename(diagram_type, flow_name)
    output_path = output_dir / filename

    full_content = D2_HEADER + "\n" + d2_content
    output_path.write_text(full_content, encoding="utf-8")

    return output_path


def _get_filename(diagram_type: str, flow_name: str | None) -> str:
    """Determine the output filename from diagram type."""
    if diagram_type == "sequence" and flow_name:
        return f"flow-{flow_name}.d2"
    return _FILENAME_MAP.get(diagram_type, f"{diagram_type}.d2")
