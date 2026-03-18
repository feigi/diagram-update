# diagram-update: Planning Summary

**Date:** 2026-03-18

---

## Artifacts Created

| File | Purpose |
|------|---------|
| `rough-idea.md` | Original concept and requirements |
| `idea-honing.md` | 12 Q&A pairs refining requirements |
| `research/d2-syntax-generation.md` | D2 syntax, Python generation, CLI usage |
| `research/github-models-api.md` | GitHub Models API evaluation, Copilot CLI discovery |
| `research/static-analysis.md` | Import extraction for Python, Java, C |
| `research/token-efficient-summarization.md` | Codebase skeleton formats, token budgeting |
| `design/detailed-design.md` | Full architecture, components, data models, error handling |
| `implementation/plan.md` | 11-step incremental implementation plan |

---

## Tool Overview

`diagram-update` is a Python CLI tool that auto-generates D2 component diagrams from source code using a hybrid approach: static analysis extracts structure cheaply, then an LLM (Claude Opus 4.6 via GitHub Copilot CLI) interprets components and generates diagrams. Anchor-based merging keeps diagrams stable across updates.

## Key Decisions

- **D2** output format (best layout quality, token efficiency, key-based stability)
- **GitHub Copilot CLI** as LLM provider (`gh copilot -p -s --model   claude-sonnet-4.6 --no-ask-user`)
- **Hybrid analysis**: static extraction (imports/file structure) + LLM interpretation
- **Python, Java, C** language support for v1
- **Three diagram types**: high-level architecture, package/module dependencies, sequence/flow
- **Anchor-based stability**: stable node IDs from code paths, minimal churn
- **Config file** (`.diagram-update.yml`) for include/exclude paths and component granularity

## Implementation Approach

11 incremental steps. Working end-to-end pipeline by Step 6 (halfway), then quality iteration. See `implementation/plan.md` for details.

## Next Steps

1. Review the detailed design at `design/detailed-design.md`
2. Review the implementation plan at `implementation/plan.md`
3. Begin implementation following the plan checklist
