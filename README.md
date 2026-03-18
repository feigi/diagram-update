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
diagram-update [project_dir] [-v]
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
```

All fields are optional -- without a config file, sensible defaults are used.

## Development

```sh
git clone https://github.com/chrisgrieser/diagram-update
cd diagram-update
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
