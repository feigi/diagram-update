# Static Analysis Strategies for Import/Dependency Extraction

Research date: 2026-03-18

This document covers strategies for statically extracting import and dependency
relationships from Python, Java, and C codebases without executing any code.

---

## 1. Python Import Extraction

### 1.1 Import Statement Forms

Python has several import forms that must be handled:

```python
import os                          # simple import
import os.path                     # dotted import
import os as operating_system      # aliased import
from os import path                # from-import
from os.path import join, exists   # from-import multiple names
from os.path import join as j      # from-import with alias
from . import sibling              # relative import (level=1)
from .. import parent              # relative import (level=2)
from ..pkg import module           # relative import with module path
from __future__ import annotations # special future imports
```

### 1.2 Regex-Based Extraction

Regex can handle common cases quickly but has limitations with multiline
statements and comments.

```python
import re

IMPORT_PATTERNS = [
    # "import X" and "import X as Y" (possibly comma-separated)
    re.compile(
        r'^import\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*)',
        re.MULTILINE
    ),
    # "from X import Y" (with optional relative dots)
    re.compile(
        r'^from\s+(\.{0,3}[\w.]*)\s+import\s+(.+)',
        re.MULTILINE
    ),
]

def extract_imports_regex(source: str) -> list[dict]:
    """Extract imports using regex. Fast but not fully reliable."""
    results = []
    for line in source.splitlines():
        line = line.strip()
        # Skip comments and strings
        if line.startswith('#') or line.startswith(('"""', "'''")):
            continue

        # Match: import X, Y, Z
        m = re.match(r'^import\s+(.+)$', line)
        if m:
            for part in m.group(1).split(','):
                part = part.strip()
                name = part.split(' as ')[0].strip()
                results.append({'type': 'import', 'module': name})
            continue

        # Match: from X import Y, Z
        m = re.match(r'^from\s+(\.{0,3}[\w.]*)\s+import\s+(.+)$', line)
        if m:
            module = m.group(1)
            # Count leading dots for relative import level
            level = len(module) - len(module.lstrip('.'))
            module_name = module.lstrip('.')
            names = [n.strip().split(' as ')[0].strip()
                     for n in m.group(2).split(',')]
            results.append({
                'type': 'from_import',
                'module': module_name,
                'names': names,
                'level': level,
            })

    return results
```

**Regex limitations:**
- Cannot handle multiline imports (parenthesized `from x import (a, b, c)`)
- Cannot distinguish imports inside strings, comments, or `if TYPE_CHECKING`
- Cannot handle `# noqa` or conditional imports reliably
- Backslash line continuations need extra handling

### 1.3 AST-Based Extraction (Recommended)

Python's built-in `ast` module is the reliable approach. It parses source code
into an Abstract Syntax Tree without executing it.

**Key AST node types:**
- `ast.Import` -- represents `import X` statements. Has `names` (list of `ast.alias`)
- `ast.ImportFrom` -- represents `from X import Y`. Has `module` (str or None),
  `names` (list of `ast.alias`), and `level` (int, 0=absolute, 1=`.`, 2=`..`, etc.)
- `ast.alias` -- has `name` (str) and `asname` (str or None)

