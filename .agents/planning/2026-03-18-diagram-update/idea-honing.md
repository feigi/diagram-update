# Idea Honing

Requirements clarification Q&A for the diagram update tool.

---

## Q1: What diagram output format do you want?

Options to consider:
- **Mermaid** — text-based, renders in GitHub/GitLab/most markdown viewers, easy to diff
- **PlantUML** — text-based, rich UML support, requires renderer
- **D2** — modern text-based diagramming language with auto-layout
- **SVG/PNG** — rendered image files
- **Multiple formats** — support several with a pluggable renderer

Which format(s) should the tool produce?

**Answer:** D2. It wins on layout quality (ELK/TALA engines), update stability (key-based identity = minimal diffs), token efficiency (~80-100 tokens for 10-node graph), and programmatic layout control (per-container direction, grid, `near`). The trade-off of no native GitHub/GitLab rendering is acceptable — pre-rendering SVGs in CI is a viable solution.

---

## Q2: What is the intended runtime environment for this tool?

Options to consider:
- **CLI tool** — run manually or in CI pipelines (e.g. `diagram-update ./src -o architecture.d2`)
- **Claude Code skill/slash command** — invoked within Claude Code sessions (e.g. `/update-diagram`)
- **MCP server** — exposed as a tool to any LLM-powered agent
- **Library/module** — imported and called programmatically from other tools
- **Some combination** of the above

How should users invoke this tool?

**Answer:** A script using the GitHub Models API (`https://models.inference.ai.azure.com`) as the LLM provider, authenticated via GitHub PAT. This satisfies the hard requirement of using GitHub Copilot as the LLM provider while giving full programmatic control (system prompts, JSON mode, structured output). The script will be a standalone CLI tool.

---

## Q3: What programming language should the script be written in?

Options to consider:
- **Bash** — zero dependencies, but string manipulation and JSON handling are painful
- **Python** — excellent for API calls, JSON parsing, file traversal; widely available
- **TypeScript/Node** — good ecosystem, but heavier runtime
- **Go** — single binary output, but more effort for a script

Which language do you prefer?

**Answer:** Python.

---

## Q4: How should the tool understand the codebase structure?

The tool needs to extract components and their relationships from source code. Options:

- **File/directory structure only** — infer components from folder layout (e.g. `src/auth/`, `src/api/`) and imports/dependencies between them
- **Language-aware parsing** — use ASTs (tree-sitter, etc.) to extract classes, modules, function calls
- **LLM-driven analysis** — send code to the LLM and ask it to identify components and relationships
- **Hybrid** — use cheap static analysis (imports, file structure) first, then LLM for higher-level interpretation

This directly impacts token efficiency and correctness. Which approach appeals to you?

**Answer:** Hybrid. Use cheap static analysis (file/directory structure, import/dependency patterns) to build a structural skeleton, then send that skeleton (not raw code) to the LLM to interpret components and relationships at an architectural level. This balances token efficiency with correctness — avoids sending entire codebases to the LLM, avoids the setup complexity of LSP, and lets the LLM handle the higher-level "what is a component?" interpretation.

---

## Q5: What types of software projects should this tool support?

This affects which static analysis strategies to implement for the skeleton extraction phase.

- **Specific languages** — e.g. Python, TypeScript, Java, Go only
- **Language-agnostic** — rely on universal signals (directory structure, file names, common patterns like `import`, `require`, `package`)
- **Start narrow, expand later** — pick 2-3 languages to nail first, then generalize

Which approach?

**Answer:** Start with Python, Java, and C. These cover three different paradigms (scripting/OOP, enterprise OOP, systems/procedural) and import styles (`import`, `import/package`, `#include`). Language-specific static analyzers for each.

---

## Q6: What types of component diagrams should the tool produce?

D2 can express many diagram styles. Which are in scope?

- **High-level architecture** — services, modules, packages and their dependencies (e.g. "API talks to Auth, Auth talks to DB")
- **Package/module dependency graph** — more granular, showing module-level imports
- **Class diagram** — classes, inheritance, composition relationships
- **Deployment/infrastructure** — containers, databases, message queues, external services
- **Sequence/flow diagrams** — call flows between components
- **Multiple types** — user picks via config

Which diagram type(s) are in scope for v1?

**Answer:** Three diagram types for v1:
1. **High-level architecture** — services, modules, packages and their dependencies
2. **Package/module dependency graph** — module-level import relationships
3. **Sequence/flow diagrams** — call flows between components

---

## Q7: How should the tool handle the "stability" requirement for diagram updates?

