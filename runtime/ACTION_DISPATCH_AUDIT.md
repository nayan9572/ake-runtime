# AKE — End-to-End Action-Dispatch Audit & Fix (UX-1.3)

Scope: the complete click path **Dashboard button → client payload → `POST /action|/query|/back|/home`
→ selected CanonicalAction → shell dispatcher → NavState JSON → final renderer**, verified
against the *real* launcher → gateway → dashboard → runtime stack (not isolated shell calls).

All reproduction and verification were performed by driving the actual FastAPI app
(`ake_server_gateway.py` wrapping `ake_server.api:app`) over HTTP with the bundled
dashboard served as static files and the v17 workbook loaded in owner mode. Unit-test
green was **not** treated as sufficient; every reported issue has an HTTP-level evidence
line in the verification harness.

---

## 1. Defects found (root cause)

| # | Symptom (as reported) | Root cause |
|---|---|---|
| D1 | "Module ← Command Master Registry (18)" opens a **single entity** instead of the list | Menu keys and results-row keys shared the `"1".."N"` string namespace. A results row click sent a bare number to `/action`; if the shell had reverted to `menu` mode it resolved that number against `self.menu` and opened one entity via `_action_page`. |
| D2 | **Analyze** renders a list, not an analysis | `analyze()` set `self.mode = "results"`. `build_nav_state` passed `"results"` through, and the payload's own `mode` therefore lied about the view; the topbar chip showed `results (N)` and `result_count` reported the truncated observation-item count. It only *looked* right because the client checked `nav.analysis` before `nav.mode==="results"`. |
| D3 | **Compare** renders a list / count mismatch | Same `mode="results"` mislabel, plus a count split: `entity_actions` advertised the true scope size (e.g. 176) while `shell.results` was capped at 80. The badge said 176; the chip/`result_count`/pairwise-fallback ledger read 80. |
| D4 | **Compare siblings** silently returns to menu | With 0 siblings, `compare()` returns `{"error":…}`; `_action_page` returned that string while leaving `mode="menu"` / `last_analysis=None`, so a forced click repainted the same menu. |
| D5 | **Back / Home** corrupt navigation | (a) Results/analysis/compare views were **never pushed to any history stack** — only entity opens touched `crumb`. So `back` from a results list popped the parent entity and jumped **straight home, skipping the list**. (b) Every renderer added its **own** `#stage` click listener on every repaint without removing the prior one; after N navigations a single click fired N handlers and advanced the server session N steps. (c) `goBackSteps(n)` fired n `/back` calls in an unguarded promise chain that raced `navRequest`. |
| D6 | **Search** misses canonical IDs | `AKE.search()` iterated rows in registry order and truncated to 50 with **no ranking**; an exact PK/name match could be pushed past position 50 by earlier substring matches, so typing an exact ID sometimes did not surface that entity. |
| D7 (infra) | Advertised badges frequently absent | The client fetches `GET /_ake/availability` for every entity menu; that route lives only in the **launcher-injected gateway**, not in the shipped `ake_server` package. Running `ake_server` standalone 404s it and the menu paints with no badges. (Behaviour retained by design; documented, not "fixed" — the gateway is the supported deployment.) |

---

## 2. Evidence (real HTTP stack, workbook v17, owner mode)

Reproduction harness drove the gateway app via `httpx.ASGITransport`. Representative
before-state captured on `MOD-002` / `CMD-001`:

```
REFERENCE (Module←CMR, key 9)   advertised 15 -> results 15   mode=results        [OK even before]
ANALYZE                          advertised 1  -> obs 5        mode=results (LIE)  branch renderAnalysis
COMPARE layer (CMD-001)          advertised 106 -> analysis 106, results CAPPED 80, result_count 80
BACK from a 15-row results view  crumb=['MOD-002'] -> one back -> mode=home  (list SKIPPED)
SEARCH 'MOD-002'                 50 hits, MOD-002 NOT among them (ranking bug)
```

After-state (same harness, 22/22 checks pass — see §5):

```
REFERENCE/RELATION  advertised == result_count for every direct relation on MOD-002
COMPARE siblings    advertised 176 == result_count 176 == analysis.targets 176
COMPARE layer       advertised 106 == result_count 106 == analysis.targets 106
ANALYZE             mode=='analysis'            branch renderAnalysis
COMPARE             mode=='analysis'            analysis.operation=='compare'
BACK from results   -> parent entity menu (MOD-002), results dict cleared
BACK from analysis  -> parent entity menu
result row (r<key>) -> opens the CORRECT entity (CMD-032), never a menu action
BACK after opening a result -> returns to the results list
2nd BACK            -> entity menu ; HOME -> empty crumb, no stale menu/results
SEARCH 'MOD-002'    -> MOD-002 present ; 'orchestrator'/'ebis_chat' -> semantic hits
Feature relations   Owner Module/Category/Family/Role all resolve to correct counts
Source-row scalars  exposed as own canonical actions ('Type','Lines'), resolve cleanly
availability keys   0/17 mismatch vs menu keys
HTTP                no 4xx/5xx across the entire workflow
```

Promoted- and discovered-entity search/promotion are additionally proven by
`tests/test_capability_synthesis.py` (31/31), which round-trips a promoted value
(`VPROM:COMPONENT_TYPE:FUNCTION_GENERIC`) through the **real API** and drills its relation
to 315 real results.

---

## 3. Files changed

