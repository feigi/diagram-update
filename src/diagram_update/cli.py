"""CLI entry point for diagram-update."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from diagram_update.analyzer import analyze
from diagram_update.config import load_config
from diagram_update.llm import generate_diagram
from diagram_update.models import ConfigError, LLMError, ToolError
from diagram_update.skeleton import generate_skeleton
from diagram_update.writer import render_png, write_diagram

logger = logging.getLogger(__name__)

# Diagram types generated in a single run
_DIAGRAM_TYPES = ["architecture", "dependencies", "sequence"]


def main(argv: list[str] | None = None) -> int:
    """Run the diagram-update pipeline."""
    t0 = time.monotonic()
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

    # CLI flag overrides config
    if args.token_budget is not None:
        config.token_budget = args.token_budget
    if args.timeout is not None:
        config.timeout = args.timeout

    logger.info("[1/4] Analyzing %s ...", project_root)
    graph = analyze(config, project_root)
    logger.info(
        "[1/4] Found %d components, %d relationships",
        len(graph.components), len(graph.relationships),
    )

    errors = 0
    attempted = 0
    diagrams_dir = project_root / "docs" / "diagrams"
    for diagram_type in _DIAGRAM_TYPES:
        attempted += 1

        logger.info("[2/4] Building %s skeleton ...", diagram_type)
        skeleton = generate_skeleton(
            graph, project_root,
            token_budget=config.token_budget,
            diagram_type=diagram_type,
        )
        logger.info("[2/4] Skeleton: %d chars", len(skeleton))

        logger.info("[3/4] Generating %s diagram ...", diagram_type)
        if diagram_type == "sequence" and not config.entry_points:
            logger.info("[3/4] No entry_points configured — LLM will infer them from the codebase")

        # Read existing diagram so the LLM can preserve node keys
        existing_d2 = _read_existing_diagram(diagrams_dir, diagram_type)
        if existing_d2:
            logger.info("[3/4] Found existing %s diagram, passing to LLM", diagram_type)

        try:
            d2_code = generate_diagram(
                skeleton,
                diagram_type=diagram_type,
                existing_d2=existing_d2,
                model=config.model,
                entry_points=config.entry_points or None,
                timeout=config.timeout,
            )
        except (ToolError, LLMError) as exc:
            print(f"Error ({diagram_type}): {exc}", file=sys.stderr)
            errors += 1
            continue

        logger.info("[4/4] Writing %s diagram ...", diagram_type)
        output_path = write_diagram(d2_code, diagram_type, project_root)
        print(f"Wrote {output_path}")
        png_path = render_png(output_path)
        if png_path:
            print(f"Rendered {png_path}")

    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.1f}s")

    if attempted > 0 and errors == attempted:
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
    parser.add_argument(
        "--token-budget",
        type=int,
        default=None,
        help="Token budget for codebase skeleton (default: from config or 30000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout in seconds for each LLM call (default: from config or 600)",
    )
    return parser.parse_args(argv)


def _read_existing_diagram(diagrams_dir: Path, diagram_type: str) -> str | None:
    """Read an existing diagram file if present, for LLM context."""
    filenames = {
        "architecture": "architecture.d2",
        "dependencies": "dependencies.d2",
    }
    filename = filenames.get(diagram_type, f"{diagram_type}.d2")
    path = diagrams_dir / filename
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def _setup_logging(verbose: bool) -> None:
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
    )
