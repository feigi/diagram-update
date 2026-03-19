
---
## Iteration: Deep Analysis - Container-Child Insertion Bug (Step 2)

Confirmed the primary review finding with live adversarial tests. Root cause is deeper than stated:

- `parse_d2()` never adds block-notation children to `node_keys` — inner lines are skipped when parsing container blocks
- `merge_diagrams()` has zero logic to detect or propagate content changes within existing container blocks
- Old block is ALWAYS preserved verbatim for containers that exist in both old and new diagrams

Three failure modes confirmed:
1. New child inside existing container → silently dropped
2. Removed child inside existing container → silently preserved (old wins)
3. Worst: new edge referencing container-internal child IS added (new edge detected fine), but child node is missing from block → corrupt diagram (orphaned edge)

Fix is clear: when container key exists in both, compare block content; if changed, replace old block with new block.
