"""Static analysis: extract imports and build dependency graphs."""

from __future__ import annotations

import fnmatch
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from diagram_update.models import (
    Component,
    DependencyGraph,
    DiagramConfig,
    FileInfo,
    ImportInfo,
    Relationship,
)

from .c_parser import parse_c_file
from .java_parser import extract_package, parse_java_file
from .python_parser import parse_python_file

logger = logging.getLogger(__name__)

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".java": "java",
    ".c": "c",
    ".h": "c",
}


def analyze(config: DiagramConfig, project_root: Path) -> DependencyGraph:
    """Run static analysis on the project.

    1. Walk project_root, filtered by config.include/exclude
    2. Detect language(s) and select appropriate parser(s)
    3. Parse all source files to extract imports
    4. Resolve imports to internal file paths
    5. Group files into components based on config.granularity
    6. Build and return the dependency graph
    """
    t0 = time.monotonic()
    files = _walk_files(config, project_root)
    logger.info("Found %d source files in %.1fs", len(files), time.monotonic() - t0)
    languages = sorted({f.language for f in files.values()})
    logger.info("Detected languages: %s", ", ".join(languages) if languages else "none")

    t1 = time.monotonic()
    _parse_imports(files, project_root)
    logger.info("Parsed imports in %.1fs", time.monotonic() - t1)

    t2 = time.monotonic()
    _resolve_imports(files, project_root)
    internal_count = sum(
        1 for f in files.values()
        for imp in f.imports if imp.is_internal
    )
    logger.info("Resolved %d internal imports in %.1fs", internal_count, time.monotonic() - t2)

    components = _group_into_components(files, config.granularity, project_root)
    relationships = _build_relationships(files, components)

    logger.info(
        "Built graph: %d components, %d relationships (granularity=%s)",
        len(components), len(relationships), config.granularity,
    )

    return DependencyGraph(
        components=list(components.values()),
        relationships=relationships,
        files=files,
        languages=languages,
        source_roots=[project_root],
    )


def _walk_files(config: DiagramConfig, project_root: Path) -> dict[str, FileInfo]:
    """Walk project directory applying include/exclude filters.

    Uses os.walk with topdown=True so that excluded directories are pruned
    before their contents are traversed — critical for large projects where
    build artifacts (build/, .gradle/, etc.) can contain tens of thousands
    of files that would otherwise be stat-ed and discarded.
    """
    files: dict[str, FileInfo] = {}

    for root_str, dirnames, filenames in os.walk(str(project_root), topdown=True):
        root_path = Path(root_str)
        rel_root = root_path.relative_to(project_root)
        rel_root_str = str(rel_root)

        # Prune excluded directories in-place; os.walk skips pruned dirs.
        pruned: list[str] = []
        for d in sorted(dirnames):
            rel_dir = d if rel_root_str == "." else f"{rel_root_str}/{d}"
            if not _matches_any(rel_dir, config.exclude):
                pruned.append(d)
        dirnames[:] = pruned

        for filename in sorted(filenames):
            path = root_path / filename
            rel = path.relative_to(project_root)
            rel_str = str(rel)

            ext = path.suffix
            if ext not in LANGUAGE_EXTENSIONS:
                continue

            if not _matches_any(rel_str, config.include):
                continue
            if _matches_any(rel_str, config.exclude):
                continue

            language = LANGUAGE_EXTENSIONS[ext]
            try:
                line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                line_count = 0

            files[rel_str] = FileInfo(
                path=rel,
                language=language,
                line_count=line_count,
            )

    return files


