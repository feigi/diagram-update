# Token-Efficient Codebase Summarization for LLM-Based Diagram Generation

Research compiled 2026-03-18.

---

## 1. Codebase Skeleton Formats

### 1.1 Annotated File Tree

The simplest representation: a directory tree where each file gets a short annotation describing its purpose.

```
src/
  auth/
    service.py        — AuthService class, handles JWT validation
    middleware.py      — Express middleware for route protection
  db/
    connection.py      — Database connection pool management
    migrations/        — Alembic migration files
  api/
    routes.py          — FastAPI router definitions
    schemas.py         — Pydantic request/response models
```

**Strengths:** Human-readable, trivial to generate, very low token cost.
**Weaknesses:** No relationship information, no signatures, annotations require either manual effort or an LLM summarization pass.

### 1.2 Import Graph as Structured Data

Representing module dependencies as JSON or YAML adjacency lists:

```json
{
  "src/api/routes.py": {
    "imports": ["src/auth/service.py", "src/db/connection.py", "src/api/schemas.py"]
  },
  "src/auth/middleware.py": {
    "imports": ["src/auth/service.py"]
  }
}
```

**Strengths:** Captures relationships explicitly; LLMs can reason about dependency direction; machine-parseable.
**Weaknesses:** Doesn't convey what each module does; can be verbose for large codebases with many cross-imports.

### 1.3 Function/Class Signature Summaries (Code Map)

Extract public API surfaces without implementation bodies. This is the approach used by aider's repo map and the "Code Maps" concept described by origo.prose.sh.

**Aider's repo map format** uses tree-sitter to parse ASTs and extract definitions:

```
aider/coders/base_coder.py:
  |class Coder:
  |  abs_fnames = None
  |  @classmethod
  |  def create(self, main_model, edit_format, io, **kwargs):
  |  def abs_root_path(self, path):
  |  def run(self, with_message=None):

aider/commands.py:
  |class Commands:
  |  voice = None
  |  def get_commands(self):
  |  def get_command_completions(self, cmd_name, partial):
  |  def run(self, inp):
```

Key details of aider's approach:
- Uses tree-sitter to parse source into ASTs and extract symbol definitions
- Tags are structured as `(rel_fname, fname, line, name, kind)`
- A **graph ranking algorithm** (PageRank-like) ranks symbols by how often they are referenced across the codebase
- Only the most-referenced symbols are included in the map
- Default token budget: **1,024 tokens** (configurable via `--map-tokens`)
- The map is regenerated contextually based on the current task

**Code Maps approach** (origo.prose.sh) extracts:
- Namespace/package declarations
- Import/include statements
- Public class/type definitions
- Method signatures (names + parameters + return types)
- Public field/property declarations
- Excludes: method bodies, private members

A code map is typically **5-10% of the original code size** while capturing ~90% of what an LLM needs to understand architecture.

### 1.4 Combined Representations

The most effective approach combines multiple layers:

1. **File tree** (for spatial awareness and project structure)
2. **Import graph** (for dependency relationships)
3. **Signature summaries** (for API surface understanding)

Repomix's XML format demonstrates this combination:

```xml
<repository>
  <file_summary>
    <!-- metadata about the repo -->
  </file_summary>
  <directory_structure>
    <!-- tree listing -->
  </directory_structure>
  <files>
    <file path="src/auth/service.py">
      <!-- file content or compressed signatures -->
    </file>
  </files>
</repository>
```

---

## 2. Token Budgeting Strategies

### 2.1 Token Costs by Project Size

Rough estimates for different representations:

| Project Size | Full Source | File Tree Only | Annotated Tree | Signatures Only | Code Map (5-10%) |
|---|---|---|---|---|---|
| Small (50 files, 5K LOC) | ~15K tokens | ~200 tokens | ~500 tokens | ~1.5K tokens | ~750-1.5K tokens |
| Medium (200 files, 25K LOC) | ~75K tokens | ~800 tokens | ~2K tokens | ~7.5K tokens | ~3.7-7.5K tokens |
| Large (1000 files, 100K LOC) | ~300K tokens | ~4K tokens | ~10K tokens | ~30K tokens | ~15-30K tokens |
| Enterprise (5000+ files) | ~1.5M+ tokens | ~20K tokens | ~50K tokens | ~150K tokens | ~75-150K tokens |

