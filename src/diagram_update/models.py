"""Core data models for diagram-update."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiagramConfig:
    """Configuration loaded from .diagram-update.yml."""

    include: list[str] = field(default_factory=lambda: ["**/*"])
    exclude: list[str] = field(
        default_factory=lambda: [
            "tests/**",
            "test/**",
            "vendor/**",
            "node_modules/**",
            ".git/**",
            "build/**",
            "bin/**",
            ".gradle/**",
            ".idea/**",
            "out/**",
            "target/**",
        ]
    )
    granularity: str = "package"
    entry_points: list[str] = field(default_factory=list)
    model: str = "claude-sonnet-4.6"
    token_budget: int = 30000
    timeout: int = 600


@dataclass
class ImportInfo:
    """A single import statement extracted from a source file."""

    module: str
    names: list[str] = field(default_factory=list)
    level: int = 0
    is_internal: bool = False
    resolved_path: Path | None = None
    lineno: int = 0


@dataclass
class FileInfo:
    """Metadata about a single source file."""

    path: Path
    language: str
    imports: list[ImportInfo] = field(default_factory=list)
    signatures: list[str] = field(default_factory=list)
    line_count: int = 0
    component_id: str = ""


@dataclass
class Component:
    """A logical grouping of source files."""

    id: str
    label: str
    files: list[Path] = field(default_factory=list)
    sub_components: list[Component] = field(default_factory=list)
    component_type: str = "module"


@dataclass
class Relationship:
    """A directed dependency between two components."""

    source: str
    target: str
    rel_type: str = "imports"
    label: str = ""
    weight: int = 1


@dataclass
class DependencyGraph:
    """Complete dependency graph of a project."""

    components: list[Component] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    files: dict[str, FileInfo] = field(default_factory=dict)
    languages: list[str] = field(default_factory=list)
    source_roots: list[Path] = field(default_factory=list)


class ConfigError(Exception):
    """Raised when the configuration file is invalid."""


class LLMError(Exception):
    """Raised when LLM invocation fails."""


class ToolError(Exception):
    """Raised when a required external tool is missing."""
