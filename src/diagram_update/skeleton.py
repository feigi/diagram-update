"""Skeleton generator: convert dependency graph to token-efficient text."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from diagram_update.models import DependencyGraph
from diagram_update.signatures import extract_signatures

# Budget allocation: file tree ~20%, signatures ~50%, edges ~30%
_TREE_BUDGET_RATIO = 0.20
_SIGS_BUDGET_RATIO = 0.50
_EDGES_BUDGET_RATIO = 0.30


def generate_skeleton(
    graph: DependencyGraph,
    project_root: Path,
    token_budget: int = 5000,
) -> str:
    """Generate a token-efficient codebase skeleton string.

    Combines three sections:
    1. Annotated file tree (~20% of budget)
    2. Ranked signatures (~50% of budget)
    3. Dependency edges (~30% of budget)

    Signatures are ranked by cross-file reference count (most-imported first).
    Each section is truncated to fit its budget allocation.
    """
    # Extract signatures for all files
    _extract_all_signatures(graph, project_root)

    # Compute reference counts for signature ranking
    ref_counts = _compute_reference_counts(graph)

    # Convert budget to word limits (1 token ~ 0.75 words)
    total_words = int(token_budget * 0.75)
    tree_words = int(total_words * _TREE_BUDGET_RATIO)
    sigs_words = int(total_words * _SIGS_BUDGET_RATIO)
    edges_words = int(total_words * _EDGES_BUDGET_RATIO)

    sections: list[str] = []

    # Section 1: Annotated file tree
    tree = _build_file_tree(graph)
    if tree:
        tree = _truncate_to_words(tree, tree_words)
        sections.append("FILE TREE:\n" + tree)

    # Section 2: Ranked signatures
    sigs = _build_ranked_signatures(graph, ref_counts)
    if sigs:
        sigs = _truncate_to_words(sigs, sigs_words)
        sections.append("SIGNATURES:\n" + sigs)

    # Section 3: Dependency edges
    edges = _build_dependency_edges(graph)
    if edges:
        edges = _truncate_to_words(edges, edges_words)
        sections.append("DEPENDENCIES:\n" + edges)

    return "\n\n".join(sections)


def _extract_all_signatures(graph: DependencyGraph, project_root: Path) -> None:
    """Extract signatures for all files in the graph."""
    for rel_str, file_info in graph.files.items():
        if not file_info.signatures:
            full_path = project_root / rel_str
            file_info.signatures = extract_signatures(full_path, file_info.language)


def _compute_reference_counts(graph: DependencyGraph) -> Counter[str]:
    """Count how many times each file is referenced (imported) by other files.

    Returns a Counter mapping file paths to their import count.
    """
    counts: Counter[str] = Counter()
    for file_info in graph.files.values():
        for imp in file_info.imports:
            if imp.is_internal and imp.resolved_path is not None:
                counts[str(imp.resolved_path)] += 1
    return counts


def _build_file_tree(graph: DependencyGraph) -> str:
    """Build an annotated file tree from the dependency graph."""
    if not graph.files:
        return ""

    paths = sorted(graph.files.keys())
    tree_lines: list[str] = []
    seen_dirs: set[str] = set()

    for file_path in paths:
        parts = Path(file_path).parts
        for depth in range(len(parts) - 1):
            dir_path = "/".join(parts[: depth + 1])
            if dir_path not in seen_dirs:
                seen_dirs.add(dir_path)
                indent = "  " * depth
                tree_lines.append(f"{indent}{parts[depth]}/")

        file_info = graph.files[file_path]
        indent = "  " * (len(parts) - 1)
        annotation = f"  ({file_info.line_count}L)" if file_info.line_count > 0 else ""
        tree_lines.append(f"{indent}{parts[-1]}{annotation}")

    return "\n".join(tree_lines)


def _build_ranked_signatures(
    graph: DependencyGraph,
    ref_counts: Counter[str],
) -> str:
    """Build signatures section ranked by cross-file reference count."""
    # Collect (file_path, signatures, ref_count) tuples
    file_sigs: list[tuple[str, list[str], int]] = []
    for rel_str, file_info in graph.files.items():
        if file_info.signatures:
            count = ref_counts.get(rel_str, 0)
            file_sigs.append((rel_str, file_info.signatures, count))

    if not file_sigs:
        return ""

    # Sort by reference count descending, then alphabetically
    file_sigs.sort(key=lambda x: (-x[2], x[0]))

    lines: list[str] = []
    for rel_str, sigs, count in file_sigs:
        ref_note = f" (refs: {count})" if count > 0 else ""
        lines.append(f"# {rel_str}{ref_note}")
        for sig in sigs:
            lines.append(sig)

    return "\n".join(lines)


def _build_dependency_edges(graph: DependencyGraph) -> str:
    """Build compact dependency edge list."""
    if not graph.relationships:
        return ""

    sorted_rels = sorted(graph.relationships, key=lambda r: r.weight, reverse=True)

    lines: list[str] = []
    for rel in sorted_rels:
        source_label = _id_to_label(rel.source)
        target_label = _id_to_label(rel.target)
        weight_note = f" (x{rel.weight})" if rel.weight > 1 else ""
        lines.append(f"{source_label} -> {target_label}{weight_note}")

    return "\n".join(lines)


def _truncate_to_words(text: str, max_words: int) -> str:
    """Truncate text to fit within a word budget.

    Truncates at line boundaries to avoid cutting mid-line.
    """
    words = text.split()
    if len(words) <= max_words:
        return text

    # Truncate at line boundaries
    lines = text.split("\n")
    result_lines: list[str] = []
    word_count = 0
    for line in lines:
        line_words = len(line.split())
        if word_count + line_words > max_words and result_lines:
            break
        result_lines.append(line)
        word_count += line_words

    return "\n".join(result_lines)


def _id_to_label(component_id: str) -> str:
    """Convert a component ID to a readable label."""
    return component_id.replace(".", "/")
