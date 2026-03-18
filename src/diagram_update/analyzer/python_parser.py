"""Python import parser using ast with regex fallback."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from diagram_update.models import ImportInfo


class _ImportExtractor(ast.NodeVisitor):
    """Extract import statements from a Python AST."""

    def __init__(self) -> None:
        self.imports: list[ImportInfo] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    names=[],
                    level=0,
                    lineno=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        # Skip __future__ imports
        if module == "__future__":
            return
        names = [alias.name for alias in node.names] if node.names else []
        self.imports.append(
            ImportInfo(
                module=module,
                names=names,
                level=node.level or 0,
                lineno=node.lineno,
            )
        )


# Regex patterns for fallback parsing
_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)", re.MULTILINE)
_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+(\.*)(\w[\w.]*)\s+import\s+(.+)", re.MULTILINE
)


def _parse_with_regex(source: str) -> list[ImportInfo]:
    """Fallback regex-based import extraction for files with syntax errors."""
    imports: list[ImportInfo] = []

    for match in _IMPORT_RE.finditer(source):
        for module in match.group(1).split(","):
            module = module.strip()
            if module:
                imports.append(ImportInfo(module=module, lineno=0))

    for match in _FROM_IMPORT_RE.finditer(source):
        dots = match.group(1)
        module = match.group(2)
        names_str = match.group(3)

        # Skip __future__
        if module == "__future__":
            continue

        level = len(dots)
        # Parse names, handling parenthesized multiline imports
        names_str = names_str.strip().rstrip("\\").strip("()")
        names = [n.strip() for n in names_str.split(",") if n.strip()]

        imports.append(
            ImportInfo(module=module, names=names, level=level, lineno=0)
        )

    return imports


def parse_python_file(path: Path) -> list[ImportInfo]:
    """Parse a Python file and extract import statements.

    Uses ast for reliable parsing, falling back to regex if the file
    has syntax errors.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    if not source.strip():
        return []

    try:
        tree = ast.parse(source, filename=str(path))
        extractor = _ImportExtractor()
        extractor.visit(tree)
        return extractor.imports
    except SyntaxError:
        return _parse_with_regex(source)
