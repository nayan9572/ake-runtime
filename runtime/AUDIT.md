# AKE Engineering Certification Audit v1.0 — RESOLUTION ADDENDUM

The three findings from the audit below have since been FIXED and verified (full regression
green, HTTP 22/22). Summary:

| Finding | Before | After | Evidence |
|---|---|---|---|
| **F-A HARDCODE-RPDE** | `relational_primitive_engine.py` branched on literals `"handler"` / `"Component"` | Literals removed; secondary target now DERIVED from where a column's values actually resolve (dominant target). 48 handler→Component edges preserved, 0 wrong-class. Tokenizer scan: no domain literals in RPDE code. | regression F-021/022/023 pass; edge count verified |
| **F-B SCALE-BUILD** | 100k-entity Phase-1 build = **256 s** (741k per-entity BFS, 5.6M `_class_of` calls) | Memoised `_class_of` + sampled candidates (≤40, deterministic stride, scaled confirmed count). Build = **35.4 s (7.2× faster)**. Queries still sub-ms. | reachability 32/32 + 13/13 + regression 101/101 |
| **F-C SCALE-SEARCH** | exact-name search = **~800 ms** at 100k (linear owner-row scan) | Name/id index built once at Phase-1; exact/prefix served from index with no scan. exact-name = **0.0 ms**. | latency re-measured; full regression green |

New capability added the same round: **Guided Discovery Engine** (`suggest_next`) — after any
resolution, ranked next-exploration suggestions derived from the graph (hop + importance +
relation multiplicity), never a fixed list; ambiguous → candidates, unknown → closest
entities (never dead-ended). Endpoints `/suggest` and suggestions embedded in `/perspective`
and context chains. Locked by `tests/test_guided_discovery.py` (10 checks).

Certification status upgraded: **PASS** (was CONDITIONAL PASS) for the runtime/architecture
axes. The one remaining CONDITIONAL item is unchanged — real-browser visual/console
verification still requires a browser outside this environment (dashboard verified by static
wiring + ASGI HTTP only).

---

# AKE Engineering Certification Audit v1.0

Scope: full certification of the AKE runtime, architecture, workbook loading, graph,
identity, API, dashboard wiring, and documentation before declaring "foundation complete".

Method (honest disclosure of what was and was NOT done):
- **Done:** Python-level static analysis (AST + tokenizer), whole-tree grep audits, in-process
  ASGI HTTP calls against the real gateway+server, a synthetic 100-registry / 100 000-entity
  scale run, memory and latency measurement, and the full automated test suite.
- **NOT done (cannot be done in this environment, not claimed):** real-browser click testing,
  visual rendering verification, and GPU/multi-process load. Dashboard verification is
  therefore static wiring + endpoint reachability only. Where a browser would be required, the
  item is marked **STATIC-ONLY** and the residual risk is stated.

Verdict summary: **CONDITIONAL PASS.** No blocker to continued development was found. One
**scale defect** (Phase-1 build time) and two **minor findings** (a domain-coupled heuristic
in RPDE; a linear search at scale) are documented below with root cause and recommended fix.
Everything else in the certification checklist passed with evidence.

---

## 1. Certification checklist — results

