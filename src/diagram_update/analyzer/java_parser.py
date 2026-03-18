"""Java import parser using regex-based extraction."""

from __future__ import annotations

import re
from pathlib import Path

from diagram_update.models import ImportInfo

# Match: import [static] com.example.Foo;
# Match: import [static] com.example.*;
_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;", re.MULTILINE
)

# Match: package com.example;
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def parse_java_file(path: Path) -> list[ImportInfo]:
    """Parse a Java file and extract import statements.

    Returns a list of ImportInfo with:
    - module: the dotted import path (e.g., 'com.example.Foo')
    - names: ['*'] for wildcard imports, else empty
    - level: 0 (Java has no relative imports)
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    if not source.strip():
        return []

    imports: list[ImportInfo] = []
    for match in _IMPORT_RE.finditer(source):
        module = match.group(1)
        names: list[str] = []
        if module.endswith(".*"):
            module = module[:-2]
            names = ["*"]
        imports.append(
            ImportInfo(module=module, names=names, level=0, lineno=match.start())
        )

    return imports


def extract_package(path: Path) -> str | None:
    """Extract the package declaration from a Java file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    m = _PACKAGE_RE.search(source)
    return m.group(1) if m else None
