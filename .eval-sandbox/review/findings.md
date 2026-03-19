# Code Review: diagram-update (correctness + drift-reduction)

## Files Reviewed
- [x] src/diagram_update/llm.py
- [x] src/diagram_update/merger.py
- [x] src/diagram_update/skeleton.py
- [x] src/diagram_update/writer.py
- [x] src/diagram_update/models.py

## Summary
REQUEST_CHANGES — Two correctness bugs found; one high-risk drift issue

## Critical Issues (Must Fix)

### 1. Merge silently breaks container-child node insertion (correctness + drift)
`merger.py` `merge_diagrams()` — when a new child node is added to an existing 
container, `new.node_spans` contains the child's line index within the *new* D2 
(which has the container wrapper). But only the child's line(s) at that span are 
inserted into the output, **at the top level** (before the first edge), not inside 
the container block. This produces invalid/incorrect D2 for any diagram that uses 
containers (which is the default for architecture diagrams).

Example: old diagram has `api: API { handler }`. New run adds `router`. The merge 
inserts `router: Router` as a top-level node instead of inside the `api { }` block.

Risk: **HIGH** — architecture diagrams always group nodes into containers.

### 2. `_parse_response` fails silently when text follows closing fence (correctness)
`llm.py` `_parse_response()` — when LLM output has prose after the closing ```,
the `_FENCE_RE` regex doesn't match (requires `$` at end), and the fallback only
removes the last line if it's *exactly* ```. Non-empty text after ``` means the
fence line stays in the output, injecting ``` into the generated D2.

## Suggestions (Should Consider)
- `_check_skeleton_coverage` only logs a WARNING at <30% coverage; generation 
  continues producing a likely-incorrect diagram. Consider rejecting and retrying.
- `_build_pass1_update_prompt` instructs LLM to keep existing IDs but the 
  instruction is in natural language — there's no mechanical enforcement. A 
  structural comparison of old vs new component IDs after pass 1 could catch drift 
  early and trigger a re-prompt.
- Edge insertion order in merge: new edges are appended at the end, while new nodes 
  are inserted before the first edge. For large diagrams this creates an inconsistent 
  file structure that accumulates over multiple runs.

## Positive Notes
- Two-pass LLM approach (identify then render) cleanly separates concerns
- Adaptive budget redistribution in `skeleton.py` is well-thought-out
- The 80% removal threshold sidecar file safety net is a good guard
- `collapse_edges` deduplication is correct and handles direction variants

---

## Deep Analysis: merge_diagrams() Container-Child Insertion Bug (Step 2)

### Confirmed Bug: Container Block Content Is Always Preserved Verbatim

**Root cause:** `parse_d2()` records container blocks as ATOMIC units. The entire `api { ... }` span is tracked under key `api`, but the CONTENT of the block is opaque — inner lines (children) are never added to `node_keys`. `merge_diagrams()` only tracks adds/removals at the container-key level, never within the block body.

**Consequence (confirmed with live tests):**

| Scenario | Expected | Actual |
|----------|----------|--------|
| Add child to existing container block (`api { handler\n router }`) | `router` appears in merged output | **SILENTLY DROPPED** |
| Remove child from existing container block | `router` removed from merged output | **OLD BLOCK PRESERVED, router stays** |
| Update label inside existing container (`label: New Label`) | New label applied | **Old label preserved** |
| New edge references container-internal child (`services.worker -> db`) | worker node also added | **Edge added, node MISSING from block — corrupt diagram** |

### Code Path

```python
# merger.py merge_diagrams():
added_nodes = new.node_keys - old.node_keys   # 'api' in both → not in added_nodes
removed_nodes = old.node_keys - new.node_keys  # 'api' in both → not in removed_nodes

# 'api' is neither added nor removed → old block lines copied verbatim
# Inner block changes (new/removed children) are invisible
```

### Adversarial Evidence

```python
old = 'api: API {\n  handler\n}\napi -> db'
new = 'api: API {\n  handler\n  router\n}\napi -> db'
result = merge_diagrams(old, new)
assert 'router' in result  # FAILS — router silently dropped
# result == 'api: API {\n  handler\n}\napi -> db'  (unchanged from old)
```

```python
# Even worse: orphaned edge without its node
old3 = 'services: Services {\n  api: API\n}\nservices.api -> db'
new3 = 'services: Services {\n  api: API\n  worker: Worker\n}\nservices.api -> db\nservices.worker -> db'
result3 = merge_diagrams(old3, new3)
assert 'worker' in result3  # FAILS for the block; only edge is added
# worker node is missing from container, but services.worker -> db edge IS added
# → corrupt diagram: edge references non-existent node
```

### Scope of Impact

Architecture diagrams always use container blocks. Every merge of an updated diagram that adds or removes children from an existing container will silently corrupt the output. This is not an edge case — it is the primary use pattern.

### Correct Fix (not implemented here)

For each container key present in BOTH old and new:
1. Compare `old.node_spans[key]` content vs `new.node_spans[key]` content
2. If different, replace old block lines with new block lines in the output

Simple replacement (replace old block with new block when content differs) is safe, correct, and preserves the ordering benefit of the merge algorithm for unchanged containers. A recursive merge of block interiors would be more nuanced but is not required for correctness.

### Secondary Bug (confirmed): Dotted-key child insertion at wrong position

When new D2 uses dotted-key notation for a new child (`api.router: Router`), the node IS detected as new and IS inserted, but placed at top level before the first edge rather than adjacent to its parent container. D2 renders it correctly (dotted keys work anywhere), but repeated merges create an inconsistent, accumulating top-level list of dotted children separate from their containers.
