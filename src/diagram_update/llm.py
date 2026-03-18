"""LLM client: invoke Claude via gh copilot CLI."""

from __future__ import annotations

import re
import shutil
import subprocess

from diagram_update.models import LLMError, ToolError

# Pattern to strip markdown code fences from LLM output
_FENCE_RE = re.compile(
    r"^```(?:d2|D2|diagram)?\s*\n(.*?)\n```\s*$",
    re.DOTALL,
)


def generate_diagram(
    skeleton: str,
    diagram_type: str = "architecture",
    existing_d2: str | None = None,
    model: str = "claude-opus-4-6",
) -> str:
    """Generate D2 diagram code via gh copilot CLI.

    Uses a single-pass approach for v1: sends the skeleton and asks
    for D2 code directly. Two-pass approach deferred to Step 10.

    Returns raw D2 string. Raises LLMError on failure.
    """
    _check_gh_available()

    prompt = _build_prompt(skeleton, diagram_type, existing_d2)
    raw = _call_gh_copilot(prompt, model)
    d2 = _parse_response(raw)

    if not d2.strip():
        raise LLMError("Empty response from gh copilot")

    return d2


def _check_gh_available() -> None:
    """Verify gh CLI is available."""
    if shutil.which("gh") is None:
        raise ToolError(
            "GitHub CLI is required. Install: https://cli.github.com "
            "and run 'gh extension install github/gh-copilot'"
        )


def _build_prompt(
    skeleton: str,
    diagram_type: str,
    existing_d2: str | None,
) -> str:
    """Build the LLM prompt from skeleton and diagram type."""
    parts = [
        "You are a software architect. Analyze the following codebase skeleton "
        "and generate a D2 diagram.\n",
        f"Diagram type: {diagram_type}\n",
        "Codebase skeleton:\n",
        skeleton,
        "\n\nD2 syntax rules:",
        "- Nodes: `key: Label`",
        "- Connections: `a -> b: label`",
        "- Containers: `group: Label { child1; child2 }`",
        "- Use `{shape: cylinder}` for databases, `{shape: queue}` for queues",
        "- Use containers to group related components by module/service",
    ]

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


def _call_gh_copilot(prompt: str, model: str) -> str:
    """Invoke gh copilot CLI and return raw output."""
    cmd = [
        "gh", "copilot",
        "-p", prompt,
        "-s",
        "--model", model,
        "--no-ask-user",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise LLMError("gh copilot timed out after 60s")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not authenticated" in stderr.lower() or "token expired" in stderr.lower():
            raise LLMError("Run 'gh auth login' to authenticate.")
        raise LLMError(f"gh copilot failed (exit {result.returncode}): {stderr}")

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
