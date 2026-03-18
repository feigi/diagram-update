# diagram-update: Implementation Plan

**Date:** 2026-03-18

---

## Progress Checklist

- [ ] Step 1: Project scaffolding and data models
- [ ] Step 2: Config loader
- [ ] Step 3: Python import parser
- [ ] Step 4: Import resolver and component grouper
- [ ] Step 5: Minimal end-to-end pipeline with skeleton generator and LLM client
- [ ] Step 6: D2 output writer and CLI entry point
- [ ] Step 7: Diagram merger (anchor-based)
- [ ] Step 8: Java and C parsers
- [ ] Step 9: Skeleton quality improvements (signatures, token budget)
- [ ] Step 10: LLM prompt refinement and multi-diagram support
- [ ] Step 11: Error handling hardening and validation

---

## Step 1: Project Scaffolding and Data Models

**Objective:** Set up the Python project structure with packaging, test infrastructure, and core data models so that all subsequent steps have a foundation to build on.

**Implementation guidance:**
- Create `pyproject.toml` with project metadata, dependencies (`pyyaml`), and dev dependencies (`pytest`)
- Create the package directory structure: `src/diagram_update/` with `__init__.py`
- Create submodules: `models.py`, `config.py`, `analyzer/`, `skeleton.py`, `llm.py`, `merger.py`, `writer.py`, `cli.py`
- Implement all data models from the design in `models.py`: `DiagramConfig`, `DependencyGraph`, `Component`, `Relationship`, `FileInfo`, `ImportInfo`
- Create `tests/` directory with `conftest.py`

**Test requirements:**
- Unit tests for data model instantiation with defaults
- Verify `DependencyGraph` can hold components and relationships
- Verify `Component` supports sub-components

**Integration with previous work:** N/A -- this is the foundation.

**Demo:** `pytest` runs and passes. The package is importable (`from diagram_update.models import DependencyGraph`). `pip install -e .` works.

---

## Step 2: Config Loader

**Objective:** Load and validate `.diagram-update.yml`, returning a typed `DiagramConfig` with defaults applied.

**Implementation guidance:**
- Implement `load_config(project_root: Path) -> DiagramConfig` in `config.py`
- Parse YAML with `pyyaml`, validate field types and values
- Apply defaults when fields are missing (see design for default values)
- Return default config when no file exists
- Raise `ConfigError` for malformed files

**Test requirements:**
- Valid config with all fields specified
- Minimal config (only one field, rest use defaults)
- Missing config file returns defaults
- Invalid YAML syntax raises `ConfigError`
- Invalid `granularity` value raises `ConfigError`
- Unknown keys produce a warning but do not error

**Integration with previous work:** Uses `DiagramConfig` from Step 1.

**Demo:** Create a sample `.diagram-update.yml`, run a test script that loads it, and print the resolved config showing defaults filled in.

---

## Step 3: Python Import Parser

**Objective:** Parse Python source files to extract import statements using `ast`, with regex fallback for files with syntax errors.

**Implementation guidance:**
- Create `src/diagram_update/analyzer/__init__.py` and `src/diagram_update/analyzer/python_parser.py`
- Implement an `ast.NodeVisitor` subclass that extracts `ast.Import` and `ast.ImportFrom` nodes
- Return a list of `ImportInfo` records per file
- Handle relative imports (record the `level` field)
- Implement regex fallback for `SyntaxError` cases
- Ignore `from __future__` imports

**Test requirements:**
- Simple `import X` statements
- `from X import Y` statements
- Relative imports (`.`, `..`) with correct level
- Multiline parenthesized imports
- `from __future__` imports are excluded
- Files with syntax errors fall back to regex and still extract imports
- Empty files return empty list

**Integration with previous work:** Returns `ImportInfo` instances from Step 1.

