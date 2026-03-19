# Research: Diagram Correctness & Drift Under Default Configuration

## Questions
- [x] Primary: What structural guarantees exist for correctness, and where does drift enter?
- [x] Follow-up: Do tests cover the identified failure modes?

## Findings

### 1. Static Analysis (analyzer/__init__.py) — SOLID
- Uses `ast.parse` with regex fallback for Python — high fidelity
- Regex-based Java/C parsers are simpler but adequate for import extraction
- Import resolution handles relative imports, Java source roots, C relative includes
- Component grouping at `package` granularity groups by first 2 directory levels for Python
- Relationships are aggregated at component level with weight counts

### 2. Skeleton Generator (skeleton.py) — GOOD WITH LIMITS
- Three-section design (tree, signatures, edges) with diagram-type-aware budget splits
- Signatures ranked by cross-file reference count — prioritizes most-imported files
- Budget redistribution from under-used sections to later ones
- **Risk:** At default 30K tokens, large projects will truncate signatures/edges, causing LLM to miss dependencies
- **Risk:** `_CHARS_PER_TOKEN = 4` is a rough approximation; actual token count may differ

### 3. LLM Generation (llm.py) — PRIMARY DRIFT SOURCE
- Two-pass through GitHub Copilot CLI: (1) identify components, (2) generate D2
- **No temperature control** — copilot CLI flags don't include temperature/seed
- **No structural enforcement** — LLM is free to rename nodes, regroup, change labels each run
- Existing diagram passed as "AUTHORITATIVE baseline" with strong textual instructions, but compliance is entirely trust-based
- **Sequence diagrams without entry_points** guess "top 5 most significant flows" — highly non-deterministic
- Validation only checks ≥1 node and ≥1 edge — doesn't verify skeleton relationships are represented
- Retry logic on empty response, but no retry on structurally wrong output

### 4. Post-Processing (merger.py) — MIXED
- `collapse_edges`: merges duplicate (source, direction, target) — correct behavior
- `remove_orphan_nodes`: removes nodes not in any edge — **can remove valid container/group nodes**
- D2 parser regex `_NODE_RE` only matches `\w[\w.]*` — misses hyphenated keys common in D2
- Parser doesn't handle nested containers, indented edges, or semicolons within containers
- `merge_diagrams` does structural diff of old vs new — good for incremental updates
- 80% removal threshold saves to `.d2.new` — safety net against catastrophic rewrites

### 5. Writer (writer.py) — SOLID
- Merges with existing file, applies removal threshold
- Hardcodes ELK layout engine and `direction: right`

### 6. Default Configuration Gaps
- `model: "claude-sonnet-4.6"` — good model but no temperature pinning
- `token_budget: 30000` — adequate for small/medium projects
- `entry_points: []` — sequence diagrams will be non-deterministic
- No post-generation verification pass (identified in project memory as future improvement)

## Summary

**Correctness likelihood under defaults: MODERATE (6/10)**

The static analysis layer is solid — imports are reliably extracted and resolved. The skeleton faithfully represents the codebase within its budget. However, the LLM generation step is the weakest link: no temperature control, no structural enforcement, and no post-generation verification that the output matches the input skeleton's relationships.

**Drift likelihood under defaults: HIGH (8/10)**

The primary drift vector is LLM non-determinism. Without temperature pinning or seed control via copilot CLI, consecutive runs on an unchanged codebase will produce different node keys, groupings, and labels. The existing-diagram pass-through mitigates this somewhat (the update prompt is well-crafted), but compliance is instruction-only. Sequence diagrams without entry_points are especially vulnerable. The D2 parser's regex limitations mean the merger may not correctly identify/preserve all existing structures.

**Highest-value unresolved question:** Do existing tests exercise any of these LLM-facing failure modes (wrong keys, missing relationships, orphan removal of valid nodes)?

## Synthesis (Wave 1 → Wave 2 handoff)

Wave 1 findings are strong and evidence-backed across all 6 pipeline stages. The correctness (6/10) and drift (8/10 instability) scores are well-supported:
- **Solid foundation:** Static analysis and skeleton generation are reliable within budget constraints
- **Primary weakness:** LLM generation has zero structural enforcement — validation only checks presence of nodes/edges, not that they match the skeleton's relationships
- **Secondary weakness:** Post-processing D2 parser has regex gaps (hyphens, nesting) that undermine the merger's ability to preserve existing structures

The critical gap for completing this research is whether the test suite provides any safety net for these failure modes. If tests don't cover LLM output validation, orphan removal edge cases, or parser limitations, the effective correctness guarantee is even lower than 6/10 because regressions would go undetected. Wave 2 will answer this.

## Wave 2: Test Coverage of Failure Modes

