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


def generate_diagram(
    skeleton: str,
    diagram_type: str = "architecture",
    existing_d2: str | None = None,
    model: str = " claude-opus-4.6",
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
    pass1_prompt = _build_pass1_prompt(skeleton, diagram_type, entry_points)
    logger.debug("Pass 1 prompt length: %d chars", len(pass1_prompt))
    components_text = _call_copilot(pass1_prompt, model)
    components_text = _parse_response(components_text)

    if not components_text.strip():
        raise LLMError("Empty response from copilot (pass 1: component identification)")

    logger.info("Pass 1 complete: %d chars of component text", len(components_text))

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

    _validate_d2(d2)
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
) -> str:
    """Build the Pass 1 prompt for component identification."""
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
            "\n\nPreserve the structure of this existing diagram where possible.",
            "Only add new components, remove deleted ones, and update changed relationships.",
            f"Existing diagram:\n{existing_d2}",
        ])

    parts.append(
        "\n\nOutput ONLY valid D2 code. No markdown fences, no explanations."
    )

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


def _validate_d2(d2: str) -> None:
    """Validate that generated D2 has at least one node and one edge.

    Raises LLMError if the D2 content is structurally invalid.
    """
    from diagram_update.merger import parse_d2

    parsed = parse_d2(d2)
    if not parsed.node_keys:
        raise LLMError("Generated D2 contains no nodes")
    if not parsed.edge_tuples:
        logger.warning(
            "Generated D2 has %d node(s) but no edges", len(parsed.node_keys)
        )
    logger.debug(
        "D2 validation passed: %d nodes, %d edges",
        len(parsed.node_keys),
        len(parsed.edge_tuples),
    )


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
