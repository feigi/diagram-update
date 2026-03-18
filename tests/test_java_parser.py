"""Tests for the Java import parser."""

from pathlib import Path

from diagram_update.analyzer.java_parser import extract_package, parse_java_file


def test_standard_import(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text("import com.example.Foo;\n")
    imports = parse_java_file(f)
    assert len(imports) == 1
    assert imports[0].module == "com.example.Foo"
    assert imports[0].names == []
    assert imports[0].level == 0


def test_wildcard_import(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text("import com.example.*;\n")
    imports = parse_java_file(f)
    assert len(imports) == 1
    assert imports[0].module == "com.example"
    assert imports[0].names == ["*"]


def test_static_import(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text("import static org.junit.Assert.assertEquals;\n")
    imports = parse_java_file(f)
    assert len(imports) == 1
    assert imports[0].module == "org.junit.Assert.assertEquals"


def test_multiple_imports(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text(
        "package com.example;\n\n"
        "import java.util.List;\n"
        "import java.util.Map;\n"
        "import com.example.bar.Bar;\n"
    )
    imports = parse_java_file(f)
    assert len(imports) == 3
    assert imports[0].module == "java.util.List"
    assert imports[1].module == "java.util.Map"
    assert imports[2].module == "com.example.bar.Bar"


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "Empty.java"
    f.write_text("")
    assert parse_java_file(f) == []


def test_no_imports(tmp_path: Path) -> None:
    f = tmp_path / "Simple.java"
    f.write_text("public class Simple {\n    int x = 1;\n}\n")
    assert parse_java_file(f) == []


def test_extract_package(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text("package com.example.foo;\n\nimport java.util.List;\n")
    assert extract_package(f) == "com.example.foo"


def test_extract_package_missing(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text("public class Foo {}\n")
    assert extract_package(f) is None


def test_static_wildcard_import(tmp_path: Path) -> None:
    f = tmp_path / "Foo.java"
    f.write_text("import static org.junit.Assert.*;\n")
    imports = parse_java_file(f)
    assert len(imports) == 1
    assert imports[0].module == "org.junit.Assert"
    assert imports[0].names == ["*"]
