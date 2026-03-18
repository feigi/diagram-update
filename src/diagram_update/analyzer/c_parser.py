"""C/C++ include parser using regex-based extraction."""

from __future__ import annotations

import re
from pathlib import Path

from diagram_update.models import ImportInfo

# Match: #include "header.h"  (local include)
_LOCAL_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.MULTILINE)

# Match: #include <stdio.h>  (system include)
_SYSTEM_INCLUDE_RE = re.compile(r"^\s*#\s*include\s+<([^>]+)>", re.MULTILINE)


def parse_c_file(path: Path) -> list[ImportInfo]:
    """Parse a C/C++ file and extract #include statements.

    Returns a list of ImportInfo with:
    - module: the included path (e.g., 'utils/helpers.h' or 'stdio.h')
    - names: ['system'] for system includes (<...>), empty for local ("...")
    - level: 0
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    if not source.strip():
        return []

    imports: list[ImportInfo] = []

    for match in _LOCAL_INCLUDE_RE.finditer(source):
        imports.append(
            ImportInfo(
                module=match.group(1),
                names=[],
                level=0,
                lineno=match.start(),
            )
        )

    for match in _SYSTEM_INCLUDE_RE.finditer(source):
        imports.append(
            ImportInfo(
                module=match.group(1),
                names=["system"],
                level=0,
                lineno=match.start(),
            )
        )

    return imports
