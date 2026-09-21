# Lifecycle Population Operation (Runtime Engine execution path) — FROZEN

**Not a new architectural engine.** Lifecycle population is the execution of the existing **LIFECYCLE
query** through the frozen Query → Primitive Sequence inside the existing **Runtime Engine**. The
architecture is unchanged:
```
Query "CMD-002 lifecycle"
  → Query Registry (LIFECYCLE_RECONSTRUCT)
  → Algorithm Generator (Query → Primitive Sequence)
  → Runtime Engine executes: resolve_entity → walk_execution → walk_relationship → attach_evidence → render_timeline
  → populate fixed lifecycle template → render result
```
`lifecycle.py` is an **implementation module** of this operation (result structuring over the IR the
Runtime primitives traverse) — it introduces no new engine, no new primitive, no lifecycle change.

## Fixed universal lifecycle template (canonical)
```
Entity → Entry → Handler → Gate → Pipeline → Bridge → Validator → Module → Output → Evidence
```

## Empty-stage classification (empty ≠ gap)
| status | meaning | phase |
|---|---|---|
| not_referenced | column "Not Found"/empty — legitimately no such stage | — |
| compiler_missed | prose exact-matches entity in TARGET registry | Phase 1 |
| registered_other_type:R | prose exact-matches entity in registry R | Phase 3 |
| genuine_metadata_gap | prose exact-matches in NO registry | Phase 6 |

## Facade
```python
from ake import AKE
AKE("workbook.xlsx").lifecycle("CMD-002")   # runs the LIFECYCLE query; returns populated stages + reasons
```

Verified (regression 65/65): fixed 9-stage template; Handler/Pipeline/Module/Gate/Evidence populated
from IR; empty stages classified by reason; CMD-048 gates GATE-002/003.

Note: "system code" as a population source is out of scope for the AKE package (source not bundled;
evidence file:line references it only).
