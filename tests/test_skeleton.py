"""Tests for skeleton generator."""

from pathlib import Path
from unittest.mock import patch

from diagram_update.models import (
    Component,
    DependencyGraph,
    FileInfo,
    ImportInfo,
    Relationship,
)
from diagram_update.skeleton import generate_skeleton


class TestGenerateSkeleton:
    """Tests for generate_skeleton()."""

    def _make_graph(
        self,
        files: dict[str, FileInfo] | None = None,
        components: list[Component] | None = None,
        relationships: list[Relationship] | None = None,
    ) -> DependencyGraph:
        return DependencyGraph(
            components=components or [],
            relationships=relationships or [],
            files=files or {},
            languages=["python"],
            source_roots=[Path("/project")],
        )

    def test_empty_graph(self):
        graph = self._make_graph()
        result = generate_skeleton(graph, Path("/project"))
        assert result == ""

    def test_file_tree_single_file(self):
        files = {
            "main.py": FileInfo(
                path=Path("main.py"), language="python", line_count=50
            ),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))
        assert "FILE TREE:" in result
        assert "main.py" in result
        assert "(50L)" in result

    def test_file_tree_nested_structure(self):
        files = {
            "src/app.py": FileInfo(
                path=Path("src/app.py"), language="python", line_count=100
            ),
            "src/utils/helpers.py": FileInfo(
                path=Path("src/utils/helpers.py"), language="python", line_count=30
            ),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))
        assert "src/" in result
        assert "utils/" in result
        assert "app.py" in result
        assert "helpers.py" in result

    def test_dependency_edges_present(self):
        files = {
            "src/api.py": FileInfo(
                path=Path("src/api.py"), language="python", component_id="src.api"
            ),
            "src/db.py": FileInfo(
                path=Path("src/db.py"), language="python", component_id="src.db"
            ),
        }
        components = [
            Component(id="src.api", label="api"),
            Component(id="src.db", label="db"),
        ]
        relationships = [
            Relationship(source="src.api", target="src.db", weight=3),
        ]
        graph = self._make_graph(
            files=files, components=components, relationships=relationships
        )
        result = generate_skeleton(graph, Path("/project"))
        assert "DEPENDENCIES:" in result
        assert "src/api -> src/db (x3)" in result

    def test_dependency_edges_weight_one_no_annotation(self):
        relationships = [
            Relationship(source="api", target="db", weight=1),
        ]
        graph = self._make_graph(relationships=relationships)
        result = generate_skeleton(graph, Path("/project"))
        assert "api -> db" in result
        assert "(x1)" not in result

    def test_dependency_edges_sorted_by_weight(self):
        relationships = [
            Relationship(source="a", target="b", weight=1),
            Relationship(source="c", target="d", weight=5),
            Relationship(source="e", target="f", weight=3),
        ]
        graph = self._make_graph(relationships=relationships)
        result = generate_skeleton(graph, Path("/project"))
        lines = result.split("\n")
        dep_lines = [l for l in lines if "->" in l]
        assert "c -> d (x5)" in dep_lines[0]
        assert "e -> f (x3)" in dep_lines[1]
        assert "a -> b" in dep_lines[2]

    def test_token_budget_enforced(self):
        # Create a graph with many files to exceed a small budget
        files = {}
        for i in range(200):
            path = f"pkg{i}/module{i}.py"
            files[path] = FileInfo(
                path=Path(path), language="python", line_count=100
            )
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"), token_budget=100)
        # With budget=100, max_words = 75
        words = result.split()
        assert len(words) <= 75

    def test_three_sections_present(self):
        """Skeleton should contain all three sections when data is available."""
        files = {
            "app.py": FileInfo(
                path=Path("app.py"),
                language="python",
                line_count=10,
                signatures=["def main():"],
            ),
        }
        relationships = [
            Relationship(source="app", target="utils", weight=1),
        ]
        graph = self._make_graph(files=files, relationships=relationships)
        result = generate_skeleton(graph, Path("/project"))
        assert "FILE TREE:" in result
        assert "SIGNATURES:" in result
        assert "DEPENDENCIES:" in result

    def test_no_line_count_omits_annotation(self):
        files = {
            "app.py": FileInfo(
                path=Path("app.py"), language="python", line_count=0
            ),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))
        assert "app.py" in result
        assert "(0L)" not in result

    def test_files_sorted_alphabetically(self):
        files = {
            "zoo.py": FileInfo(path=Path("zoo.py"), language="python"),
            "alpha.py": FileInfo(path=Path("alpha.py"), language="python"),
            "mid.py": FileInfo(path=Path("mid.py"), language="python"),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))
        lines = result.split("\n")
        file_lines = [l.strip() for l in lines if l.strip() and not l.startswith("FILE")]
        assert file_lines[0].startswith("alpha.py")
        assert file_lines[1].startswith("mid.py")
        assert file_lines[2].startswith("zoo.py")


