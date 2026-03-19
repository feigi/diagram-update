"""LLM client: invoke Claude via GitHub Copilot CLI."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from diagram_update.models import LLMError, ToolError

logger = logging.getLogger(__name__)

# Pattern to strip markdown code fences from LLM output
_FENCE_RE = re.compile(
    r"^```(?:d2|D2|diagram)?\s*\n(.*?)\n```\s*$",
    re.DOTALL,
)

# Pattern to extract component IDs from pass 1 structured output
_COMPONENT_ID_RE = re.compile(r"^\s*-\s*id:\s*(\S+)", re.MULTILINE)


def generate_diagram(
    skeleton: str,
    diagram_type: str = "architecture",
    existing_d2: str | None = None,
    model: str = "claude-sonnet-4.6",
    entry_points: list[str] | None = None,
) -> str:
    """Generate D2 diagram code via GitHub Copilot CLI.

    Uses a two-pass approach:
    1. Identify components and relationships from skeleton
    2. Convert to D2 code

    Returns raw D2 string. Raises LLMError on failure.
    """
    _check_copilot_available()

    # Pass 1: Identify components and relationships
    logger.info("Pass 1: identifying %s components...", diagram_type)
    pass1_prompt = _build_pass1_prompt(skeleton, diagram_type, entry_points, existing_d2)
    logger.debug("Pass 1 prompt length: %d chars", len(pass1_prompt))
    components_text = _call_copilot(pass1_prompt, model)
    components_text = _parse_response(components_text)

    if not components_text.strip():
        raise LLMError("Empty response from copilot (pass 1: component identification)")

    # Validate pass 1 structure and extract component IDs
    pass1_ids = _extract_pass1_ids(components_text)
    if pass1_ids:
        logger.info("Pass 1 complete: %d components identified", len(pass1_ids))
    else:
        logger.warning("Pass 1 returned text but no parseable component IDs")

    # Pass 2: Convert to D2 code
    logger.info("Pass 2: generating D2 code for %s...", diagram_type)
    pass2_prompt = _build_pass2_prompt(
        components_text, diagram_type, existing_d2,
    )
    logger.debug("Pass 2 prompt length: %d chars", len(pass2_prompt))
    raw = _call_copilot(pass2_prompt, model)
    d2 = _parse_response(raw)

    if not d2.strip():
        # Retry once with error correction prompt
        logger.warning("Empty D2 response, retrying with error correction prompt")
        d2 = _retry_generation(components_text, diagram_type, model)

    if not d2.strip():
        raise LLMError("Empty response from copilot after retry")

    # Post-process: collapse duplicate edges, remove orphan nodes
    from diagram_update.merger import collapse_edges, remove_orphan_nodes
    d2 = collapse_edges(d2)
    d2 = remove_orphan_nodes(d2)

    _validate_d2(d2, skeleton=skeleton)
    return d2


def _check_copilot_available() -> None:
    """Verify GitHub Copilot CLI is installed."""
    if shutil.which("copilot") is None:
        raise ToolError(
            "GitHub Copilot CLI is required. "
            "Install: npm install -g @github/copilot "
            "or: curl -fsSL https://gh.io/copilot-install | bash"
        )


def _build_pass1_prompt(
    skeleton: str,
    diagram_type: str,
    entry_points: list[str] | None = None,
    existing_d2: str | None = None,
) -> str:
    """Build the Pass 1 prompt for component identification."""
    if existing_d2:
        return _build_pass1_update_prompt(skeleton, diagram_type, existing_d2, entry_points)

    parts = [
        "You are a software architect analyzing a codebase. Given the following "
        "codebase skeleton, identify the key architectural components and their "
        "relationships.\n",
        f"Diagram type: {diagram_type}\n",
        "Codebase skeleton:\n",
        skeleton,
    ]

    if diagram_type == "architecture":
        parts.append(
            "\n\nFocus on high-level services, modules, and packages. "
            "Group related files into logical architectural components."
        )
    elif diagram_type == "dependencies":
        parts.append(
            "\n\nFocus on package-level and module-level import relationships. "
            "Show every direct dependency between packages."
        )
    elif diagram_type == "sequence":
        if entry_points:
            ep_list = ", ".join(entry_points)
            parts.append(
                f"\n\nTrace the call flows starting from these entry points: {ep_list}. "
                "Show the sequence of interactions between components for each flow."
            )
        else:
            parts.append(
                "\n\nInfer the top 5 most significant entry points or call flows. "
                "Show the sequence of interactions between components for each flow."
            )

    parts.extend([
        "\n\nIMPORTANT: Use the exact file/package paths from the skeleton as component IDs. "
        "For example, if the skeleton shows 'src/auth/handler.py', use 'auth.handler' as the id. "
        "Do NOT invent new names — derive IDs directly from the skeleton paths.",
        "",
        "Output a structured list, with components sorted alphabetically by id:",
        "COMPONENTS:",
        "- id: <key derived from skeleton path>, label: <human name>, type: <service|module|database|queue|external>",
        "- ...",
        "",
        "RELATIONSHIPS:",
        "- <source_id> -> <target_id>: <relationship description>",
        "(List relationships sorted by source_id, then target_id)",
        "- ...",
        "",
        "Output ONLY the structured list, no explanations. "
        "Determinism matters: always produce the same output for the same input.",
    ])

    return "\n".join(parts)


def _build_pass1_update_prompt(
    skeleton: str,
    diagram_type: str,
    existing_d2: str,
    entry_points: list[str] | None = None,
) -> str:
    """Build pass 1 prompt that updates an existing diagram rather than creating from scratch."""
    parts = [
        "You are updating an existing software architecture diagram. "
        "The existing diagram below is the AUTHORITATIVE baseline. "
        "Your job is to identify ONLY what changed based on the current codebase skeleton.\n",
        f"Diagram type: {diagram_type}\n",
        "EXISTING DIAGRAM (this is your starting point — replicate it exactly unless "
        "the codebase skeleton shows something changed):\n",
        existing_d2,
        "\n\nCURRENT CODEBASE SKELETON (use this to detect additions, removals, or changes):\n",
        skeleton,
    ]

    parts.extend([
        "\n\nRules:",
        "- Keep ALL existing component IDs, labels, groupings, and relationship descriptions UNCHANGED "
        "unless the codebase skeleton proves they are wrong or outdated.",
        "- Do NOT rename, re-label, regroup, or rephrase existing components or relationships.",
        "- Only ADD components/relationships that are new in the codebase but missing from the diagram.",
        "- Only REMOVE components/relationships that no longer exist in the codebase.",
        "- If nothing changed, reproduce the existing diagram's components and relationships exactly.",
    ])

    if diagram_type == "sequence" and entry_points:
        ep_list = ", ".join(entry_points)
        parts.append(f"\nEntry points: {ep_list}")

    parts.extend([
        "\n\nOutput a structured list:",
        "COMPONENTS:",
        "- id: <key>, label: <human name>, type: <service|module|database|queue|external>",
        "- ...",
        "",
        "RELATIONSHIPS:",
        "- <source_id> -> <target_id>: <relationship description>",
        "- ...",
        "",
        "Output ONLY the structured list, no explanations.",
    ])

    return "\n".join(parts)


def _build_pass2_prompt(
    components_text: str,
    diagram_type: str,
    existing_d2: str | None,
) -> str:
    """Build the Pass 2 prompt for D2 generation."""
    parts = [
        "Convert the following software architecture components into a valid D2 diagram.\n",
        components_text,
        "\n\nD2 syntax rules:",
        "- Nodes: `key: Label`",
        "- Connections: `a -> b: label`",
        "- Containers: `group: Label { child1; child2 }`",
        "- Use `{shape: cylinder}` for databases, `{shape: queue}` for queues",
        "- Use `{shape: cloud}` for external services",
        "- Use containers to group related components by module/service",
    ]

    if diagram_type == "sequence":
        parts.extend([
            "",
            "This is a sequence diagram. Use this D2 structure:",
            "- Create a container with `shape: sequence_diagram`",
            "- Declare actors as nodes inside the container",
            "- Declare messages as edges between actors (in call order)",
        ])

    if existing_d2:
        parts.extend([
            "\n\nCRITICAL: An existing diagram is provided below. You MUST reproduce it as closely "
            "as possible. Keep the same node keys, labels, container structure, edge labels, "
            "and ordering. Only apply the minimal changes needed to reflect the component list above. "
            "If a node/edge exists in the existing diagram and in the component list, copy it verbatim.",
            f"\nExisting diagram:\n{existing_d2}",
        ])

    parts.extend([
        "",
        "IMPORTANT RULES FOR DETERMINISM:",
        "1. Use the EXACT component IDs from the list above as D2 node keys — "
        "do NOT rename, abbreviate, or rephrase them.",
        "2. Declare nodes in alphabetical order by key.",
        "3. Declare edges in alphabetical order by source, then target.",
        "4. Ensure every '{' has a matching '}' on its own line.",
        "5. Every edge endpoint must reference a declared node key.",
        "",
        "Output ONLY valid D2 code. No markdown fences, no explanations.",
    ])

    return "\n".join(parts)


def _retry_generation(
    components_text: str,
    diagram_type: str,
    model: str,
) -> str:
    """Retry D2 generation with an error correction prompt."""
    prompt = (
        "The previous attempt to generate a D2 diagram produced an empty or "
        "invalid response. Please try again.\n\n"
        "Convert these components into valid D2 code:\n\n"
        f"{components_text}\n\n"
        "D2 syntax rules:\n"
        "- Nodes: `key: Label`\n"
        "- Connections: `a -> b: label`\n"
        "- Containers: `group: Label { child1; child2 }`\n"
    )
    if diagram_type == "sequence":
        prompt += (
            "- This is a sequence diagram: use `shape: sequence_diagram` on a container\n"
        )
    prompt += "\nOutput ONLY valid D2 code. No markdown fences, no explanations."

    raw = _call_copilot(prompt, model)
    return _parse_response(raw)


def _validate_d2(d2: str, skeleton: str | None = None) -> None:
    """Validate generated D2 has nodes/edges and covers skeleton relationships.

    Raises LLMError if the D2 content is structurally invalid.
    Logs warnings for missing skeleton coverage (does not reject).
    """
    from diagram_update.merger import parse_d2

    # Check balanced braces
    _check_balanced_braces(d2)

    parsed = parse_d2(d2)
    if not parsed.node_keys:
        raise LLMError("Generated D2 contains no nodes")
    if not parsed.edge_tuples:
        logger.warning(
            "Generated D2 has %d node(s) but no edges", len(parsed.node_keys)
        )

    # Check that edge endpoints reference declared nodes or their children
    _check_edge_endpoints(parsed)

    # Check skeleton relationship coverage if skeleton provided
    if skeleton:
        _check_skeleton_coverage(parsed, skeleton)

    logger.debug(
        "D2 validation passed: %d nodes, %d edges",
        len(parsed.node_keys),
        len(parsed.edge_tuples),
    )


def _check_balanced_braces(d2: str) -> None:
    """Verify that braces are balanced in the D2 output."""
    depth = 0
    for i, ch in enumerate(d2):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise LLMError(
                    f"Generated D2 has unbalanced braces (unexpected '}}' at char {i})"
                )
    if depth != 0:
        raise LLMError(
            f"Generated D2 has unbalanced braces ({depth} unclosed '{{' remaining)"
        )


def _check_edge_endpoints(parsed: object) -> None:
    """Warn if edge endpoints don't reference any declared node."""
    all_node_keys = parsed.node_keys
    if not all_node_keys:
        return

    for source, _, target in parsed.edge_tuples:
        for endpoint in (source, target):
            # An endpoint is valid if it matches a node key directly,
            # or if it's a dotted child of a node (container.child)
            found = endpoint in all_node_keys
            if not found:
                # Check if any node is a prefix (container reference)
                for key in all_node_keys:
                    if endpoint.startswith(key + ".") or key.startswith(endpoint + "."):
                        found = True
                        break
            if not found:
                logger.warning(
                    "Edge endpoint %r not found in declared nodes", endpoint
                )