Notes:
- Rough rule of thumb: 1 LOC ~ 3 tokens (varies by language)
- File tree: ~4 tokens per entry (path + indentation)
- Annotated tree: ~10-15 tokens per entry
- Signatures: ~30% of full source tokens

### 2.2 Compression Techniques

**AST-based compression (Repomix `--compress`):**
- Uses tree-sitter to strip method bodies, keeping only signatures
- Achieves **~70% token reduction** while preserving semantic meaning
- Preserves class hierarchies, function signatures, type annotations

**Abbreviation strategies:**
- Collapse common path prefixes: `src/components/` becomes `s/c/`
- Use short aliases for repeated module names
- Omit standard library imports (assume LLM knows them)

**Deduplication:**
- Group files by pattern (e.g., all React components share similar structure)
- Summarize groups: "12 React components in `src/components/`, each exporting a default functional component"
- Show one representative example + list of similar files

**Hierarchical summaries:**
- Summarize at directory level first: "The `auth/` module handles authentication with JWT tokens, RBAC, and session management"
- Only expand directories relevant to the current task

### 2.3 Progressive Detail (Progressive Disclosure)

A layered approach that reveals complexity gradually:

**Layer 1 — Index (lowest token cost):**
Show lightweight metadata only: file names, types, token counts, last-modified dates.

**Layer 2 — Structure:**
Expand to signatures, imports, and class hierarchies for relevant modules.

**Layer 3 — Deep Dive:**
Full source code for specific files that need detailed understanding.

This pattern reduces token overhead by **85-95%** compared to sending everything upfront. The key insight: let the LLM request more detail rather than front-loading all context.

Applied to codebase summarization for diagram generation:
1. First call: send annotated file tree + high-level module descriptions (~500-2K tokens)
2. LLM identifies which modules/relationships it needs more detail on
3. Second call: send signatures and import graphs for those specific areas (~1-5K tokens)
4. LLM generates the diagram

### 2.4 Single Call vs. Multi-Call

