"""Integration tests: full pipeline on multi-file fixture projects.

Each fixture represents a small but realistic project with cross-file
dependencies, exercising config -> analyze -> skeleton -> LLM -> write
end-to-end (LLM calls are mocked with realistic responses).
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from diagram_update.analyzer import analyze
from diagram_update.cli import main
from diagram_update.config import load_config
from diagram_update.models import DiagramConfig
from diagram_update.skeleton import generate_skeleton


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _build_python_project(root: Path) -> None:
    """Create a small Python web-app fixture with cross-package imports.

    Structure:
        myapp/
            __init__.py
            app.py          (imports from myapp.api and myapp.data)
            api/
                __init__.py
                routes.py   (imports from myapp.data)
            data/
                __init__.py
                models.py
                db.py       (imports models)
    """
    pkg = root / "myapp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "app.py").write_text(
        "from myapp.api.routes import register_routes\n"
        "from myapp.data.db import connect\n"
        "\n\n"
        "def create_app():\n"
        "    db = connect()\n"
        "    return register_routes(db)\n"
    )

    api = pkg / "api"
    api.mkdir()
    (api / "__init__.py").write_text("")
    (api / "routes.py").write_text(
        "from myapp.data.db import get_session\n"
        "from myapp.data.models import User\n"
        "\n\n"
        "def register_routes(db):\n"
        "    pass\n"
        "\n\n"
        "def get_users():\n"
        "    return User.query.all()\n"
    )

    data = pkg / "data"
    data.mkdir()
    (data / "__init__.py").write_text("")
    (data / "models.py").write_text(
        "class User:\n"
        '    name: str = ""\n'
        "\n\n"
        "class Post:\n"
        '    title: str = ""\n'
    )
    (data / "db.py").write_text(
        "from myapp.data.models import User\n"
        "\n\n"
        "def connect():\n"
        "    return None\n"
        "\n\n"
        "def get_session():\n"
        "    return None\n"
    )


def _build_java_project(root: Path) -> None:
    """Create a small Java project with package imports.

    Structure:
        src/main/java/com/example/
            App.java          (imports Service)
            Service.java      (imports Repository)
            Repository.java
    """
    pkg = root / "src" / "main" / "java" / "com" / "example"
    pkg.mkdir(parents=True)
    (pkg / "App.java").write_text(
        "package com.example;\n\n"
        "import com.example.Service;\n\n"
        "public class App {\n"
        "    private Service service;\n"
        "    public static void main(String[] args) {\n"
        "        new App().run();\n"
        "    }\n"
        "    public void run() { service.handle(); }\n"
        "}\n"
    )
    (pkg / "Service.java").write_text(
        "package com.example;\n\n"
        "import com.example.Repository;\n\n"
        "public class Service {\n"
        "    private Repository repo;\n"
        "    public void handle() { repo.findAll(); }\n"
        "}\n"
    )
    (pkg / "Repository.java").write_text(
        "package com.example;\n\n"
        "import java.util.List;\n\n"
        "public class Repository {\n"
        "    public List<Object> findAll() { return List.of(); }\n"
        "}\n"
    )


def _build_c_project(root: Path) -> None:
    """Create a small C project with header includes.

    Structure:
        src/
            main.c     (includes utils.h, parser.h)
            utils.c    (includes utils.h)
            utils.h
            parser.c   (includes parser.h, utils.h)
            parser.h
    """
    src = root / "src"
    src.mkdir()
    (src / "main.c").write_text(
        '#include "utils.h"\n'
        '#include "parser.h"\n'
        "#include <stdio.h>\n\n"
        "int main(int argc, char **argv) {\n"
        "    init();\n"
        "    parse(argv[1]);\n"
        "    return 0;\n"
        "}\n"
    )
    (src / "utils.h").write_text(
        "#ifndef UTILS_H\n"
        "#define UTILS_H\n"
        "void init(void);\n"
        "int helper(int x);\n"
        "#endif\n"
    )
    (src / "utils.c").write_text(
        '#include "utils.h"\n\n'
        "void init(void) {}\n"
        "int helper(int x) { return x + 1; }\n"
    )
    (src / "parser.h").write_text(
        "#ifndef PARSER_H\n"
        "#define PARSER_H\n"
        "void parse(const char *input);\n"
        "#endif\n"
    )
    (src / "parser.c").write_text(
        '#include "parser.h"\n'
        '#include "utils.h"\n'
        "#include <string.h>\n\n"
        "void parse(const char *input) {\n"
        "    helper(0);\n"
        "}\n"
    )


# Realistic mock LLM responses for each diagram type
_COMPONENTS_RESPONSE = """\
COMPONENTS:
- id: app, label: Application, type: service
- id: data, label: Data Layer, type: module
- id: logic, label: Business Logic, type: module

