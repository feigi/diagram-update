
## Iteration 1 — Primary Review Pass

### Goal
Review diagram-update tool for correctness + drift reduction.

### Top findings
1. **`_matches_any()` broken `**` glob** — patterns like `**/vendor/**` are silently
   ignored; only bare `"**/*"` and `prefix/**` patterns work. This lets excluded
   files pollute the dependency graph → wrong diagram.

2. **`_compute_component_id()` Python package grouping** — always groups by first 2
   directory levels, so `src/diagram_update/analyzer/` merges into `src.diagram_update`.
   Cross-sub-package imports become self-loops and are dropped → diagram loses structure.

3. **`merge_diagrams()` new node insertion** — always inserts before first edge,
   causing large diffs on every add. Should insert at sorted position.

4. **`parse_d2()` single-line block depth bug** — `node { shape: cylinder }` causes
   node_span to extend to next closing brace, swallowing subsequent nodes.

### Plan
Primary pass done. Deep-dive into issues 1 & 2 (analyzer) next.

## Iteration 2 — Deep Analyzer Pass

### Focus: _matches_any + _compute_component_id

**Bug 1 revised:** `_matches_any` has a FALSE POSITIVE (not false negative) for `**`-prefix patterns.
`dir_pattern=''` branch returns True for ALL files when exclude patterns start with `**`.
Default config NOT affected (uses `vendor/**`, not `**/vendor/**`). User configs with gitignore-style
`**/...` exclude patterns will get empty diagrams.

**Bug 2 confirmed:** `_compute_component_id` uses hardcoded `parts[:2]` for Python package grouping.
Sub-packages collapse into parents → self-loops dropped → missing nodes + edges in diagram.
Fix: use `".".join(parts[:-1])` — same as Java path. This is a correctness regression that
affects any project with Python sub-packages (including this project itself).

### Findings documented in .eval-sandbox/review/findings.md