When re-running the tool after code changes, we want minimal diagram churn. Strategies:

- **Diff-based approach** — compare old D2 file with newly generated one, apply only necessary changes (add/remove nodes/edges), preserve all existing layout hints and ordering
- **Anchor-based** — assign stable IDs to components, regenerate only changed sections while keeping the D2 structure order intact
- **Full regenerate with constraints** — always regenerate from scratch but feed the existing diagram to the LLM as context with instructions to preserve structure where possible

The diff-based approach is the most predictable but requires careful merging logic. The LLM-with-context approach is simpler to implement but less deterministic. Which do you lean toward, or a combination?

**Answer:** Anchor-based. Each component gets a stable ID derived from its code path (e.g. `src.auth.service` → node key `auth_service`). On re-run, compare keys against the existing D2 file — add new nodes, remove deleted ones, update changed edges. Existing node ordering and layout hints stay untouched. This is deterministic and works naturally with D2's key-based node model. No AST diffing or fuzzy matching needed.

---

## Q8: What configuration options should users have?

You mentioned users should be able to guide the creation process. Some possibilities:

- **Include/exclude paths** — e.g. ignore `tests/`, `vendor/`, only diagram `src/core/`
- **Component granularity** — e.g. "treat each top-level directory as a component" vs "treat each module as a component"
- **Diagram type selection** — which of the three diagram types to generate
- **Custom component grouping** — user-defined groupings (e.g. "these 3 modules are the 'Auth' subsystem")
- **Max depth** — limit how deep into nested packages the diagram goes
- **Output path** — where to write the `.d2` file

Which of these are important for v1? Any others?

**Answer:** For v1:
1. **Include/exclude paths** — filter which directories/files are analyzed
2. **Component granularity** — control whether top-level directories, packages, or individual modules are treated as components

Other options (diagram type selection, custom grouping, max depth, output path) deferred to later versions.

---

## Q9: Where should configuration live?

Options:
- **CLI arguments** — e.g. `diagram-update --exclude tests/ --granularity package ./src`
- **Config file** — e.g. `.diagram-update.yml` in the project root
- **Both** — config file for defaults, CLI args to override

Which do you prefer?

**Answer:** Config file (e.g. `.diagram-update.yml` in the project root). No CLI argument overrides for v1.

---

## Q10: How should the tool handle the sequence/flow diagram type?

The high-level architecture and package dependency diagrams can be derived from static analysis + LLM interpretation. But sequence/flow diagrams are different — they describe runtime call flows, which are harder to extract statically.

Options:
- **Static call-chain analysis** — trace function calls through the code to build call sequences (works for simple flows, breaks down with polymorphism/callbacks)
- **User-specified entry points** — user names a function or endpoint in config, tool traces the call flow from there
- **LLM-inferred** — send relevant code to the LLM and ask it to identify key flows (e.g. "request handling flow", "auth flow")

User-specified entry points seems most practical — it scopes the problem and avoids hallucinated flows. Thoughts?

**Answer:** LLM-inferred entry points with optional user override. The LLM identifies key entry points (e.g. `main()`, HTTP handlers, CLI entry points) from the codebase skeleton, capped at top 5 most significant flows. Users can override or supplement via config file. This keeps it fully automatic by default while allowing control when needed.

---

## Q11: What model should we use via the GitHub Models API?

The GitHub Models API offers several options. For structured D2 generation from code analysis, we need strong reasoning and instruction following.

Options available through GitHub Models:
- **GPT-4o** — strong all-around, good at structured output
- **GPT-4o-mini** — cheaper/faster, still capable
- **o3-mini** — reasoning model, good for complex analysis

Which model, or should the tool default to one with the option to configure?

**Answer:** Claude Opus 4.6 via GitHub Copilot CLI. Invoked as `gh copilot -p "..." -s --model  claude-opus-4.6 --no-ask-user`. The `-s` flag strips decoration for scriptable plain-text output. No JSON mode available, so prompts must instruct the model to output only D2 code. This satisfies both requirements: GitHub Copilot as provider + Claude Opus 4.6 as model.

---

## Q12: Where should the generated diagrams be stored?

Options:
- **Project root** — e.g. `architecture.d2`, `dependencies.d2`
- **Dedicated directory** — e.g. `docs/diagrams/`
- **Configurable in config file**

What's your preference?

**Answer:** Dedicated directory `docs/diagrams/`. Files like `docs/diagrams/architecture.d2`, `docs/diagrams/dependencies.d2`, `docs/diagrams/flow-{name}.d2`.
