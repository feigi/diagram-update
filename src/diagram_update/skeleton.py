"""Skeleton generator: convert dependency graph to token-efficient text."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from diagram_update.models import DependencyGraph
from diagram_update.signatures import extract_signatures

logger = logging.getLogger(__name__)

# Chars per token approximation for code content
_CHARS_PER_TOKEN = 4

# Per-diagram-type budget allocations (tree, signatures, edges)
_BUDGET_SPLITS: dict[str, tuple[float, float, float]] = {
    "architecture": (0.20, 0.40, 0.40),
    "dependencies": (0.15, 0.15, 0.70),
    "sequence":     (0.20, 0.10, 0.70),
}
_DEFAULT_SPLIT = (0.20, 0.30, 0.50)


def generate_skeleton(
    graph: DependencyGraph,
    project_root: Path,
    token_budget: int = 30000,
    diagram_type: str = "architecture",
) -> str:
    """Generate a token-efficient codebase skeleton string.

    Combines three sections:
    1. Annotated file tree
    2. Ranked signatures
    3. Dependency edges

    Budget allocation varies by diagram_type. Unused budget from earlier
    sections is redistributed to later sections.

    For dependency diagrams, edges are never truncated — they get their full
    content first, and the remaining budget is split between tree and signatures.
    """
    # Extract signatures for all files
    _extract_all_signatures(graph, project_root)

    # Compute reference counts for signature ranking
    ref_counts = _compute_reference_counts(graph)

    # Build all three raw sections (untruncated)
    raw_tree = _build_file_tree(graph)
    raw_sigs = _build_ranked_signatures(graph, ref_counts)
    raw_edges = _build_dependency_edges(graph)

    # Compute total char budget
    total_chars = token_budget * _CHARS_PER_TOKEN

    # Get the split for the diagram_type
    tree_frac, sigs_frac, edges_frac = _BUDGET_SPLITS.get(diagram_type, _DEFAULT_SPLIT)

    # Apply budget allocation and adaptive reallocation
    if diagram_type == "dependencies":
        # For dependency diagrams: edges get full content first (never truncated),
        # then remaining budget is split between tree and signatures
        final_edges = raw_edges
        remaining = total_chars - len(raw_edges)
        if remaining < 0:
            remaining = 0

        # Split remaining between tree and sigs proportionally
        # Original split ratios for tree and sigs
        tree_sigs_total = tree_frac + sigs_frac
        if tree_sigs_total > 0:
            tree_share = tree_frac / tree_sigs_total
            sigs_share = sigs_frac / tree_sigs_total
        else:
            tree_share = 0.5
            sigs_share = 0.5

        tree_budget = int(remaining * tree_share)
        sigs_budget = int(remaining * sigs_share)

        # Build tree first, redistribute leftover to sigs
        final_tree, tree_truncated = _truncate_to_chars(raw_tree, tree_budget)
        tree_leftover = tree_budget - len(final_tree)
        if tree_leftover > 0:
            sigs_budget += tree_leftover

        final_sigs, sigs_truncated = _truncate_to_chars(raw_sigs, sigs_budget)

        edges_truncated = False

        if tree_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "tree", len(raw_tree), len(final_tree),
            )
        if sigs_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "signatures", len(raw_sigs), len(final_sigs),
            )

    elif diagram_type in ("sequence",):
        # sequence: tree first, then edges (more important), then signatures
        tree_budget = int(total_chars * tree_frac)
        edges_budget = int(total_chars * edges_frac)
        sigs_budget = int(total_chars * sigs_frac)

        # Build tree first
        final_tree, tree_truncated = _truncate_to_chars(raw_tree, tree_budget)
        tree_leftover = tree_budget - len(final_tree)

        # Redistribute tree leftover to edges and sigs proportionally
        if tree_leftover > 0:
            edges_sigs_total = edges_frac + sigs_frac
            if edges_sigs_total > 0:
                edges_budget += int(tree_leftover * edges_frac / edges_sigs_total)
                sigs_budget += int(tree_leftover * sigs_frac / edges_sigs_total)
            else:
                edges_budget += tree_leftover

        # Build edges second (more important for sequence)
        final_edges, edges_truncated = _truncate_to_chars(raw_edges, edges_budget)
        edges_leftover = edges_budget - len(final_edges)

        # Redistribute edges leftover to sigs
        if edges_leftover > 0:
            sigs_budget += edges_leftover

        # Build signatures last
        final_sigs, sigs_truncated = _truncate_to_chars(raw_sigs, sigs_budget)

        if tree_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "tree", len(raw_tree), len(final_tree),
            )
        if edges_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "edges", len(raw_edges), len(final_edges),
            )
        if sigs_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "signatures", len(raw_sigs), len(final_sigs),
            )

    else:
        # architecture (default): tree first, then signatures, then edges
        tree_budget = int(total_chars * tree_frac)
        sigs_budget = int(total_chars * sigs_frac)
        edges_budget = int(total_chars * edges_frac)

        # Build tree first
        final_tree, tree_truncated = _truncate_to_chars(raw_tree, tree_budget)
        tree_leftover = tree_budget - len(final_tree)

        # Redistribute tree leftover to sigs and edges proportionally
        if tree_leftover > 0:
            sigs_edges_total = sigs_frac + edges_frac
            if sigs_edges_total > 0:
                sigs_budget += int(tree_leftover * sigs_frac / sigs_edges_total)
                edges_budget += int(tree_leftover * edges_frac / sigs_edges_total)
            else:
                sigs_budget += tree_leftover

        # Build signatures second (more important for architecture)
        final_sigs, sigs_truncated = _truncate_to_chars(raw_sigs, sigs_budget)
        sigs_leftover = sigs_budget - len(final_sigs)

        # Redistribute sigs leftover to edges
        if sigs_leftover > 0:
            edges_budget += sigs_leftover

        # Build edges last
        final_edges, edges_truncated = _truncate_to_chars(raw_edges, edges_budget)

        if tree_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "tree", len(raw_tree), len(final_tree),
            )
        if sigs_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "signatures", len(raw_sigs), len(final_sigs),
            )
        if edges_truncated:
            logger.info(
                "Skeleton %s section truncated: %d -> %d chars",
                "edges", len(raw_edges), len(final_edges),
            )

    # Assemble sections
    sections: list[str] = []
    if final_tree:
        sections.append("FILE TREE:\n" + final_tree)
    if final_sigs:
        sections.append("SIGNATURES:\n" + final_sigs)
    if final_edges:
        sections.append("DEPENDENCIES:\n" + final_edges)

    result = "\n\n".join(sections)

    # Log summary stats
    num_files = len(graph.files)
    num_edges = len(graph.relationships)
    logger.info(
        "Skeleton: %d files, %d edges, %d chars (budget: %d tokens / %d chars)",
        num_files, num_edges, len(result), token_budget, total_chars,
    )

    return result


def _truncate_to_chars(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate text to fit within a character budget.

    Truncates at line boundaries to avoid cutting mid-line.
    Returns a tuple of (truncated_text, was_truncated).
    """
    if len(text) <= max_chars:
        return text, False

    # Truncate at line boundaries
    lines = text.split("\n")
    result_lines: list[str] = []
    char_count = 0
    for line in lines:
        # Account for newline character between lines
        line_chars = len(line) + (1 if result_lines else 0)
        if char_count + line_chars > max_chars and result_lines:
            break
        result_lines.append(line)
        char_count += line_chars

    return "\n".join(result_lines), True