```python
import ast
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ImportInfo:
    module: str          # The module being imported
    names: list[str]     # Specific names imported (empty for plain import)
    level: int           # 0=absolute, 1=relative ., 2=relative .., etc.
    lineno: int          # Line number in source file
    is_from_import: bool # True for "from X import Y" style

class ImportExtractor(ast.NodeVisitor):
    """Extract all imports from a Python source file using AST."""

    def __init__(self):
        self.imports: list[ImportInfo] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[],
                level=0,
                lineno=node.lineno,
                is_from_import=False,
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        names = [alias.name for alias in node.names]
        self.imports.append(ImportInfo(
            module=node.module or '',  # None for "from . import X"
            names=names,
            level=node.level,
            lineno=node.lineno,
            is_from_import=True,
        ))

def extract_imports(source: str, filename: str = '<unknown>') -> list[ImportInfo]:
    """Parse Python source and extract all import statements."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []  # Gracefully handle unparseable files
    extractor = ImportExtractor()
    extractor.visit(tree)
    return extractor.imports

# Alternative: simpler approach using ast.walk (no visitor subclass needed)
def extract_imports_simple(source: str) -> list[dict]:
    """Simpler extraction using ast.walk instead of NodeVisitor."""
    tree = ast.parse(source)
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append({
                    'type': 'import',
                    'module': alias.name,
                    'lineno': node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            results.append({
                'type': 'from_import',
                'module': node.module or '',
                'names': [a.name for a in node.names],
                'level': node.level,
                'lineno': node.lineno,
            })
    return results
```

**AST advantages over regex:**
- Handles multiline imports, comments, string literals correctly
- Provides line numbers for each import
- Correctly parses relative import levels
- Part of Python's standard library (no dependencies)
- Handles all valid Python syntax

**AST limitations:**
- Requires valid Python syntax (cannot parse partial/broken files)
- Does not resolve imports to file paths (that requires additional logic)
- Cannot detect dynamic imports like `importlib.import_module('foo')`

### 1.4 Handling Packages, `__init__.py`, and Namespace Packages

```python
from pathlib import Path

def resolve_import_to_path(
    module_name: str,
    level: int,
    current_file: Path,
    project_root: Path,
) -> Path | None:
    """
    Resolve a Python import to a file path within a project.

    Args:
        module_name: Dotted module name (e.g., 'foo.bar.baz')
        level: Relative import level (0=absolute, 1=., 2=.., etc.)
        current_file: Path to the file containing the import
        project_root: Root directory of the project
    """
    if level > 0:
        # Relative import: resolve from current file's package
        base = current_file.parent
        for _ in range(level - 1):
            base = base.parent
        if module_name:
            parts = module_name.split('.')
            candidate = base / '/'.join(parts)
        else:
            candidate = base
    else:
        # Absolute import: resolve from project root
        parts = module_name.split('.')
        candidate = project_root / '/'.join(parts)

    # Check: is it a package (directory with __init__.py)?
    if candidate.is_dir():
        init = candidate / '__init__.py'
        if init.exists():
            return init
        # Namespace package (PEP 420): directory without __init__.py
        # Still valid in Python 3.3+
        if candidate.exists():
            return candidate

    # Check: is it a module file?
    module_file = candidate.with_suffix('.py')
    if module_file.exists():
        return module_file

    return None  # External dependency or not found
```

**Key considerations for Python packages:**
- Regular packages have `__init__.py` files
- Namespace packages (PEP 420, Python 3.3+) do NOT require `__init__.py`
- `__init__.py` may itself contain imports that re-export names
- The import `from pkg import X` might resolve to `pkg/X.py` OR to a name
  defined in `pkg/__init__.py`
- For diagram purposes, resolving to the package level is usually sufficient

### 1.5 Mapping Imports to Project vs External Dependencies

For architecture diagrams, we typically want to distinguish internal (project)
imports from external (pip-installed) dependencies:

```python
def classify_import(module_name: str, project_root: Path) -> str:
    """Classify an import as 'internal', 'stdlib', or 'external'."""
    top_level = module_name.split('.')[0]

    # Check if it exists as a file/package in the project
    if (project_root / top_level).is_dir() or \
       (project_root / f'{top_level}.py').exists():
        return 'internal'

    # Check stdlib (Python 3.10+ has sys.stdlib_module_names)
    import sys
    if hasattr(sys, 'stdlib_module_names'):
        if top_level in sys.stdlib_module_names:
            return 'stdlib'

    return 'external'
```

---

## 2. Java Import Extraction

### 2.1 Import Statement Forms

