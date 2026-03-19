# Deep Analysis Findings — Cross-Pass ID Gap & Update Prompt Ordering

## Finding 1 (CRITICAL): `pass1_ids` extracted but never enforced in Pass 2

**Location:** `src/diagram_update/llm.py` lines 52–62

```python
pass1_ids = _extract_pass1_ids(components_text)   # IDs extracted
if pass1_ids:
    logger.info("Pass 1 complete: %d components identified", len(pass1_ids))
# ...
pass2_prompt = _build_pass2_prompt(
    components_text, diagram_type, existing_d2,   # pass1_ids NOT passed
)
```

`pass1_ids` is extracted, logged, then **discarded**. The only "enforcement" in Pass 2 is
the soft instruction at line 246–247:

> "Use the EXACT component IDs from the list above as D2 node keys — do NOT rename,
> abbreviate, or rephrase them."

This is a text hint. The LLM can silently:
- Abbreviate: `auth.handler` → `auth`
- CamelCase: `api_gateway` → `ApiGateway`
- Re-derive from context rather than from Pass 1 IDs

No post-generation validation checks that D2 node keys match `pass1_ids`.
`_validate_d2` checks braces, node existence, and skeleton coverage — not ID fidelity.

**Impact on correctness:** LLM can silently rename nodes across passes, creating
phantom components or missing real ones.

**Impact on drift:** Each run may produce slightly different node keys even for
identical input, since ID derivation happens independently in Pass 2 rather than
being constrained by Pass 1 output.

**Strongest fix:**
1. Pass `pass1_ids` as a parameter to `_build_pass2_prompt`.
2. In the prompt, list the exact allowed IDs explicitly (not "the list above").
3. Add a validation step in `_validate_d2` or after Pass 2 to check that each
   extracted `pass1_id` appears in `parsed.node_keys` (or a known alias).

---

## Finding 2 (CRITICAL): `_build_pass1_update_prompt` missing determinism instructions

**Location:** `src/diagram_update/llm.py` lines 158–204

`_build_pass1_prompt` (new diagram path, called when no existing diagram):
- Line 141: `"Output a structured list, with components sorted alphabetically by id:"`
- Line 148: `"(List relationships sorted by source_id, then target_id)"`
- Line 152: `"Determinism matters: always produce the same output for the same input."`

`_build_pass1_update_prompt` (update path, called when existing diagram present — the
**most common production path**):
- **None of the above instructions are present.**
- Output format section (lines 191–202) only specifies structure, not ordering.

**Impact on drift:** The update path is used on every subsequent run after the first
diagram is generated. Without ordering instructions, the LLM can:
- Reorder components differently across runs (different topological ordering)
- List new components before existing ones or vice versa
- Produce different Pass 1 → Pass 2 transitions for identical input

Even though Pass 2 re-sorts alphabetically, non-deterministic Pass 1 output can
affect which components the LLM *chooses to include* in Pass 2.

**No tests:** `_build_pass1_update_prompt` has zero direct tests. The test
`test_determinism_instructions` (line 103) only tests the new-diagram path.

**Fix:** Add identical ordering and determinism instructions to
`_build_pass1_update_prompt` output section.

---

## Finding 3 (MODERATE): `_validate_d2` has no ID cross-check against pass1_ids

**Location:** `src/diagram_update/llm.py` lines 285–309

`_validate_d2` checks:
- Balanced braces
- Node existence
- Edge endpoints reference declared nodes
- Skeleton relationship coverage

It does **not** check: "Do Pass 2 D2 node keys match the component IDs from Pass 1?"

This means the two-pass system can silently diverge without any error or warning.
The gap described in Finding 1 is also undetectable at runtime.

---

## Summary

| # | Finding | Severity | Path Affected |
|---|---------|----------|--------------|
| 1 | `pass1_ids` discarded — no enforcement in Pass 2 | CRITICAL | Both paths |
| 2 | Update prompt missing alphabetical/determinism rules | CRITICAL | Update path (most common) |
| 3 | `_validate_d2` has no cross-pass ID validation | MODERATE | Both paths |

The combination of #1 and #2 means: in the most common production scenario
(updating an existing diagram), both the ordering and the ID consistency guarantees
are absent, maximising both drift and correctness risk.
