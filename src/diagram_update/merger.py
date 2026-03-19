"""Anchor-based D2 diagram merger."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Regex patterns for parsing D2 content
# Node: identifier optionally followed by label/style/block
# Supports hyphens and dots in keys (e.g., my-service, auth-api.handler, container.child)
_NODE_RE = re.compile(r"^([\w][\w.\-]*)(?:\s*:\s*(.+?))?(?:\s*\{)?\s*$")
# Edge: source -> target with optional label
# Supports dotted paths for container references (e.g., container.child -> other.child)
_EDGE_RE = re.compile(
    r"^([\w][\w.\-]*)\s*(->|<->|<-|--)\s*([\w][\w.\-]*)(?:\s*:\s*(.+))?\s*$"
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


def collapse_edges(d2: str) -> str:
    """Collapse duplicate edges between the same (source, target) pair.

    When multiple edges share the same source, direction, and target,
    merge them into a single edge with combined labels:
    - 1 label: kept as-is
    - 2-3 labels: comma-separated list
    - 4+ labels: common prefix + count, or short list if no common prefix
    """
    lines = d2.splitlines()
    # Collect edges in order: (source, direction, target) -> list of (label, line_index)
    edge_groups: dict[tuple[str, str, str], list[tuple[str, int]]] = {}
    edge_order: list[tuple[str, str, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        edge_match = _EDGE_RE.match(stripped)
        if edge_match:
            source = edge_match.group(1)
            direction = edge_match.group(2)
            target = edge_match.group(3)
            label = (edge_match.group(4) or "").strip()
            key = (source, direction, target)
            if key not in edge_groups:
                edge_groups[key] = []
                edge_order.append(key)
            edge_groups[key].append((label, i))

    # Nothing to collapse
    if all(len(v) <= 1 for v in edge_groups.values()):
        return d2

    # Build set of lines to remove (duplicate edge lines)
    remove_lines: set[int] = set()
    # Map first occurrence line -> merged label
    replace_lines: dict[int, str] = {}

    for key, entries in edge_groups.items():
        if len(entries) <= 1:
            continue

        source, direction, target = key
        labels = [label for label, _ in entries if label]
        first_line_idx = entries[0][1]

        # Remove all but first occurrence
        for _, line_idx in entries[1:]:
            remove_lines.add(line_idx)

        merged_label = _merge_labels(labels)
        if merged_label:
            replace_lines[first_line_idx] = (
                f"{source} {direction} {target}: {merged_label}"
            )
        else:
            replace_lines[first_line_idx] = (
                f"{source} {direction} {target}"
            )

    output = []
    for i, line in enumerate(lines):
        if i in remove_lines:
            continue
        if i in replace_lines:
            output.append(replace_lines[i])
        else:
            output.append(line)

    return "\n".join(output)


def _merge_labels(labels: list[str]) -> str:
    """Merge multiple edge labels into a single label."""
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if label and label not in seen:
            seen.add(label)
            unique.append(label)

    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]

    # For 2-3 unique labels, use a comma-separated list
    if len(unique) <= 3:
        return ", ".join(unique)

    # For 4+ labels, try to find a common prefix
    prefix = _common_prefix(unique)
    if prefix:
        return f"{prefix} ({len(unique)}x)"

    # Fall back to first 3 + count
    return ", ".join(unique[:3]) + f" (+{len(unique) - 3} more)"


def _common_prefix(labels: list[str]) -> str:
    """Find a meaningful common prefix among labels."""
    if not labels:
        return ""
    words_lists = [label.split() for label in labels]
    min_len = min(len(w) for w in words_lists)
    prefix_words: list[str] = []
    for i in range(min_len):
        if all(w[i] == words_lists[0][i] for w in words_lists):
            prefix_words.append(words_lists[0][i])
        else:
            break
    result = " ".join(prefix_words)
    # Only use prefix if it's meaningful (at least one word)
    return result if result else ""


def remove_orphan_nodes(d2: str) -> str:
    """Remove nodes that have no edges connecting to or from them.

    A node is considered connected if its key (or a dotted child of it)
    appears as a source or target in any edge.
    """
    parsed = parse_d2(d2)

    if not parsed.node_keys or not parsed.edge_tuples:
        return d2

    # Collect all keys referenced in edges (sources and targets)
    referenced: set[str] = set()
    for source, _, target in parsed.edge_tuples:
        referenced.add(source)
        referenced.add(target)

    # Collect all node keys that have edges within container blocks.
    # A container block is connected if any edge inside it references
    # nodes that are also inside it (non-dotted child references).
    container_edge_nodes: set[str] = set()
    for node_key in parsed.node_keys:
        if node_key in parsed.node_spans:
            start, end = parsed.node_spans[node_key]
            if end > start:
                # Multi-line block — check if any edges are inside it
                for edge_key, edge_line in parsed.edge_line_indices.items():
                    if start < edge_line < end:
                        container_edge_nodes.add(node_key)
                        break

    # A node is connected if:
    # 1. Its key matches directly in an edge, or
    # 2. It's a prefix of a referenced dotted path (container whose children have edges), or
    # 3. It's a container block that contains edges between its children
    orphans: set[str] = set()
    for node_key in parsed.node_keys:
        is_connected = False
        for ref in referenced:
            if ref == node_key or ref.startswith(node_key + "."):
                is_connected = True
                break
        # Protect container nodes that have internal edges
        if not is_connected and node_key in container_edge_nodes:
            is_connected = True
        if not is_connected:
            orphans.add(node_key)

    if not orphans:
        return d2

    # Build set of lines to remove
    remove_lines: set[int] = set()
    for node_key in orphans:
        if node_key in parsed.node_spans:
            start, end = parsed.node_spans[node_key]
            for li in range(start, end + 1):
                remove_lines.add(li)

    output = [line for i, line in enumerate(parsed.lines) if i not in remove_lines]
    return "\n".join(output)


def _is_config_line(stripped: str) -> bool:
    """Check if a line is part of the D2 config/header block."""
    for prefix in _SKIP_PREFIXES:
        if stripped.startswith(prefix):
            return True
    # Also skip lines inside vars block (indented config)
    if stripped in ("}", "{"):
        return False
    return False
