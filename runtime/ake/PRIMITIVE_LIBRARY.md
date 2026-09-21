# Universal Runtime Primitive Library — FROZEN

Canonical source: `Capability Catalog` sheet (Opcode·Category·Input·Output·Cardinality·Composable-With·Executor).
Implemented in `runtime_primitives.py`. Frozen: adding a primitive requires a new library entry + executor.

## 45 primitives, 7 categories
| Category | N | Examples |
|---|---|---|
| Resolution | 6 | resolve_entity, resolve_pk, resolve_fk, owner_lookup, reference_lookup |
| Spreadsheet | 10 | op_filter, op_sort, op_group, op_aggregate, op_join, op_expand, op_project, op_distinct, op_search |
| Traversal | 8 | walk_parent, walk_child, walk_relationship, walk_dataflow, walk_upstream, walk_downstream, walk_execution, walk_lifecycle |
| Graph | 6 | graph_bfs, graph_dfs, graph_reachability, graph_dependency, graph_cycles, graph_shortest_path |
| Validation | 6 | check_fk, find_orphan, find_dead, find_missing_lifecycle, find_missing_evidence, find_duplicate |
| Analysis | 3 | op_compare, gap_analysis, explain |
| Rendering | 6 | attach_evidence, render_list, render_table, render_tree, render_graph, render_timeline |

## Minimality
Specific engineering walks are **compositions**, not new primitives:
- WALK_GATE = walk_relationship + relation filter (gate)
- WALK_PIPELINE = walk_relationship + relation filter (pipeline)
- FIND_OWNER = walk_parent ; FIND_PRODUCERS/CONSUMERS = walk_dataflow(in/out)

## Composition model (Query → Primitive Sequence)
Query-kind → primitive sequence is DATA (Query Family Registry) + entity-first applicable queries
(`query_discovery.py`). Every sequence references only library primitives (closure-verified).

Lifecycle composition (defined; full execution pending Phase 3 Command edges):
```
LIFECYCLE_RECONSTRUCT = resolve_entity → walk_execution → walk_relationship → attach_evidence → render_timeline
```

## Verification (regression)
- Library: 45 primitives cataloged, 100% implemented.
- Composition closure: every primitive referenced by any query pipeline is in the library (0 outside).
- LIFECYCLE_RECONSTRUCT uses only library primitives.

## Status
Phase 1 (Universal Runtime Primitive Library) + Phase 2 (composition model) COMPLETE + FROZEN.
Phase 3 (Command prose → typed IR edges → executable lifecycle) is the next finding.
Full algorithmic sequence *derivation* (M10) remains open research (OP-005); current composition is registry-driven.
