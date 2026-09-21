# AKE Execution Architecture Audit

Scope: identify the single execution planner *by execution authority* (not by class name),
trace every entry point's real call chain, and prove whether they converge. No new code.

Method: static call-chain tracing through the actual runtime (`ake/__init__.py`, `ake/shell.py`,
`ake/runtime_engine.py`, `ake/algorithm_derivation.py`, `server/ake_server/api.py`).

---

## 1. Is there an execution planner? YES — and it is not what the last report implied.

The execution authority is **`RuntimeEngine.run(plan, req)`** (`ake/runtime_engine.py`), wired as
`self.engine` in `AKE.__init__` (`ake/__init__.py:30`). Its contract:

```
def run(self, plan, req):
    ctx = {"token": req.get("target")}
    for fn, kwargs in plan:            # plan = ordered list of (opcode, kwargs)
        getattr(self.rp, fn)(ctx, **kwargs)   # execute each opcode against runtime primitives
        trace.append(fn)
    return {"result", "evidence", "executed": trace, "target"}
```

A **plan** is a canonical operation sequence: an ordered list of `(opcode, kwargs)`. Plans are
compiled by two planner components, both feeding `engine.run`:
- **`AlgorithmDerivation`** (`ake/algorithm_derivation.py`, header: *"M10 — Algorithm Derivation
  (deterministic planner)"*) — `derive_for_entity()` produces a path-aware plan.
- **`AlgorithmGenerator`** (`ake/algorithm_generator.py`) — `compile(request)` returns
  `(qid, seq, plan)`.

So the execution authority = **RuntimeEngine.run**, and the planning authority = **AlgorithmDerivation
/ AlgorithmGenerator** which emit the opcode sequence it runs.

**Callers of `engine.run` (verified — only three):**
- `AKE.run_query()` — `__init__.py:66`
- `AKE.derive_algorithm()` — `__init__.py:549`
- `AKE.generate_algorithm()` (compile path) — `__init__.py:562`

---

## 2. Entry-point call chains (traced, with evidence)

| Entry point | API route | Call chain | Reaches `engine.run`? |
|---|---|---|---|
| **Entity open** | `/query`, `/action` | `shell.handle()` → `open_object(eid)` → reads `self.model.universal_graph` directly | **NO** |
| **Analyze** | `/action` → `shell.handle("analyze(...)")` | `shell` verb `analyze` → `ake.analyze(eid)` → operates directly on `universal_graph` (`__init__.py:1021`) | **NO** |
| **Compare (siblings / layer)** | `/action` → `shell.handle("compare(...)")` | `shell` verb `compare` → `ake.compare(target, scope)` → direct `universal_graph` + `_resolve_scope` (`__init__.py:936`) | **NO** |
| **Perspective** | `/perspective` | `ake.perspective()` → `SemanticPerspectiveEngine` traversal on `universal_graph` | **NO** |
| **Intersect** | `/intersect` | `ake.intersect()` → `SemanticPerspectiveEngine` | **NO** |
| **/discover** | `/discover` | `ake.discover()` → `resolve()` + `graph.path_between()` + `suggest_next()` | **NO** |
| **Search** | `/search` | `ake.search()` directly (api.py comment: *"shell skipped"*) | **NO** |
| **run_query / derive_algorithm** | (not a dashboard button) | `engine.run(plan, req)` | **YES** |

---

## 3. Verdict: the entry points DIVERGE. The claim in the last report was not proven — and is false.

- The six user-facing operations (**entity open, analyze, compare, perspective, intersect,
  /discover**) do **NOT** converge on `RuntimeEngine.run`. Each reads `self.model.universal_graph`
  directly through its own method.
- The planner (`RuntimeEngine` + `AlgorithmDerivation/Generator`) is only reached by
  `run_query` / `derive_algorithm` / `generate_algorithm`, which the dashboard buttons do not call.
- Therefore "single-authority planner" was accurate only in the narrow sense that **one shared
  graph** (`universal_graph`) is the single source of truth for data. It was **not** accurate that
  one execution planner sequences all operations. Two different things were conflated.

There is **one execution authority that is actually universal**, but it is one level down: every
entry point above ultimately reads the **single `UniversalEdgeGraph`** built once at load. No
entry point builds a second graph or re-derives the workbook. That is the real invariant that
holds; the "single planner" framing was not.

---

## 4. Operation-sequence gap for natural queries (the second challenge)

Requested proof: does `"Brand 1 total customers"` become

```
Resolve Brand → Traverse Product → Traverse OrderItem → Traverse Order → Unique Customer → Count
```

**before** graph execution?

**Finding: NO — that capability does not exist today, in any entry point.**

- `/discover` resolves ONE target and finds a path; it does not parse a multi-clause intent
  ("total", "customers") into an aggregation opcode sequence. It has no COUNT / UNIQUE / AGGREGATE
  step. Trace: `discover()` → `resolve(query)` (single entity) → `path_between` → `suggest_next`.
  There is no operation compiler on this path.
- The only component that emits an opcode sequence is `AlgorithmDerivation/Generator` → `engine.run`,
  but (a) the dashboard/`/discover` never call it, and (b) its opcodes are graph-walk/analysis
  primitives (`walk_*`, etc.), not natural-language-derived aggregation plans. It compiles from a
  fixed `QUERY_DEFINITIONS` registry, not from free text like "total customers".
- `"John buys which brand most"` similarly has no path: nothing tokenises an intent into
  `Customer → Brand → group → count → argmax`.

So the "Ask anything" box currently maps a query to **one resolved entity + a path**, not to a
**canonical operation sequence**. The user's concern is correct: as built, it is a new front door
to the existing single-entity/path capability, **not** an operation planner. Making
`"Brand 1 total customers"` work would require an intent→operation compiler that emits an opcode
sequence for `engine.run` — which does not exist and was not added.

---

## 5. Embedding / ANN status (third challenge)

Confirmed: **no embeddings or ANN were added.** `KNOWN_LIMITATIONS` states the L5 tier "can be
swapped for embeddings without backend changes" — that is a future hook, not an implementation.
Evidence-tier L5 is `difflib` lexical similarity (`SequenceMatcher`), verified in
`entity_resolver.py` and the evidence ladder. If the goal was semantic search **now**, it is not
done.

---

## 6. Recommendation (no code changed in this audit)

To make the claims true without new parallel engines, the minimal, reuse-only path is:

1. **Converge execution on the existing planner.** Route `analyze`, `compare`, `perspective`,
   `intersect`, and `/discover` so their graph operations are expressed as **plans executed by
   `RuntimeEngine.run`**, instead of each calling `universal_graph` directly. The opcodes they need
   (traverse, collect, compare, count, unique) become runtime primitives on `self.rp`. This gives a
   genuine single execution authority — the thing the last report claimed.
2. **Add an intent→operation compiler in front of the existing planner** (not a new executor): a
   component that turns `"Brand 1 total customers"` into the canonical
   `(resolve, traverse×N, unique, count)` opcode sequence, then hands it to `RuntimeEngine.run`.
   This is the "canonical intent object → existing planner" design the user described. Rule-based
   first; an embedding front-end can replace only the intent-parsing stage later.
3. **Only then** is "Ask anything" more than a new UI — it becomes the front of a real operation
   pipeline with one execution authority.

None of the above is implemented here — this document is the audit and the evidence, as requested.

---

## Appendix — exact line references

- Execution authority: `ake/runtime_engine.py::RuntimeEngine.run`
- Planner: `ake/algorithm_derivation.py` (header line 1), `ake/algorithm_generator.py::compile`
- `engine.run` callers: `ake/__init__.py:66, 549, 562`
- Bypassers (direct graph): `analyze` `__init__.py:1014`, `compare` `__init__.py:927`,
  `discover` `__init__.py:303`, `perspective`/`intersect` via `semantic_perspective.py`,
  `open_object` `shell.py:246`
- Single shared graph (the real invariant): `ake/workbook_runtime.py::_build_universal_graph`,
  one `UniversalEdgeGraph`, built once; no entry point re-reads the workbook (proven separately in
  the certification audit: 0 file reopens across 4000 queries).

---

# ADDENDUM — Plan Ownership Trace (per-feature)

Question: for each feature, WHO creates the plan, WHO owns the operation sequence, WHO executes,
and is RuntimeEngine the planner or just the executor? Proven by instrumenting all three roles
(plan creators + executor) and calling each feature.

## Role classification (proven)

**RuntimeEngine = EXECUTOR ONLY.** Its entire class is one method `run(plan, req)` that iterates a
plan it is *given* and calls `getattr(self.rp, fn)(ctx, **kwargs)` per opcode. It contains zero
plan-creation logic — no query-type branching, no opcode selection. It cannot plan; it can only
execute a plan handed to it. (`ake/runtime_engine.py`, full class is ~14 lines.)

**Plan creators = THREE distinct sites (not unified):**

| `engine.run` caller | Plan builder | Plan source | Role |
|---|---|---|---|
| `AKE.run_query` (`__init__.py:65`) | inline list-comprehension over `query["pipeline"]` | a pre-defined query object | simple binder |
| `AKE.derive_algorithm` (`__init__.py:548`) | **`AlgorithmDerivation.derive_for_entity`** | reachability registry, path-aware | **canonical planner** |
| `AKE.ask` (`__init__.py:561`) | `AlgorithmGenerator.compile` | Query Type Registry pipeline | pipeline binder |

**Canonical plan creator = `AlgorithmDerivation.derive_for_entity`** (`ake/algorithm_derivation.py:151`).
It is the only creator that owns a *derived, path-explicit* operation sequence:
`resolve_entity → walk_discovery(path,hops) → attach_evidence → render_*`, built from the
reachability registry with no hardcoded names. The other two only bind a pre-listed pipeline.

## Per-feature ownership (instrumented, call-counted)

| Feature | Plan creator invoked | engine.run invoked | Who executes | Verdict |
|---|---|---|---|---|
| Entity Open | none (0) | some paths call run with an INLINE plan | RuntimeEngine (when at all) | does not use the canonical planner |
| Analyze | none (0) | **0** | reads `universal_graph` directly | **bypasses planner + executor** |
| Compare | none (0) | **0** | reads `universal_graph` directly | **bypasses planner + executor** |
| Perspective | none (0) | **0** | `SemanticPerspectiveEngine` on graph | **bypasses planner + executor** |
| Intersect | none (0) | **0** | `SemanticPerspectiveEngine` on graph | **bypasses planner + executor** |
| Discover | none (0) | **0** | `resolve` + `path_between` + `suggest_next` | **bypasses planner + executor** |

Empirical result (call counts): Analyze/Compare/Perspective/Intersect/Discover → **0** calls to
both the plan creators AND `engine.run`. They each read the single `universal_graph` directly.

## Conclusion (this closes the open questions)

1. **RuntimeEngine is the executor, not the planner.** Proven: single `run(plan,req)` method, no
   planning logic.
2. **AlgorithmDerivation is the canonical plan creator.** Proven: it is the only site that derives
   a path-explicit opcode sequence from the reachability registry.
3. **The dashboard bypasses both.** Proven: all six features reach neither the planner nor the
   executor; they operate on the shared graph directly.

Therefore the user's proposed target architecture is exactly right and requires **no new engine**:

```
Natural Query → Intent Adapter → Canonical Plan
   → AlgorithmDerivation (existing planner, extended to accept the plan)
   → RuntimeEngine (existing executor)
   → Universal Graph → Analysis → Evidence
```

The only genuinely missing piece is the **Intent Adapter** (natural query → canonical opcode
sequence). The planner (`AlgorithmDerivation`) and executor (`RuntimeEngine`) already exist and
already have the right separation of authority; the work is to route the six features through them
instead of direct graph access, and to add the intent→plan front stage. No parallel executor, no
second planner, no new graph.
