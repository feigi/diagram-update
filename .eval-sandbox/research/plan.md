# Research Plan: Diagram Correctness & Drift Under Default Configuration

## Wave 1: End-to-end pipeline analysis
**Question:** What are the structural correctness guarantees and drift-inducing gaps in the default pipeline (analyze → skeleton → LLM → post-process → merge/write)?

Focus areas:
- Static analysis fidelity (analyzer accuracy)
- Skeleton completeness vs truncation
- LLM prompt constraints and validation
- Post-processing side effects
- Merge/drift safeguards

## Wave 2 (conditional): Test coverage of correctness-critical paths
**Question:** Do the existing tests exercise the failure modes identified in Wave 1?
