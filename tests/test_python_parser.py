"""Tests for Python import parser."""

from pathlib import Path

from diagram_update.analyzer.python_parser import parse_python_file


def _write_py(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test_module.py"
    p.write_text(content)
    return p


def test_simple_import(tmp_path):
    path = _write_py(tmp_path, "import os\nimport sys\n")
    imports = parse_python_file(path)
    assert len(imports) == 2
    assert imports[0].module == "os"
    assert imports[0].level == 0
    assert imports[1].module == "sys"


def test_from_import(tmp_path):
    path = _write_py(tmp_path, "from os.path import join, exists\n")
    imports = parse_python_file(path)
    assert len(imports) == 1
    assert imports[0].module == "os.path"
    assert imports[0].names == ["join", "exists"]
    assert imports[0].level == 0


def test_relative_import_single_dot(tmp_path):
    path = _write_py(tmp_path, "from . import utils\n")
    imports = parse_python_file(path)
    assert len(imports) == 1
    assert imports[0].module == ""
    assert imports[0].names == ["utils"]
    assert imports[0].level == 1


def test_relative_import_double_dot(tmp_path):
    path = _write_py(tmp_path, "from ..models import User\n")
    imports = parse_python_file(path)
    assert len(imports) == 1
    assert imports[0].module == "models"
    assert imports[0].names == ["User"]
    assert imports[0].level == 2


def test_relative_import_with_module(tmp_path):
    path = _write_py(tmp_path, "from .sub.module import func\n")
    imports = parse_python_file(path)
    assert len(imports) == 1
    assert imports[0].module == "sub.module"
    assert imports[0].names == ["func"]
    assert imports[0].level == 1


def test_multiline_parenthesized_import(tmp_path):
    path = _write_py(
        tmp_path,
        "from os.path import (\n    join,\n    exists,\n    isfile,\n)\n",
    )
    imports = parse_python_file(path)
    assert len(imports) == 1
    assert imports[0].module == "os.path"
    assert set(imports[0].names) == {"join", "exists", "isfile"}


def test_future_import_excluded(tmp_path):
    path = _write_py(
        tmp_path,
        "from __future__ import annotations\nimport os\n",
    )
    imports = parse_python_file(path)
    assert len(imports) == 1
    assert imports[0].module == "os"


def test_syntax_error_falls_back_to_regex(tmp_path):
    path = _write_py(
        tmp_path,
        "import os\nfrom pathlib import Path\ndef broken(:\n    pass\n",
    )
    imports = parse_python_file(path)
    assert len(imports) >= 2
    modules = [i.module for i in imports]
    assert "os" in modules
    assert "pathlib" in modules


def test_syntax_error_regex_excludes_future(tmp_path):
    path = _write_py(
        tmp_path,
        "from __future__ import annotations\nimport os\ndef broken(:\n    pass\n",
    )
    imports = parse_python_file(path)
    modules = [i.module for i in imports]
    assert "__future__" not in modules
    assert "os" in modules


def test_empty_file(tmp_path):
    path = _write_py(tmp_path, "")
    imports = parse_python_file(path)
    assert imports == []


def test_no_imports(tmp_path):
    path = _write_py(tmp_path, "x = 1\nprint(x)\n")
    imports = parse_python_file(path)
    assert imports == []


def test_lineno_captured(tmp_path):
    path = _write_py(tmp_path, "# comment\nimport os\n")
    imports = parse_python_file(path)
    assert imports[0].lineno == 2


def test_multiple_import_types(tmp_path):
    path = _write_py(
        tmp_path,
        "import os\nimport sys\nfrom pathlib import Path\nfrom . import utils\n",
    )
    imports = parse_python_file(path)
    assert len(imports) == 4