**Demo:** Point the parser at a real Python file (e.g., one from this project's own source) and print the extracted imports.

---

## Step 4: Import Resolver and Component Grouper

**Objective:** Resolve raw import strings to internal file paths and group files into components, producing a complete `DependencyGraph`.

**Implementation guidance:**
- Implement `analyze(config: DiagramConfig, project_root: Path) -> DependencyGraph` in `analyzer/__init__.py`
- File walker: traverse `project_root`, apply include/exclude glob filters from config, detect language by extension
- Import resolver for Python: convert dotted paths to file paths, handle `module.py` vs `module/__init__.py`, classify unresolved imports as external
- Component grouper: group files by `granularity` setting (`directory`, `package`, `module`)
- Build `DependencyGraph` with `Component` nodes and `Relationship` edges (aggregated from file-level imports)

**Test requirements:**
- File walker respects include/exclude patterns
- Python relative imports resolve correctly from various directory depths
- External vs internal import classification (stdlib and third-party are external)
- `"directory"` granularity groups files by top-level directory
- `"package"` granularity groups by Python package
- `"module"` granularity creates one component per file
- Relationships aggregate file-level imports to component-level edges with correct weights

**Integration with previous work:** Uses config from Step 2, Python parser from Step 3, data models from Step 1.

**Demo:** Run the analyzer on a small sample Python project (create a fixture with 5-10 files). Print the resulting component list and dependency edges.

---

## Step 5: Minimal End-to-End Pipeline with Skeleton Generator and LLM Client

**Objective:** Get the first working end-to-end pipeline: analyze a project, generate a skeleton, call the LLM, and get back D2 code. This is the critical integration milestone.

**Implementation guidance:**
- Implement `generate_skeleton()` in `skeleton.py`: produce a simplified skeleton with annotated file tree and dependency edges (defer signature ranking to Step 9)
- Implement `generate_diagram()` in `llm.py`: invoke `gh copilot -p "..." -s --model claude-opus-4-6 --no-ask-user` via `subprocess.run`
- Start with a single-pass LLM call (combined component identification and D2 generation) to get something working quickly; refine to two-pass in Step 10
- Implement basic response parsing: strip whitespace, remove markdown fences
- Check for `gh` binary availability before calling
- Wire the pipeline together: config -> analyze -> skeleton -> LLM -> raw D2 output to stdout

**Test requirements:**
- Skeleton generator produces output containing file tree and dependency edges sections
- Skeleton generator respects token budget (approximate check via word count)
- LLM client correctly constructs the subprocess command
- LLM response parser strips markdown fences
- LLM response parser detects empty responses
- Unit tests for the LLM client should mock `subprocess.run` to avoid real API calls

**Integration with previous work:** Consumes `DependencyGraph` from Step 4, uses config from Step 2.

**Demo:** Run the tool on a sample Python project and see D2 diagram code printed to the terminal. This is the first time the full analysis-to-diagram path works end-to-end.

---

## Step 6: D2 Output Writer and CLI Entry Point

**Objective:** Write generated D2 to files and provide a CLI command so the tool is usable as a real command-line application.

**Implementation guidance:**
- Implement `write_diagram()` in `writer.py`: create `docs/diagrams/` directory, write D2 with the `vars.d2-config` header (ELK layout engine, `direction: right`)
- File naming: `architecture.d2`, `dependencies.d2`, `flow-{name}.d2`
- Implement CLI entry point in `cli.py` using `argparse`
- Wire the full pipeline in CLI: load config -> analyze -> skeleton -> LLM -> write files
- Add the CLI entry point to `pyproject.toml` (`[project.scripts]`)
- For now, generate only the architecture diagram type

**Test requirements:**
- Writer creates `docs/diagrams/` if it doesn't exist
- Writer produces files with correct names
- Written files contain the D2 config header
- CLI runs without errors when given a project directory
- CLI handles missing `gh` binary gracefully with a clear error message

**Integration with previous work:** Connects the LLM output from Step 5 to file output. Wraps the entire pipeline from Steps 2-5 in a CLI.

**Demo:** Run `diagram-update` (or `python -m diagram_update`) on a sample project. The tool creates `docs/diagrams/architecture.d2` with a valid D2 diagram generated by the LLM.

---

## Step 7: Diagram Merger (Anchor-Based)

**Objective:** Implement anchor-based merging so that re-running the tool on an unchanged project preserves existing diagrams, and changes produce minimal diffs.

**Implementation guidance:**
- Implement D2 file parsing in `merger.py`: extract node keys and edge tuples using line-based regex (node pattern, edge pattern, brace depth tracking)
- Implement `merge_diagrams(old_d2, new_d2) -> str`: compute added/removed/kept node and edge sets, build merged output preserving existing ordering
- Handle edge label updates in-place
- Implement the 80% removal protection (write to `.d2.new` instead of overwriting)
- Wire the merger into the pipeline: before writing, read existing D2 file if present and merge

**Test requirements:**
- Parsing extracts correct node keys from D2 content
- Parsing extracts correct edge tuples from D2 content
- Merging into empty old content returns new content unchanged
- Adding new nodes to an existing diagram
- Removing deleted nodes
- Updating edge labels in-place
- Preserving ordering of unchanged nodes
- Preserving comments and layout hints
- Idempotent: merging identical old and new produces old unchanged
- 80% removal threshold triggers `.d2.new` output

**Integration with previous work:** Sits between LLM output (Step 5) and file writing (Step 6) in the pipeline.

**Demo:** Run the tool twice on the same project. Show that the second run produces identical output (no diff). Then add a file to the sample project, re-run, and show that only the new component appears in the diff.

---

## Step 8: Java and C Parsers

**Objective:** Add Java and C language support so the tool works on multi-language codebases.

**Implementation guidance:**
- Implement `analyzer/java_parser.py`: regex-based import extraction, package declaration parsing
- Implement `analyzer/c_parser.py`: regex-based `#include` extraction, distinguish system vs local includes
- Add Java import resolution: dotted package paths to file paths, `src/main/java/` source root detection
- Add C import resolution: resolve `"header.h"` relative to including file, then include directories; collapse `.c`/`.h` pairs
- Register parsers in the analyzer based on detected file extensions
- Add language detection to the file walker

**Test requirements:**
- Java parser extracts standard imports, wildcard imports, static imports
- Java parser extracts package declarations
- C parser extracts local includes (`"..."`) and identifies system includes (`<...>`)
- C parser handles path-based includes (`"utils/helpers.h"`)
- Java import resolution maps `com.example.Foo` to `com/example/Foo.java`
- C header resolution finds headers relative to the including file
- C `.c`/`.h` pairs are collapsed into single components
- Analyzer correctly handles mixed-language projects

**Integration with previous work:** Extends the analyzer from Step 4 with new parsers. The rest of the pipeline (skeleton, LLM, merger, writer) works unchanged.

**Demo:** Run the tool on a sample Java project and a sample C project. Show that it produces architecture diagrams for each.

---

## Step 9: Skeleton Quality Improvements

**Objective:** Improve the skeleton generator to produce higher-quality LLM input with ranked signatures and proper token budget management.

**Implementation guidance:**
- Add signature extraction: use `ast` for Python (class/function signatures without bodies), regex for Java (class and method declarations), regex for C (function prototypes from headers)
- Rank signatures by cross-file reference count (most-imported symbols first)
- Implement three-section skeleton format: annotated file tree (~20% budget), ranked signatures (~50% budget), dependency edges (~30% budget)
- Implement token budget enforcement: truncate signatures and low-connectivity components to fit
- Use a simple token estimation (word count * 1.3) rather than a tokenizer dependency

**Test requirements:**
- Python signature extraction captures class and function signatures
- Signatures are ranked by reference count (most-referenced first)
- Skeleton contains all three sections (file tree, signatures, edges)
- Token budget is enforced: output does not exceed budget
- Large projects truncate gracefully (low-connectivity components elided)
- Empty project produces a minimal valid skeleton

**Integration with previous work:** Replaces the simplified skeleton from Step 5. All downstream components (LLM, merger, writer) work unchanged.

**Demo:** Run the tool on a medium-sized project. Compare the skeleton output before and after this step to show richer information within the token budget.

---

## Step 10: LLM Prompt Refinement and Multi-Diagram Support

**Objective:** Implement the two-pass LLM approach and generate all three diagram types (architecture, dependencies, sequence/flow).

**Implementation guidance:**
- Refactor `llm.py` to implement the two-pass approach from the design: Pass 1 identifies components/relationships as structured text, Pass 2 converts to D2
- Add diagram-type-specific prompts: architecture (high-level services/modules), dependencies (package-level import graph), sequence (call flows)
- For sequence diagrams: have the LLM infer top-5 entry points unless overridden by config `entry_points`
- Add retry logic: on empty or non-D2 response, retry once with an error correction prompt
- Update the CLI to generate all three diagram types in a single run

**Test requirements:**
- Two-pass approach produces valid D2 (mock LLM responses for both passes)
- Each diagram type generates with appropriate structure (architecture has containers, dependencies has edges, sequence uses `shape: sequence_diagram`)
- Retry logic triggers on empty response and tries again
- Markdown fence stripping works for various fence formats
- Entry points from config are passed to the sequence diagram prompt

**Integration with previous work:** Refines the LLM client from Step 5. The CLI from Step 6 now generates multiple files. The merger from Step 7 handles each file independently.

**Demo:** Run the tool on a sample project and get three output files: `architecture.d2`, `dependencies.d2`, and `flow-{name}.d2`. Open them to verify each shows a different view of the codebase.

---

## Step 11: Error Handling Hardening and Validation

**Objective:** Harden all error paths and validate the tool against real-world repositories.

**Implementation guidance:**
- Add `gh copilot` availability check: verify `gh` binary exists, copilot extension is installed, authentication works
- Add subprocess timeout (60 seconds) and stderr capture
- Detect authentication errors in stderr and provide actionable messages
- Validate generated D2 has at least one node and one edge
- Add logging throughout the pipeline (use Python `logging` module)
- Create sample project fixtures for integration tests (small Python, Java, C projects)
- Run the tool against 2-3 public repositories as validation

**Test requirements:**
- Missing `gh` binary produces clear error message
- Missing copilot extension produces clear error message
- Subprocess timeout raises `LLMError` with descriptive message
- Authentication error detection works
- D2 validation catches node-only output (no edges)
- Integration test: full pipeline on a small Python fixture project
- Integration test: full pipeline on a small Java fixture project
- Integration test: full pipeline on a small C fixture project

**Integration with previous work:** Adds error handling across all components from Steps 1-10. Integration tests exercise the full pipeline.

**Demo:** Demonstrate error messages for common failure modes (no `gh` binary, timeout). Run the tool on a cloned public repository and show the generated diagrams.
