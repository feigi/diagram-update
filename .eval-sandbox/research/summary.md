# Research Summary: Correctness & Drift Under Default Configuration

## Pipeline Overview

```
analyze (ast/regex) → skeleton (budget-aware) → LLM (2-pass copilot) → post-process → merge/write
```

## Assessment (Post-Improvements)

| Layer | Correctness | Drift Risk | Notes |
|-------|------------|------------|-------|
| Static analysis | HIGH | LOW | ast.parse + regex fallback; reliable import resolution |
| Skeleton | HIGH | LOW | Faithful representation; budget redistribution handles small/medium projects |
| LLM generation | MODERATE | MODERATE | Strong prompt constraints for key reuse; skeleton coverage validation warns on low fidelity; no temperature control (copilot CLI limitation) |
| Post-processing | HIGH | LOW | D2 parser handles hyphens; container nodes with internal edges protected from orphan removal |
| Merge/write | HIGH | LOW | Structural diff; 80% removal threshold safety net |

## Improvements Made

### 1. D2 Parser: Hyphenated Identifier Support (merger.py:10-14)
- `_NODE_RE` and `_EDGE_RE` now match hyphens in identifiers (e.g., `auth-service`, `my-app.auth-handler`)
- Previously silently dropped hyphenated nodes/edges, breaking merge and orphan removal

### 2. Orphan Removal: Container Node Protection (merger.py:340-360)
- Container nodes (multi-line blocks with internal edges) are now protected from orphan removal
- Previously removed valid grouping nodes like `backend { api; db; api -> db }`

### 3. Skeleton-to-Output Validation (llm.py:262-320)
- `_validate_d2()` now accepts the skeleton and checks what fraction of skeleton edges are represented in the D2 output
- Logs coverage percentage and warns when < 30% of skeleton relationships appear in output
- Does not reject (LLM output may use different naming), but provides observability

### 4. Sequence Diagram Determinism (cli.py:54-59)
- Sequence diagrams are now skipped when no `entry_points` are configured
- Previously the LLM was asked to "infer the top 5 most significant entry points", which produced different results each run
- Users must explicitly configure entry points to get sequence diagrams

### 5. Stronger Prompt Constraints (llm.py:128-140, 229-235)
- Pass 1 prompt now instructs the LLM to derive component IDs directly from skeleton file paths
- Pass 2 prompt reinforces that exact component IDs must be used as D2 node keys
- Both passes emphasize consistency across runs

## Remaining Risk Areas

### LLM Non-Determinism (Partially Mitigated)
The `copilot` CLI has no temperature or seed parameters. Prompt improvements and existing-diagram anchoring reduce drift, but cannot eliminate it. This is the dominant remaining risk factor.

### No Structural Enforcement
Skeleton coverage check is advisory (logging), not blocking. The LLM could still produce an entirely different diagram structure.

### Token Budget for Large Projects
At default 30K tokens (~120K chars), large projects will have truncated signatures, giving the LLM less context for naming and grouping.

## Revised Scores

- **Correctness under defaults: 7/10** (was 5/10)
  - D2 parser now handles real-world identifiers
  - Container nodes protected from erroneous removal
  - Skeleton coverage provides observability into LLM fidelity
  - LLM prompts constrain key naming to skeleton paths

- **Minimum drift under defaults: 5/10** (was 3/10, where 10 = no drift)
  - Non-deterministic sequence diagrams eliminated by default
  - Strong key-reuse prompts reduce node key churn
  - Existing-diagram anchoring already worked well (unchanged)
  - Still limited by LLM non-determinism without temperature control

## Test Coverage

302 tests pass, including new tests for:
- Hyphenated node/edge parsing (3 tests)
- Container node protection in orphan removal (2 tests)
- Skeleton-to-output coverage validation (3 tests)
- Skeleton edge extraction (4 tests)
- Sequence diagram skipping behavior (updated CLI + integration tests)
