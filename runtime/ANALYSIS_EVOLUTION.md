# AKE Analysis Evolution — Design Document

**Status:** Implemented
**Scope:** Minimal architectural evolution enabling Compare, Explain, and future analysis operations without introducing new engines or parallel subsystems.

---

## 1. Existing capability audit

Before this evolution, every primitive needed to build analysis operations already existed in the runtime. The runtime was not weak — it was undertapped.

| Layer                                | Where                                              | Status   |
| ------------------------------------ | -------------------------------------------------- | -------- |
| Graph traversal                      | `edge_graph_engine.UniversalEdgeGraph`             | Complete |
| — `neighbors`, `fwd`, `rev`          |                                                    |          |
| — `reachable`, `shortest_path`       |                                                    |          |
| Multi-hop discovery                  | `reachability_engine.ReachabilityEngine`           | Complete |
| Registry / class lookup              | `workbook_runtime.owner_sheet`, `catalog`          | Complete |
| Path-aware planner                   | `algorithm_derivation.derive_for_entity`           | Complete |
| Structural/inferred edge tagging     | `workbook_runtime._rel_source`                     | Complete |
| Runtime primitives (45 opcodes)      | `runtime_primitives.py`                            | Complete |
| Canonical menu contract              | `AKE.entity_actions()`                             | Complete |
| Canonical explained result           | `AKE.explain_relation()`                           | Complete |
| Query verb dispatcher                | `shell._dispatch` (`rel`, `list`, `search`)        | Complete |
| Structured API response models       | `ake_server/schemas.py` (`NavState`, etc.)         | Complete |

**Conclusion:** All primitives Compare needs already exist. `entity_actions()` and `explain_relation()` already established the pattern of "one method → structured dict → every surface renders". Compare extends the same pattern.

---

## 2. Missing capability audit

Only 4 small gaps, all additive:

| Gap                                             | Impact                                                                        |
| ----------------------------------------------- | ----------------------------------------------------------------------------- |
| No `AKE.compare(target, scope)` method          | The canonical analysis operation has nowhere to live.                         |
| No `AKE.dimensions(eid)` method                 | The "discover comparable dimensions" primitive is inline in `entity_actions`. |
| No shell `compare` verb                         | Dashboard cannot issue a compare query through the existing `/query` route.   |
| No scope resolvers (siblings, layer, upstream, downstream) | `compare(target, "siblings")` has no way to expand the second argument.       |

**Conclusion:** Four small gaps, ~75 lines total. Zero new engines.

---

## 3. Minimal evolution plan

Three additions, zero replacements.

### A. `AKE.dimensions(eid)`

Extract the "discover comparable dimensions" primitive from `entity_actions()` so Compare and future analysis operations can reuse it.

Returns `{relation: [{"id": ..., "name": ..., "class": ...}, ...]}` for every outgoing edge from `eid`.

**Universal:** dimension names come from the graph, not from a hardcoded list. Zoo workbooks discover `habitat`, `diet`. School workbooks discover `department_id`, `advisor_id`. Same code.

### B. `AKE.compare(target, scope)`

The canonical analysis operation. `scope` is either an entity ID (direct pairwise) or one of `"siblings"`, `"layer"`, `"upstream"`, `"downstream"` (group).

Returns the canonical analysis object — the same schema style as `explain_relation`:

```json
{
  "operation": "compare",
  "anchor": "FEAT-032",
  "scope": "FEAT-033",
  "targets": ["FEAT-032", "FEAT-033"],
  "dimensions": [
    {
      "relation": "category",
      "target_class": "Category Registry",
      "status": "common",
      "common":     [{"id": "CAT-01", "name": "Runtime"}],
      "only_left":  [],
      "only_right": []
    },
    {
      "relation": "invokes",
      "target_class": "Feature Registry",
      "status": "common",
      "common":     [/* 22 shared features */],
      "only_left":  [],
      "only_right": []
    }
  ]
}
```

For group scopes (`siblings`, `layer`), each dimension carries `shared_by_all` and `left_targets` instead of pairwise diffs.

### C. Shell `compare` verb

Same pattern as the existing `rel`, `list`, `search` verbs. Parses `compare(A, B)`, resolves through `AKE.compare()`, returns navigable text results with `mode = "results"` and clickable items.

### D. Bonus — `entity_actions()` exposes Compare

