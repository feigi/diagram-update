"""Tests for the C include parser."""

from pathlib import Path

from diagram_update.analyzer.c_parser import parse_c_file


def test_local_include(tmp_path: Path) -> None:
    f = tmp_path / "main.c"
    f.write_text('#include "utils.h"\n')
    imports = parse_c_file(f)
    assert len(imports) == 1
    assert imports[0].module == "utils.h"
    assert imports[0].names == []


def test_system_include(tmp_path: Path) -> None:
    f = tmp_path / "main.c"
    f.write_text("#include <stdio.h>\n")
    imports = parse_c_file(f)
    assert len(imports) == 1
    assert imports[0].module == "stdio.h"
    assert imports[0].names == ["system"]


def test_path_based_include(tmp_path: Path) -> None:
    f = tmp_path / "main.c"
    f.write_text('#include "utils/helpers.h"\n')
    imports = parse_c_file(f)
    assert len(imports) == 1
    assert imports[0].module == "utils/helpers.h"


def test_mixed_includes(tmp_path: Path) -> None:
    f = tmp_path / "main.c"
    f.write_text(
        '#include <stdio.h>\n'
        '#include <stdlib.h>\n'
        '#include "config.h"\n'
        '#include "utils/helpers.h"\n'
    )
    imports = parse_c_file(f)
    assert len(imports) == 4
    # Local includes
    local = [i for i in imports if "system" not in i.names]
    assert len(local) == 2
    assert local[0].module == "config.h"
    assert local[1].module == "utils/helpers.h"
    # System includes
    system = [i for i in imports if "system" in i.names]
    assert len(system) == 2


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.c"
    f.write_text("")
    assert parse_c_file(f) == []


def test_no_includes(tmp_path: Path) -> None:
    f = tmp_path / "simple.c"
    f.write_text("int main() { return 0; }\n")
    assert parse_c_file(f) == []


def test_include_with_spaces(tmp_path: Path) -> None:
    f = tmp_path / "main.c"
    f.write_text('  #  include  "header.h"\n')
    imports = parse_c_file(f)
    assert len(imports) == 1
    assert imports[0].module == "header.h"


def test_header_file(tmp_path: Path) -> None:
    f = tmp_path / "utils.h"
    f.write_text(
        '#ifndef UTILS_H\n'
        '#define UTILS_H\n'
        '#include "types.h"\n'
        '#endif\n'
    )
    imports = parse_c_file(f)
    assert len(imports) == 1
    assert imports[0].module == "types.h"
