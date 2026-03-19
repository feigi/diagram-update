# Review Plan: commit 195ec66 — Strengthen D2 validation, determinism prompts, skeleton edge matching

## Step 1: Primary Pass (review:step-01:primary)
Identify top 1-2 highest-risk areas in the changed files:
- src/diagram_update/llm.py (main changes)
- src/diagram_update/skeleton.py (edge sort order)
- src/diagram_update/merger.py (regex comment)
- tests/test_llm.py

## Step 2: Deep Analysis — Pass 1 IDs Not Used + Update Prompt Missing Alphabetical Sort (review:step-02:cross-pass-gap)
The commit claims "cross-pass consistency" via pass1 ID extraction, but IDs are never fed into pass2 validation.
Also, _build_pass1_update_prompt lacks the alphabetical ordering added to _build_pass1_prompt.
This is the highest-risk gap for both correctness and drift dimensions.

## Final Step: Synthesis and REVIEW_COMPLETE