```java
import java.util.List;                    // single class import
import java.util.*;                       // wildcard import
import static java.lang.Math.PI;         // static import
import static org.junit.Assert.*;        // static wildcard import
```

Java also has `package` declarations that define where the current file sits:

```java
package com.example.myapp.service;       // package declaration
```

### 2.2 Regex-Based Extraction

Java imports are simpler than Python's -- they are always single-line and have
a consistent format.

```python
import re

# Java import patterns
JAVA_IMPORT = re.compile(
    r'^import\s+(static\s+)?([\w.]+(?:\.\*)?)\s*;',
    re.MULTILINE
)
JAVA_PACKAGE = re.compile(
    r'^package\s+([\w.]+)\s*;',
    re.MULTILINE
)

def extract_java_imports(source: str) -> dict:
    """Extract package declaration and imports from Java source."""
    result = {
        'package': None,
        'imports': [],
    }

    # Extract package declaration
    pkg_match = JAVA_PACKAGE.search(source)
    if pkg_match:
        result['package'] = pkg_match.group(1)

    # Extract imports
    for match in JAVA_IMPORT.finditer(source):
        is_static = bool(match.group(1))
        import_path = match.group(2)
        is_wildcard = import_path.endswith('.*')

        result['imports'].append({
            'path': import_path,
            'is_static': is_static,
            'is_wildcard': is_wildcard,
        })

    return result

# Example usage:
source = """
package com.example.app;

import java.util.List;
import java.util.Map;
import static org.junit.Assert.*;
import com.example.core.Service;

public class MyApp {
    // ...
}
"""
print(extract_java_imports(source))
# {
#   'package': 'com.example.app',
#   'imports': [
#     {'path': 'java.util.List', 'is_static': False, 'is_wildcard': False},
#     {'path': 'java.util.Map', 'is_static': False, 'is_wildcard': False},
#     {'path': 'org.junit.Assert.*', 'is_static': True, 'is_wildcard': True},
#     {'path': 'com.example.core.Service', 'is_static': False, 'is_wildcard': False},
#   ]
# }
```

**Why regex works well for Java imports:**
- Java imports are always single-line (no multiline continuation)
- They always end with a semicolon
- They appear at the top of the file (before class definitions)
- The syntax is highly regular
- No relative imports exist in Java

### 2.3 Mapping Package Names to Directory Paths

Java has a strong convention: package names map directly to directory structure.

```python
from pathlib import Path

def java_import_to_path(
    import_path: str,
    source_roots: list[Path],
) -> Path | None:
    """
    Resolve a Java import to a file path.

    Args:
        import_path: e.g., 'com.example.app.Service'
        source_roots: list of source root directories (e.g., [src/main/java/])
    """
    # Convert dotted path to directory path
    # For 'com.example.app.Service', we want 'com/example/app/Service.java'
    parts = import_path.split('.')
    relative_path = Path('/'.join(parts[:-1])) / f'{parts[-1]}.java'

    for root in source_roots:
        candidate = root / relative_path
        if candidate.exists():
            return candidate

    return None  # External dependency

def java_package_to_dir(package_name: str, source_roots: list[Path]) -> Path | None:
    """Resolve a Java package to its directory."""
    parts = package_name.split('.')
    relative_path = Path('/'.join(parts))
    for root in source_roots:
        candidate = root / relative_path
        if candidate.is_dir():
            return candidate
    return None

def classify_java_import(import_path: str, project_packages: set[str]) -> str:
    """Classify a Java import as internal, JDK, or external."""
    # JDK packages
    if import_path.startswith(('java.', 'javax.', 'jdk.', 'sun.', 'com.sun.')):
        return 'jdk'

    # Check against known project packages
    for pkg in project_packages:
        if import_path.startswith(pkg):
            return 'internal'

    return 'external'
```

