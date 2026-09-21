# AKE Operation Inventory Audit (Stage 2)

Every operation the planner can sequence, surveyed from code (`ake/runtime_primitives.py`,
executed by `RuntimeEngine.run`). For each: the **opcode** (the name the planner emits), the
**owner** (where the real logic lives), the **executor** (always `RuntimeEngine` → the primitive),
and **evidence** (whether the op contributes to `ctx["evidence"]`).

Status legend: **real** = implemented and executes; **STUB→now real** = was `return ctx`, made real
in this build by delegating to the existing owner (no new authority).

## Retrieval / resolution

| Operation | Opcode | Owner (real logic) | Executor | Evidence |
|---|---|---|---|---|
| Resolve entity | `resolve_entity` | `EntityResolver.resolve` (via `ctx`) | RuntimeEngine | seeds target |
| Load registry | `load_registry` | `WorkbookModel.rows` | RuntimeEngine | — |
| Resolve PK | `resolve_pk` | `WorkbookModel.owner_row` | RuntimeEngine | — |
| Resolve FK | `resolve_fk` | `WorkbookModel` FK cols | RuntimeEngine | — |
| Owner lookup | `owner_lookup` | `model.owner_by_prefix` | RuntimeEngine | — |
| Reference lookup | `reference_lookup` | graph neighbours | RuntimeEngine | edges |
| Search | `op_search` | `AKE.search` name index | RuntimeEngine | — |

## Tabular algebra (FILTER/GROUP/COUNT/SUM/AVG/MIN/MAX/UNIQUE/SORT/JOIN/PROJECT)

| Operation | Opcode | Owner | Executor | Evidence |
|---|---|---|---|---|
| FILTER | `op_filter` | primitive (col/pred over rows) | RuntimeEngine | — |
| SORT / ORDER | `op_sort` | primitive | RuntimeEngine | — |
| GROUP | `op_group` | primitive (`ctx["groups"]`) | RuntimeEngine | — |
| COUNT/SUM/AVG/MIN/MAX | `op_aggregate(fn)` | primitive (`ctx["metrics"]`) | RuntimeEngine | — |
| JOIN | `op_join` | primitive (key match) | RuntimeEngine | — |
| EXPAND | `op_expand` | primitive (FK expand) | RuntimeEngine | — |
| PROJECT | `op_project` | primitive | RuntimeEngine | — |
| UNIQUE / DISTINCT | `op_distinct` | primitive | RuntimeEngine | — |
| PIVOT | `op_pivot` | primitive | RuntimeEngine | — |

Note: `op_aggregate` covers COUNT today via group sizes; SUM/AVG/MIN/MAX over a numeric column are
added in this build (fn-parameterised) so RANK/aggregation intents have canonical execution.

## Graph traversal / discovery (TRAVERSE / PATH / DEPENDENCY / IMPACT / PERSPECTIVE)

| Operation | Opcode | Owner | Executor | Evidence |
|---|---|---|---|---|
| TRAVERSE (rel) | `walk_relationship` | graph fwd/rev | RuntimeEngine | edges+evidence |
| Upstream / Downstream | `walk_upstream`/`walk_downstream` | `walk_relationship` | RuntimeEngine | edges |
| Dataflow | `walk_dataflow` | `walk_relationship(flow)` | RuntimeEngine | edges |
| Multi-hop discovery | `walk_discovery` | reachability registry path | RuntimeEngine | path+confirmed ratio |
| Execution walk | `walk_execution` | exec sheets | RuntimeEngine | — |
| Lifecycle walk | `walk_lifecycle` | lifecycle sheet | RuntimeEngine | — |
| BFS | `graph_bfs` | graph | RuntimeEngine | nodes |
| **PATH (A→B)** | `graph_shortest_path` | **`UniversalEdgeGraph.path_between`** (bidirectional) | RuntimeEngine | per-hop evidence+tier |
| **DEPENDENCY** | `graph_dependency` | **`walk_relationship(direction=in)`** owner | RuntimeEngine | edges |
| **IMPACT / reachability** | `graph_reachability` | **`walk_relationship(direction=out)`** owner | RuntimeEngine | edges |

## Analysis / comparison (COMPARE / INTERSECT / RANK / EXPLAIN / EVIDENCE / GAP)

| Operation | Opcode | Owner | Executor | Evidence |
|---|---|---|---|---|
| **COMPARE** | `op_compare` | **`AKE.compare`** (siblings/layer/pairwise) | RuntimeEngine | dimensions+evidence |
| INTERSECT | (perspective op) | `SemanticPerspectiveEngine.intersect` | via facade | shared+paths |
| PERSPECTIVE | (perspective op) | `SemanticPerspectiveEngine.perspective` | via facade | bands+trails |
| RANK / TOP | `op_aggregate`+`op_sort` | primitive (metrics→sort) | RuntimeEngine | — |
| **EXPLAIN** | `explain` | **`AKE.explain_relation`** | RuntimeEngine | mode+per-edge evidence |
| EVIDENCE | `attach_evidence` | primitive (evidence cols+edges) | RuntimeEngine | ctx["evidence"] |
| GAP | `gap_analysis` | primitive (lifecycle grid) | RuntimeEngine | missing set |

## Validation / integrity

| Operation | Opcode | Owner | Executor | Evidence |
|---|---|---|---|---|
| FK check | `check_fk` | primitive | RuntimeEngine | violations |
| Orphans | `find_orphan` | primitive | RuntimeEngine | list |
| Dead nodes | `find_dead` | primitive | RuntimeEngine | list |
| Missing lifecycle | `find_missing_lifecycle` | primitive | RuntimeEngine | list |
| Missing evidence | `find_missing_evidence` | primitive | RuntimeEngine | list |

## Terminals (render)

`render_list`, `render_table`, `render_tree`, `render_graph`, `render_timeline` — all real; each
writes `ctx["result"]`.

## Stub → real in this build (delegating to existing owners, no new authority)

| Opcode | Was | Now delegates to |
|---|---|---|
| `op_compare` | `return ctx` | `AKE.compare` result into `ctx["result"]`/`ctx["evidence"]` |
| `graph_shortest_path` | `return ctx` | `UniversalEdgeGraph.path_between` → `ctx["path"]`+evidence |
| `graph_dependency` | `return ctx` | `walk_relationship(direction="in")` |
| `graph_reachability` | `return ctx` | `walk_relationship(direction="out")` |
| `explain` | `return ctx` | `AKE.explain_relation` → `ctx["result"]`+evidence |
| `op_aggregate` | count only | count/sum/avg/min/max over a numeric column |

Remaining intentional stubs (not on the required operation list; left as no-ops rather than faked):
`op_pivot`, `graph_dfs`, `graph_cycles`, `find_duplicate`. These have no current consumer and no
owner to delegate to; implementing them would be inventing behaviour, so they stay explicit no-ops.

## Conclusion

Every operation on the required list (TRAVERSE, FILTER, GROUP, COUNT, SUM, AVG, MIN, MAX, UNIQUE,
COMPARE, INTERSECT, RANK, SORT, DEPENDENCY, IMPACT, PERSPECTIVE, EXPLAIN, EVIDENCE, PATH, JOIN) has
a canonical opcode with a single real owner, executed by `RuntimeEngine`. The five stubs that
blocked this are made real by delegating to the existing owners — no parallel authority, no new
engine.
