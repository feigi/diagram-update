# Research Summary: Correctness & Drift Under Default Configuration

## Pipeline Overview

```
analyze (ast/regex) → skeleton (budget-aware) → LLM (2-pass copilot) → post-process → merge/write
```

## Current Scores (post prior improvements)

- **Correctness: 7/10** (was 5/10 before prior improvements)
- **Drift Reduction: 5/10** (was 3/10 before prior improvements, where 10 = no drift)

## Prior Improvements (already committed)

1. D2 parser: hyphenated identifier support (merger.py:10-14)
2. Orphan removal: container node protection (merger.py:340-360)
3. Skeleton-to-output coverage validation warning at <30% (llm.py:262-320)
4. Sequence diagram skipping when no entry_points configured (cli.py:54-59)
5. Stronger prompt constraints: derive IDs from skeleton paths (llm.py:128-140)

## Remaining Gap Analysis

### Gap D1: Existing node keys not explicitly injected (HIGHEST IMPACT for drift)

**Evidence:** `llm.py:_build_pass1_update_prompt()` shows the full existing D2 block but only
instructs "Keep ALL existing component IDs...UNCHANGED". The LLM still has to parse the block
itself to discover which keys to reuse.

**Problem:** When the LLM sees a large D2 block, it tends to paraphrase/reorganize rather than
copy verbatim. Even with "keep UNCHANGED" instructions, key drift occurs between runs.

**Fix:** Call `parse_d2(existing_d2)` to extract node keys and inject them as an explicit list:
```
CANONICAL NODE KEYS (reuse VERBATIM): key1, key2, key3, ...
```
This converts a fuzzy instruction into a hard, unambiguous constraint that's trivially easy to follow.

### Gap D2: Skeleton component IDs not seeded into fresh-diagram pass 1 (HIGH IMPACT for drift)

**Evidence:** `llm.py:_build_pass1_prompt()` tells the LLM to "derive IDs from skeleton paths" but
doesn't provide a deterministic seed list. The skeleton DEPENDENCIES section contains exactly the
right component IDs already (`src/api -> src/db` → IDs are `src/api`, `src/db`).

**Fix:** Extract component names from DEPENDENCIES section of skeleton and inject as:
```
REQUIRED COMPONENT KEYS (derived from your codebase): key1, key2, ...
Use these keys verbatim as component IDs.
```
This eliminates LLM creativity in ID naming for initial generation too.

### Gap C1: Low skeleton coverage triggers no retry (MEDIUM IMPACT for correctness)

**Evidence:** `llm.py:_check_skeleton_coverage()` (lines ~280-320) logs a warning when coverage
< 30% but takes no corrective action. If the LLM produces a diagram that only covers 10-15% of
skeleton relationships, the tool silently accepts it.

**Fix:** In `generate_diagram()`, after `_validate_d2()`, if skeleton coverage < 20%, perform
a single retry with an error-correction prompt that explicitly lists the missed skeleton edges.
This adds a correctness enforcement layer.

### Gap D3: Pass 2 doesn't explicitly require alphabetical node ordering (LOW IMPACT)

**Evidence:** The pass 2 prompt says "Declare nodes in alphabetical order" but this is advisory.
Different orderings don't affect correctness but add noise to diffs.

**Fix (low priority):** Post-process D2 output to normalize top-level node ordering alphabetically.

## Highest-Value Implementation Plan

Priority 1 (Drift, High): Inject explicit node key list into update prompts
- `llm.py:_build_pass1_update_prompt()` + `_build_pass2_prompt()` when existing_d2 is provided
- Expected impact: drift 5/10 → 7/10

Priority 2 (Drift, High): Inject skeleton-derived component IDs into fresh-diagram pass 1  
- `llm.py:_build_pass1_prompt()`: extract IDs from skeleton DEPENDENCIES, inject as required list
- Expected impact: +1 drift score for fresh diagrams

Priority 3 (Correctness, Medium): Retry on <20% skeleton coverage
- `llm.py:generate_diagram()`: check coverage after `_validate_d2()`, retry once if < 20%
- Expected impact: correctness 7/10 → 8/10 for large/complex projects

## Projected Scores After Improvements

- **Correctness: 8/10** (retry catches worst-case LLM drift-offs)
- **Drift Reduction: 7/10** (explicit key injection drastically reduces key churn)

## Test Coverage

310 tests currently passing. New tests needed for:
- `_build_pass1_update_prompt()` node key injection
- `_build_pass1_prompt()` skeleton ID injection  
- Low-coverage retry in `generate_diagram()`