Runtime (`ake/`):
- **`ake/shell.py`** — nav-frame stack (`self.stack`) with `_snapshot`/`_push_frame`/
  `_maybe_push`/`_restore`; `open_object` snapshots the view it leaves; `back` pops a frame
  and replays it, falling back to the crumb only when the stack is empty; `home` clears the
  stack; **analyze/compare now set `mode="analysis"`** and delegate body-building to one
  shared `_render_analysis()` (reused verbatim on back-replay); `result_total` set by every
  producer (REL, GET_NEIGHBORS, list, rel, search, analyze, compare) carrying the **true,
  uncapped** count; unambiguous **`r<N>` result-row selector** added so a row click can
  never collide with a menu action number; one-shot `_suppress_next_frame` flag prevents a
  double push when compare/analyze are reached via `_action_page`.
- **`ake/__init__.py`** — `AKE.search()` **ranked**: exact id/name > id/name prefix >
  word-start > substring, stable within a rank, before the 50-row cap. Canonical IDs now
  always surface.

Server (`ake_server/`):
- **`responses.py`** — `build_nav_state` passes `mode="analysis"` through; `_results()`
  ships navigable rows for analysis mode too; `result_count = shell.result_total` (true
  size, not capped list length); `can_go_back` also true when a view frame is on the stack.
- **`schemas.py`** — `NavState.mode` literal extended with `"analysis"`.
- **`events.py`** — analysis treated as a results-type view change (`results_changed`).

Launcher:
- **`AKE_Master_Launcher.py`** — embedded dashboard (`_DASHBOARD_HTML_B64`) regenerated
  from the fixed HTML. Changes: **one delegated `#stage` click listener** bound once at
  boot (renderers no longer attach their own — the fix for multi-dispatch Back/Home
  corruption); `applyNav` routes `mode==="analysis"`; ledger rows emit **`data-rowkey` →
  `r<key>`** via a new `openResult()` (distinct from menu-action `runAction`); Results
  heading uses the true `result_count`; `goBackSteps` made deterministic/seq-guarded.

Tests:
- **`tests/test_semantic_fidelity.py`** — back-navigation hygiene test updated to the
  corrected stack contract (results is a real back-step to the entity menu, then home),
  preserving its original anti-stale-state intent.
- The fixed **`ake_server/`** package is now bundled inside the runtime ZIP so the
  co-located API round-trip check in `tests/test_capability_synthesis.py` runs
  (pre-existing skip when the server was absent).

---

## 4. Design rationale

- **Single authority preserved.** The shell remains the only owner of navigation state.
  Server and client render what the shell exposes; neither re-derives counts or view mode.
  `result_total` and `mode` are read straight off the shell instance — no second source.
- **A view is a first-class history step.** The prior model equated history with the
  *entity* crumb, so non-entity views (results/analysis) were invisible to `back`. The
  nav-frame stack makes each rendered view restorable and replays it through the *same*
  renderer that first produced it, so no divergent second render path exists.
- **Namespacing over heuristics.** The menu/results key collision is fixed by an explicit
  `r<N>` selector, not by guessing intent from mode — deterministic and independent of any
  race between mode transitions.
- **Truth in the payload.** `mode="analysis"` makes the NavState self-describing; the
  client no longer relies on inspecting `nav.analysis` to correct a mislabelled mode.
- **One listener, bound once.** Delegated event handling removes an entire class of
  repaint-accumulation bugs at the source rather than de-duplicating per render.
- **Ranked search** guarantees the most specific match (exact id/name) is never truncated
  away, which is the property a canonical-ID lookup must have.

---

## 5. Verification performed

Real launcher → gateway → dashboard → runtime, over HTTP:

- **22/22** end-to-end checks pass, covering every reported issue: relation buttons open
  the correct set; advertised == rendered counts (incl. uncapped compare); analyze always
  renders analysis; compare always renders comparison; Back/Home deterministic with no
  stale state; search by canonical ID / semantic name / filename token; Owner / Family /
  Feature / Category / Module relations resolve; Source-row scalars promoted to their own
  actions; correct entity on every row open; availability keys align 0/17; **no 4xx/5xx**.
- Dashboard JS validated for syntax (no browser parse/console errors).
- `availability`/menu key alignment: **0 mismatches**.

Regression (unchanged workbook + retail fixture):

```
test_capability_synthesis  31/31
test_cli_dispatch          35/35
test_explorer_ux           23/23
test_reachability_engine   13/13
test_reachability_universality 32/32
test_semantic_fidelity     25/25
test_stabilization         12/12
regression                 101/101
TOTAL                      272/272   ALL SUITES CLEAN
```

---

## 6. Remaining known limitations

- **`/_ake/availability` lives in the gateway, not `ake_server`.** Running the bare
  `ake_server` package without the launcher gateway means entity menus paint with no count
  badges (menus still work; only the badge/availability layer is absent). This is the
  documented deployment boundary (ADR-008), not a regression. If badge support is wanted in
  standalone `ake_server`, the `_availability_for` route must be promoted into the package
  — a separate scope decision.
- **Compare/analyze printed rows remain capped at 80** in the console text; the *structured*
  payload and `result_total` carry the full count and the dashboard renders all of them
  from `analysis.targets`, so the cap is cosmetic (console pane only).
- Pre-existing loader/resolver limitations (F-02, F-05..F-08, etc. in KNOWN_LIMITATIONS.md)
  are untouched by this work.
