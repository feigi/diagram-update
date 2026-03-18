"""Tests for the static analyzer: file walking, import resolution, component grouping."""

from __future__ import annotations

from pathlib import Path

import pytest

from diagram_update.analyzer import (
    _build_relationships,
    _compute_component_id,
    _group_into_components,
    _matches_any,
    _path_to_dotted,
    _resolve_imports,
    _walk_files,
    analyze,
)
from diagram_update.models import (
    Component,
    DiagramConfig,
    FileInfo,
    ImportInfo,
)


# --- File walker tests ---


class TestWalkFiles:
    def test_finds_python_files(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "readme.md").write_text("hi")
        config = DiagramConfig(include=["**/*"], exclude=[])
        files = _walk_files(config, tmp_path)
        assert "app.py" in files
        assert "readme.md" not in files

    def test_respects_exclude(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("x = 1")
        config = DiagramConfig(include=["**/*"], exclude=["tests/**"])
        files = _walk_files(config, tmp_path)
        assert "src/main.py" in files
        assert "tests/test_main.py" not in files

    def test_respects_include(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")
        (tmp_path / "other").mkdir()
        (tmp_path / "other" / "stuff.py").write_text("x = 1")
        config = DiagramConfig(include=["src/**/*"], exclude=[])
        files = _walk_files(config, tmp_path)
        assert "src/main.py" in files
        assert "other/stuff.py" not in files

    def test_detects_language(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("x = 1")
        config = DiagramConfig(include=["**/*"], exclude=[])
        files = _walk_files(config, tmp_path)
        assert files["app.py"].language == "python"

    def test_counts_lines(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("a\nb\nc\n")
        config = DiagramConfig(include=["**/*"], exclude=[])
        files = _walk_files(config, tmp_path)
        assert files["app.py"].line_count == 3


class TestMatchesAny:
    def test_simple_glob(self):
        assert _matches_any("tests/test_foo.py", ["tests/**"])

    def test_no_match(self):
        assert not _matches_any("src/main.py", ["tests/**"])

    def test_star_pattern(self):
        assert _matches_any("foo.py", ["*.py"])

    def test_double_star(self):
        assert _matches_any("a/b/c.py", ["**/*.py"])


# --- Path to dotted module tests ---


class TestPathToDotted:
    def test_simple_file(self):
        assert _path_to_dotted("src/models.py") == "src.models"

    def test_init_file(self):
        assert _path_to_dotted("src/analyzer/__init__.py") == "src.analyzer"

    def test_nested(self):
        assert _path_to_dotted("src/a/b/c.py") == "src.a.b.c"

    def test_non_python(self):
        assert _path_to_dotted("src/main.java") is None


# --- Import resolution tests ---


class TestResolveImports:
    def _make_files(self, paths: list[str], tmp_path: Path) -> dict[str, FileInfo]:
        """Create FileInfo entries and actual files for testing."""
        files: dict[str, FileInfo] = {}
        for p in paths:
            full = tmp_path / p
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("")
            files[p] = FileInfo(path=Path(p), language="python")
        return files

    def test_absolute_import_resolves(self, tmp_path: Path):
        files = self._make_files(
            ["pkg/foo.py", "pkg/bar.py"], tmp_path
        )
        files["pkg/foo.py"].imports = [
            ImportInfo(module="pkg.bar", names=["something"])
        ]
        _resolve_imports(files, tmp_path)
        imp = files["pkg/foo.py"].imports[0]
        assert imp.is_internal is True
        assert str(imp.resolved_path) == "pkg/bar.py"

    def test_absolute_import_to_package(self, tmp_path: Path):
        files = self._make_files(
            ["pkg/foo.py", "pkg/sub/__init__.py"], tmp_path
        )
        files["pkg/foo.py"].imports = [
            ImportInfo(module="pkg.sub", names=["something"])
        ]
        _resolve_imports(files, tmp_path)
        imp = files["pkg/foo.py"].imports[0]
        assert imp.is_internal is True
        assert str(imp.resolved_path) == "pkg/sub/__init__.py"

    def test_relative_import_resolves(self, tmp_path: Path):
        files = self._make_files(
            ["pkg/foo.py", "pkg/bar.py"], tmp_path
        )
        files["pkg/foo.py"].imports = [
            ImportInfo(module="bar", names=["x"], level=1)
        ]
        _resolve_imports(files, tmp_path)
        imp = files["pkg/foo.py"].imports[0]
        assert imp.is_internal is True
        assert str(imp.resolved_path) == "pkg/bar.py"

    def test_parent_relative_import(self, tmp_path: Path):
        files = self._make_files(
            ["pkg/sub/foo.py", "pkg/bar.py"], tmp_path
        )
        files["pkg/sub/foo.py"].imports = [
            ImportInfo(module="bar", names=["x"], level=2)
        ]
        _resolve_imports(files, tmp_path)
        imp = files["pkg/sub/foo.py"].imports[0]
        assert imp.is_internal is True
        assert str(imp.resolved_path) == "pkg/bar.py"

    def test_external_import_not_resolved(self, tmp_path: Path):
        files = self._make_files(["pkg/foo.py"], tmp_path)
        files["pkg/foo.py"].imports = [
            ImportInfo(module="requests", names=["get"])
        ]
        _resolve_imports(files, tmp_path)
        imp = files["pkg/foo.py"].imports[0]
        assert imp.is_internal is False

    def test_stdlib_import_not_resolved(self, tmp_path: Path):
        files = self._make_files(["pkg/foo.py"], tmp_path)
        files["pkg/foo.py"].imports = [
            ImportInfo(module="os.path", names=["join"])
        ]
        _resolve_imports(files, tmp_path)
        imp = files["pkg/foo.py"].imports[0]
        assert imp.is_internal is False


# --- Component grouping tests ---


class TestComputeComponentId:
    def test_module_granularity(self):
        assert _compute_component_id("src/models.py", "module", "python") == "src.models"

    def test_directory_granularity(self):
        assert _compute_component_id("src/sub/models.py", "directory", "python") == "src"

    def test_directory_single_file(self):
        assert _compute_component_id("main.py", "directory", "python") == "main"

    def test_package_granularity_python(self):
        assert _compute_component_id("src/auth/service.py", "package", "python") == "src.auth"

    def test_package_granularity_shallow(self):
        assert _compute_component_id("src/main.py", "package", "python") == "src"


class TestGroupIntoComponents:
    def test_module_creates_one_per_file(self, tmp_path: Path):
        files = {
            "a.py": FileInfo(path=Path("a.py"), language="python"),
            "b.py": FileInfo(path=Path("b.py"), language="python"),
        }
        components = _group_into_components(files, "module", tmp_path)
        assert len(components) == 2
        assert "a" in components
        assert "b" in components

    def test_directory_groups_by_top_dir(self, tmp_path: Path):
        files = {
            "src/a.py": FileInfo(path=Path("src/a.py"), language="python"),
            "src/b.py": FileInfo(path=Path("src/b.py"), language="python"),
            "lib/c.py": FileInfo(path=Path("lib/c.py"), language="python"),
        }
        components = _group_into_components(files, "directory", tmp_path)
        assert len(components) == 2
        assert "src" in components
        assert "lib" in components
        assert len(components["src"].files) == 2

    def test_package_groups_by_python_package(self, tmp_path: Path):
        files = {
            "src/auth/login.py": FileInfo(
                path=Path("src/auth/login.py"), language="python"
            ),
            "src/auth/logout.py": FileInfo(
                path=Path("src/auth/logout.py"), language="python"
            ),
            "src/api/routes.py": FileInfo(
                path=Path("src/api/routes.py"), language="python"
            ),
        }
        components = _group_into_components(files, "package", tmp_path)
        assert len(components) == 2
        assert "src.auth" in components
        assert "src.api" in components
        assert len(components["src.auth"].files) == 2

    def test_assigns_component_id_to_files(self, tmp_path: Path):
        files = {
            "src/a.py": FileInfo(path=Path("src/a.py"), language="python"),
        }
        _group_into_components(files, "directory", tmp_path)
        assert files["src/a.py"].component_id == "src"


# --- Relationship building tests ---


class TestBuildRelationships:
    def test_aggregates_to_component_level(self):
        files = {
            "src/a.py": FileInfo(
                path=Path("src/a.py"),
                language="python",
                component_id="src",
                imports=[
                    ImportInfo(module="lib.b", is_internal=True, resolved_path=Path("lib/b.py")),
                    ImportInfo(module="lib.c", is_internal=True, resolved_path=Path("lib/c.py")),
                ],
            ),
            "lib/b.py": FileInfo(
                path=Path("lib/b.py"), language="python", component_id="lib"
            ),
            "lib/c.py": FileInfo(
                path=Path("lib/c.py"), language="python", component_id="lib"
            ),
        }
        components = {
            "src": Component(id="src", label="src"),
            "lib": Component(id="lib", label="lib"),
        }
        rels = _build_relationships(files, components)
        assert len(rels) == 1
        assert rels[0].source == "src"
        assert rels[0].target == "lib"
        assert rels[0].weight == 2

    def test_ignores_self_loops(self):
        files = {
            "pkg/a.py": FileInfo(
                path=Path("pkg/a.py"),
                language="python",
                component_id="pkg",
                imports=[
                    ImportInfo(module="pkg.b", is_internal=True, resolved_path=Path("pkg/b.py")),
                ],
            ),
            "pkg/b.py": FileInfo(
                path=Path("pkg/b.py"), language="python", component_id="pkg"
            ),
        }
        components = {"pkg": Component(id="pkg", label="pkg")}
        rels = _build_relationships(files, components)
        assert len(rels) == 0

    def test_ignores_external_imports(self):
        files = {
            "pkg/a.py": FileInfo(
                path=Path("pkg/a.py"),
                language="python",
                component_id="pkg",
                imports=[
                    ImportInfo(module="requests", is_internal=False),
                ],
            ),
        }
        components = {"pkg": Component(id="pkg", label="pkg")}
        rels = _build_relationships(files, components)
        assert len(rels) == 0


# --- Full integration test ---


class TestAnalyze:
    def test_full_pipeline(self, tmp_path: Path):
        """Integration test: analyze a small Python project."""
        # Create a small project
        src = tmp_path / "src"
        auth = src / "auth"
        api = src / "api"
        for d in [auth, api]:
            d.mkdir(parents=True)
            (d / "__init__.py").write_text("")

        (auth / "service.py").write_text(
            "class AuthService:\n    pass\n"
        )
        (api / "routes.py").write_text(
            "from src.auth.service import AuthService\n"
            "from src.auth import something\n"
        )

        config = DiagramConfig(include=["**/*"], exclude=[], granularity="package")
        graph = analyze(config, tmp_path)

        # Should find files
        assert len(graph.files) >= 4
        assert "python" in graph.languages

        # Should have components
        assert len(graph.components) >= 2
        comp_ids = {c.id for c in graph.components}
        assert "src.auth" in comp_ids
        assert "src.api" in comp_ids

    def test_empty_project(self, tmp_path: Path):
        config = DiagramConfig()
        graph = analyze(config, tmp_path)
        assert len(graph.components) == 0
        assert len(graph.relationships) == 0

    def test_module_granularity(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("")
        config = DiagramConfig(include=["**/*"], exclude=[], granularity="module")
        graph = analyze(config, tmp_path)
        assert len(graph.components) == 2
