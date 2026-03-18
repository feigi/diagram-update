"""Anchor-based D2 diagram merger."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Regex patterns for parsing D2 content
# Node: identifier optionally followed by label/style/block
_NODE_RE = re.compile(r"^(\w[\w.]*)(?:\s*:\s*(.+?))?(?:\s*\{)?\s*$")
# Edge: source -> target with optional label
_EDGE_RE = re.compile(
    r"^([\w.]+)\s*(->|<->|<-|--)\s*([\w.]+)(?:\s*:\s*(.+))?\s*$"
)
# Closing brace
_CLOSE_BRACE_RE = re.compile(r"^\s*\}\s*$")

# Config/header lines to skip during parsing
_SKIP_PREFIXES = ("vars:", "d2-config:", "layout-engine:", "direction:")


@dataclass
class _ParsedD2:
    """Parsed representation of a D2 file."""

    node_keys: set[str] = field(default_factory=set)
    edge_tuples: set[tuple[str, str, str]] = field(default_factory=set)
    edge_labels: dict[tuple[str, str, str], str] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)
    # Map node key -> (start_line, end_line) indices (inclusive)
    node_spans: dict[str, tuple[int, int]] = field(default_factory=dict)
    # Map edge tuple -> line index
    edge_line_indices: dict[tuple[str, str, str], int] = field(
        default_factory=dict
    )


def parse_d2(content: str) -> _ParsedD2:
    """Parse D2 content to extract nodes, edges, and their positions."""
    result = _ParsedD2()
    lines = content.splitlines()
    result.lines = lines

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines, comments, config blocks
        if not stripped or stripped.startswith("#") or _is_config_line(stripped):
            i += 1
            continue

        # Try edge first (edges also match the node pattern)
        edge_match = _EDGE_RE.match(stripped)
        if edge_match:
            source, direction, target = (
                edge_match.group(1),
                edge_match.group(2),
                edge_match.group(3),
            )
            label = edge_match.group(4) or ""
            key = (source, direction, target)
            result.edge_tuples.add(key)
            result.edge_labels[key] = label.strip()
            result.edge_line_indices[key] = i
            i += 1
            continue

        # Try node
        node_match = _NODE_RE.match(stripped)
        if node_match:
            node_key = node_match.group(1)
            result.node_keys.add(node_key)
            start = i

            # Check if it opens a block
            if stripped.endswith("{"):
                depth = 1
                i += 1
                while i < len(lines) and depth > 0:
                    inner = lines[i].strip()
                    depth += inner.count("{") - inner.count("}")
                    i += 1
                result.node_spans[node_key] = (start, i - 1)
            else:
                result.node_spans[node_key] = (start, start)
                i += 1
            continue

        # Closing brace or unrecognized line
        i += 1

    return result


def merge_diagrams(old_d2: str, new_d2: str) -> str:
    """Merge new D2 content into existing D2 content.

    Preserves ordering and layout of unchanged nodes/edges.
    Adds new nodes, removes deleted nodes, updates changed edges.

    If old_d2 is empty, returns new_d2 unchanged.
    """
    if not old_d2.strip():
        return new_d2

    old = parse_d2(old_d2)
    new = parse_d2(new_d2)

    added_nodes = new.node_keys - old.node_keys
    removed_nodes = old.node_keys - new.node_keys
    added_edges = new.edge_tuples - old.edge_tuples
    removed_edges = old.edge_tuples - new.edge_tuples

    # Build set of line indices to remove
    remove_lines: set[int] = set()

    # Remove lines for deleted nodes
    for node_key in removed_nodes:
        if node_key in old.node_spans:
            start, end = old.node_spans[node_key]
            for li in range(start, end + 1):
                remove_lines.add(li)

    # Remove lines for deleted edges
    for edge_key in removed_edges:
        if edge_key in old.edge_line_indices:
            remove_lines.add(old.edge_line_indices[edge_key])

    # Build output: keep non-removed lines, update edge labels in-place
    output_lines: list[str] = []
    # Track where to insert new nodes (before first edge)
    first_edge_output_idx: int | None = None

    for i, line in enumerate(old.lines):
        if i in remove_lines:
            continue

        # Check if this line is an edge that needs label update
        stripped = line.strip()
        edge_match = _EDGE_RE.match(stripped)
        if edge_match:
            source, direction, target = (
                edge_match.group(1),
                edge_match.group(2),
                edge_match.group(3),
            )
            key = (source, direction, target)
            if key in new.edge_labels and new.edge_labels[key] != old.edge_labels.get(key, ""):
                new_label = new.edge_labels[key]
                if new_label:
                    line = f"{source} {direction} {target}: {new_label}"
                else:
                    line = f"{source} {direction} {target}"

            if first_edge_output_idx is None:
                first_edge_output_idx = len(output_lines)

        output_lines.append(line)

    # Build new node lines from new D2 content
    new_node_lines: list[str] = []
    for node_key in sorted(added_nodes):
        if node_key in new.node_spans:
            start, end = new.node_spans[node_key]
            for li in range(start, end + 1):
                new_node_lines.append(new.lines[li])

    # Build new edge lines
    new_edge_lines: list[str] = []
    for edge_key in sorted(added_edges):
        if edge_key in new.edge_line_indices:
            new_edge_lines.append(new.lines[new.edge_line_indices[edge_key]])

    # Insert new nodes before first edge, or at end if no edges
    if new_node_lines:
        insert_idx = first_edge_output_idx if first_edge_output_idx is not None else len(output_lines)
        for j, node_line in enumerate(new_node_lines):
            output_lines.insert(insert_idx + j, node_line)

    # Append new edges at end
    output_lines.extend(new_edge_lines)

    return "\n".join(output_lines)


def check_removal_threshold(
    old_d2: str, merged_d2: str, threshold: float = 0.8
) -> bool:
    """Check if merge would remove more than threshold fraction of old nodes.

    Returns True if the removal exceeds the threshold (merge should be
    written to .d2.new instead).
    """
    old = parse_d2(old_d2)
    merged = parse_d2(merged_d2)

    if not old.node_keys:
        return False

    removed_count = len(old.node_keys - merged.node_keys)
    removal_fraction = removed_count / len(old.node_keys)
    return removal_fraction > threshold


def _is_config_line(stripped: str) -> bool:
    """Check if a line is part of the D2 config/header block."""
    for prefix in _SKIP_PREFIXES:
        if stripped.startswith(prefix):
            return True
    # Also skip lines inside vars block (indented config)
    if stripped in ("}", "{"):
        return False
    return False