| # | Requirement | Result | Evidence |
|---|---|---|---|
| C-01 | ❌ No duplicate authority | **PASS** | One construction path (`AKE()` → `WorkbookModel`). `load_workbook` appears in two files but each is a single-format loader invoked once at construction (xlsx in workbook_runtime; the CSD copy is the CSV/TSV branch). No two components both own execution. |
| C-02 | ❌ No hidden hardcoding (decision logic) | **MOSTLY PASS — 1 finding** | AST/tokenizer scan of every `ake/*.py`: zero domain-word or entity-id literals in executable code. Registry/entity-noun-as-branch scan surfaced ONE real coupling in RPDE (`"handler"`/`"Component"`); see F-A. All other flagged literals (`"Registry Catalog"`, `"Architecture Registry Workbook"`) are the workbook FORMAT convention, not domain entities — legitimate. |
| C-03 | ❌ No stale runtime | **PASS** | Stress sequence (open→relation→open→back→back→home→search→context→home) leaves no stale menu/results/breadcrumb/context. `open_object` resets results+analysis; navigation invalidates `last_analysis`; snapshot/restore trims the crumb. |
| C-04 | ❌ No second graph | **PASS** | Exactly one `UniversalEdgeGraph`; object identity stable across 4 000 queries; CSD builds no graph. |
| C-05 | ❌ No workbook re-derivation | **PASS** | Over 4 000 queries: 0 file reopens, 0 `load_workbook` calls (both instrumented). Queries are pure in-memory. `test_semantic_perspective.py` also answers with the workbook path removed. |
| C-06 | ❌ No undocumented assumptions | **PASS (with this doc)** | Format assumptions ("Registry Catalog" meta-sheet, owner-role string, PK schema) are documented in IDENTITY_SPEC.md and the KNOWN_LIMITATIONS table. The RPDE heuristic (F-A) was previously under-documented; now recorded. |
| C-07 | ❌ No dead code | **PASS** | Every `ake/*.py` module has ≥1 real importer; 23/25 load on the AKE runtime path, the other two (`classifier`, `shell`) are reachable via `runner` (export route) and the CLI/`responses.py` respectively. No orphan module. |
| C-08 | ❌ No unreachable capability | **PASS** | All shell verbs, all API endpoints, and all dashboard handlers resolve to live code paths (see §4). |
| C-09 | ❌ No orphan registry | **PASS** | Every owner registry participates in at least one edge (0 orphan owner registries on the reference workbook). |
| C-10 | ❌ No inconsistent API | **PASS** | 14 endpoints; 13 declare a `response_model`; the one exception (`/export`) returns a ZIP `FileResponse` by design. Error handling present (11 `HTTPException` sites); ambiguous entities return 409 candidates, unknown 404. |

---

## 2. Findings (root cause + fix)

### F-A — Domain-coupled heuristic in the relational primitive engine  (severity: LOW, not a blocker)
**What:** `ake/relational_primitive_engine.py` branches on domain literals in decision logic:
- `if "handler" in rel` (line ~149) and `elif "handler" in col.lower()` (line ~192)
- `if "Component" in r` (line ~164, selecting the Component registry)

This is the F-022 "implementation = Component" rule: it encodes that, in the EBIS workbook, a
`handler`-named relation whose prose target isn't found should fall back to matching the
**Component** registry.

**Impact (measured):** 48 of 1 937 edges on the reference workbook are produced via this
fallback. On a workbook with no `handler` relation and no `Component` registry the branch is
simply dead — so it does not crash other workbooks, but it *is* domain knowledge embedded in
code, which violates C-02 in spirit.

**Root cause:** a workbook-specific relation-name→registry mapping was hard-coded instead of
being derived from the catalog (e.g. from an FK declaration or a relation-target rule).