def _check_skeleton_coverage(parsed: object, skeleton: str) -> None:
    """Check how well the D2 output covers skeleton relationships."""
    skeleton_edges = _extract_skeleton_edges(skeleton)
    if not skeleton_edges:
        return

    d2_node_lower = {k.lower() for k in parsed.node_keys}
    covered = 0
    for source, target in skeleton_edges:
        # Match if skeleton edge component appears as substring or suffix of any D2 node
        src_found = any(
            source in k or source.split(".")[-1] in k for k in d2_node_lower
        )
        tgt_found = any(
            target in k or target.split(".")[-1] in k for k in d2_node_lower
        )
        if src_found and tgt_found:
            covered += 1
    coverage = covered / len(skeleton_edges)
    logger.info(
        "Skeleton coverage: %d/%d edges (%.0f%%)",
        covered, len(skeleton_edges), coverage * 100,
    )
    if coverage < 0.3:
        logger.warning(
            "Low skeleton coverage (%.0f%%): LLM output may not reflect codebase structure",
            coverage * 100,
        )


def _extract_pass1_ids(components_text: str) -> list[str]:
    """Extract component IDs from pass 1 structured output.

    Returns a list of IDs in order, or empty list if the format
    doesn't match the expected structured output.
    """
    ids = _COMPONENT_ID_RE.findall(components_text)
    # Strip trailing commas that might be part of "id: foo, label: bar"
    return [id_.rstrip(",") for id_ in ids]