def _matches_any(path_str: str, patterns: list[str]) -> bool:
    """Check if a path matches any of the given glob patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(path_str, pattern):
            return True
        # fnmatch doesn't handle ** as recursive glob - handle it manually
        if "**" in pattern:
            # "**/*" should match any depth including root files
            # "tests/**" should match anything under tests/
            dir_pattern = pattern.split("**")[0].rstrip("/")
            if not dir_pattern:
                # Pattern like "**/*" matches everything
                return True
            if path_str.startswith(dir_pattern + "/") or path_str == dir_pattern:
                return True
    return False


def _parse_one_file(
    rel_str: str, language: str, project_root: Path,
) -> tuple[str, list[ImportInfo]]:
    """Parse imports for a single file. Returns (rel_str, imports_list)."""
    full_path = project_root / rel_str
    if language == "python":
        return rel_str, parse_python_file(full_path)
    elif language == "java":
        return rel_str, parse_java_file(full_path)
    elif language == "c":
        return rel_str, parse_c_file(full_path)
    return rel_str, []


def _parse_imports(files: dict[str, FileInfo], project_root: Path) -> None:
    """Parse imports from all source files using parallel threads."""
    total = len(files)
    if total == 0:
        return

    logger.info("Parsing imports for %d files ...", total)
    max_workers = min(8, os.cpu_count() or 4)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_parse_one_file, rel_str, fi.language, project_root): rel_str
            for rel_str, fi in files.items()
        }
        for future in as_completed(futures):
            rel_str_result, imports_list = future.result()
            files[rel_str_result].imports = imports_list
            completed += 1
            if total >= 20 and completed % max(1, total // 5) == 0:
                logger.info("Parsing imports: %d/%d files ...", completed, total)


def _resolve_imports(files: dict[str, FileInfo], project_root: Path) -> None:
    """Resolve import strings to internal file paths."""
    internal_paths = set(files.keys())

    # Build a mapping from dotted module paths to file paths for Python
    module_to_path: dict[str, str] = {}
    for rel_str in internal_paths:
        if rel_str.endswith(".py"):
            dotted = _path_to_dotted(rel_str)
            if dotted:
                module_to_path[dotted] = rel_str

    # Detect Java source roots (directories containing src/main/java/)
    java_source_roots = _detect_java_source_roots(internal_paths)

    for rel_str, file_info in files.items():
        if file_info.language == "python":
            for imp in file_info.imports:
                resolved = _resolve_python_import(
                    imp, rel_str, module_to_path, internal_paths
                )
                if resolved:
                    imp.is_internal = True
                    imp.resolved_path = Path(resolved)
                else:
                    imp.is_internal = False
        elif file_info.language == "java":
            for imp in file_info.imports:
                resolved = _resolve_java_import(
                    imp, internal_paths, java_source_roots
                )
                if resolved:
                    imp.is_internal = True
                    imp.resolved_path = Path(resolved)
                else:
                    imp.is_internal = False
        elif file_info.language == "c":
            for imp in file_info.imports:
                resolved = _resolve_c_include(
                    imp, rel_str, internal_paths
                )
                if resolved:
                    imp.is_internal = True
                    imp.resolved_path = Path(resolved)
                else:
                    imp.is_internal = False


def _path_to_dotted(rel_path: str) -> str | None:
    """Convert a Python file path to a dotted module name.

    e.g., 'src/diagram_update/models.py' -> 'src.diagram_update.models'
          'src/diagram_update/__init__.py' -> 'src.diagram_update'
    """
    if not rel_path.endswith(".py"):
        return None
    path = rel_path[:-3]  # strip .py
    if path.endswith("/__init__"):
        path = path[:-9]  # strip /__init__
    return path.replace("/", ".")


def _resolve_python_import(
    imp: ImportInfo,
    importing_file: str,
    module_to_path: dict[str, str],
    internal_paths: set[str],
) -> str | None:
    """Resolve a single Python import to an internal file path."""
    if imp.level > 0:
        # Relative import
        parts = importing_file.split("/")
        # Go up `level` directories from the importing file's directory
        if importing_file.endswith("/__init__.py"):
            pkg_parts = parts[:-1]  # directory containing __init__.py
        else:
            pkg_parts = parts[:-1]  # directory containing the file

        levels_up = imp.level - 1  # level=1 means current package
        if levels_up > 0:
            pkg_parts = pkg_parts[:-levels_up] if levels_up < len(pkg_parts) else []

        if not pkg_parts:
            base = imp.module
        elif imp.module:
            base = "/".join(pkg_parts) + "/" + imp.module.replace(".", "/")
        else:
            base = "/".join(pkg_parts)

        # Check file.py and package/__init__.py
        candidates = [base + ".py", base + "/__init__.py"]
        for candidate in candidates:
            if candidate in internal_paths:
                return candidate
        return None
    else:
        # Absolute import
        module = imp.module
        if module in module_to_path:
            return module_to_path[module]

        # Try progressively shorter prefixes (e.g., 'a.b.c' -> 'a.b' -> 'a')
        parts = module.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in module_to_path:
                return module_to_path[prefix]

        return None


def _detect_java_source_roots(internal_paths: set[str]) -> list[str]:
    """Detect Java source root prefixes (e.g., 'src/main/java/')."""
    roots: set[str] = set()
    for p in internal_paths:
        if not p.endswith(".java"):
            continue
        # Look for src/main/java/ pattern
        idx = p.find("src/main/java/")
        if idx != -1:
            roots.add(p[: idx + len("src/main/java/")])
        else:
            # Also check src/ as a common source root
            idx = p.find("src/")
            if idx != -1:
                roots.add(p[: idx + len("src/")])
    return sorted(roots)


def _resolve_java_import(
    imp: ImportInfo,
    internal_paths: set[str],
    source_roots: list[str],
) -> str | None:
    """Resolve a Java import to an internal file path.

    Converts dotted package path to file path and checks against known files.
    """
    # System includes are never internal
    if "system" in imp.names:
        return None

    # Convert com.example.Foo -> com/example/Foo.java
    file_path = imp.module.replace(".", "/") + ".java"

    # Try each source root
    for root in source_roots:
        candidate = root + file_path
        if candidate in internal_paths:
            return candidate

    # Try without source root (files at project root or flat layout)
    if file_path in internal_paths:
        return file_path

    return None


def _resolve_c_include(
    imp: ImportInfo,
    including_file: str,
    internal_paths: set[str],
) -> str | None:
    """Resolve a C #include to an internal file path.

    For local includes ("..."), resolves relative to the including file first,
    then tries the path as-is from project root.
    System includes (<...>) are marked external.
    """
    # System includes are never internal
    if "system" in imp.names:
        return None

    include_path = imp.module

    # Try relative to the including file's directory
    including_dir = str(Path(including_file).parent)
    if including_dir == ".":
        relative_candidate = include_path
    else:
        relative_candidate = including_dir + "/" + include_path

    if relative_candidate in internal_paths:
        return relative_candidate

    # Try from project root
    if include_path in internal_paths:
        return include_path

    return None


def _group_into_components(
    files: dict[str, FileInfo],
    granularity: str,
    project_root: Path,
) -> dict[str, Component]:
    """Group files into components based on granularity setting."""
    components: dict[str, Component] = {}
    file_to_component: dict[str, str] = {}

    for rel_str, file_info in files.items():
        comp_id = _compute_component_id(rel_str, granularity, file_info.language)
        file_to_component[rel_str] = comp_id
        file_info.component_id = comp_id

        if comp_id not in components:
            components[comp_id] = Component(
                id=comp_id,
                label=_compute_component_label(comp_id),
                files=[],
                component_type=granularity,
            )
        components[comp_id].files.append(file_info.path)

    return components


def _compute_component_id(rel_path: str, granularity: str, language: str) -> str:
    """Compute the component ID for a file based on granularity."""
    parts = Path(rel_path).parts

    if granularity == "module":
        # Each file is its own component
        return rel_path.replace("/", ".").rsplit(".", 1)[0]

    if granularity == "directory":
        # Group by top-level directory
        if len(parts) > 1:
            return parts[0]
        return parts[0].rsplit(".", 1)[0]

    # granularity == "package" (default)
    if language == "python":
        # Group by Python package (directory containing __init__.py or
        # the parent directory for standalone files)
        if len(parts) > 1:
            # Use the first two directory levels if available, otherwise first
            if len(parts) > 2:
                return ".".join(parts[:2])
            return parts[0]
        return parts[0].rsplit(".", 1)[0]
    elif language == "java":
        # Group by package directory
        if len(parts) > 1:
            return ".".join(parts[:-1])
        return parts[0].rsplit(".", 1)[0]
    else:
        # C: group by directory
        if len(parts) > 1:
            return parts[0] if len(parts) == 2 else ".".join(parts[:2])
        return parts[0].rsplit(".", 1)[0]


def _compute_component_label(comp_id: str) -> str:
    """Generate a human-readable label from a component ID."""
    # Use the last segment of the dotted path
    parts = comp_id.split(".")
    return parts[-1]


def _build_relationships(
    files: dict[str, FileInfo],
    components: dict[str, Component],
) -> list[Relationship]:
    """Build component-level relationships from file-level imports."""
    # Aggregate import edges: (source_component, target_component) -> count
    edge_counts: dict[tuple[str, str], int] = defaultdict(int)

    for rel_str, file_info in files.items():
        source_comp = file_info.component_id
        for imp in file_info.imports:
            if not imp.is_internal or imp.resolved_path is None:
                continue
            target_file = str(imp.resolved_path)
            if target_file not in files:
                continue
            target_comp = files[target_file].component_id
            if source_comp != target_comp:
                edge_counts[(source_comp, target_comp)] += 1

    relationships = []
    for (source, target), weight in sorted(edge_counts.items()):
        relationships.append(
            Relationship(
                source=source,
                target=target,
                rel_type="imports",
                weight=weight,
            )
        )

    return relationships