def _load_sig_cache(project_root: Path) -> dict:
    """Load signature cache from .diagram-update.cache. Return empty dict if missing/corrupt."""
    cache_path = project_root / ".diagram-update.cache"
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == 1:
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def _save_sig_cache(project_root: Path, cache: dict) -> None:
    """Write signature cache JSON to project root."""
    cache_path = project_root / ".diagram-update.cache"
    try:
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        logger.debug("Failed to write signature cache")


def _extract_all_signatures(graph: DependencyGraph, project_root: Path) -> None:
    """Extract signatures for all files in the graph, with mtime+size caching."""
    items = [(rel_str, fi) for rel_str, fi in graph.files.items() if not fi.signatures]
    if not items:
        return

    t0 = time.monotonic()
    logger.info("Extracting signatures for %d files ...", len(items))

    cache = _load_sig_cache(project_root)
    cached_sigs = cache.get("signatures", {})

    hits = 0
    misses_items: list[tuple[str, object]] = []

    for rel_str, file_info in items:
        full_path = project_root / rel_str
        try:
            st = full_path.stat()
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            mtime, size = 0.0, 0

        entry = cached_sigs.get(rel_str)
        if entry and entry.get("mtime") == mtime and entry.get("size") == size:
            file_info.signatures = entry["sigs"]
            hits += 1
        else:
            misses_items.append((rel_str, file_info))

    # Parallelise cache misses
    total_misses = len(misses_items)
    if total_misses > 0:
        max_workers = min(8, os.cpu_count() or 4)

        def _extract_one(rel_str: str, language: str) -> tuple[str, list[str]]:
            return rel_str, extract_signatures(project_root / rel_str, language)

        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_extract_one, rel_str, fi.language): (rel_str, fi)
                for rel_str, fi in misses_items
            }
            for future in as_completed(futures):
                rel_str, file_info = futures[future]
                rel_str_result, sigs = future.result()
                file_info.signatures = sigs
                # Update cache entry
                full_path = project_root / rel_str_result
                try:
                    st = full_path.stat()
                    cached_sigs[rel_str_result] = {
                        "mtime": st.st_mtime,
                        "size": st.st_size,
                        "sigs": sigs,
                    }
                except OSError:
                    pass
                completed += 1
                if total_misses >= 20 and completed % max(1, total_misses // 5) == 0:
                    logger.info("Extracting signatures: %d/%d files ...", completed, total_misses)

    elapsed = time.monotonic() - t0
    logger.info("Signature cache: %d hits, %d misses (%.1fs)", hits, total_misses, elapsed)

    cache["version"] = 1
    cache["signatures"] = cached_sigs
    _save_sig_cache(project_root, cache)


def _compute_reference_counts(graph: DependencyGraph) -> Counter[str]:
    """Count how many times each file is referenced (imported) by other files.

    Returns a Counter mapping file paths to their import count.
    """
    counts: Counter[str] = Counter()
    for file_info in graph.files.values():
        for imp in file_info.imports:
            if imp.is_internal and imp.resolved_path is not None:
                path_str = str(imp.resolved_path)
                # Handle absolute paths by making them relative to any source root
                for root in graph.source_roots:
                    root_str = str(root)
                    if path_str.startswith(root_str):
                        path_str = path_str[len(root_str):].lstrip("/")
                        break
                counts[path_str] += 1
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

    sorted_rels = sorted(
        graph.relationships,
        key=lambda r: (-r.weight, r.source, r.target),
    )

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
