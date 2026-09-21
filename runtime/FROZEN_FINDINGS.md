# AKE — Frozen Findings (canonical compiler stages)

Both findings completed the lifecycle: Finding → Design → Implementation → Verification → Measurement
→ Regression → Evidence → COMPLETE. Regression: `python tests/regression.py` (17/17 pass).

## Finding RP-13 — FK ≠ Edge (missing knowledge-compilation pass)
- Root cause: FK observed but never compiled into typed traversable edges; edge graph was Feature-only.
- Implementation: `relational_primitive_engine.py` (RPDE) + `edge_graph_engine.py`.
- Status: **FROZEN** as canonical compiler stage.

## Finding — Edge-graph IR attribute-incomplete
- Root cause: IR carried edges only; node attributes (has_PK/has_Evidence/lifecycle/execution) absent.
- Implementation: Universal **Property Graph** (`_build_node_attributes` in `workbook_runtime.py`,
  `UniversalEdgeGraph.node_attrs/attrs()`).
- Status: **FROZEN** as canonical IR.

## Frozen compiler pipeline
```
Workbook → Observation → Primitive → RPDE → Universal Property Graph (Canonical IR)
        → Invariant → Query Discovery → Algorithm Generator → Runtime
```
Four-layer separation: Registry=facts · RPDE=knowledge compilation · Property Graph=canonical
engineering knowledge (IR) · Runtime=knowledge execution.

## Sufficiency statement (scoped, paper-safe)
Within the evaluated engineering workbooks (EBIS v17, robotics), the Universal Property Graph was
sufficient to derive all evaluated downstream outputs (relationship + attribute + graph invariants,
lifecycle/execution/evidence queries, rendering) without re-reading the source workbook.

## Open (not claimed complete)
- Whole-system universality (loader/resolver F-04..F-08; Command prose-links).
- Next research question: **What is the minimal canonical engineering IR?** (test whether temporal
  behavior / probabilistic confidence / execution traces are mandatory IR members or redundancy).
- Mechanical refactor: downstream engines still call the workbook in code (sufficiency proven, not yet
  enforced as IR-only).

## Completion criteria (extended)
A finding is COMPLETE only when, in addition to code+tests+verification+evidence+regression+docs+reproducible:
✓ Baseline generated (BASELINE.json)
✓ Schema version assigned (SCHEMA_VERSION.json)
✓ Known limitations recorded (KNOWN_LIMITATIONS.md)
Freeze artifacts: CHANGELOG.md, BASELINE.json, SCHEMA_VERSION.json, COMPATIBILITY.md, KNOWN_LIMITATIONS.md.

## F-021 — precise architecture conclusion
- Command IR substrate is now **partially** populated through compiler resolution; lifecycle reconstruction is now possible for **resolved** commands. Full coverage depends on canonicalizing remaining unmatched prose (F-022).
- **Algorithm Derivation (M10) remains an open research problem (OP-005).** Current lifecycle execution uses the **frozen composition model** over the populated IR, not a universally derived algorithm-synthesis mechanism.

## F-023 — investigation discipline verdict (per-reference phase localization)
Rule applied: unresolved reference is an INVESTIGATION CANDIDATE, not a gap, until root cause proven across
6 phases (registration → resolution → query → primitive → algorithm → metadata). Result for 181 refs:
- Phase 1 (compiler matcher format): 5 — FIXED ('/'-split).
- Phase 2/4/5 (resolution/primitive/algorithm): 0 — not the cause.
- Phase 3 (query targets wrong entity type): 7.
- Phase 6 (genuine source metadata gap, exact-absent in ALL registries): ~169–174.
Conclusion: "resolve fail ≠ registry-absent." Only exact-absent-in-all-registries is a metadata gap.

## F-024 — architecture correction (naming)
Lifecycle population is NOT a new architectural engine. It is the execution of the existing LIFECYCLE
query through the frozen Query → Primitive Sequence inside the existing Runtime Engine. `lifecycle.py`
(class LifecycleOperation) is an implementation module, not an engine. The frozen architecture is
unchanged:
Workbook → Discovery Primitive → Discovery → Rule Derivation → Query Derivation → Algorithm Generator → Runtime Engine.