**Single call** works when:
- The codebase representation fits within ~10-20% of context window (leaves room for instructions + output)
- The diagram scope is narrow (e.g., one module's internal structure)
- Token budget for the representation stays under ~10K tokens

**Multi-call** is better when:
- Large codebase that would consume too much context
- Complex diagram requiring multiple views
- Need to validate or iterate on diagram structure
- Progressive disclosure pattern: overview -> drill-down -> generate

**Recommended approach for diagram generation:**
- For projects under ~200 files: single call with code map + annotated tree
- For larger projects: two-call approach (overview then targeted detail)
- Always reserve at least 4K tokens for the LLM's diagram output

---

## 3. Existing Tools and Approaches

### 3.1 Aider's Repo Map

**Source:** [aider.chat/docs/repomap](https://aider.chat/docs/repomap.html)

Aider is a terminal-based AI coding assistant. Its repo map is one of the most mature implementations of token-efficient codebase representation.

**How it works:**
1. Tree-sitter parses all source files into ASTs
2. Extracts all symbol definitions (functions, classes, variables, types) and their references
3. Builds a **dependency graph**: nodes = files, edges = import/reference relationships
4. Applies a **graph ranking algorithm** (similar to PageRank) to identify the most important symbols
5. Selects symbols that fit within the token budget, prioritizing the most-referenced ones
6. Formats as an indented tree showing file paths and key definitions with signatures

**Key design decisions:**
- Default budget of **1,024 tokens** — deliberately small, forces extreme prioritization
- The map is **contextual**: when the user is working on specific files, nearby symbols in the dependency graph get higher rank
- Uses `|` and `...` notation to show that content is elided
- Includes enough of each definition to identify it (name + signature) but never the body

**Evolution:** Started with ctags (simpler, less accurate), moved to tree-sitter for better AST parsing and cross-language support.

References:
- [Building a better repository map with tree sitter](https://aider.chat/2023/10/22/repomap.html)
- [Improving GPT-4's codebase understanding with ctags](https://aider.chat/docs/ctags.html)
- [Repository Mapping System (DeepWiki)](https://deepwiki.com/Aider-AI/aider/4.1-repository-mapping)

### 3.2 Repomix (formerly Repopack)

**Source:** [repomix.com](https://repomix.com/) / [GitHub](https://github.com/yamadashy/repomix)

Repomix takes the opposite approach to aider: instead of extreme compression, it packs the entire repository into a single AI-friendly file.

**Output formats:** XML (default), Markdown, JSON, Plain text.

**Key features:**
- **Token counting**: Shows token counts per file and total, with configurable encoding (o200k_base for GPT-4o, cl100k_base for GPT-3.5/4)
- **`--compress` mode**: Uses tree-sitter to extract only signatures and structure, achieving **~70% token reduction**
- **`--token-count-tree`**: Shows file tree with token counts, can filter by threshold (files with >= N tokens)
- **Security**: Uses Secretlint to detect and exclude sensitive information
- **Respects `.gitignore`** and custom `.repomixignore`

**XML output structure:**
```xml
<repository>
  <file_summary>...</file_summary>
  <directory_structure>...</directory_structure>
  <files>
    <file path="src/main.py">
      [file content or compressed signatures]
    </file>
  </files>
</repository>
```

**When to use:** Best for smaller-to-medium codebases where you want full context, or with `--compress` for larger codebases. The XML format is well-optimized for Claude's XML parsing.

References:
- [Repomix Configuration](https://repomix.com/guide/configuration)
- [Repomix Command Line Options](https://repomix.com/guide/command-line-options)

### 3.3 Code Maps (origo.prose.sh)

**Source:** [Code Maps: Blueprint Your Codebase for LLMs Without Hitting Token Limits](https://origo.prose.sh/code-maps)

A conceptual approach (not a specific tool) that advocates for structured XML code maps as the optimal middle ground.

**Key arguments:**
- A code map at 5-10% of original size captures 90% of architectural understanding
- Even with million-token context windows, signal-to-noise ratio matters — structural overview of an entire codebase beats detailed implementations of 50 files
- LLMs suffer from "lost in the middle" attention degradation on very long inputs

**What to include:**
- Namespace/package declarations
- Import statements
- Public class/type definitions with method signatures
- Public fields/properties
- Type references (what types a module uses from other modules)

**What to exclude:**
- Method bodies / implementation details
- Private members
- Comments (unless they are doc-level API descriptions)

### 3.4 Meta-RAG for Codebases

**Source:** [arxiv.org/html/2508.02611v1](https://arxiv.org/html/2508.02611v1)

Academic approach using hierarchical code summaries for retrieval:
- Generates summaries at multiple granularity levels: file, class, function
- LLM traverses from high-level summaries down to specific code units
- **~80% average token reduction** through summarization
- Incremental summary updates achieve **57.9% further reduction** vs. re-summarizing from scratch

### 3.5 RepoPrompt

A macOS tool (referenced by the Code Maps article) that provides:
- Token estimation for instant cost visibility
- Structured XML prompts optimized for LLM comprehension
- Automatic code map extraction of classes and functions
- Intelligent type reference detection

### 3.6 Reducing Token Usage (Academic)

**Source:** [TU Wien thesis by Hrubec (2025)](https://repositum.tuwien.at/bitstream/20.500.12708/224666/1/Hrubec%20Nicolas%20-%202025%20-%20Reducing%20Token%20Usage%20of%20Software%20Engineering%20Agents.pdf)

A diploma thesis studying token reduction strategies for SE agents. Key finding: AST-based summarization achieves approximately **10% of original code size** in tokens while preserving the information needed for code understanding tasks.

---

## 4. Prompt Engineering for D2 Diagram Generation

### 4.1 D2 Syntax Overview

D2 is a declarative diagram scripting language. Key syntax elements:

```d2
# Shapes (nodes)
server: API Server
database: PostgreSQL {shape: cylinder}

# Connections (edges)
server -> database: queries

# Containers (grouping)
backend: Backend {
  server: API Server
  worker: Background Worker
  server -> worker: enqueues jobs
}

# Styling
server.style.fill: "#e3f2fd"

# Labels
server -> database: reads/writes {
  style.stroke-dash: 3
}
```

**Container syntax** is particularly relevant for architecture diagrams — it maps naturally to modules/packages:

```d2
auth: Authentication {
  service: AuthService
  middleware: AuthMiddleware
  service -> middleware: validates tokens
}

api: API Layer {
  routes: Routes
  schemas: Schemas
}

api.routes -> auth.middleware: protected routes
```

### 4.2 Strategies for LLM D2 Generation

**Finding from simmering.dev:** Commonly used LLMs (GPT-4o, Claude, Gemini) are already familiar with D2 syntax. D2 creates the most aesthetic and readable diagrams, especially using the ELK layout engine. No "magic prompt" is required — just ask for D2 code.

**However, for consistent and accurate output, the following strategies help:**

#### Strategy A: Structured Instructions with Syntax Reference

Provide a concise D2 syntax reference in the system prompt:

```
Generate a D2 architecture diagram. Use this syntax:
- Shapes: `name: Label`
- Connections: `a -> b: label`
- Containers: `group: Label { ... }`
- Shape types: `{shape: cylinder}` for databases, `{shape: queue}` for queues
- Use containers to group related components by module/service
```

#### Strategy B: Few-Shot Examples

Provide 1-2 small complete D2 examples that demonstrate the exact style you want:

```
Example D2 output for a simple web app:

client: Browser
server: Express Server
db: PostgreSQL {shape: cylinder}
cache: Redis {shape: queue}

client -> server: HTTP requests
server -> db: queries
server -> cache: session lookup
```

Few-shot examples are more token-expensive but produce more consistent formatting and style.

#### Strategy C: Output Constraints

Explicitly constrain the output format:

```
Rules:
- Output ONLY valid D2 code, no explanations
- Use containers to group components by module
- Every connection must have a descriptive label
- Use shape types: cylinder for databases, queue for message queues, cloud for external services
- Keep identifiers lowercase with underscores
- Keep labels concise (2-4 words)
```

#### Strategy D: Two-Pass Generation

1. **First pass:** LLM outputs a structured list of components and relationships (JSON or YAML)
2. **Second pass:** Convert the structured data to D2 syntax (can be done programmatically or by LLM)

This separates the "understanding architecture" task from the "producing valid syntax" task, reducing errors in both.

### 4.3 Recommended Approach for This Project

Combine strategies for best results:

1. **System prompt:** Include a compact D2 syntax reference (Strategy A) — ~200 tokens
2. **One example:** Show one small but complete D2 diagram in the style you want (Strategy B) — ~100 tokens
3. **Output constraints:** Specify formatting rules (Strategy C) — ~100 tokens
4. **Input format:** Send the codebase as a code map (signatures + import graph) — variable tokens
5. **Instruction:** "Generate a D2 architecture diagram showing the major components and their relationships based on the codebase structure provided."

**Error handling:** D2's parser provides clear error messages. If the output has syntax errors, feed the error back to the LLM for correction. The stakes are low — syntax errors are caught during rendering, content errors are spotted during visual review.

### 4.4 D2 vs. Mermaid for LLM Generation

| Criterion | D2 | Mermaid |
|---|---|---|
| Aesthetic quality | Higher (ELK layout) | Adequate |
| LLM familiarity | Good (in training data) | Excellent (very common) |
| Container support | First-class | Limited |
| Architecture diagrams | Strong | Moderate |
| GitHub rendering | No (needs CLI) | Yes (native in markdown) |
| Error messages | Excellent | Basic |

For architecture diagrams from codebase analysis, D2 is preferred due to superior container support and layout quality.

---

## 5. Synthesis: Recommended Approach for Diagram Generation

### Pipeline

```
Codebase
  -> Tree-sitter AST parsing
  -> Extract: file tree + signatures + import graph
  -> Rank by reference count (PageRank-style)
  -> Budget: fit into ~2-4K tokens
  -> Format as structured prompt (annotated tree + key signatures)
  -> LLM generates D2 diagram
  -> Validate D2 syntax
  -> Render to SVG/PNG
```

### Token Budget Allocation (for a ~10K token call)

| Component | Tokens |
|---|---|
| System prompt + D2 reference | ~400 |
| D2 example | ~150 |
| Codebase representation | ~4,000-6,000 |
| Generation instructions | ~200 |
| Reserved for D2 output | ~3,000-5,000 |

### Codebase Representation Format

For the codebase input, combine:

1. **Directory tree with annotations** (~20% of representation budget)
2. **Top-ranked signatures** (~50% of representation budget)
3. **Import/dependency edges** (~30% of representation budget)

```
## Project Structure
src/
  auth/          — Authentication module (JWT, RBAC)
  api/           — REST API endpoints
  db/            — Database layer (SQLAlchemy)
  workers/       — Background job processing

## Key Definitions
src/auth/service.py:
  class AuthService:
    def validate_token(self, token: str) -> User
    def create_token(self, user: User) -> str
    def check_permission(self, user: User, resource: str) -> bool

src/api/routes.py:
  def register_routes(app: FastAPI) -> None
  class UserRouter:
    def get_user(self, user_id: int) -> UserResponse
    def create_user(self, data: CreateUserRequest) -> UserResponse

## Dependencies
api/routes.py -> auth/service.py (AuthService.validate_token)
api/routes.py -> db/repository.py (UserRepository)
auth/middleware.py -> auth/service.py (AuthService.validate_token)
workers/email.py -> db/repository.py (UserRepository.get_email)
```

This format gives the LLM enough information to produce an accurate architecture diagram while staying within a few thousand tokens even for medium-sized codebases.

---

## Sources

- [Aider Repository Map Documentation](https://aider.chat/docs/repomap.html)
- [Building a better repository map with tree sitter (aider blog)](https://aider.chat/2023/10/22/repomap.html)
- [Improving GPT-4's codebase understanding with ctags (aider)](https://aider.chat/docs/ctags.html)
- [Repository Mapping System (DeepWiki)](https://deepwiki.com/Aider-AI/aider/4.1-repository-mapping)
- [Repomix GitHub Repository](https://github.com/yamadashy/repomix)
- [Repomix Documentation](https://repomix.com/)
- [Repomix Configuration Guide](https://repomix.com/guide/configuration)
- [Code Maps: Blueprint Your Codebase for LLMs Without Hitting Token Limits](https://origo.prose.sh/code-maps)
- [Meta-RAG on Large Codebases Using Code Summarization (arXiv)](https://arxiv.org/html/2508.02611v1)
- [Reducing Token Usage of Software Engineering Agents (TU Wien thesis)](https://repositum.tuwien.at/bitstream/20.500.12708/224666/1/Hrubec%20Nicolas%20-%202025%20-%20Reducing%20Token%20Usage%20of%20Software%20Engineering%20Agents.pdf)
- [Diagrams as Code: Supercharged by AI Assistants (simmering.dev)](https://simmering.dev/blog/diagrams/)
- [D2 Language Documentation](https://d2lang.com/)
- [D2 Containers Documentation](https://d2lang.com/tour/containers/)
- [D2 Connections Documentation](https://d2lang.com/tour/connections/)
- [Progressive Context Enrichment for LLMs (Inferable)](https://www.inferable.ai/blog/posts/llm-progressive-context-encrichment)
- [Effective context engineering for AI agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Project Context for Code Summarization with LLMs (EMNLP 2024)](https://aclanthology.org/2024.emnlp-industry.65.pdf)