**Java source root conventions:**
- Maven: `src/main/java/`, `src/test/java/`
- Gradle: same as Maven by default
- Legacy: `src/` directly
- Multi-module: each module has its own `src/main/java/`

### 2.4 Discovering Project Packages

```python
def discover_java_packages(source_roots: list[Path]) -> set[str]:
    """Scan source roots to find all declared packages."""
    packages = set()
    for root in source_roots:
        for java_file in root.rglob('*.java'):
            with open(java_file) as f:
                content = f.read()
            match = JAVA_PACKAGE.search(content)
            if match:
                packages.add(match.group(1))
    return packages
```

---

## 3. C Include Extraction

### 3.1 Include Statement Forms

```c
#include <stdio.h>          // system/standard library header
#include <sys/types.h>       // system header with path
#include "myheader.h"        // project-local header
#include "utils/helpers.h"   // project-local header with path
```

Key distinction:
- `<header.h>` -- searched in system include paths
- `"header.h"` -- searched first in the current file's directory, then in
  include paths (order is implementation-defined but this is the common behavior)

### 3.2 Regex-Based Extraction

```python
import re

C_INCLUDE = re.compile(
    r'^\s*#\s*include\s+([<"])([^>"]+)[>"]',
    re.MULTILINE
)

def extract_c_includes(source: str) -> list[dict]:
    """Extract #include directives from C/C++ source."""
    results = []
    for match in C_INCLUDE.finditer(source):
        bracket_type = match.group(1)
        header_path = match.group(2)
        results.append({
            'header': header_path,
            'is_system': bracket_type == '<',
            'is_local': bracket_type == '"',
        })
    return results

# Example:
source = """
#include <stdio.h>
#include <stdlib.h>
#include "config.h"
#include "utils/helpers.h"

int main() {
    return 0;
}
"""
print(extract_c_includes(source))
# [
#   {'header': 'stdio.h', 'is_system': True, 'is_local': False},
#   {'header': 'stdlib.h', 'is_system': True, 'is_local': False},
#   {'header': 'config.h', 'is_system': False, 'is_local': True},
#   {'header': 'utils/helpers.h', 'is_system': False, 'is_local': True},
# ]
```

**Edge cases to handle:**
- Conditional includes inside `#ifdef`/`#ifndef` blocks
- Includes in comments (should be ignored)
- Macro-generated includes: `#include SOME_MACRO` (not statically resolvable)
- Include guards / `#pragma once` (relevant for understanding the graph)

### 3.3 Resolving Include Paths

```python
from pathlib import Path

def resolve_c_include(
    header: str,
    is_system: bool,
    current_file: Path,
    include_dirs: list[Path],
    project_root: Path,
) -> Path | None:
    """
    Resolve a C #include to a file path.

    Args:
        header: The header path (e.g., 'utils/helpers.h')
        is_system: True for <header.h>, False for "header.h"
        current_file: The file containing the #include
        include_dirs: List of -I include directories
        project_root: Project root directory
    """
    search_paths = []

    if not is_system:
        # For "header.h", first search relative to the current file
        search_paths.append(current_file.parent)

    # Then search include directories
    search_paths.extend(include_dirs)

    for search_dir in search_paths:
        candidate = search_dir / header
        if candidate.exists():
            return candidate.resolve()

    return None

def build_include_graph(
    source_files: list[Path],
    include_dirs: list[Path],
    project_root: Path,
) -> dict[str, list[str]]:
    """
    Build a dependency graph from C source/header files.

    Returns adjacency list: {file_path: [included_file_paths]}
    """
    graph = {}
    for source_file in source_files:
        content = source_file.read_text(errors='ignore')
        includes = extract_c_includes(content)
        deps = []
        for inc in includes:
            if inc['is_system']:
                continue  # Skip system headers for project graphs
            resolved = resolve_c_include(
                inc['header'], inc['is_system'],
                source_file, include_dirs, project_root,
            )
            if resolved:
                deps.append(str(resolved))
        graph[str(source_file.resolve())] = deps
    return graph
```

