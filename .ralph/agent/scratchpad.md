
## Iteration: review.start (2026-03-19)

### Context
Reviewing commit 195ec66 which strengthened D2 validation, determinism prompts, and skeleton edge matching.
Goal: maximize correctness (diagram reflects reality) and drift reduction (diagram stable over changes).

### Key Findings
1. **CRITICAL**: `_extract_pass1_ids()` extracts component IDs but they are NEVER passed to `_build_pass2_prompt`. The "cross-pass consistency" is logging only, not enforcement.
2. **CRITICAL**: `_build_pass1_update_prompt` (update mode = most common path) is missing the alphabetical sort instructions added to `_build_pass1_prompt`.
3. **SUGGESTION**: `_check_balanced_braces` is string-literal unaware (low practical risk).
4. **SUGGESTION**: `_check_edge_endpoints` typed as `object` (duck typing, no safety).
5. **SUGGESTION**: `_check_skeleton_coverage` leaf-name fallback partially reintroduces the issue it was fixing.

### Highest-Risk Area for Deep Analysis
Gap between claimed behavior ("cross-pass consistency") and actual implementation (IDs extracted but unused).
Plus update prompt lacking alphabetical ordering (most common production path).

### Tasks Created
- review:step-01:primary (task-1773910550-d51d) — primary pass ✓ done
- review:step-02:cross-pass-gap (task-1773911066-fe9a) — deep analysis