def _extract_skeleton_edges(skeleton: str) -> list[tuple[str, str]]:
    """Extract (source, target) pairs from DEPENDENCIES section of skeleton.

    Uses both full path and leaf name for matching to avoid false positives
    when multiple components share the same leaf name.
    """
    edges: list[tuple[str, str]] = []
    in_deps = False
    for line in skeleton.splitlines():
        if line.strip() == "DEPENDENCIES:":
            in_deps = True
            continue
        if in_deps:
            if line.strip() and not line.startswith(" ") and ":" in line and "->" not in line:
                # Hit a new section header
                break
            if "->" in line:
                parts = line.split("->", 1)
                if len(parts) == 2:
                    src_raw = parts[0].strip().lower()
                    tgt_raw = parts[1].strip().split("(")[0].strip().lower()
                    # Use full path for more precise matching
                    src = src_raw.replace("/", ".")
                    tgt = tgt_raw.replace("/", ".")
                    if src and tgt:
                        edges.append((src, tgt))
    return edges


def _call_copilot(prompt: str, model: str) -> str:
    """Invoke GitHub Copilot CLI in non-interactive mode and return output."""
    cmd = [
        "copilot",
        "-p", prompt,
        "-s",
        "--model", model,
        "--no-ask-user",
        "--no-custom-instructions",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise LLMError("copilot timed out after 120s")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.debug("copilot stderr: %s", stderr)
        if "not authenticated" in stderr.lower() or "token expired" in stderr.lower():
            raise LLMError(
                "GitHub authentication failed. Run 'copilot login' to authenticate."
            )
        raise LLMError(f"copilot failed (exit {result.returncode}): {stderr}")

    logger.debug("copilot returned %d chars", len(result.stdout))
    return result.stdout


def _parse_response(raw: str) -> str:
    """Parse and clean LLM response, stripping markdown fences."""
    text = raw.strip()
    if not text:
        return ""

    # Strip markdown code fences
    match = _FENCE_RE.match(text)
    if match:
        return match.group(1).strip()

    # Also handle fences that aren't the entire output
    # Remove leading/trailing fence lines
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()