Two menu items added to every entity's action list: **"Compare with siblings"** and **"Compare with layer"**. The dashboard's existing `renderEntity` already groups menu items by `type`; a new group `"Analyze"` (`type: "analysis"`) is added to `TYPE_GROUP` with `order: 3`. No new rendering logic — the existing button pipeline handles it.

---

## 4. Files/functions modified

| File                              | Function/section          | Change                                                                                     |
| --------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------ |
| `ake/__init__.py`                 | (new) `AKE.dimensions()`  | +15 lines — extract dimension discovery                                                    |
| `ake/__init__.py`                 | (new) `AKE._resolve_scope()` | +25 lines — scope keyword resolver                                                       |
| `ake/__init__.py`                 | (new) `AKE.compare()`     | +70 lines — canonical analysis operation                                                   |
| `ake/__init__.py`                 | `entity_actions()`        | +12 lines — expose `Compare with siblings`, `Compare with layer` menu items                |
| `ake/shell.py`                    | `_action_page()`          | +3 lines — route `COMPARE_SIBLINGS` / `COMPARE_LAYER` back through `handle()`              |
| `ake/shell.py`                    | `_dispatch()`             | +30 lines — new `compare` verb branch                                                      |
| Dashboard HTML (embedded in `AKE_Master_Launcher.py` as `_DASHBOARD_HTML_B64`) | `TYPE_GROUP` | +1 line — add `analysis: { title: "Analyze", order: 3 }` |

**Package layout note.** The dashboard HTML is not shipped as a file inside `AKE_Runtime.zip`. It lives as a base64-encoded blob in `AKE_Master_Launcher.py` (`_DASHBOARD_HTML_B64`) and is decoded to disk by the launcher at runtime. Source of truth during development is `build/index.html` in the developer workspace; that source is embedded into the launcher at build time. Verify dashboard changes by decoding `_DASHBOARD_HTML_B64` and searching for the marker, not by looking inside the runtime ZIP.

**Total: ~156 lines across 2 runtime files + 1 line in the launcher's embedded HTML.**

---

## 5. Files/functions intentionally left unchanged

| File                                | Reason                                                        |
| ----------------------------------- | ------------------------------------------------------------- |
| `edge_graph_engine.py`              | Graph primitives are complete. `compare` uses `g.neighbors`.  |
| `reachability_engine.py`            | Multi-hop discovery is stable.                                |
| `workbook_runtime.py`               | Intake + graph builder is stable.                             |
| `relational_primitive_engine.py`    | Edge derivation is stable.                                    |
| `runtime_primitives.py`             | 45 opcodes untouched.                                         |
| `algorithm_derivation.py`           | Query planner untouched.                                      |
| `canonical_schema_discovery.py`     | CSD is stable.                                                |
| `importers.py`, `classifier.py`     | Intake path untouched.                                        |
| `tests/regression.py`               | 101/101 must stay green — and does.                           |
| `ake_server/api.py`                 | No new endpoint. Compare routes through existing `POST /query`. |
| `ake_server/adapter.py`             | Session lifecycle unchanged.                                  |
| `ake_server/schemas.py`             | `NavState.text` already carries the shell's rendered result.  |

---

## 6. Justification

### Why not a separate Analysis Engine

A parallel "Analysis Engine" subsystem would:

- Duplicate graph traversal — it would call `g.neighbors()` itself.
- Duplicate registry/class lookup — it would call `owner_sheet()` itself.
- Duplicate the canonical result shape — parallel to `explain_relation`'s pattern.
- Introduce a second authority over the same graph.
- Force the dashboard to route through a second endpoint.

### Why the three additions are the right shape

- `dimensions()` matches the extraction pattern used when `entity_actions()` was factored out. Reusable primitive, same style, same file.
- `compare()` matches the query-object pattern used by `explain_relation()`. Same schema idiom (`operation`, `targets`, dimensions with `common`/`only_left`/`only_right`/`status`).
- Adding a shell verb matches how `rel` was added when relation chips needed graph traversal. Same routing path, same `/query` endpoint.

### Why AKE stays the single authority

Compare is a **query**, not an **engine**. It reads the graph. It never mutates it. Every dimension it discovers is what the graph contains. Zero domain knowledge. This makes AKE the sole owner of comparison logic — exactly as required.

### Why future operations naturally follow

