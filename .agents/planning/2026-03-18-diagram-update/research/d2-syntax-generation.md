# D2 Diagramming Language: Research for Programmatic Generation from Python

**Date:** 2026-03-18
**Sources:** d2lang.com official docs, GitHub repos (terrastruct/d2, MrBlenny/py-d2, dacog/d2-python-wrapper), PyPI

---

## 1. D2 Syntax for Component Diagrams

### Nodes (Shapes)

Nodes are declared by simply naming them. Labels default to the key name, or can be set explicitly:

```d2
# Implicit label (displays "server")
server

# Explicit label
server: My Server

# With shape type
database: Users DB {
  shape: cylinder
}

# Available shapes include:
# rectangle (default), square, page, parallelogram, document, cylinder,
# queue, package, step, callout, stored_data, person, diamond,
# oval, circle, hexagon, cloud
```

### Styling Nodes

```d2
server: API Server {
  shape: rectangle
  style.fill: "#e3f2fd"
  style.stroke: "#1565c0"
  style.border-radius: 8
  style.font-size: 16
  style.bold: true
  style.shadow: true
  style.multiple: true     # stacked appearance (multiple instances)
  style.opacity: 0.9
}
```

### Icons

```d2
server: API Server {
  icon: https://icons.terrastruct.com/essentials/005-programmer.svg
  icon.near: outside-top-right
  label.near: top-center
}
```

### Edges (Connections)

```d2
# Basic directional
server -> database

# With label
server -> database: queries

# Bidirectional
server <-> cache: read/write

# No arrow (line only)
Read Replica 1 -- Read Replica 2: Kept in sync

# Chained connections
a -> b -> c -> d

# Multiple connections between same nodes (each creates a separate edge)
server -> database: read
server -> database: write
```

### Edge Labels and Arrowheads

```d2
a -> b: relationship {
  source-arrowhead: 1
  target-arrowhead: * {
    shape: diamond
    style.filled: true
  }
}

# Arrowhead shape options:
#   triangle (default), arrow, diamond, circle, box
#   cf-one, cf-one-required (crow's foot notation)
#   cf-many, cf-many-required
#   cross

# Dashed edges
a -> b: optional {
  style.stroke-dash: 5
}

# Animated edges
a -> b: data flow {
  style.animated: true
}
```

### Containers (Groups)

Containers are created by nesting objects inside braces:

```d2
# Nested syntax
clouds: {
  aws: {
    load_balancer
    api
    db: {
      shape: cylinder
    }
  }
  gcp: {
    load_balancer
    api
    db: {
      shape: cylinder
    }
  }
}

# Dot notation (equivalent to nesting)
clouds.aws.api -> clouds.gcp.api: sync
```

Container labels can use the `label` keyword:

```d2
cloud: {
  label: Amazon Web Services
  api: REST API
  auth: Auth Service
  db: Users DB {
    shape: cylinder
  }
}
```

Referencing parent containers from within a nested scope uses underscore (`_`):

```d2
christmas: {
  presents
  presents: {
    _ -> regift
  }
}
```

### Direction Control

```d2
# Top-level direction
direction: right    # Options: up, down, left, right

# Per-container direction (TALA layout engine only)
direction: down
a -> b -> c

b: {
  direction: right
  1 -> 2 -> 3
}
```

### Layout Engine Selection (in-file)

Layout engine and theme can be set inside the D2 file using `vars.d2-config`:

```d2
vars: {
  d2-config: {
    layout-engine: elk       # Options: dagre, elk, tala
    theme-id: 0              # Theme ID (0 = default)
    dark-theme-id: 200       # Dark mode theme
  }
}

server -> database
```

### Complete Component Diagram Example

```d2
vars: {
  d2-config: {
    layout-engine: elk
  }
}

direction: right

frontend: Web Frontend {
  style.fill: "#e8f5e9"
  spa: React SPA
  cdn: CDN {
    shape: cloud
  }
}

backend: Backend Services {
  style.fill: "#e3f2fd"
  api: REST API {
    shape: rectangle
    style.multiple: true
  }
  auth: Auth Service
  worker: Background Worker {
    shape: hexagon
  }
}

data: Data Layer {
  style.fill: "#fff3e0"
  postgres: PostgreSQL {
    shape: cylinder
  }
  redis: Redis Cache {
    shape: cylinder
  }
  queue: Message Queue {
    shape: queue
  }
}

frontend.spa -> backend.api: HTTPS
frontend.cdn -> frontend.spa: serves

backend.api -> data.postgres: queries
backend.api -> data.redis: cache
backend.api -> data.queue: publish
data.queue -> backend.worker: consume
backend.auth -> data.postgres: verify
backend.api -> backend.auth: authenticate {
  style.stroke-dash: 5
}
```