### 3.4 Distinguishing System vs Project Includes

For architecture diagrams, we typically only care about project-internal
includes. Strategies for filtering:

1. **Bracket style**: `<...>` is almost always system; `"..."` is almost always
   project-local. This heuristic works well in practice.
2. **Path resolution**: If the resolved path falls inside the project root,
   it is a project include.
3. **Known system headers**: Maintain a list of common system headers
   (`stdio.h`, `stdlib.h`, `string.h`, etc.) to filter out.

### 3.5 Header Dependency Graphs

C projects have a unique challenge: the dependency graph includes both `.c`
(source) and `.h` (header) files. Headers include other headers, creating
transitive dependency chains.

```
main.c --> config.h --> types.h
       --> utils.h  --> types.h (shared dependency)
```

For architecture diagrams, consider:
- Showing only `.c` -> `.c` dependencies (via shared headers)
- Collapsing header/source pairs (e.g., `module.c` + `module.h` = one node)
- Grouping by directory to show component-level dependencies

---

## 4. Directory Structure Analysis

### 4.1 Common Project Layouts

**Python projects:**
```
project/
  src/
    package_name/
      __init__.py
      module_a.py
      subpackage/
        __init__.py
        module_b.py
  tests/
  setup.py / pyproject.toml
```

Or flat layout:
```
project/
  package_name/
    __init__.py
    ...
  tests/
```

**Java projects (Maven/Gradle):**
```
project/
  src/
    main/
      java/
        com/example/app/
          App.java
          service/
            MyService.java
      resources/
    test/
      java/
        com/example/app/
          AppTest.java
  pom.xml / build.gradle
```

Multi-module:
```
project/
  module-core/
    src/main/java/...
    pom.xml
  module-web/
    src/main/java/...
    pom.xml
  pom.xml
```

**C projects:**
```
project/
  src/
    main.c
    module_a.c
    module_b.c
  include/
    module_a.h
    module_b.h
  lib/
    external_lib/
  Makefile / CMakeLists.txt
```

Or flat:
```
project/
  main.c
  utils.c
  utils.h
```

### 4.2 Detecting Project Layout

```python
from pathlib import Path

def detect_project_type(root: Path) -> dict:
    """Detect project type and layout from directory structure."""
    info = {
        'languages': [],
        'layout': 'unknown',
        'source_roots': [],
    }

    # Python indicators
    if any(root.rglob('*.py')):
        info['languages'].append('python')
        if (root / 'src').is_dir() and list((root / 'src').rglob('__init__.py')):
            info['layout'] = 'src-layout'
            info['source_roots'].append(root / 'src')
        elif list(root.glob('*/__init__.py')):
            info['layout'] = 'flat-layout'
            info['source_roots'].append(root)

    # Java indicators
    if any(root.rglob('*.java')):
        info['languages'].append('java')
        # Maven/Gradle
        for src_main in root.rglob('src/main/java'):
            info['source_roots'].append(src_main)
        if not info['source_roots']:
            # Fallback: find directories containing .java files
            for java_file in root.rglob('*.java'):
                src_root = java_file.parent
                if src_root not in info['source_roots']:
                    info['source_roots'].append(src_root)

    # C/C++ indicators
    c_extensions = {'*.c', '*.h', '*.cpp', '*.hpp', '*.cc', '*.hh'}
    if any(f for ext in c_extensions for f in root.rglob(ext)):
        info['languages'].append('c/c++')
        for d in ['src', 'include', 'lib']:
            if (root / d).is_dir():
                info['source_roots'].append(root / d)
        if not info['source_roots']:
            info['source_roots'].append(root)

    return info
```

### 4.3 Inferring Component Boundaries

For architecture diagrams, we need to group files into logical components.
Strategies, ranked by reliability:

