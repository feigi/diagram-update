"""Tests for signature extraction."""

from pathlib import Path

from diagram_update.signatures import (
    extract_c_signatures,
    extract_java_signatures,
    extract_python_signatures,
    extract_signatures,
)


class TestPythonSignatures:
    """Tests for Python signature extraction."""

    def test_function_signature(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def process(data: list[str]) -> bool:\n    return True\n")
        sigs = extract_python_signatures(f)
        assert len(sigs) == 1
        assert "def process(" in sigs[0]
        assert "-> bool" in sigs[0]

    def test_class_signature(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("class MyClass(Base):\n    pass\n")
        sigs = extract_python_signatures(f)
        assert any("class MyClass(Base):" in s for s in sigs)

    def test_class_with_methods(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text(
            "class Foo:\n"
            "    def bar(self, x: int) -> str:\n"
            "        return str(x)\n"
            "    def baz(self):\n"
            "        pass\n"
        )
        sigs = extract_python_signatures(f)
        assert any("class Foo:" in s for s in sigs)
        assert any("bar" in s for s in sigs)
        assert any("baz" in s for s in sigs)

    def test_async_function(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("async def fetch(url: str) -> bytes:\n    pass\n")
        sigs = extract_python_signatures(f)
        assert len(sigs) == 1
        assert "async def fetch(" in sigs[0]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("")
        assert extract_python_signatures(f) == []

    def test_no_signatures(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("x = 1\ny = 2\n")
        assert extract_python_signatures(f) == []

    def test_syntax_error_fallback(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def broken(x:\n    pass\ndef good(y):\n    pass\n")
        sigs = extract_python_signatures(f)
        # Regex fallback should catch at least the good one
        assert any("good" in s for s in sigs)

    def test_class_no_bases(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("class Simple:\n    pass\n")
        sigs = extract_python_signatures(f)
        assert any("class Simple:" in s for s in sigs)


class TestJavaSignatures:
    """Tests for Java signature extraction."""

    def test_class_declaration(self, tmp_path):
        f = tmp_path / "Foo.java"
        f.write_text("public class Foo {\n}\n")
        sigs = extract_java_signatures(f)
        assert any("class Foo" in s for s in sigs)

    def test_method_signature(self, tmp_path):
        f = tmp_path / "Foo.java"
        f.write_text(
            "public class Foo {\n"
            "    public String process(int x, String y) {\n"
            "        return y;\n"
            "    }\n"
            "}\n"
        )
        sigs = extract_java_signatures(f)
        assert any("String process(int x, String y)" in s for s in sigs)

    def test_interface(self, tmp_path):
        f = tmp_path / "Service.java"
        f.write_text("public interface Service {\n}\n")
        sigs = extract_java_signatures(f)
        assert any("interface Service" in s for s in sigs)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "Empty.java"
        f.write_text("")
        assert extract_java_signatures(f) == []


class TestCSignatures:
    """Tests for C signature extraction."""

    def test_function_definition(self, tmp_path):
        f = tmp_path / "main.c"
        f.write_text("int main(int argc, char *argv[]) {\n    return 0;\n}\n")
        sigs = extract_c_signatures(f)
        assert any("main" in s for s in sigs)

    def test_function_prototype(self, tmp_path):
        f = tmp_path / "utils.h"
        f.write_text("void process(const char *data);\nint compute(int x, int y);\n")
        sigs = extract_c_signatures(f)
        assert len(sigs) >= 2
        assert any("process" in s for s in sigs)
        assert any("compute" in s for s in sigs)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.c"
        f.write_text("")
        assert extract_c_signatures(f) == []

    def test_skips_control_flow(self, tmp_path):
        f = tmp_path / "main.c"
        f.write_text("int main() {\n    if (x) {\n    }\n    while (y) {\n    }\n}\n")
        sigs = extract_c_signatures(f)
        # Should not include 'if' or 'while' as signatures
        assert not any("if" == s.split("(")[0].split()[-1] for s in sigs)
        assert not any("while" == s.split("(")[0].split()[-1] for s in sigs)


class TestExtractSignatures:
    """Tests for the dispatch function."""

    def test_dispatches_python(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo():\n    pass\n")
        sigs = extract_signatures(f, "python")
        assert len(sigs) == 1

    def test_dispatches_java(self, tmp_path):
        f = tmp_path / "Foo.java"
        f.write_text("public class Foo {\n}\n")
        sigs = extract_signatures(f, "java")
        assert len(sigs) >= 1

    def test_dispatches_c(self, tmp_path):
        f = tmp_path / "main.c"
        f.write_text("int main() {\n    return 0;\n}\n")
        sigs = extract_signatures(f, "c")
        assert len(sigs) >= 1

    def test_unknown_language(self, tmp_path):
        f = tmp_path / "mod.rs"
        f.write_text("fn main() {}\n")
        assert extract_signatures(f, "rust") == []
