"""Tests for core data models."""

from pathlib import Path

from diagram_update.models import (
    Component,
    ConfigError,
    DependencyGraph,
    DiagramConfig,
    FileInfo,
    ImportInfo,
    LLMError,
    Relationship,
    ToolError,
)


class TestDiagramConfig:
    def test_defaults(self):
        config = DiagramConfig()
        assert config.include == ["**/*"]
        assert "tests/**" in config.exclude
        assert config.granularity == "package"
        assert config.entry_points == []
        assert config.model == "claude-opus-4-6"

    def test_custom_values(self):
        config = DiagramConfig(
            include=["src/**"],
            exclude=["vendor/**"],
            granularity="module",
            entry_points=["src/main.py:main"],
            model="claude-sonnet-4-6",
        )
        assert config.include == ["src/**"]
        assert config.granularity == "module"
        assert config.entry_points == ["src/main.py:main"]


class TestImportInfo:
    def test_defaults(self):
        imp = ImportInfo(module="os")
        assert imp.module == "os"
        assert imp.names == []
        assert imp.level == 0
        assert imp.is_internal is False
        assert imp.resolved_path is None
        assert imp.lineno == 0

    def test_from_import(self):
        imp = ImportInfo(module="os.path", names=["join", "exists"], lineno=5)
        assert imp.names == ["join", "exists"]
        assert imp.lineno == 5

    def test_relative_import(self):
        imp = ImportInfo(module="utils", level=1, is_internal=True)
        assert imp.level == 1
        assert imp.is_internal is True


class TestFileInfo:
    def test_defaults(self):
        fi = FileInfo(path=Path("src/main.py"), language="python")
        assert fi.path == Path("src/main.py")
        assert fi.language == "python"
        assert fi.imports == []
        assert fi.signatures == []
        assert fi.line_count == 0
        assert fi.component_id == ""

    def test_with_imports(self):
        imp = ImportInfo(module="os")
        fi = FileInfo(
            path=Path("src/app.py"),
            language="python",
            imports=[imp],
            line_count=100,
            component_id="app",
        )
        assert len(fi.imports) == 1
        assert fi.line_count == 100


class TestComponent:
    def test_defaults(self):
        c = Component(id="auth", label="Auth Service")
        assert c.id == "auth"
        assert c.label == "Auth Service"
        assert c.files == []
        assert c.sub_components == []
        assert c.component_type == "module"

    def test_with_files(self):
        c = Component(
            id="api",
            label="API Layer",
            files=[Path("src/api/routes.py"), Path("src/api/handlers.py")],
            component_type="package",
        )
        assert len(c.files) == 2
        assert c.component_type == "package"

    def test_sub_components(self):
        child = Component(id="auth_utils", label="Auth Utils")
        parent = Component(
            id="auth",
            label="Auth Service",
            sub_components=[child],
        )
        assert len(parent.sub_components) == 1
        assert parent.sub_components[0].id == "auth_utils"


class TestRelationship:
    def test_defaults(self):
        r = Relationship(source="api", target="auth")
        assert r.source == "api"
        assert r.target == "auth"
        assert r.rel_type == "imports"
        assert r.label == ""
        assert r.weight == 1

    def test_with_details(self):
        r = Relationship(
            source="api",
            target="db",
            rel_type="uses",
            label="queries",
            weight=5,
        )
        assert r.rel_type == "uses"
        assert r.weight == 5


class TestDependencyGraph:
    def test_empty_graph(self):
        g = DependencyGraph()
        assert g.components == []
        assert g.relationships == []
        assert g.files == {}
        assert g.languages == []
        assert g.source_roots == []

    def test_graph_holds_components_and_relationships(self):
        c1 = Component(id="api", label="API")
        c2 = Component(id="auth", label="Auth")
        r = Relationship(source="api", target="auth")
        g = DependencyGraph(
            components=[c1, c2],
            relationships=[r],
            languages=["python"],
            source_roots=[Path("src")],
        )
        assert len(g.components) == 2
        assert len(g.relationships) == 1
        assert g.languages == ["python"]

    def test_graph_files_dict(self):
        fi = FileInfo(path=Path("src/main.py"), language="python")
        g = DependencyGraph(files={"src/main.py": fi})
        assert "src/main.py" in g.files
        assert g.files["src/main.py"].language == "python"


class TestExceptions:
    def test_config_error(self):
        err = ConfigError("bad yaml")
        assert str(err) == "bad yaml"

    def test_llm_error(self):
        err = LLMError("empty response")
        assert str(err) == "empty response"

    def test_tool_error(self):
        err = ToolError("gh not found")
        assert str(err) == "gh not found"
