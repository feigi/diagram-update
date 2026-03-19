# diagram-update

Auto-generate [D2](https://d2lang.com/) architecture diagrams from source code. Analyzes your codebase's imports and structure, then uses an LLM to produce clean, readable diagrams.

## Features

- **Multi-language support** -- Python, Java, and C/C++
- **Three diagram types** -- architecture overview, dependency graph, and sequence diagrams
- **Stable updates** -- merges new diagrams into existing ones, preserving layout and minimizing churn
- **Token-efficient** -- generates a compact codebase skeleton to keep LLM costs low
- **Configurable** -- control granularity, include/exclude patterns, entry points, and model selection

## Requirements

- Python 3.10+
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli) (`npm install -g @github/copilot` or `curl -fsSL https://gh.io/copilot-install | bash`)

## Quick start

Run directly without installing:

```sh
uvx diagram-update
```

Or point it at a specific project:

```sh
uvx diagram-update /path/to/project
```

### Install locally

```sh
pip install diagram-update
```

Then run:

```sh
diagram-update [project_dir] [-v] [--token-budget N]
```

## What it does

1. **Analyze** -- walks the project tree, parses imports, and resolves internal dependencies
2. **Build skeleton** -- produces a token-efficient summary (file tree, ranked signatures, dependency edges)
3. **Generate diagrams** -- sends the skeleton to an LLM in two passes (identify components, then emit D2 code)
4. **Write & merge** -- outputs `.d2` files to `docs/diagrams/`, merging with any existing diagrams to keep diffs minimal

Output files:

| File | Description |
|---|---|
| `docs/diagrams/architecture.d2` | High-level component overview |
| `docs/diagrams/dependencies.d2` | Package/module import graph |
| `docs/diagrams/flow-*.d2` | Sequence diagrams for key call flows |

## How it works internally

### 1. Static analysis

The analyzer walks the project tree (filtered by include/exclude globs) and detects source files by extension (`.py`, `.java`, `.c`/`.h`). Each file is parsed with a language-specific import parser that extracts import statements into a uniform `ImportInfo` model. Imports are then resolved against the project's own files to distinguish internal from external dependencies.

Files are grouped into **components** based on the configured granularity (`module`, `package`, or `directory`). Import edges between files are aggregated up to the component level, producing a `DependencyGraph` of components and weighted relationships.

### 2. Skeleton generation

A separate skeleton is built **per diagram type**, each tailored to what that diagram needs most. The dependency graph is condensed into a text skeleton that fits within a configurable token budget (default 30 000 tokens, using ~4 chars/token). The budget is split across three sections with **diagram-type-aware ratios**:

| Section | Architecture | Dependencies | Sequence | Content |
|---|---|---|---|---|
| **File tree** | 20% | 15% | 20% | Directory structure with line counts |
| **Signatures** | 40% | 15% | 10% | Function/class signatures ranked by cross-file reference count |
| **Dependencies** | 40% | 70% | 70% | Component edges sorted by weight, e.g. `src/api -> src/db (x5)` |

Dependency and sequence diagrams heavily prioritize edges (70%) since those are the core of what they visualize. For dependency diagrams, edges are **never truncated** -- they get their full content first, with the remainder split between tree and signatures.

Budget is allocated adaptively: if a section uses less than its allocation, the unused chars are redistributed to the remaining sections. Truncation is logged at INFO level when `--verbose` is set.

### 3. Two-pass LLM generation

The skeleton is sent to an LLM (via GitHub Copilot CLI) in two passes:

- **Pass 1 -- Component identification**: The LLM reads the skeleton and outputs a structured list of components (with ids, labels, and types like service/module/database/queue/external) and their relationships with semantic descriptions.
- **Pass 2 -- D2 code generation**: The structured list is converted into valid D2 syntax with containers, shapes, and labeled edges. If an existing diagram is provided, the LLM is asked to preserve its structure and only apply changes.

If pass 2 returns empty output, an automatic retry with an error-correction prompt is attempted.

### 4. Post-processing

Generated D2 goes through two cleanup steps before being written:

- **Edge collapsing**: When the LLM produces multiple edges between the same pair of nodes (e.g. `api -> db: reads` and `api -> db: writes`), they are collapsed into a single edge with a merged label (`api -> db: reads, writes`). For four or more edges sharing a common label prefix, the label is summarized (e.g. `imports (4x)`).
- **Orphan removal**: Nodes with no connecting edges are removed from the diagram.
- **Validation**: The D2 is parsed to verify it contains at least one node and one edge.

### 5. Merge and write

Output files are written to `docs/diagrams/`. When a diagram file already exists, an **anchor-based merge** is applied:

1. Both the old and new D2 are parsed to extract nodes (with block spans) and edges (with labels).
2. Added nodes are inserted before the first edge line; removed nodes (and their blocks) are deleted.
3. Existing edges whose labels changed are updated in-place; new edges are appended at the end.
4. Comments and layout hints in the old file are preserved.

As a safety net, if a merge would remove more than 80% of existing nodes, the result is written to a `.d2.new` sidecar file instead of overwriting.

## Configuration

Create a `.diagram-update.yml` in your project root:

```yaml
# Glob patterns for files to include (default: all)
include:
  - "src/**"

# Glob patterns for files to exclude
exclude:
  - "tests/**"
  - "vendor/**"

# Component grouping: "directory", "package", or "module"
granularity: package

# Entry points for sequence diagrams
entry_points:
  - "src/main.py:main"

# LLM model to use
model: claude-sonnet-4.6

# Token budget for codebase skeleton (default: 30000)
token_budget: 30000
```

All fields are optional -- without a config file, sensible defaults are used:

| Field | Default | Description |
|---|---|---|
| `include` | `["**/*"]` | Glob patterns for files to analyze |
| `exclude` | `["tests/**", "test/**", "vendor/**", "node_modules/**", ".git/**"]` | Glob patterns to skip |
| `granularity` | `"package"` | Component grouping: `directory`, `package`, or `module` |
| `entry_points` | `[]` | Entry points for sequence diagram tracing |
| `model` | `"claude-sonnet-4.6"` | Copilot CLI model to use |
| `token_budget` | `30000` | Token budget for codebase skeleton (also settable via `--token-budget`) |

## Development

```sh
git clone https://github.com/feigi/diagram-update
cd diagram-update
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