---

## 2. Python Libraries for D2

### Option A: `py-d2` (Typed Python API for building .d2 files)

- **PyPI:** https://pypi.org/project/py-d2/
- **GitHub:** https://github.com/MrBlenny/py-d2
- **Version:** 1.0.1 (May 2024)
- **License:** MIT
- **Python:** 3.7+

**What it does:** Provides Python classes to programmatically build D2 syntax. It generates `.d2` text -- it does NOT render diagrams itself (you still need the `d2` CLI).

**Core API:**

| Class | Purpose |
|-------|---------|
| `D2Diagram` | Top-level container; call `str(diagram)` to get D2 text |
| `D2Shape` | A node with name, label, style |
| `D2Connection` | An edge between two shape names |
| `D2Style` | Style properties (fill, stroke, etc.) |

**Usage:**

```python
from py_d2 import D2Diagram, D2Shape, D2Connection, D2Style

shapes = [
    D2Shape(name="api", style=D2Style(fill='"#e3f2fd"')),
    D2Shape(name="db", style=D2Style(fill='"#fff3e0"')),
]
connections = [
    D2Connection(shape_1="api", shape_2="db"),
]
diagram = D2Diagram(shapes=shapes, connections=connections)

# Write .d2 file
with open("arch.d2", "w") as f:
    f.write(str(diagram))
```

**Supported features:** Shapes, connections, styles, nested containers, arrow directions, markdown/block strings, icons, empty labels.
**Not supported:** Sequence diagrams, SQL tables, classes (as of 1.0.1). Does not support containers/groups in a first-class way beyond nesting.

**Assessment:** Useful for simple diagrams but limited. For complex diagrams (containers, sequence diagrams, layout config), generating D2 as plain text is more flexible.

### Option B: `d2-python-wrapper` (CLI wrapper for rendering)

- **PyPI:** https://pypi.org/project/d2-python-wrapper/
- **GitHub:** https://github.com/dacog/d2-python-wrapper
- **License:** MPL 2.0

**What it does:** Wraps the D2 CLI binary, bundling platform-specific binaries. Renders `.d2` files to SVG/PNG/PDF from Python without manual binary management.

**Usage:**

```python
from d2_python import D2

d2 = D2()

# Render a .d2 file to SVG
d2.render("input.d2", "output.svg")

# With options
d2.render(
    "input.d2",
    "output.svg",
    format="svg",
    layout="elk",        # dagre, elk
    theme="dark",
    sketch=False,
    pad=100,
    scale=-1,            # -1 = auto
    bundle=True,         # bundle SVG assets
    timeout=120,
)
```

**Assessment:** Complements `py-d2` or plain text generation by providing rendering. Bundles D2 binaries so no separate install needed.

### Option C: Plain Text Generation (Recommended for Complex Diagrams)

Since D2 is a simple text format, generating it with Python string operations or templates (Jinja2, f-strings) is straightforward and gives full control:

```python
def generate_d2(nodes: list[dict], edges: list[dict], config: dict = None) -> str:
    lines = []

    # Config block
    if config:
        lines.append("vars: {")
        lines.append("  d2-config: {")
        if "layout" in config:
            lines.append(f"    layout-engine: {config['layout']}")
        if "theme" in config:
            lines.append(f"    theme-id: {config['theme']}")
        lines.append("  }")
        lines.append("}")
        lines.append("")

    # Direction
    if config and "direction" in config:
        lines.append(f"direction: {config['direction']}")
        lines.append("")

    # Nodes
    for node in nodes:
        props = []
        if "label" in node:
            label = node["label"]
        else:
            label = None
        key = node["key"]
        if "shape" in node:
            props.append(f"  shape: {node['shape']}")
        if "style" in node:
            for k, v in node["style"].items():
                props.append(f"  style.{k}: {v}")
        if props:
            label_part = f": {label}" if label else ""
            lines.append(f"{key}{label_part} {{")
            lines.extend(props)
            lines.append("}")
        elif label:
            lines.append(f"{key}: {label}")
        else:
            lines.append(key)

    lines.append("")

    # Edges
    for edge in edges:
        label_part = f": {edge['label']}" if "label" in edge else ""
        lines.append(f"{edge['from']} -> {edge['to']}{label_part}")

    return "\n".join(lines)
```