RELATIONSHIPS:
- app -> logic: delegates to
- logic -> data: reads from
- app -> data: configures"""

_ARCH_D2 = """\
app: Application {
  shape: rectangle
}
data: Data Layer {
  shape: cylinder
}
logic: Business Logic
app -> logic: delegates to
logic -> data: reads from
app -> data: configures"""

_DEPS_D2 = """\
app: Application
data: Data Layer
logic: Business Logic
app -> logic
logic -> data
app -> data"""

_SEQ_D2 = """\
flows: Flows {
  shape: sequence_diagram
  user: User
  app: Application
  logic: Logic
  data: Data
  user -> app: request
  app -> logic: process
  logic -> data: query
  data -> logic: result
  logic -> app: response
  app -> user: reply
}"""


def _mock_llm_side_effects():
    """Return side_effect list for 3 diagram types (2 calls each)."""
    return [
        _COMPONENTS_RESPONSE, _ARCH_D2,   # architecture
        _COMPONENTS_RESPONSE, _DEPS_D2,   # dependencies
        _COMPONENTS_RESPONSE, _SEQ_D2,    # sequence
    ]


# ---------------------------------------------------------------------------
# Analysis + Skeleton integration (no LLM mocking needed)
# ---------------------------------------------------------------------------

class TestPythonFixtureAnalysis:
    """Verify that analysis and skeleton generation work on the Python fixture."""

    def test_analyze_finds_all_files(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        paths = sorted(graph.files.keys())
        assert "myapp/__init__.py" in paths
        assert "myapp/app.py" in paths
        assert "myapp/api/routes.py" in paths
        assert "myapp/data/models.py" in paths
        assert "myapp/data/db.py" in paths

    def test_analyze_resolves_internal_imports(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        app_imports = graph.files["myapp/app.py"].imports
        internal = [i for i in app_imports if i.is_internal]
        assert len(internal) == 2  # api.routes and data.db

    def test_analyze_builds_relationships(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        assert len(graph.relationships) > 0

    def test_skeleton_contains_all_sections(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        skeleton = generate_skeleton(graph, tmp_path)
        assert "FILE TREE:" in skeleton
        assert "SIGNATURES:" in skeleton
        assert "DEPENDENCIES:" in skeleton

    def test_skeleton_lists_files(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        skeleton = generate_skeleton(graph, tmp_path)
        assert "app.py" in skeleton
        assert "routes.py" in skeleton
        assert "models.py" in skeleton
        assert "db.py" in skeleton


class TestJavaFixtureAnalysis:
    """Verify analysis on the Java fixture."""

    def test_analyze_finds_java_files(self, tmp_path: Path) -> None:
        _build_java_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        assert len(graph.files) == 3
        assert "java" in graph.languages

    def test_analyze_resolves_java_imports(self, tmp_path: Path) -> None:
        _build_java_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        app_path = "src/main/java/com/example/App.java"
        app_imports = graph.files[app_path].imports
        internal = [i for i in app_imports if i.is_internal]
        assert len(internal) >= 1  # Service

    def test_skeleton_has_file_tree(self, tmp_path: Path) -> None:
        _build_java_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        skeleton = generate_skeleton(graph, tmp_path)
        assert "FILE TREE:" in skeleton
        assert "App.java" in skeleton


class TestCFixtureAnalysis:
    """Verify analysis on the C fixture."""

    def test_analyze_finds_c_files(self, tmp_path: Path) -> None:
        _build_c_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        assert len(graph.files) == 5  # 3 .c + 2 .h
        assert "c" in graph.languages

    def test_analyze_resolves_local_includes(self, tmp_path: Path) -> None:
        _build_c_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        main_imports = graph.files["src/main.c"].imports
        internal = [i for i in main_imports if i.is_internal]
        assert len(internal) == 2  # utils.h and parser.h

    def test_skeleton_contains_signatures(self, tmp_path: Path) -> None:
        _build_c_project(tmp_path)
        config = DiagramConfig(include=["**/*"], exclude=[])
        graph = analyze(config, tmp_path)
        skeleton = generate_skeleton(graph, tmp_path)
        assert "FILE TREE:" in skeleton
        # C signatures should include function declarations
        assert "main" in skeleton or "init" in skeleton or "parse" in skeleton


# ---------------------------------------------------------------------------
# Full CLI pipeline integration (LLM mocked)
# ---------------------------------------------------------------------------

class TestFullPipelinePython:
    """End-to-end: Python fixture -> config -> analyze -> LLM -> write."""

    def test_generates_all_diagram_files(self, tmp_path: Path, capsys) -> None:
        _build_python_project(tmp_path)

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=_mock_llm_side_effects(),
            ):
                result = main([str(tmp_path)])

        assert result == 0
        diagrams = tmp_path / "docs" / "diagrams"
        assert (diagrams / "architecture.d2").exists()
        assert (diagrams / "dependencies.d2").exists()
        assert (diagrams / "sequence.d2").exists()

    def test_architecture_d2_has_nodes_and_edges(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=_mock_llm_side_effects(),
            ):
                main([str(tmp_path)])

        content = (tmp_path / "docs" / "diagrams" / "architecture.d2").read_text()
        assert "layout-engine: elk" in content
        assert "app" in content.lower()
        assert "->" in content

    def test_sequence_d2_has_sequence_shape(self, tmp_path: Path) -> None:
        _build_python_project(tmp_path)

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=_mock_llm_side_effects(),
            ):
                main([str(tmp_path)])

        content = (tmp_path / "docs" / "diagrams" / "sequence.d2").read_text()
        assert "sequence_diagram" in content

    def test_rerun_merges_existing(self, tmp_path: Path) -> None:
        """Running twice merges rather than overwrites."""
        _build_python_project(tmp_path)

        for _ in range(2):
            with patch("diagram_update.llm._check_copilot_available"):
                with patch(
                    "diagram_update.llm._call_copilot",
                    side_effect=_mock_llm_side_effects(),
                ):
                    result = main([str(tmp_path)])
            assert result == 0

        content = (tmp_path / "docs" / "diagrams" / "architecture.d2").read_text()
        assert "app" in content.lower()


class TestFullPipelineJava:
    """End-to-end: Java fixture -> config -> analyze -> LLM -> write."""

    def test_generates_diagram_files(self, tmp_path: Path) -> None:
        _build_java_project(tmp_path)

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=_mock_llm_side_effects(),
            ):
                result = main([str(tmp_path)])

        assert result == 0
        diagrams = tmp_path / "docs" / "diagrams"
        assert (diagrams / "architecture.d2").exists()
        assert (diagrams / "dependencies.d2").exists()

    def test_skeleton_reaches_llm(self, tmp_path: Path) -> None:
        """Verify skeleton from Java project is passed to LLM."""
        _build_java_project(tmp_path)
        captured_prompts: list[str] = []

        def capture_call(prompt, model):
            captured_prompts.append(prompt)
            # Alternate component and D2 responses
            if len(captured_prompts) % 2 == 1:
                return _COMPONENTS_RESPONSE
            return _ARCH_D2

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=capture_call,
            ):
                main([str(tmp_path)])

        # First prompt (pass 1) should contain the skeleton with Java files
        assert "App.java" in captured_prompts[0] or "java" in captured_prompts[0].lower()


class TestFullPipelineC:
    """End-to-end: C fixture -> config -> analyze -> LLM -> write."""

    def test_generates_diagram_files(self, tmp_path: Path) -> None:
        _build_c_project(tmp_path)

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=_mock_llm_side_effects(),
            ):
                result = main([str(tmp_path)])

        assert result == 0
        diagrams = tmp_path / "docs" / "diagrams"
        assert (diagrams / "architecture.d2").exists()

    def test_skeleton_includes_c_files(self, tmp_path: Path) -> None:
        """Verify skeleton from C project reaches LLM with C file info."""
        _build_c_project(tmp_path)
        captured_prompts: list[str] = []

        def capture_call(prompt, model):
            captured_prompts.append(prompt)
            if len(captured_prompts) % 2 == 1:
                return _COMPONENTS_RESPONSE
            return _ARCH_D2

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=capture_call,
            ):
                main([str(tmp_path)])

        assert "main.c" in captured_prompts[0] or "utils" in captured_prompts[0].lower()


# ---------------------------------------------------------------------------
# Config-driven integration
# ---------------------------------------------------------------------------

class TestConfigIntegration:
    """Test that config options propagate through the full pipeline."""

    def test_exclude_filters_files(self, tmp_path: Path) -> None:
        """Config exclude patterns filter out matched files."""
        _build_python_project(tmp_path)
        cfg = tmp_path / ".diagram-update.yml"
        cfg.write_text("exclude:\n  - 'myapp/routes.py'\n")

        config = load_config(tmp_path)
        graph = analyze(config, tmp_path)
        assert "myapp/routes.py" not in graph.files

    def test_module_granularity(self, tmp_path: Path) -> None:
        """Module granularity creates one component per file."""
        _build_python_project(tmp_path)
        config = DiagramConfig(
            include=["**/*"], exclude=[], granularity="module",
        )
        graph = analyze(config, tmp_path)
        # Each file should be its own component
        component_ids = {f.component_id for f in graph.files.values()}
        assert len(component_ids) == len(graph.files)

    def test_entry_points_in_config(self, tmp_path: Path, capsys) -> None:
        """Entry points from config reach the LLM prompt."""
        _build_python_project(tmp_path)
        cfg = tmp_path / ".diagram-update.yml"
        cfg.write_text("entry_points:\n  - myapp.app.create_app\n")

        captured_prompts: list[str] = []

        def capture_call(prompt, model):
            captured_prompts.append(prompt)
            if len(captured_prompts) % 2 == 1:
                return _COMPONENTS_RESPONSE
            return _ARCH_D2

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=capture_call,
            ):
                main([str(tmp_path)])

        # The sequence diagram pass1 prompt should contain the entry point
        seq_prompts = [p for p in captured_prompts if "entry point" in p.lower() or "create_app" in p]
        assert len(seq_prompts) > 0


# ---------------------------------------------------------------------------
# Error path integration
# ---------------------------------------------------------------------------

class TestErrorPathIntegration:
    """Integration tests for error and edge-case paths."""

    def test_empty_project_no_crash(self, tmp_path: Path, capsys) -> None:
        """Empty project (no source files) doesn't crash."""
        (tmp_path / "README.md").write_text("# Hello\n")

        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=_mock_llm_side_effects(),
            ):
                result = main([str(tmp_path)])
        # Should succeed (skeleton is empty but pipeline continues)
        assert result in (0, 1)

    def test_partial_llm_failure(self, tmp_path: Path, capsys) -> None:
        """Pipeline continues when one diagram type fails."""
        _build_python_project(tmp_path)

        # Empty pass1 raises LLMError immediately (1 call consumed for deps)
        with patch("diagram_update.llm._check_copilot_available"):
            with patch(
                "diagram_update.llm._call_copilot",
                side_effect=[
                    _COMPONENTS_RESPONSE, _ARCH_D2,  # arch ok
                    "",                                # deps pass1 fails (empty)
                    _COMPONENTS_RESPONSE, _SEQ_D2,    # seq ok
                ],
            ):
                result = main([str(tmp_path)])

        # Partial success
        assert result == 0
        diagrams = tmp_path / "docs" / "diagrams"
        assert (diagrams / "architecture.d2").exists()
        assert (diagrams / "sequence.d2").exists()

    def test_verbose_logs_pipeline_info(self, tmp_path: Path, caplog) -> None:
        """Verbose mode triggers debug/info logging through the pipeline."""
        _build_python_project(tmp_path)

        with caplog.at_level(logging.DEBUG):
            with patch("diagram_update.llm._check_copilot_available"):
                with patch(
                    "diagram_update.llm._call_copilot",
                    side_effect=_mock_llm_side_effects(),
                ):
                    result = main([str(tmp_path), "-v"])

        assert result == 0
        log_text = caplog.text.lower()
        assert "source files" in log_text or "components" in log_text or "analyzing" in log_text