1. **Top-level directories under source root** -- the most common boundary.
   In Python: top-level packages. In Java: top-level packages under the
   reverse-domain prefix. In C: top-level `src/` subdirectories.

2. **Build system modules** -- Maven/Gradle modules, CMake subdirectories,
   separate `pyproject.toml` files each define a component.

3. **Import clustering** -- files that import each other heavily likely belong
   to the same component. Files with fewer cross-imports represent component
   boundaries.

4. **Naming conventions** -- directories named `api/`, `service/`, `model/`,
   `controller/`, `util/` often represent architectural layers.

```python
def infer_components(
    file_paths: list[Path],
    source_root: Path,
    max_depth: int = 2,
) -> dict[str, list[Path]]:
    """
    Group files into components based on directory structure.

    Groups by relative path up to max_depth directories deep.
    """
    components: dict[str, list[Path]] = {}
    for path in file_paths:
        try:
            rel = path.relative_to(source_root)
        except ValueError:
            continue
        # Use up to max_depth parts as the component name
        parts = rel.parts[:max_depth]
        if len(parts) > 1:
            component = '/'.join(parts[:-1])  # directory, not filename
        else:
            component = '<root>'
        components.setdefault(component, []).append(path)
    return components
```

---

## 5. Existing Tools and Libraries

### 5.1 Python Ecosystem

