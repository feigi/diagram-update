"""D2 file writer: write generated diagrams to docs/diagrams/."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

from diagram_update.merger import check_removal_threshold, merge_diagrams

logger = logging.getLogger(__name__)

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

    logger.info("Writing %s diagram to %s", diagram_type, output_path)

    # If existing file, merge with anchor-based strategy
    if output_path.exists():
        old_content = output_path.read_text(encoding="utf-8")
        merged_content = merge_diagrams(old_content, full_content)

        # Check 80% removal threshold
        if check_removal_threshold(old_content, merged_content):
            new_path = output_path.with_suffix(".d2.new")
            new_path.write_text(merged_content, encoding="utf-8")
            logger.warning(
                "Merge would remove >80%% of existing nodes. "
                "Wrote to %s instead of overwriting.",
                new_path,
            )
            return new_path

        output_path.write_text(merged_content, encoding="utf-8")
    else:
        output_path.write_text(full_content, encoding="utf-8")

    return output_path


def render_png(d2_path: Path) -> Path | None:
    """Render a D2 file to PNG using the `d2` CLI.

    Returns the PNG path on success, or None if `d2` is not installed or
    rendering fails.
    """
    if not shutil.which("d2"):
        logger.warning("d2 CLI not found — skipping PNG render of %s", d2_path)
        return None

    png_path = d2_path.with_suffix(".png")
    logger.info("Rendering PNG for %s ...", d2_path.name)
    t0 = time.monotonic()
    try:
        subprocess.run(
            ["d2", str(d2_path), str(png_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning("d2 render failed for %s: %s", d2_path, exc.stderr.strip())
        return None

    logger.info("Rendered PNG to %s (%.1fs)", png_path, time.monotonic() - t0)
    return png_path


def _get_filename(diagram_type: str, flow_name: str | None) -> str:
    """Determine the output filename from diagram type."""
    if diagram_type == "sequence" and flow_name:
        return f"flow-{flow_name}.d2"
    return _FILENAME_MAP.get(diagram_type, f"{diagram_type}.d2")