**Recommendation:** Use plain text generation for full control over D2 syntax (containers, sequence diagrams, layout config, etc.), and optionally use `d2-python-wrapper` for rendering.

---

## 3. D2 File Parsing and Merging

### D2 File Structure

D2 files are plain text with a consistent structure:
- Top-level `vars` block (config)
- `direction` directive
- Node declarations (possibly nested in containers)
- Edge declarations
- Style overrides

### Parsing Strategy

There is no Python-native D2 parser. The official D2 parser is written in Go (`d2/d2parser`). Options:

1. **Regex/line-based parsing** -- For simple D2 files with known structure, parse line-by-line:

```python
import re

def parse_d2_file(content: str) -> dict:
    """Parse a simple D2 file to extract node keys and edges."""
    nodes = set()
    edges = []

    # Match node declarations: "key" or "key: label" or "key: label {"
    node_pattern = re.compile(r'^(\w[\w.]*)\s*(?::\s*(.+?))?(?:\s*\{)?$')
    # Match edge declarations: "a -> b" or "a -> b: label"
    edge_pattern = re.compile(r'^([\w.]+)\s*(->|<->|<-|--)\s*([\w.]+)(?:\s*:\s*(.+))?')

    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        edge_match = edge_pattern.match(stripped)
        if edge_match:
            edges.append({
                'from': edge_match.group(1),
                'arrow': edge_match.group(2),
                'to': edge_match.group(3),
                'label': edge_match.group(4),
            })
            # Also register nodes
            nodes.add(edge_match.group(1).split('.')[0])
            nodes.add(edge_match.group(3).split('.')[0])
            continue

        node_match = node_pattern.match(stripped)
        if node_match and stripped not in ('vars: {', '}'):
            nodes.add(node_match.group(1))

    return {'nodes': nodes, 'edges': edges}
```

2. **Go-based parsing via subprocess** -- Shell out to a Go tool that uses `d2/d2parser` and outputs JSON AST. This is more robust but requires Go tooling.

3. **Tree-sitter grammar** -- There is a tree-sitter grammar for D2 (`tree-sitter-d2`) that could be used via `py-tree-sitter` for robust parsing.

### Merging Strategy

To merge changes into an existing D2 file while preserving structure:

```python
def merge_d2_changes(
    existing_content: str,
    add_nodes: list[dict] = None,
    remove_node_keys: set[str] = None,
    add_edges: list[dict] = None,
    remove_edges: list[tuple] = None,   # (from, to) pairs
) -> str:
    """Merge changes into existing D2 content, preserving order of unchanged elements."""
    lines = existing_content.split('\n')
    result_lines = []

    remove_node_keys = remove_node_keys or set()
    remove_edges = remove_edges or []
    remove_edge_set = {(e[0], e[1]) for e in remove_edges}

    edge_pattern = re.compile(r'^(\s*)([\w.]+)\s*(->|<->|<-|--)\s*([\w.]+)')
    node_pattern = re.compile(r'^(\s*)(\w[\w.]*)\s*(?::|{|$)')

    skip_depth = 0
    for line in lines:
        stripped = line.strip()

        # Handle block skipping for removed nodes
        if skip_depth > 0:
            skip_depth += stripped.count('{') - stripped.count('}')
            continue

        # Check if this is an edge to remove
        edge_match = edge_pattern.match(line)
        if edge_match:
            from_key = edge_match.group(2)
            to_key = edge_match.group(4)
            if (from_key, to_key) in remove_edge_set:
                continue

        # Check if this is a node to remove
        node_match = node_pattern.match(line)
        if node_match and node_match.group(2) in remove_node_keys:
            if '{' in stripped:
                skip_depth = 1
            continue

        result_lines.append(line)

    # Append new nodes before the edges section
    if add_nodes:
        # Find insertion point (before first edge line)
        insert_idx = len(result_lines)
        for i, line in enumerate(result_lines):
            if edge_pattern.match(line):
                insert_idx = i
                break
        for node in reversed(add_nodes):
            node_line = f"{node['key']}: {node.get('label', node['key'])}"
            if node.get('shape'):
                node_line += f" {{\n  shape: {node['shape']}\n}}"
            result_lines.insert(insert_idx, node_line)

    # Append new edges at end
    if add_edges:
        for edge in add_edges:
            label_part = f": {edge['label']}" if 'label' in edge else ""
            result_lines.append(f"{edge['from']} -> {edge['to']}{label_part}")

    return '\n'.join(result_lines)
```

