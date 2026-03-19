# Review Plan: diagram-update

## Objective
Maximize two dimensions:
1. **Correctness** — diagram accurately reflects reality
2. **Drift reduction** — keep diagram stable over changes

## Step 1: Primary pass (task-1773910550-d51d, review:step-01:primary)
Bounded adversarial review to identify top 1-2 highest-risk concerns.

## Step 2: Deep analysis — analyzer glob/grouping correctness (review:step-02:analyzer-correctness)
Deep dive into `_matches_any()` and `_compute_component_id()` to verify files
are correctly included/excluded and grouped. These directly impact correctness.

## Final step: Synthesis and completion
