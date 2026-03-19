# Review Plan

## Step 1 (current): Primary adversarial pass
- Scan all core modules for correctness and drift issues
- Status: COMPLETE → findings.md written
- Key finding: container-child node insertion bug in merge_diagrams()

## Step 2: Deep analysis — merge_diagrams container handling
- Trace exactly what happens when a container with children has a new child added
- Verify parse_d2 correctly identifies child nodes vs container nodes
- Reproduce the bug with a minimal D2 example
- Assess: is the bug triggered in practice? (yes — architecture diagrams use containers)
- key: review:step-02:merge-container

## Final Step: Synthesis and completion
- Consolidate all findings
- Emit REVIEW_COMPLETE