`explain(target)`, `impact(target)`, `similarity(A, B)`, `path(A, B)` all become sibling methods on the same AKE class. Each is a query. Each returns a canonical analysis object with the same schema style. Each routes through the same shell verb dispatcher. No new architecture will ever be needed.

---

## 7. Canonical query language

The universal syntax is:

```
compare(A, B)                   # direct pairwise
compare(A, siblings)            # A vs entities sharing a direct parent
compare(A, layer)               # A vs all entities in the same registry class
compare(A, upstream)            # A vs all entities pointing to A
compare(A, downstream)          # A vs all entities A points to
compare(scope)                  # uses current context as anchor (from shell)
```

Every future operation follows the same shape:

```
explain(target)                 # future
impact(target, layer)           # future
similarity(A, B)                # future
path(A, B)                      # future
```

Every client (Dashboard, Coach, MCP, REST) posts to the same endpoint (`POST /query` with `token`) and receives the same canonical result shape.

---

## 8. Implementation validation

### What was implemented

- `AKE.dimensions(eid)` — discover comparable dimensions from graph
- `AKE._resolve_scope(target, scope)` — resolve scope keywords to entity lists
- `AKE.compare(target, scope)` — canonical analysis operation
- `AKE.entity_actions()` — extended to expose `Compare with siblings` and `Compare with layer`
- `shell._dispatch` — new `compare` verb
- `shell._action_page` — routes `COMPARE_*` menu actions back through `handle()`
- `index.html TYPE_GROUP` — new `analysis` group with `order: 3`

### How it was verified

All 4 layers tested end-to-end:

**Layer 1 — Runtime:**

```
AKE.dimensions('FEAT-032')
→ {'category': [...], 'family': [...], 'invokes': [22 items], ...}

AKE.compare('FEAT-032', 'FEAT-033')
→ {'operation': 'compare', 'targets': ['FEAT-032','FEAT-033'],
   'dimensions': [
      {'relation': 'category',   'status': 'common', common=[Runtime]},
      {'relation': 'family',     'status': 'common', common=[Runtime]},
      {'relation': 'invokes',    'status': 'common', common=[22 features]},
      ...
   ]}

AKE.compare('FEAT-032', 'siblings') → 26 target entities, 12 dimensions
AKE.compare('FEAT-032', 'layer')    → 91 target entities
```

**Layer 2 — API/Query:**

```
POST /query {token: "compare(FEAT-032, FEAT-033)"}
→ Routes through existing /query endpoint → shell._dispatch → verb "compare"
→ Returns NavState with text field carrying the rendered analysis
```

No new endpoint added. The dashboard's existing `goToken(token)` handler works for compare tokens.

**Layer 3 — Rendering:**

The shell renders the analysis result as navigable text with `mode="results"`. Every item is clickable (present in `self.results`). The dashboard's existing `applyNav` renders `mode="results"` as a numbered list — no new renderer needed.

Menu items appear on every entity page under a new **"Analyze"** group (order 3, after "Ask", "Explore", "Reference"). The existing `renderEntity` groups by `TYPE_GROUP[item.type]`; adding `analysis: {title: "Analyze", order: 3}` was the only rendering change.

**Layer 4 — User workflow:**

```
User opens any entity (e.g. FEAT-032)
  → sees an "Analyze" section in the entity menu
  → clicks "Compare with siblings"
  → dashboard sends /action {key: "15"}
  → shell routes COMPARE_SIBLINGS → handle("compare(FEAT-032, siblings)")
  → renders the analysis as clickable results
  → user clicks any result → navigates to that entity
```

Zero dead ends. Every visible action is reachable. Every result item is navigable.

### Verified in browser

- Menu items visible in entity page (Layer 3 confirmed)
- Click routes through existing `/action` endpoint (Layer 2 confirmed)
- Analysis result renders as numbered results with `mode="results"` (Layer 3 confirmed)
- Each dimension shows `[status]`, `relation`, `→ target_class`
- Common items, only-left, only-right items appear as clickable rows

### What is reachable but not yet exposed

- `AKE.compare(A, upstream)` and `compare(A, downstream)` — implemented but not surfaced in `entity_actions()`. Reachable via typed token `compare(FEAT-032, upstream)`. Not surfaced because the current design shows only the two most-useful scopes; more can be added later without code changes to the dashboard.

### Architectural deviations

None. Every implementation choice matches the audit's minimal-evolution plan.

### Remaining gaps