### Failure Mode 1: LLM renaming node keys — NOT TESTED
- `test_llm.py` mocks all `_call_copilot` calls with canned responses. No test supplies a skeleton with known node keys and then checks the LLM output preserves those keys.
- `_validate_d2()` (llm.py:262-280) only checks ≥1 node exists, ≥0 edges. It does NOT compare generated node keys against skeleton-provided component names.
- Integration tests (`test_integration.py`) use generic canned LLM responses (e.g. `_ARCH_D2` with `app`, `data`, `logic`) that don't correspond to the actual skeleton components (`myapp`, `myapp.api`, `myapp.data`). No test asserts that generated node keys match skeleton components.

### Failure Mode 2: Missing skeleton relationships in output — NOT TESTED
- `_validate_d2()` warns when there are zero edges but does not raise. It never checks whether specific skeleton relationships appear in the output.
- No test compares the skeleton's DEPENDENCIES section edges against the generated D2 edges.
- Integration tests only check that _some_ edges exist (`"->" in content`), not that specific expected relationships appear.

### Failure Mode 3: Orphan removal of valid containers — PARTIALLY TESTED
- `test_merger.py:TestRemoveOrphanNodes` has 2 positive tests for container preservation:
  - `test_keeps_container_with_child_edges` (line 332): tests `layer.api -> layer.db` preserves `layer`
  - `test_keeps_container_as_edge_prefix` (line 337): tests `infra.cache -> other` preserves `infra`
- **Gap:** No test for a container node that has NO dotted-path children in edges but IS a valid grouping container (e.g., `backend { api; db }` where edges reference `api -> db` without `backend.` prefix). The current `remove_orphan_nodes` would remove `backend` since it doesn't appear in any edge.

### Failure Mode 4: D2 parser missing hyphens/nesting — NOT TESTED
- `_NODE_RE = re.compile(r"^(\w[\w.]*)...")` — `\w` matches `[a-zA-Z0-9_]`, so hyphens are excluded.
- No test in `TestParseD2` uses hyphenated node keys like `my-service` or `api-gateway`.
- Confirmed by grep: zero occurrences of "hyphen", "kebab", "dash", or any hyphenated identifier in the entire test suite.
- Nested containers are tested (line 76: `test_nested_blocks`) but only for parsing — indented edges inside containers are not tested.

### Failure Mode 5: Sequence diagram non-determinism — NOT TESTED (structurally untestable with current approach)
- `test_llm.py:test_sequence_infers_entry_points` (line 82) verifies the prompt says "top 5" when no entry_points are provided — this confirms the NON-DETERMINISTIC path exists but doesn't test for stability.
- `test_integration.py:test_sequence_d2_has_sequence_shape` (line 380) only checks `"sequence_diagram" in content` — confirms shape but not flow stability.
- No test runs the sequence generation twice and compares outputs.
- This is inherently hard to test with mocked LLM — you'd need real multi-run comparison or snapshot testing.

### Summary: Test Safety Net Assessment

| Failure Mode | Test Coverage | Safety Net |
|---|---|---|
| 1. LLM renaming keys | None | ❌ No detection |
| 2. Missing relationships | None | ❌ No detection |
| 3. Orphan removal of containers | Partial (dotted-path only) | ⚠️ Misses non-dotted containers |
| 4. D2 parser hyphens/nesting | None | ❌ No detection |
| 5. Sequence non-determinism | None (untestable with mocks) | ❌ No detection |

**Conclusion:** The test suite provides NO safety net for 4 of 5 failure modes and only partial coverage for the 5th. The effective correctness guarantee should be revised DOWN from 6/10 to **5/10** because regressions in LLM output validation, parser regex, and orphan removal would go completely undetected. The test suite is strong for the static analysis and skeleton layers but stops at the LLM boundary.

## Final Synthesis

**Original question:** How likely is this tool to produce correct diagrams with minimum drift under default configuration?

**Answer (evidence-backed):**

- **Correctness: 5/10** — The pre-LLM pipeline (analysis + skeleton) is solid and faithfully represents the codebase. But the LLM generation layer has zero structural enforcement (validation only checks node/edge existence, not fidelity to the skeleton), and the test suite provides no safety net for LLM-boundary failure modes. Regressions in key renaming, relationship omission, or parser gaps would go undetected.

- **Drift: 8/10 instability** — Primary vector is LLM non-determinism (no temperature/seed control via copilot CLI). The existing-diagram pass-through mitigates this with well-crafted "AUTHORITATIVE baseline" prompts, but compliance is instruction-only. Sequence diagrams without explicit entry_points are especially vulnerable ("top 5 most significant flows" is inherently non-deterministic). The D2 parser's regex limitations (`\w` excludes hyphens) can cause the merger to fail to recognize existing structures, compounding drift.

- **Strongest layers:** Static analysis (ast.parse + regex fallback), skeleton generation (budget-aware, cross-ref ranked), edge collapse, 80% removal threshold safety net.

- **Weakest layers:** LLM validation (presence-only, no skeleton fidelity check), D2 parser (misses hyphens, nested container edges), orphan removal (can drop valid non-dotted containers).

Both research waves complete. No further gaps require investigation.
