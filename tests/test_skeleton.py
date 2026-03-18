"""Tests for skeleton generator."""

from pathlib import Path

from diagram_update.models import (
    Component,
    DependencyGraph,
    FileInfo,
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

    def test_both_sections_present(self):
        files = {
            "app.py": FileInfo(
                path=Path("app.py"), language="python", line_count=10
            ),
        }
        relationships = [
            Relationship(source="app", target="utils", weight=1),
        ]
        graph = self._make_graph(files=files, relationships=relationships)
        result = generate_skeleton(graph, Path("/project"))
        assert "FILE TREE:" in result
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