class TestSignatureRanking:
    """Tests for signature ranking by reference count."""

    def _make_graph(
        self,
        files: dict[str, FileInfo] | None = None,
        relationships: list[Relationship] | None = None,
    ) -> DependencyGraph:
        return DependencyGraph(
            components=[],
            relationships=relationships or [],
            files=files or {},
            languages=["python"],
            source_roots=[Path("/project")],
        )

    def test_signatures_ranked_by_reference_count(self):
        """Most-referenced files should appear first in signatures section."""
        files = {
            "utils.py": FileInfo(
                path=Path("utils.py"),
                language="python",
                signatures=["def helper():"],
            ),
            "core.py": FileInfo(
                path=Path("core.py"),
                language="python",
                signatures=["def process():"],
                imports=[
                    ImportInfo(
                        module="utils",
                        is_internal=True,
                        resolved_path=Path("utils.py"),
                    ),
                ],
            ),
            "api.py": FileInfo(
                path=Path("api.py"),
                language="python",
                signatures=["def handle():"],
                imports=[
                    ImportInfo(
                        module="utils",
                        is_internal=True,
                        resolved_path=Path("utils.py"),
                    ),
                    ImportInfo(
                        module="core",
                        is_internal=True,
                        resolved_path=Path("core.py"),
                    ),
                ],
            ),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))

        # utils.py has 2 refs, core.py has 1 ref, api.py has 0 refs
        sig_section = result.split("SIGNATURES:\n")[1].split("\n\nDEPENDENCIES:")[0]
        lines = sig_section.split("\n")
        file_headers = [l for l in lines if l.startswith("# ")]
        assert "utils.py" in file_headers[0]
        assert "(refs: 2)" in file_headers[0]
        assert "core.py" in file_headers[1]
        assert "(refs: 1)" in file_headers[1]

    def test_signatures_section_shows_ref_counts(self):
        """Files with references should show their count."""
        files = {
            "a.py": FileInfo(
                path=Path("a.py"),
                language="python",
                signatures=["def foo():"],
            ),
            "b.py": FileInfo(
                path=Path("b.py"),
                language="python",
                signatures=["def bar():"],
                imports=[
                    ImportInfo(
                        module="a",
                        is_internal=True,
                        resolved_path=Path("a.py"),
                    ),
                ],
            ),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))
        assert "(refs: 1)" in result

    def test_no_signatures_omits_section(self):
        """SIGNATURES section should be absent when no files have signatures."""
        files = {
            "app.py": FileInfo(
                path=Path("app.py"), language="python", line_count=10
            ),
        }
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"))
        assert "SIGNATURES:" not in result

    def test_large_project_truncates_gracefully(self):
        """With a tight budget, low-connectivity files should be elided."""
        files = {}
        for i in range(50):
            files[f"mod{i:03d}.py"] = FileInfo(
                path=Path(f"mod{i:03d}.py"),
                language="python",
                line_count=100,
                signatures=[f"def func{i}():", f"class Class{i}:"],
            )
        graph = self._make_graph(files=files)
        result = generate_skeleton(graph, Path("/project"), token_budget=200)
        # Should fit within budget
        words = result.split()
        max_words = int(200 * 0.75)
        assert len(words) <= max_words

    def test_empty_project_minimal_skeleton(self):
        """Empty project produces empty skeleton."""
        graph = self._make_graph()
        result = generate_skeleton(graph, Path("/project"))
        assert result == ""
