"""Skeleton generator: convert dependency graph to token-efficient text."""

from __future__ import annotations

from pathlib import Path

from diagram_update.models import DependencyGraph


def generate_skeleton(
    graph: DependencyGraph,
    project_root: Path,
    token_budget: int = 5000,
) -> str:
    """Generate a token-efficient codebase skeleton string.

    Combines annotated file tree and dependency edges into a compact
    text representation. Truncates to fit within token_budget.

    Signatures are not included in this version (deferred to Step 9).
    """
    sections: list[str] = []

    # Section 1: Annotated file tree
    tree = _build_file_tree(graph)
    if tree:
        sections.append("FILE TREE:\n" + tree)

    # Section 2: Dependency edges
    edges = _build_dependency_edges(graph)
    if edges:
        sections.append("DEPENDENCIES:\n" + edges)

    skeleton = "\n\n".join(sections)

    # Enforce token budget via word-count approximation (1 token ~ 0.75 words)
    max_words = int(token_budget * 0.75)
    words = skeleton.split()
    if len(words) > max_words:
        skeleton = " ".join(words[:max_words])

    return skeleton


def _build_file_tree(graph: DependencyGraph) -> str:
    """Build an annotated file tree from the dependency graph."""
    if not graph.files:
        return ""

    # Collect all file paths and organize into a tree structure
    paths = sorted(graph.files.keys())

    # Group files by their directory for a compact tree view
    tree_lines: list[str] = []
    seen_dirs: set[str] = set()

    for file_path in paths:
        parts = Path(file_path).parts
        # Add directory entries we haven't seen
        for depth in range(len(parts) - 1):
            dir_path = "/".join(parts[: depth + 1])
            if dir_path not in seen_dirs:
                seen_dirs.add(dir_path)
                indent = "  " * depth
                tree_lines.append(f"{indent}{parts[depth]}/")

        # Add file entry
        file_info = graph.files[file_path]
        indent = "  " * (len(parts) - 1)
        annotation = f"  ({file_info.line_count}L)" if file_info.line_count > 0 else ""
        tree_lines.append(f"{indent}{parts[-1]}{annotation}")

    return "\n".join(tree_lines)


def _build_dependency_edges(graph: DependencyGraph) -> str:
    """Build compact dependency edge list."""
    if not graph.relationships:
        return ""

    # Sort by weight descending so most important edges come first
    sorted_rels = sorted(graph.relationships, key=lambda r: r.weight, reverse=True)

    lines: list[str] = []
    for rel in sorted_rels:
        source_label = _id_to_label(rel.source)
        target_label = _id_to_label(rel.target)
        weight_note = f" (x{rel.weight})" if rel.weight > 1 else ""
        lines.append(f"{source_label} -> {target_label}{weight_note}")

    return "\n".join(lines)


def _id_to_label(component_id: str) -> str:
    """Convert a component ID to a readable label."""
    return component_id.replace(".", "/")