**Key principle:** For reliable merging, maintain a canonical data model (list of nodes/edges) in Python and regenerate the entire D2 file, rather than doing in-place text surgery on complex files.

---

## 4. D2 Sequence Diagrams

### Basic Syntax

Sequence diagrams use `shape: sequence_diagram` on a container:

```d2
shape: sequence_diagram

alice: Alice
bob: Bob

alice -> bob: Hello!
bob -> alice: Hi there!
```

### Key Rules

1. **Order matters** -- Elements appear in the order they are defined (unlike other D2 diagrams).
2. **Shared scope** -- All actors within a sequence diagram share the same scope, even inside groups.
3. **No special syntax** -- Uses standard D2 connection syntax.

### Actors

```d2
shape: sequence_diagram

# Simple actor
alice

# Actor with label
alice: Alice Anderson

# Actor with shape
scorer: {
  shape: person
}
```

### Messages (Connections)

```d2
shape: sequence_diagram

alice -> bob: synchronous call
alice -> bob: another call
bob -> alice: response {
  style.stroke-dash: 5    # dashed = async/return
}
```

### Self-Referential Messages

```d2
shape: sequence_diagram
alice -> alice: self-check
```

### Groups (Fragments/Frames)

Groups label subsets of interactions. Actors referenced inside groups must be declared at the top level:

```d2
shape: sequence_diagram

# Pre-declare actors
alice
bob

shower thoughts: {
  alice -> bob: A physicist is an atom's way of knowing about atoms.
  alice -> bob: Today is the first day of the rest of your life.
}

life advice: {
  bob -> alice: If all else fails, lower your standards.
}
```

### Notes

Notes are nested objects on actors with no connections:

```d2
shape: sequence_diagram
alice -> bob: hello
alice: {
  This is a note on Alice
}
```

### Spans (Activation Boxes)

Spans show when an actor is active. Created by appending `.t` (or `.t1`, `.t2` etc.) to actor names:

```d2
shape: sequence_diagram

scorer: {shape: person}

scorer.t -> itemResponse.t: getItem()
scorer.t <- itemResponse.t: item {
  style.stroke-dash: 5
}

scorer.t -> item.t1: getRubric()
scorer.t <- item.t1: rubric {
  style.stroke-dash: 5
}
```

### Nested Sequence Diagrams

Sequence diagrams are regular D2 objects, so they can be nested inside containers and connected:

```d2
direction: right

Before and after: {
  2007: Chatter in 2007 {
    shape: sequence_diagram
    alice: Alice
    bob: Bobby
    awkward small talk: {
      alice -> bob: uhm, hi
      bob -> alice: oh, hello
    }
  }

  2012: Chatter in 2012 {
    shape: sequence_diagram
    alice: Alice
    bob: Bobby
    alice -> bob: Want to play with ChatGPT?
    bob -> alice: Yes!
  }

  2007 -> 2012: Five years later
}
```

---

## 5. D2 CLI

### Installation

```bash
# Install script (recommended, Linux/macOS)
curl -fsSL https://d2lang.com/install.sh | sh -s --

# Homebrew (macOS)
brew install d2

# From source (requires Go 1.22+)
go install oss.terrastruct.com/d2@latest

# Verify
d2 --version
```

### Basic Rendering

```bash
# Render to SVG (default)
d2 input.d2 output.svg

# Render to PNG
d2 input.d2 output.png

# Render to PDF
d2 input.d2 output.pdf

# Read from stdin, write to stdout
echo "x -> y -> z" | d2 - - > output.svg

# Watch mode (live reload in browser)
d2 --watch input.d2 output.svg
```

### Layout Engine Selection

```bash
# Use dagre (default)
d2 -l dagre input.d2 output.svg

# Use ELK (bundled, better for complex diagrams)
d2 -l elk input.d2 output.svg

# Use TALA (requires separate binary install from terrastruct.com)
d2 -l tala input.d2 output.svg
```