**Recommended fix (deferred — not applied this pass):** replace the literals with a derived
rule. Two clean options: (a) read the fallback target registry from the relationship column's
declared FK in the Registry Catalog; or (b) generalise to "if a prose target is unresolved,
attempt exact-match against the registry named by the relation's declared target class",
using `relation_target_map()` which already exists. Either removes the literals while keeping
the 48 edges. Add a guard test (like the semantic engine's) over RPDE code tokens afterward.

### F-B — Phase-1 build is super-linear; impractical for 100k+ entities  (severity: MEDIUM — scale, not a blocker)
**What (measured):** synthetic 100 registries × 1 000 entities = 100 000 entities:
- Phase-1 build: **256 s**  (nodes=100 000, edges=99 000)
- Peak Python heap: **378 MB**
- Query latency after build — excellent: resolve **0.0 ms**, discovery_chain **0.0 ms**,
  perspective(4-hop) **0.2 ms median / 1.2 ms max**.

So the *runtime* scales beautifully; the *one-time build* does not.

**Root cause (profiled):** `ake/reachability_engine.py::derive()` dominates (≈15 s of a 21 s
build at 20k; grows worse at 100k). Although its OUTPUT is class-level ("one record per class
pair"), its computation probes **every candidate entity**:
`for e in candidates: g.shortest_path(e, …)` — 741 000 BFS calls at 20k, and `_class_of` is
called 5.6 million times. With deep FK chains this is effectively all-pairs BFS.

**Recommended fix (deferred):**
1. Memoise `_class_of` (it recomputes the owning class per node repeatedly) — cache node→class
   once; this alone removes millions of calls.
2. Replace per-entity confirmation with **sampling**: the record already reports
   `confirmed_instances`/`sampled_instances`; probe a bounded sample (e.g. up to N per class
   pair) instead of every candidate, since the representative example + a confirmation count
   don't require exhaustive traversal.
3. Optionally compute class-level reachability on a **condensed class graph** (one node per
   registry) instead of the full entity graph — O(classes²) not O(entities²).
Any one of these brings the build back to near-linear. None affect query behaviour.

**Interim guidance (documented in KNOWN_LIMITATIONS):** the reference workbook (~1 000
entities) builds in a few seconds; workbooks up to a few thousand entities are comfortable;
tens of thousands will be slow to load but fast to query; 100k+ needs the fix above before it
is practical.

### F-C — Owner-row / name search is a linear scan  (severity: LOW — scale)
**What (measured):** at 100k entities, `search("entity_50_500")` took **~800 ms** median,
while ID resolution (indexed) was sub-millisecond.

**Root cause:** `AKE.search()` scans all owner rows and substring-matches names; there is no
name index (IDs are indexed via the canonical identity registry, names are not).

**Recommended fix (deferred):** build a lowercased name→(registry,id) index once at Phase-1
(same place the canonical identity index is built) and consult it for exact/prefix matches,
falling back to a scan only for substring queries. Brings exact-name search to O(1).

---

## 3. Scale test — raw numbers

Synthetic Architecture Registry Workbook, 100 registries × 1 000 entities, 100-deep FK chain:

| Metric | Value | Assessment |
|---|---|---|
| Workbook generation | 4.3 s, 2.4 MB file | — |
| Phase-1 build | **256 s** | ❌ too slow (see F-B) |
| Nodes / edges | 100 000 / 99 000 | correct |
| Peak Python heap | 378 MB | acceptable |
| resolve() | 0.0 ms median / 0.1 ms max | ✅ excellent |
| discovery_chain() | 0.0 ms / 0.1 ms | ✅ excellent |
| perspective(4-hop) | 0.2 ms / 1.2 ms | ✅ excellent |
| search() exact name | 800 ms / 853 ms | ❌ slow (see F-C) |

Memory-leak check: 4 000 mixed queries → **+67 KB** net Python heap. No leak, no session
corruption, graph object identity stable.

---

## 4. Dashboard wiring — static verification (STATIC-ONLY)

Browser not available in this environment; the following were verified statically:

- **JS parses** (Function-constructor compile of the whole `<script>`): valid.
- **Every `getElementById` id exists in markup:** 32 unique ids referenced, **0 missing**.
- **Every `api()` call maps to a real endpoint:** dashboard calls
  `/upload, /query, /action, /back, /home, /search, /contexts, /context_query,
  /perspective, /intersect, /session/:id` (server) and `/_ake/availability, /_ake/public_state`
  (gateway) — all present. **No 404 targets.**
- **New Phase-2 controls wired:** `perspDir, perspHops, perspGo, intersectB, intersectGo`
  all exist and bind to `runPerspective` / `runIntersect`.
- **All endpoints exercised over ASGI HTTP:** `_verify.py` (22/22) + `_semtest.py`
  (perspective/intersect) + `_ctxtest.py` (contexts) pass end-to-end.

**Residual risk (requires a browser to close):** actual visual rendering, CSS layout, click
behaviour, and absence of runtime console errors cannot be certified here. Recommend a manual
browser pass (or a Playwright/headless run outside this sandbox) before production sign-off.

---

## 5. Test suite

Full automated suite at time of audit: **335 / 335 checks across 11 suites**
(`test_canonical_identity` 27, `test_capability_synthesis` 31, `test_cli_dispatch` 35,
`test_context_discovery` 17, `test_explorer_ux` 23, `test_reachability_engine` 13,
`test_reachability_universality` 32, `test_semantic_fidelity` 25, `test_semantic_perspective`
19, `test_stabilization` 12, `regression` 101). Real-HTTP verification 22/22.

---

## 6. Certification decision

**CONDITIONAL PASS — foundation is sound; no blocker to building new capabilities.**

Before onboarding large real-world workbooks (tens of thousands of entities or more), address
**F-B** (build-time reachability) and **F-C** (name-search index). **F-A** (RPDE domain
coupling) should be cleaned up for architectural purity but does not affect correctness on any
workbook. All three are documented in KNOWN_LIMITATIONS with IDs SCALE-BUILD, SCALE-SEARCH,
and HARDCODE-RPDE respectively.

No duplicate authority, no second graph, no workbook re-derivation, no stale runtime, no
memory leak, no orphan registry, no dead module, and no unreachable capability were found.
