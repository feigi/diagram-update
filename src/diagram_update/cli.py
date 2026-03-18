"""CLI entry point for diagram-update."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from diagram_update.analyzer import analyze
from diagram_update.config import load_config
from diagram_update.llm import generate_diagram
from diagram_update.models import ConfigError, LLMError, ToolError
from diagram_update.skeleton import generate_skeleton
from diagram_update.writer import write_diagram

logger = logging.getLogger(__name__)

# Diagram types generated in a single run
_DIAGRAM_TYPES = ["architecture", "dependencies", "sequence"]


def main(argv: list[str] | None = None) -> int:
    """Run the diagram-update pipeline."""
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    project_root = Path(args.project_dir).resolve()
    if not project_root.is_dir():
        print(f"Error: {project_root} is not a directory", file=sys.stderr)
        return 1

    try:
        config = load_config(project_root)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    logger.info("Analyzing %s ...", project_root)
    graph = analyze(config, project_root)
    logger.info(
        "Found %d components, %d relationships",
        len(graph.components),
        len(graph.relationships),
    )

    skeleton = generate_skeleton(graph, project_root)
    logger.info("Generated skeleton (%d chars)", len(skeleton))

    errors = 0
    for diagram_type in _DIAGRAM_TYPES:
        try:
            d2_code = generate_diagram(
                skeleton,
                diagram_type=diagram_type,
                model=config.model,
                entry_points=config.entry_points or None,
            )
        except (ToolError, LLMError) as exc:
            print(f"Error ({diagram_type}): {exc}", file=sys.stderr)
            errors += 1
            continue

        output_path = write_diagram(d2_code, diagram_type, project_root)
        print(f"Wrote {output_path}")

    if errors == len(_DIAGRAM_TYPES):
        return 1

    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="diagram-update",
        description="Auto-generate D2 architecture diagrams from source code.",
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args(argv)


def _setup_logging(verbose: bool) -> None:
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )
