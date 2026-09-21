# M10 — Algorithm Derivation (deterministic planner) — FROZEN

## Architecture separation (corrected)
Query Derivation and Algorithm Derivation are SEPARATE:
```
User Input → Entity Resolver → Relation Inventory → Canonical Query Selection (frozen defs)
          → Algorithm Derivation (M10 planner) → Primitive Sequence → Execution → Evidence-backed Answer
```
- **Relation Inventory** (`RelationInventory`) reports which relation GROUPS an entity has
  (Identity/Ownership/Control/DataFlow/Classification/Evidence). It does NOT create queries.
- **Canonical Query Selection** offers only queries whose target relation is present in the inventory.
- **Algorithm Derivation** (`AlgorithmDerivation`) derives the primitive sequence.

## What is code vs data
- **DATA:** Query Definitions (`QUERY_DEFINITIONS`: objective·relation·direction·render) + relation
  inventory (from IR). Adding `GET_MONITORS` = one dict row → runtime supports it, no code change.
- **PLANNING RULES (deterministic, small):** objective → sequence shape:
  | objective | derived sequence |
  |---|---|
  | traverse | resolve_entity → walk_relationship(direction, relation) → attach_evidence → render_<type> |
  | attribute | resolve_entity → attach_evidence → render_table |
  | validate | resolve_entity → check_fk → render_table |
- **PRIMITIVE LIBRARY:** the frozen 45 primitives (sequence uses only these — closure-verified).

Sequence is NOT hardcoded per query and NOT produced by LLM reasoning. `derive()` has no query-name
branches (verified). It is derived from (query definition + registry schema + primitive library).

## Proven (regression 72/72)
- GET_HANDLER → resolve→walk_relationship→attach_evidence→render_tree; GET_UPSTREAM → …→render_graph (different).
- Every derived primitive ∈ library (closure). No hardcoded query-name branches.
- Relation inventory gates queries: GET_HANDLER absent for edge-less CMD-001, present for CMD-002.
- Execution: GET_HANDLER(CMD-002)→HND-026; GET_GATE(CMD-048)→GATE-002/003; GET_CATEGORY(FEAT-016)→CAT-02.
- Extensibility: GET_MONITORS auto-derives from a data row, no code change.
- Works across families (Command + Feature) via the same planner — new PKs are only an Entity-Resolver concern.

## Facade
```python
AKE(wb).relation_inventory("CMD-002")            # relation groups
AKE(wb).applicable_canonical_queries("CMD-002")  # queries selected from inventory
AKE(wb).answer("GET_HANDLER", "CMD-002")         # derive + execute -> evidence-backed
```

## Freeze statement (both validations PASSED)
```
M10
✓ Deterministic planner
✓ Primitive-library based execution
✓ Query-independent planning        [VALIDATED: name-independence]
✓ Registry-schema driven
✓ Family-independent pipeline
✓ Planner extensibility             [VALIDATED]
✓ Zero-code addition proof          [VALIDATED: GET_MONITORS, planner .py byte-identical]
```
- V1 (name-independence): rename-invariance holds; value-sensitivity holds; zero GET_* literals in planner logic.
- V2 (zero-code): Monitors relation added via workbook data + GET_MONITORS via query-definition registry (JSON);
  planner .py files byte-identical (md5 unchanged); GET_MONITORS derived + executed (NODE-1 -monitors-> MON-1).

## Remaining (explicitly NOT claimed)
Query DEFINITIONS are now data (registry). Planning RULES (objective→sequence) remain a small deterministic
rule set in code. Making planning rules registry-driven is the natural next evolution — it does not
invalidate M10. No "fully data-driven forever" claim is made until planning rules are also externalized.
