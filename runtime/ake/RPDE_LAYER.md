# RPDE — Relational Primitive Derivation Engine (the missing compiler pass)

## Discovery (RP-13: Universal Relational Primitive Derivation)
FK ≠ Edge. FK is an OBSERVATION; a typed edge is DERIVED knowledge. Between Observation and Runtime
a knowledge-compilation pass was missing:
```
Observation → Primitive → [Relational Primitive → Universal Edge Graph] → Invariant → … → Runtime
```

## What RPDE does (relational_primitive_engine.py + edge_graph_engine.py)
- Scans EVERY owner class's FK columns (not Feature-only).
- Derives the relation TYPE from the column header (workbook semantics) — vocabulary is data-derived,
  not hardcoded (e.g. `category`, `owner_module`, `handler_name`, `gates`, `consumes`).
- Resolves targets by ID, and by NAME when a column stores names instead of IDs.
- Derives cardinality by counting (1→1 / 1→N / N→1 / N→N).
- Builds a Universal Edge Graph (forward + reverse + reachability) consumed by GRAPH_NEIGHBORS and the
  runtime walk.

## Effect (measured on v17)
| Metric | Before (Feature-only) | After RPDE |
|---|---|---|
| universal edges | 280 | 1642 |
| classes with traversable edges | 1/13 | 13/13* |
| relation vocabulary | fixed (Feature edges) | derived from column headers |
| cardinality | not computed | derived by count |

\*Command rows store links as free-text descriptions that match no entity name → still 0 resolvable
edges. This is a workbook-data form issue (RP: relationships not stored as IDs/names), not an RPDE
algorithm gap. Handler/Gate/Module/Component/Category/Family/Role/Validator/Variable all now populate.

## Principle upheld
Registry stores raw facts; the ALGORITHM derives knowledge. RPDE derives edges + relation types +
cardinality from observed structure — no hardcoded relation list.
