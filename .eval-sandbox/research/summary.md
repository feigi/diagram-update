# Research Summary: Correctness & Drift Under Default Configuration

## Pipeline Overview

```
analyze (ast/regex) → skeleton (budget-aware) → LLM (2-pass copilot) → post-process → merge/write
```

## Assessment

| Layer | Correctness | Drift Risk | Notes |
|-------|------------|------------|-------|
| Static analysis | HIGH | LOW | ast.parse + regex fallback; reliable import resolution |
| Skeleton | HIGH | LOW | Faithful representation; budget redistribution handles small/medium projects |
| LLM generation | MODERATE | HIGH | No temperature/seed control; instruction-only stability; no output verification |
| Post-processing | MODERATE | MODERATE | Orphan removal can drop valid containers; D2 parser misses hyphens/nesting |
| Merge/write | HIGH | LOW | Structural diff; 80% removal threshold safety net |

## Key Risk Areas

### 1. LLM Non-Determinism (llm.py:283-293)
The `copilot` CLI invocation has no temperature or seed parameters. Consecutive runs on an unchanged codebase will produce different:
- Node keys and labels
- Component groupings
- Relationship descriptions
- Edge ordering

The existing-diagram update prompt (llm.py:144-190) is well-crafted with strong "keep existing" instructions, but compliance is entirely trust-based with no structural enforcement.

### 2. No Post-Generation Verification
After the LLM produces D2, validation (llm.py:262-280) only checks:
- At least 1 node exists
- At least 1 edge exists

It does NOT verify:
- That skeleton relationships are represented in the output
- That node keys match component IDs from the skeleton
- That no phantom relationships were invented

### 3. Sequence Diagram Instability
With default `entry_points: []`, the LLM is asked to "infer the top 5 most significant entry points" (llm.py:124-126). This is inherently non-deterministic and will produce different flows each run.

### 4. D2 Parser Limitations (merger.py:10-11)
`_NODE_RE = re.compile(r"^(\w[\w.]*)...")` only matches word characters and dots. D2 keys commonly use hyphens (`my-service`), which this regex silently drops. This means:
- The merger won't recognize hyphenated nodes from existing diagrams
- Orphan removal may delete nodes with hyphenated keys

### 5. Orphan Node Removal (merger.py:323-364)
`remove_orphan_nodes` deletes nodes not referenced in edges. This incorrectly removes:
- Container/group nodes that hold child components
- Styling nodes (e.g., `classes`, `vars` blocks)

### 6. Token Budget Truncation (skeleton.py:57)
At default 30K tokens (~120K chars), the skeleton fits small/medium projects. For large projects:
- Architecture: signatures get 40% (48K chars) — adequate
- Dependencies: edges get full priority — good design
- But truncated signatures mean the LLM has less context for naming and grouping

## Scores

- **Correctness under defaults: 6/10** — Static analysis is reliable, but LLM output is unverified against the source data
- **Minimum drift under defaults: 3/10** (where 10 = no drift) — LLM non-determinism is the dominant factor; existing-diagram prompting helps but doesn't guarantee stability

## Recommendations (for context, not implementation)

1. Pin LLM temperature to 0 (if copilot CLI supports it)
2. Add post-generation verification: diff skeleton edges against D2 output edges
3. Require `entry_points` for sequence diagrams or skip them when unspecified
4. Extend D2 parser regex to handle hyphens: `[\w][\w.-]*`
5. Exclude container/parent nodes from orphan removal
6. Consider a structural hash of the skeleton to detect "no actual change" and skip LLM call

## Wave 2: Test Coverage of Failure Modes

### Test Suite Structure
- 13 test files covering all pipeline stages
- Key files: `test_llm.py` (LLM mocking), `test_merger.py` (D2 parser/merger), `test_writer.py` (file output), `test_integration.py` (end-to-end with mocked LLM)

### Coverage by Failure Mode

| # | Failure Mode | Coverage | Evidence |
|---|---|---|---|
| 1 | LLM renaming node keys | ❌ None | `_validate_d2()` checks ≥1 node, never compares against skeleton. Integration tests use generic canned responses that don't match actual skeleton components. |
| 2 | Missing skeleton relationships | ❌ None | No test compares skeleton DEPENDENCIES edges against D2 output. Integration tests only check `"->" in content`. |
| 3 | Orphan removal of valid containers | ⚠️ Partial | `test_keeps_container_with_child_edges` and `test_keeps_container_as_edge_prefix` cover dotted-path containers. No test for non-dotted grouping containers (e.g., `backend { api; db }` where edges use `api -> db`). |
| 4 | D2 parser missing hyphens/nesting | ❌ None | Zero test cases use hyphenated identifiers. `_NODE_RE` regex `\w[\w.]*` excludes hyphens. Nested blocks tested for parsing only, not for indented edges. |
| 5 | Sequence diagram non-determinism | ❌ None | Tests confirm "top 5" appears in prompt and `sequence_diagram` shape appears in output. No multi-run stability test exists. |

### Impact on Scores

The test suite is strong for the static analysis and skeleton generation layers (well-tested with real fixture projects across Python, Java, and C). However, it provides **no safety net** for the 4 most impactful failure modes at the LLM boundary and beyond.

**Revised correctness score: 5/10** (down from 6/10) — regressions in LLM output validation, parser regex, and orphan removal would go completely undetected.

**Drift score unchanged: 3/10 stability** — tests can't prevent drift because the LLM boundary is entirely mocked with static responses, so test passes give no confidence about run-to-run consistency.

### Key Gap: No Skeleton-to-Output Verification Tests
The most impactful missing test category is **skeleton-to-output fidelity**: given a known skeleton with specific component names and relationships, does the generated (or mocked) D2 contain those same components and relationships? This would catch both failure mode 1 (key renaming) and failure mode 2 (missing relationships) and could be implemented even with mocked LLM responses by making the mock responses correspond to the fixture project's actual components.