| Tool | Approach | Notes |
|------|----------|-------|
| **`ast` (stdlib)** | Parses source to AST | Recommended. Reliable, no dependencies. |
| **[findimports](https://github.com/mgedmin/findimports)** | AST-based static analysis | Extracts imports, finds unused imports, generates dependency graphs. MIT license. Maintainer suggests pydeps for larger projects. |
| **[pydeps](https://github.com/thebjorn/pydeps)** | Bytecode inspection (import opcodes) | Generates module dependency graphs. Requires Graphviz. Has cycle detection (`--show-cycles`). Filters by "hops" distance. |
| **[import-deps](https://pypi.org/project/import-deps/)** | AST-based | Lightweight import dependency finder. |
| **`importlib.util.find_spec()`** | Runtime resolution | Resolves module names to file paths. Useful but requires the environment to have packages installed. |
| **`sys.stdlib_module_names`** | Runtime set (Python 3.10+) | Set of all stdlib module names. Useful for classifying imports. |

### 5.2 Java Ecosystem

| Tool | Approach | Notes |
|------|----------|-------|
| **Regex on source** | Text pattern matching | Works very well for Java due to simple, single-line import syntax. |
| **[jdeps](https://docs.oracle.com/en/java/javase/11/tools/jdeps.html)** | Bytecode analysis (JDK tool) | Analyzes `.class` files for dependencies. Supports `--dot-output` for Graphviz. Requires compiled code. |
| **[Jarviz](https://github.com/ExpediaGroup/jarviz)** | Bytecode analysis | Dependency analysis with visualization. By Expedia Group. |
| **[seguard-java](https://github.com/semantic-graph/seguard-java)** | Static analysis | Extracts approximate dependency graph from Java/Android/JavaScript. |

### 5.3 C/C++ Ecosystem

| Tool | Approach | Notes |
|------|----------|-------|
| **Regex on source** | Text pattern matching | Simple and effective for `#include` extraction. |
| **[cpp-dependency-analyzer](https://github.com/jeremy-rifkin/cpp-dependency-analyzer)** | Parses includes, resolves via compile_commands.json | Builds transitive dependency graph. Outputs adjacency matrices. |
| **[cinclude2dot](https://github.com/Leedehai/C-include-2-dot)** | Include parsing to .dot format | Generates Graphviz-compatible output. |
| **[cppdep](https://github.com/rakhimov/cppdep)** | Static analysis | Rewrite of John Lakos' dep_utils. Generates dependency reports. |
| **[CppDepend](https://www.cppdepend.com/)** | Commercial static analysis | Full dependency visualization and architecture enforcement. |
| **[Doxygen](https://www.doxygen.nl/)** | Documentation + include graphs | Can generate include dependency graphs as a side effect. |

### 5.4 Language-Agnostic / Multi-Language

| Tool | Approach | Notes |
|------|----------|-------|
| **[madge](https://github.com/pahen/madge)** | JS/CSS module analysis | Generates visual dependency graphs. Detects circular deps. Supports CommonJS, AMD, ES6. Good model for our tool's UX. |
| **[Graphviz](https://graphviz.org/)** | Graph rendering | Industry standard for rendering dependency graphs. Many tools output `.dot` format for Graphviz. |
| **[D2](https://d2lang.com/)** | Diagram scripting language | Modern alternative to Graphviz with better default styling. |

---

## 6. Recommended Strategy for Our Tool

### 6.1 Architecture

```
Source Files --> Language-specific Parser --> Normalized Import List
                                                    |
                                                    v
                                          Import Resolver
                                          (maps to file paths)
                                                    |
                                                    v
                                          Component Grouper
                                          (infers boundaries)
                                                    |
                                                    v
                                          Dependency Graph
                                          (adjacency list)
                                                    |
                                                    v
                                          Diagram Renderer
                                          (Mermaid / D2 / DOT)
```

### 6.2 Parser Selection by Language

- **Python**: Use `ast` module. It is reliable, fast, and has zero dependencies.
  Fall back to regex only for files that fail to parse (syntax errors).
- **Java**: Use regex. Java import syntax is regular enough that regex is
  reliable and much simpler than bringing in a Java parser.
- **C/C++**: Use regex for `#include` extraction. Resolve paths using a
  combination of the file's directory and discovered include directories.

### 6.3 Import Resolution Strategy

1. Parse all source files in the project to extract raw imports.
2. Build a map of all known modules/files in the project.
3. Resolve each import against the project map.
4. Classify unresolved imports as external/stdlib.
5. Build the adjacency list of file-to-file or component-to-component deps.

### 6.4 Key Design Decisions

- **File-level vs module-level granularity**: Start with file-level, then
  aggregate to component/package level for the diagram.
- **Internal-only by default**: Filter out stdlib and external dependencies
  unless explicitly requested.
- **Graceful degradation**: If a file cannot be parsed, skip it and log a
  warning rather than failing the entire analysis.
- **No code execution**: Everything must be static analysis. Never import
  or execute project code.

---

## Sources

- [Python ast module documentation](https://docs.python.org/3/library/ast.html)
- [Python import system documentation](https://docs.python.org/3/reference/import.html)
- [Python importlib documentation](https://docs.python.org/3/library/importlib.html)
- [findimports - Static analysis of Python imports](https://github.com/mgedmin/findimports)
- [pydeps - Python Module Dependency graphs](https://github.com/thebjorn/pydeps)
- [jdeps - Java Dependency Analysis Tool](https://docs.oracle.com/en/java/javase/11/tools/jdeps.html)
- [Jarviz - Java dependency analysis](https://github.com/ExpediaGroup/jarviz)
- [seguard-java - Dependency graph extraction](https://github.com/semantic-graph/seguard-java)
- [cpp-dependency-analyzer](https://github.com/jeremy-rifkin/cpp-dependency-analyzer)
- [cinclude2dot - C/C++ include dependency generator](https://github.com/Leedehai/C-include-2-dot)
- [cppdep - C/C++ Dependency Analyzer](https://github.com/rakhimov/cppdep)
- [madge - JS module dependency graph](https://github.com/pahen/madge)
- [Matt Layman - How to use Abstract Syntax Trees](https://www.mattlayman.com/blog/2018/decipher-python-ast/)
- [Using Python AST to resolve dependencies](https://gauravsarma1992.medium.com/using-python-ast-to-resolve-dependencies-c849bd184020)