**Layout engine comparison:**

| Engine | Bundled | Best For | Per-Container Direction |
|--------|---------|----------|------------------------|
| dagre | Yes (default) | Simple hierarchical layouts | No |
| ELK | Yes | Complex node-link diagrams, port support | No |
| TALA | No (separate install) | Software architecture diagrams | Yes |

### Theme Selection

```bash
# Set theme by ID
d2 --theme=300 input.d2 output.svg

# Set dark theme
d2 --dark-theme=200 input.d2 output.svg

# Common theme IDs:
#   0   = default
#   1   = Neutral default
#   3   = Flagship Terrastruct
#   4   = Cool classics
#   5   = Mixed berry blue
#   6   = Grape soda
#   7   = Aubergine
#   8   = Colorblind clear
#   100 = Vanilla nitro cola
#   102 = Shirley temple
#   103 = Earth tones
#   104 = Everglade green
#   105 = Buttered toast
#   200 = Terminal (dark)
#   201 = Terminal Grayscale (dark)
#   300 = Origami
```

### Other CLI Flags

```bash
# Full syntax
d2 [--watch false] [--theme 0] [--salt string] file.d2 [file.svg | file.png]

# Padding
d2 --pad 50 input.d2 output.svg

# Sketch mode (hand-drawn look)
d2 --sketch input.d2 output.svg

# ASCII export
d2 --ascii-mode standard input.d2 output.txt

# Multiple flags combined
d2 --theme=300 --dark-theme=200 -l elk --pad 0 input.d2 output.svg
```

### Rendering from Python

Using `d2-python-wrapper`:

```python
from d2_python import D2

d2 = D2()
d2.render("input.d2", "output.svg", layout="elk", theme=0)
```

Or using subprocess directly:

```python
import subprocess

def render_d2(input_path: str, output_path: str, layout: str = "elk") -> None:
    subprocess.run(
        ["d2", "-l", layout, input_path, output_path],
        check=True,
        capture_output=True,
    )
```

---

## 6. Summary and Recommendations

### For our use case (programmatic diagram generation from Python):

1. **Generate D2 as plain text** -- D2's syntax is simple enough that building strings/templates in Python gives full flexibility. `py-d2` is too limited for containers, sequence diagrams, and layout config.

2. **Use `vars.d2-config` block** in generated D2 to set layout engine and theme, keeping rendering configuration in the diagram file itself.

3. **For rendering**, either:
   - Call `d2` CLI via `subprocess` (simplest, requires d2 installed)
   - Use `d2-python-wrapper` (bundles binaries, no separate install)

4. **For parsing/merging existing D2 files**, maintain a canonical data model in Python and regenerate the full file. Line-by-line regex parsing works for simple cases but is fragile for deeply nested containers.

5. **Layout engine choice**: ELK is the best bundled option for complex diagrams. TALA offers per-container direction control but requires a separate install.

### Key D2 syntax cheatsheet:

| Feature | Syntax |
|---------|--------|
| Node | `key: Label` |
| Shaped node | `key: Label { shape: cylinder }` |
| Edge | `a -> b: label` |
| Bidirectional | `a <-> b` |
| Container | `group: { child1; child2 }` |
| Dot notation | `group.child -> other.child` |
| Direction | `direction: right` |
| Layout engine | `vars: { d2-config: { layout-engine: elk } }` |
| Sequence diagram | `shape: sequence_diagram` |
| Style | `style.fill: "#hex"` |
| Dashed edge | `style.stroke-dash: 5` |
| Multiple instances | `style.multiple: true` |

---

## Sources

- [D2 Official Documentation](https://d2lang.com/)
- [D2 GitHub Repository (terrastruct/d2)](https://github.com/terrastruct/d2)
- [D2 Sequence Diagrams](https://d2lang.com/tour/sequence-diagrams/)
- [D2 CLI Manual](https://d2lang.com/tour/man/)
- [D2 Containers](https://d2lang.com/tour/containers/)
- [py-d2 on PyPI](https://pypi.org/project/py-d2/)
- [py-d2 on GitHub](https://github.com/MrBlenny/py-d2)
- [d2-python-wrapper on PyPI](https://pypi.org/project/d2-python-wrapper/)
- [d2-python-wrapper on GitHub](https://github.com/dacog/d2-python-wrapper)
- [D2 Playground](https://play.d2lang.com/)
