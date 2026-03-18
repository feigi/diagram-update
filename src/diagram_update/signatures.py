"""Signature extraction for Python, Java, and C source files."""

from __future__ import annotations

import ast
import re
from pathlib import Path


def extract_python_signatures(path: Path) -> list[str]:
    """Extract class and function signatures from a Python file using ast.

    Returns signatures without bodies, e.g.:
      'class MyClass(Base):'
      'def process(data: list[str]) -> bool:'
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not source.strip():
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return _extract_python_signatures_regex(source)

    signatures: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            sig = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
            signatures.append(sig)
            # Also extract methods
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    args = ast.unparse(item.args)
                    ret = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                    signatures.append(f"  {prefix} {item.name}({args}){ret}:")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            args = ast.unparse(node.args)
            ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            signatures.append(f"{prefix} {node.name}({args}){ret}:")

    return signatures


_PY_SIG_RE = re.compile(
    r"^(\s*)(class\s+\w+[^:]*:|(?:async\s+)?def\s+\w+\s*\([^)]*\)[^:]*:)",
    re.MULTILINE,
)


def _extract_python_signatures_regex(source: str) -> list[str]:
    """Fallback regex extraction for Python files with syntax errors."""
    return [m.group(2).strip() for m in _PY_SIG_RE.finditer(source)]


# Java: class/interface declarations and method signatures
_JAVA_CLASS_RE = re.compile(
    r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:abstract\s+)?"
    r"(?:final\s+)?(?:class|interface|enum)\s+(\w+)(?:\s+extends\s+\w+)?"
    r"(?:\s+implements\s+[\w,\s]+)?",
    re.MULTILINE,
)
_JAVA_METHOD_RE = re.compile(
    r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?"
    r"(?:abstract\s+)?(?:synchronized\s+)?([\w<>\[\],\s]+?)\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)


def extract_java_signatures(path: Path) -> list[str]:
    """Extract class and method signatures from a Java file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not source.strip():
        return []

    signatures: list[str] = []

    for m in _JAVA_CLASS_RE.finditer(source):
        signatures.append(m.group(0).strip())

    for m in _JAVA_METHOD_RE.finditer(source):
        # Reconstruct a compact signature
        ret_type = m.group(1).strip()
        name = m.group(2)
        params = m.group(3).strip()
        signatures.append(f"{ret_type} {name}({params})")

    return signatures


# C: function prototypes/definitions (return_type name(params))
_C_FUNC_RE = re.compile(
    r"^(?!.*#)\s*([\w*\s]+?)\s+(\*?\w+)\s*\(([^)]*)\)\s*[{;]",
    re.MULTILINE,
)


def extract_c_signatures(path: Path) -> list[str]:
    """Extract function signatures from a C/C++ file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not source.strip():
        return []

    signatures: list[str] = []
    # Skip common non-function keywords
    skip_keywords = {"if", "else", "while", "for", "switch", "return", "sizeof", "typedef"}

    for m in _C_FUNC_RE.finditer(source):
        ret_type = m.group(1).strip()
        name = m.group(2).strip()
        params = m.group(3).strip()

        # Skip false positives
        if name in skip_keywords or ret_type in skip_keywords:
            continue
        if ret_type.startswith("#"):
            continue

        signatures.append(f"{ret_type} {name}({params})")

    return signatures


def extract_signatures(path: Path, language: str) -> list[str]:
    """Extract signatures from a file based on its language."""
    if language == "python":
        return extract_python_signatures(path)
    elif language == "java":
        return extract_java_signatures(path)
    elif language == "c":
        return extract_c_signatures(path)
    return []