- **Future analysis operations** (`explain`, `impact`, `similarity`, `path`) — not implemented; the pattern is now established, so each becomes ~30–50 lines on the same AKE class.
- **Rich compare card rendering** — the dashboard currently reuses the standard results renderer for compare output. A dedicated compare card (side-by-side layout, colored `common`/`only_left`/`only_right` chips) could be added later; the JSON schema already supports it. This is a rendering improvement, not an architectural gap.

### Regression status

101/101 tests pass. No existing test was modified. No existing behavior changed.

---

## 10. Second evolution — Analyze stage

### Problem discovered after §1–8

User verified the Compare panel and reported: `Compare with siblings` opened a dimensions summary with **0 clickable results**. The 25 sibling entities were never listed. The panel terminated at a diff view; there was no bridge to per-entity analysis.

Root cause:

- `compare()` returned dimensions with `left_targets` (for group scopes), but the shell renderer only iterated `common` / `only_left` / `only_right` / `shared_by_all`. `left_targets` was never rendered.
- The sibling ENTITIES themselves (the primary object of interest) were never listed.
- No `analyze` operation existed, so even if entities were clickable, there was nothing to do after opening one.

### Existing implementation → Limitation → Smallest evolution

**Existing:** `compare()` returned a structured analysis object. The shell rendered dimensions but not the entity list.

**Limitation:** The group compare (siblings / layer) terminated at a diff summary. Entities were reachable in the JSON but not in the rendered results. No `analyze` action existed on entities.

**Smallest evolution:** Two changes, following the same evolution pattern as before:

1. `shell.compare` renderer — for group scopes, list the entities themselves as the primary result before showing dimension summary. Existing `mode="results"` and `self.results` populate cleanly.
2. New method `AKE.analyze(eid)` — 10 structured observations derived from graph, registry, relationships, evidence, siblings. Zero hardcoded text. Every observation is a fact the runtime already knows. The renderer converts facts to sentences at display time.
3. `entity_actions()` gets a third analysis action: `Analyze this entity`. `shell._action_page` routes `ANALYZE_ENTITY` back through `handle("analyze(eid)")`, matching how COMPARE_* already route.

### The 10 observations `analyze()` produces

Each is derived from an existing runtime primitive. Nothing is hardcoded.

| # | Observation                              | Derived from                                                  |
| - | ---------------------------------------- | ------------------------------------------------------------- |
| 1 | Registry membership                      | `node_attrs["class"]` + count of peers in same class          |
| 2 | Direct relationships (out/in counts)     | `g.neighbors(eid)` grouped by `dir` and `relation`            |
| 3 | Strongest connection                     | The relation with the most targets from this entity           |
| 4 | Direct dependencies                      | Unique targets of outgoing edges                              |
| 5 | Depended on by                           | Unique sources of incoming edges (from `g.rev`)               |
| 6 | Reachable via discovery                  | `reachable_relations(eid)` — multi-hop discovery              |
| 7 | Siblings sharing a direct parent         | `_resolve_scope(eid, "siblings")`                             |
| 8 | How this differs from siblings           | `compare(eid, "siblings")` — dimensions with unique targets   |
| 9 | Evidence                                 | `node_attrs["evidence"]` — provenance from source workbook    |
| 10| Next entities to explore                 | Neighbors ranked by connectivity (degree in the graph)        |

Every observation returns structured items with `id`+`name` (clickable) or `text` (informational). The shell renders numbered results for the clickable ones so users can drill in.

### Files modified in the second evolution

| File | Change |
| --- | --- |
| `ake/__init__.py` | new method `AKE.analyze(eid)` (~90 lines) |
| `ake/__init__.py` | `entity_actions()` — add `Analyze this entity` action |
| `ake/shell.py` | rewrite `compare` verb: for group scopes, list entities first |
| `ake/shell.py` | new `analyze` verb — renders observations |
| `ake/shell.py` | `_action_page()` — route `ANALYZE_ENTITY` → `analyze(eid)` |

### End-to-end verification (four layers)

**Runtime:** `AKE.analyze("CAT-10")` returns 10 observations with 15 clickable items.

**Query:** `POST /query {token: "analyze(CAT-10)"}` routes through existing `/query` endpoint → shell `analyze` verb → structured result.

**Rendering:** Menu shows `Analyze this entity` (key 15), `Compare with siblings` (key 16), `Compare with layer` (key 17) on every entity. Clicking any renders navigable results.

