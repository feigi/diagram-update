# Code Review: diagram-update

## Files Reviewed
- [x] src/diagram_update/analyzer/__init__.py
- [x] src/diagram_update/merger.py
- [x] src/diagram_update/llm.py
- [x] src/diagram_update/skeleton.py
- [x] src/diagram_update/signatures.py
- [x] src/diagram_update/writer.py
- [x] src/diagram_update/models.py
- [x] src/diagram_update/config.py

## Summary
**REQUEST_CHANGES** — Several concrete correctness bugs and drift-amplifying issues found.

---

## Critical Issues (Must Fix)

### 1. `_matches_any()` — broken `**` glob expansion (correctness)
**File:** `src/diagram_update/analyzer/__init__.py`

The function falls back to a manual `**` handler that only checks `path_str.startswith(dir_pattern + "/")` — it cannot match patterns like `**/test_*.py`, `vendor/**/*.java`, or `**/node_modules/**`. For example, the default exclude `"tests/**"` will only be matched if `path_str` starts with `"tests/"`, so a file at just `"tests"` (top-level) would never match. More importantly, patterns that start with `**` other than `"**/*"` are silently dropped, meaning exclude rules with `**/vendor/**` are ignored and those files pollute the graph.

**Concrete impact on correctness:** Files that should be excluded get analyzed and appear in the diagram.

### 2. `_compute_component_id()` for Python `"package"` granularity — incorrect grouping (correctness)
**File:** `src/diagram_update/analyzer/__init__.py`

For Python files with `granularity="package"`, files are always grouped into "first two directory levels":
- `src/diagram_update/merger.py` → `src.diagram_update`
- `src/diagram_update/analyzer/python_parser.py` → `src.diagram_update` ← WRONG

The sub-package `analyzer/` is grouped into the same component as its parent, making
all cross-analyzer imports appear as self-loops (source == target) and get silently
dropped. The diagram shows fewer nodes and relationships than actually exist.

**Concrete impact on correctness:** Sub-packages are collapsed into parent packages,
losing architectural structure.

### 3. `merge_diagrams()` — new nodes inserted at wrong position (drift)
**File:** `src/diagram_update/merger.py`

New nodes are bulk-inserted at `first_edge_output_idx` (before the first existing edge)
in `sorted(added_nodes)` order. This means adding a single new module appends a block
before all existing edges in the file, creating a large diff even when the change is
minimal. Existing nodes that are alphabetically after the new node are not shifted —
the sorted-insertion guarantee only applies to the new nodes among themselves.

**Concrete impact on drift:** Every new component addition shuffles edge-preceding
content in the output file.

### 4. `parse_d2()` — depth tracking fails on single-line blocks (correctness/drift)
**File:** `src/diagram_update/merger.py`

When a node is declared as a single-line block: `node: Label { shape: cylinder }`,
`_NODE_RE` matches because it ends with `{`, but the block is never closed (depth
never decrements) because the closing `}` is on the same line and the code only
checks lines[i+1:]. This results in `node_spans[key]` running to the next top-level
`}`, which may swallow subsequent nodes. Merge then removes those "inner" nodes when
diffing, causing data loss.

---

## Suggestions (Should Consider)

- **`remove_orphan_nodes()`**: Sequence diagram containers have all edges inside
  them; the top-level container node is never directly referenced in top-level edges.
  The current heuristic (`container_edge_nodes`) only guards against this partially —
  it checks `start < edge_line < end` but `parse_d2()` doesn't record edge line
  indices for edges inside containers (they're consumed during brace-depth scan).
  Sequence diagram containers may be incorrectly pruned.

- **`_check_skeleton_coverage()`**: Coverage is computed using substring matching
  (`source in k or source.split(".")[-1] in k`). A leaf name like `api` matching
  `external-api` falsely boosts coverage and hides a real low-coverage problem.

- **`_call_copilot()` timeout**: 120s is the only guard. No retry on transient failures.

## Positive Notes
- The two-pass LLM approach is smart: separates "what exists" from "how to render", enabling the update prompt to preserve IDs.
- `check_removal_threshold()` is a good safety net against catastrophic LLM drift.
- `collapse_edges()` is a solid post-processing step to reduce visual noise.
- Adaptive budget reallocation in `skeleton.py` is well-designed.

---

## Deep Analysis: Analyzer Correctness (glob + component grouping)

### Finding 1 (Revised): `_matches_any()` — false-positive for `**`-prefix patterns

**Actual behavior differs from primary review findings.**

The bug is a **false positive**, not a miss. When any pattern starts with `**` (e.g., `**/vendor/**`), the fallback branch computes `dir_pattern = ""` and immediately returns `True` — matching **every file**.

Concrete evidence:
```python
_matches_any('src/foo.py', ['**/vendor/**'])  # returns True  ← BUG
_matches_any('src/bar.py', ['**/node_modules/**'])  # returns True  ← BUG
```

**Impact on DEFAULT config:** Low. Default exclude patterns are `tests/**`, `vendor/**` etc. (no leading `**`), so defaults work correctly. `"**/*"` in the include list also accidentally returns `True` via this branch, which happens to be correct.

**Impact on user-provided config:** High. Any gitignore-style pattern like `**/vendor/**`, `**/dist/**`, `**/generated/**` in a user's `.diagram-update.yml` exclude list causes ALL files to be excluded → empty diagram, no error message.

**Root cause:** `dir_pattern = pattern.split("**")[0].rstrip("/")` yields `""` for leading-`**` patterns, then `if not dir_pattern: return True` treats them as match-everything.

**Fix:** For patterns starting with `**/`, strip the prefix and recursively check the path against the suffix pattern at each path segment:
```python
if pattern.startswith('**/'):
    suffix = pattern[3:]
    if fnmatch.fnmatch(path_str, suffix):
        return True
    parts = path_str.split('/')
    for i in range(1, len(parts)):
        if fnmatch.fnmatch('/'.join(parts[i:]), suffix):
            return True
```

---

### Finding 2 (Confirmed): `_compute_component_id()` — sub-packages collapse into parent

**Confirmed by tracing the code path.** For Python files, the code uses `".".join(parts[:2])` (first two path components), hardcoded regardless of depth:

```
src/diagram_update/merger.py          → parts[:2] = ['src','diagram_update'] → src.diagram_update
src/diagram_update/analyzer/parser.py → parts[:2] = ['src','diagram_update'] → src.diagram_update  ← WRONG
```

All files in `src/diagram_update/analyzer/` get component id `src.diagram_update`, identical to parent package files. Cross-package imports (e.g., `merger.py → analyzer`) appear as self-loops and are silently dropped by `_build_relationships()` (`if source_comp != target_comp`).

**Verified: self-loops are silently discarded:**
```python
# _build_relationships:
if source_comp != target_comp:
    edge_counts[(source_comp, target_comp)] += 1
```
No warning is emitted.

**Root cause:** Hard-coded `parts[:2]` instead of using the file's actual directory.

**Fix:** Use `".".join(parts[:-1])` (all directory levels, excluding filename) — consistent with how Java packages already work in the same function.

**This fix changes diagram output** — sub-packages that were previously collapsed will appear as distinct nodes. Existing diagrams will drift on next regeneration, but they will then accurately reflect the architecture.

---

### Summary

| Bug | Severity | Affects defaults? | Diagram impact |
|-----|----------|-------------------|----------------|
| `_matches_any` false positive | Medium | No (only `**`-prefix patterns) | Empty diagram if user excludes with `**/...` patterns |
| `_compute_component_id` over-collapse | High | Yes (any project with sub-packages) | Missing nodes, missing edges, architecture misrepresented |