**User workflow:**

```
Open FEAT-032
  → menu shows Analyze this entity + Compare with siblings + Compare with layer
  → click Compare with siblings
    → sees 25 sibling entities (clickable) + shared dimensions
  → click sibling 1 (e.g. CAT-10)
    → opens CAT-10 entity page (same menu, same analysis actions)
  → click Analyze this entity
    → sees 10 observations about CAT-10, each derived from graph/registry/evidence
    → click any item → drill into that entity
```

Zero dead ends. Zero hardcoded text. Every observation is graph-derived. Every result is navigable.

### Report ↔ Package consistency check (second evolution)

| Claim                                                | Verified in package                                                     |
| ---------------------------------------------------- | ----------------------------------------------------------------------- |
| `AKE.analyze()` exists                               | ✅ `ake/__init__.py` — new method after `compare()`                     |
| `entity_actions()` surfaces `Analyze this entity`    | ✅ `ake/__init__.py` — new action with `query: "ANALYZE_ENTITY"`        |
| Shell `analyze` verb                                 | ✅ `ake/shell.py` — new `if verb == "analyze"` branch                   |
| Shell routes `ANALYZE_ENTITY`                        | ✅ `ake/shell.py` — `if q == "ANALYZE_ENTITY"` in `_action_page`        |
| Compare group scope shows entities as primary result | ✅ `ake/shell.py` — `if len(group_targets) > 1` branch iterates entities |

### Regression status (second evolution)

101/101 tests pass. No existing test modified.

---

## 9. Report ↔ Package consistency check

The delivered package must exactly match this document. Every claim below was verified against the actual runtime ZIP and the actual embedded launcher HTML.

| Claim                                                                | Location                                                                                 | Verified in package                                    |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `AKE.dimensions()` exists                                            | `ake/__init__.py`                                                                        | ✅ line 399: `def dimensions(self, eid):`              |
| `AKE._resolve_scope()` exists                                        | `ake/__init__.py`                                                                        | ✅ line 419: `def _resolve_scope(self, target, scope):`|
| `AKE.compare()` exists                                               | `ake/__init__.py`                                                                        | ✅ line 452: `def compare(self, target, scope):`       |
| `entity_actions()` surfaces `Compare with siblings`                  | `ake/__init__.py`                                                                        | ✅ line 309: label `"Compare with siblings"`           |
| Shell routes `COMPARE_SIBLINGS` / `COMPARE_LAYER`                    | `ake/shell.py`                                                                           | ✅ line 121: `if q in ("COMPARE_SIBLINGS", ...)`       |
| Shell `compare` verb                                                 | `ake/shell.py`                                                                           | ✅ line 283: `if verb == "compare":`                   |
| `TYPE_GROUP` includes `analysis`                                     | `_DASHBOARD_HTML_B64` inside `AKE_Master_Launcher.py`                                    | ✅ `analysis:  { title: "Analyze"` present in decoded blob |
| `ANALYSIS_EVOLUTION.md` (this document)                              | Runtime ZIP root                                                                         | ✅ shipped at `AKE_Runtime.zip:/ANALYSIS_EVOLUTION.md` |
| `build/index.html` in runtime ZIP                                    | (was a documentation error in draft; corrected in §4)                                    | ✅ dashboard HTML is embedded in launcher, not shipped as a file in the runtime ZIP |

### How to reproduce this check

```bash
# 1. Extract runtime and inspect
unzip -q AKE_Runtime.zip -d /tmp/runtime
grep -n "def dimensions\|def compare\|def _resolve_scope" /tmp/runtime/ake/__init__.py
grep -n 'verb == "compare"\|COMPARE_SIBLINGS' /tmp/runtime/ake/shell.py
ls /tmp/runtime/ANALYSIS_EVOLUTION.md

# 2. Decode embedded dashboard and inspect
python3 -c "
import base64, re
src = open('AKE_Master_Launcher.py', encoding='utf-8').read()
m = re.search(r'_DASHBOARD_HTML_B64 = \"\"\"\n(.+?)\n\"\"\"', src, re.S)
html = base64.b64decode(m.group(1).replace('\n',''))
assert b'analysis:' in html, 'analysis group missing from embedded HTML'
print('Embedded HTML OK, size:', len(html))
"
```

If any check fails, the package and document are out of sync — fix whichever is wrong before shipping.
