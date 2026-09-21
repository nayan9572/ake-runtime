# AKE Changelog

## [UX-1.9] Universal Intent Discovery — context is the source node, not a search boundary
Root-cause fix for F-D (Context=A, Query=B -> "No matches"). Rewires existing subsystems into
one discovery pipeline; no new engines, backend logic reused.

- **Bug:** context was a search boundary (query filtered inside the context's registry), so a
  target in another registry returned no matches even when the graph connected them.
- **Root cause:** the query path filtered one registry instead of resolving globally + pathing.
- **Fix (reuse, not rebuild):**
  * `UniversalEdgeGraph.path_between()` — bidirectional shortest path reusing the already-stored
    fwd+rev maps (no new structure); returns per-hop {from,to,relation,direction,evidence}.
  * Evidence tiering L1..L5 as a layer over the loader's existing `_rel_source` tagging
    (declared->structural, inferred->value); path confidence = product of hop confidences, so
    structural always outranks lexical (a single weak hop can't fake an all-structural path).
  * `EntityResolver` gains typo tolerance (difflib against the workbook's own discovered names)
    — candidates only, never auto-opens.
  * `AKE.discover(query, context)` assembles resolve -> bidirectional path -> evidence ->
    suggest_next into one result. Context is the source; the query resolves globally.
  * `POST /discover` routes straight to `AKE.discover()`. Existing endpoints preserved.
  * Dashboard: a single "Ask anything" prompt (source optional) renders one clear result —
    path visualization with per-hop evidence tiers, distance, confidence %, and a concise
    "Explore next" chip row. Old controls moved under "Advanced tools".
- **Zero hardcoding:** no registry/entity/prefix literals; everything derives from graph +
  `_rel_source` + discovered names. Guard test enforces it.
- **Verification:** new `tests/test_discovery_pipeline.py` (15 checks); full regression
  **360/360** across 13 suites; real-HTTP 22/22; `/discover` verified end-to-end (context=source,
  global resolve, bidirectional path + evidence, ambiguous->candidates, unknown->closest).


## [UX-1.8] Certification fixes (F-A/F-B/F-C) + Guided Discovery Engine
Certification Audit v1.0 findings resolved and a guided-discovery capability added.

- **F-A (architecture purity):** removed hardcoded `"handler"`/`"Component"` literals from
  `relational_primitive_engine.py`. The secondary-target fallback is now DERIVED from where a
  column's unmatched values actually resolve (dominant registry), reproducing the exact 48
  handler→Component edges with 0 wrong-class and no domain literals in code.
- **F-B (scale):** reachability build no longer probes every entity — memoised `_class_of`
  and sampled candidates (≤40, deterministic). 100k-entity Phase-1 build 256 s → 35.4 s.
- **F-C (scale):** added a name/id index built once at load; exact-name search ~800 ms → 0 ms.
- **Guided Discovery Engine (`suggest_next`):** after any resolution, ranked next-exploration
  suggestions derived from the graph neighbourhood (hop distance + degree importance +
  relation multiplicity) — never a fixed list. Ambiguous → candidates; unknown → closest /
  most-connected entities, so the user is never dead-ended. Exposed via `POST /suggest` and
  embedded in `/perspective` and context-chain responses; the dashboard renders a
  "Suggested next exploration" chip row whose chips open the entity (continuing the loop).
- **Verification:** new `tests/test_guided_discovery.py` (10 checks); full regression
  **345/345** across 12 suites; real-HTTP 22/22; `/suggest` verified end-to-end.


## [UX-1.7] Semantic perspective engine — Phase-2 multi-hop knowledge runtime
Turns AKE from a single-hop explorer into a knowledge runtime: every query runs on the graph
derived once at load (Phase 1); the workbook is never re-read per query (proven by a test
that answers with the workbook path removed).

- **Multi-hop perspective** (`AKE.perspective(entity, direction, max_hops)`, `ake/semantic_perspective.py`):
  transitive traversal from one entity, layered by hop and grouped into class bands
  (e.g. an entity -> Variables -> Features -> Modules -> Commands -> Handlers -> ...). Each
  reached entity carries the shortest relation path back to the origin (its evidence trail).
- **Directed intersection** (`AKE.intersect(a, b, direction)`): two perspectives intersected,
  where direction defines the question — A->B and B->A, and "drives" (out) vs "driven-by"
  (in), are genuinely different analyses. Returns the shared entities with each side's path.
- **Derived result table** (`AKE.derive_table(view)`): columns are chosen from what the
  traversal actually found — Owner only if class info exists, Evidence only if evidence
  exists, Runtime-impact only if execution/lifecycle flags exist; Strength always (derived
  from path length, execution, and evidence, normalised 0..1). Nothing hardcoded.
- **No domain vocabulary in code.** The engine contains zero entity/registry/domain literals
  in executable code (only column headers, direction synonyms, and property-graph field
  names). A permanent guard test strips comments+strings and fails if any domain literal ever
  appears. Names are discovered at runtime from node `class`, edge `relation`, and graph
  attributes.
- **API:** `POST /perspective` and `POST /intersect` (schemas Perspective*/Intersect*),
  computed under the session lock on the derived graph. Ambiguous entities return candidates
  (409) rather than guessing.
- **Dashboard:** the discovery console gains a Semantic-perspective panel — direction + hop
  selectors, a Perspective button (multi-hop bands + derived table) and an Intersect button
  (second entity, directional). Rows stay clickable to descend.
- **Verification:** new `tests/test_semantic_perspective.py` (19 checks, incl. the
  no-hardcoding guard and the workbook-gone in-memory proof); full regression **335/335**
  across 11 suites; real-HTTP 22/22 unchanged; perspective/intersect endpoints verified
  end-to-end (CA50 -> 718 reached / 13 bands; Fuel n CA50 out=1 vs in=0).


## [UX-1.6] Discovery console — "AKE>" becomes a context selector, not a second search box
Removes the two overlapping free-text boxes (they did the same thing) and turns the top
prompt into a discovery-CONTEXT selector with the lower box scoped to it. AKE becomes an
engineering discovery console instead of a search engine.

- **Contexts are derived from the EXISTING registry catalog — no duplicate model.** A first
  attempt introduced a parallel ContextEngine; that was removed. The context vocabulary
  (handler / module / feature / variable / command / registry / relation / …) is read
  directly from model.catalog (role + prefix) via new AKE methods (`contexts`,
  `resolve_context`, `query_in_context`), so it works for ANY workbook, not just EBIS.
- **Dynamic resolution.** A context word resolves against the entity noun, registry name, or
  pk prefix (singular/startswith tolerant). Words not present in a workbook resolve to
  nothing (no hardcoded vocabulary). Plus a special `relation` mode.
- **Discovery chain (new behaviour).** context + entity no longer just opens the entity — it
  returns the outward chain (identity → related entities grouped by direction/relation/class,
  ordered by size), built structurally from the universal graph. `discovery_chain` /
  `relation_view` on the AKE object.
- **Backend + dashboard together.** New endpoints `GET /contexts` and `POST /context_query`
  (schemas: ContextListResponse / ContextQueryRequest / ContextQueryResponse); the shell
  gains a `context <word>` command and persistent `console_context`. The dashboard rail now
  shows an `AKE>` context input (autocompletes from /contexts) + a scoped entity input, and
  renders discovery chains, the relation view, and scoped candidates. Empty context = the old
  global search (nothing lost).
- **Verification:** new `tests/test_context_discovery.py` (17 checks); full regression
  **316/316** across 10 suites; real-HTTP dashboard verification 22/22 unchanged; new context
  endpoints verified end-to-end over HTTP.


## [UX-1.5] Deployment reliability — tunnel readiness + auto-reconnect (launcher)
Fixes the biggest real-world bottleneck: the dashboard URL being unreachable
(DNS_PROBE_FINISHED_NXDOMAIN / "site can't be reached") even when the backend is healthy.
Cause was the ephemeral Cloudflare quick tunnel, not AKE. Launcher-only change; runtime and
server packages are unchanged.

- **DNS-readiness gate before printing the URL.** cloudflared prints a random-subdomain URL
  the instant the tunnel *registers*, but Cloudflare edge DNS for that subdomain takes
  seconds to propagate — opening it in that window returns NXDOMAIN. The launcher now polls
  the URL end-to-end (real DNS resolution + HTTP round-trip to /health through the edge) and
  only prints it as live once it actually serves. Config: `TUNNEL_DNS_TIMEOUT` (default 75s).
- **Retry with a fresh subdomain.** If a tunnel registers but never becomes reachable, or
  the process dies during startup, it is torn down and retried up to `TUNNEL_ATTEMPTS`
  (default 3) times — the launcher returns the first URL that is actually reachable, never a
  dead one.
- **Reconnect watchdog.** A daemon thread detects when the cloudflared process has dropped
  mid-session (another source of "site can't be reached") and brings up a fresh,
  readiness-verified tunnel, updating the shared URL in place. Healthy tunnels are never
  touched.
- **Honest status output.** The banner distinguishes "live and reachable", "URL registered
  but DNS still propagating" (with guidance), and "no reachable tunnel after N attempts",
  instead of always printing a URL as if it worked.


## [UX-1.4] Canonical identity (IR-only entity identity) — numeric PKs, type-aware resolver, immutable registry
See `IDENTITY_SPEC.md` for the full contract.

- **New `ake/canonical_identity.py` — immutable identity registry.** Composite `(class, pk)`
  identity reduced to a stable canonical hash `CID-...`. Built once, then frozen
  (`__slots__` + `MappingProxyType` + guarded `__setattr__`). Fixed public API only:
  `infer_schema / is_numeric / is_composite / canonical_id / canonical_for / display_id /
  owner / resolve / translate / classes_for_pk / node_key / node_key_for`. No module reaches
  into internals.
- **Numeric primary keys are first-class** (previously impossible). Structural PK-schema
  inference (prefixed/numeric/composite/opaque — no prefix whitelist); prefix-independent
  `owner()`; numeric FK edges derived; numeric ids searchable and navigable by typing the id;
  all node keys/edge endpoints string-normalised (fixes int/str split).
- **Type-aware resolver.** Exact name auto-resolves only if globally unique; the same name in
  two classes returns candidates (never opens the wrong class). `Class:name` disambiguation.
- **Graph lookups routed through identity.** `UniversalEdgeGraph` normalises every access via
  `node_key` (display → canonical → node key); `ake/__init__.py` uses `graph.attrs(...)`; no
  module indexes the graph with a raw string.
- **Ambiguous display — no synthetic IDs.** A colliding pk shows "Multiple entities found"
  with Registry per line and the raw pk; selection uses an opaque internal canonical token.
  No `1@Class` visible identifier.
- **Backward compatible.** Prefixed workbooks (EBIS v17) bit-identical: display id == raw pk,
  0 ambiguous pks, all schemas `prefixed`. Real-HTTP dashboard verification 22/22 unchanged.
- **Verification:** new `tests/test_canonical_identity.py` (27 checks); full regression
  **299/299** across 9 suites.


## [UX-1.3] End-to-end action-dispatch audit & fix (real launcher/gateway/dashboard/runtime)
Full deliverable — reproduced, fixed, regressed, and verified over the real HTTP stack.
See `ACTION_DISPATCH_AUDIT.md` for the complete engineering audit, evidence, and rationale.

- **Nav-frame stack in `ake/shell.py`.** Results/analysis views are now real history steps:
  `back` returns to the parent entity menu instead of skipping straight home. Adds
  `self.stack` + `_snapshot`/`_push_frame`/`_maybe_push`/`_restore`; replays each view
  through the same renderer that produced it.
- **Analyze/Compare are `mode="analysis"`** (was mislabelled `"results"`). NavState is now
  self-describing; `schemas.py` allows the mode; `events.py` treats it as a view change.
- **`result_total`** (true, uncapped count) set by every producer; server reports
  `result_count = result_total`, so advertised badge == rendered count even when the printed
  list is truncated (compare 176/106 no longer collapse to 80).
- **`r<N>` result-row selector** removes the menu/results key collision — a row click can no
  longer be mis-resolved as a menu action ("opens a single entity instead of the list").
- **Ranked `AKE.search()`** (exact id/name > prefix > word-start > substring, before the
  50-cap) so canonical IDs always surface.
- **Dashboard (embedded in launcher): one delegated `#stage` listener bound once.** Renderers
  no longer attach per-repaint listeners (the multi-dispatch Back/Home corruption); ledger
  rows emit `data-rowkey`→`r<key>`; `goBackSteps` made deterministic/seq-guarded.
- **Verification:** 22/22 real-HTTP checks pass; **272/272** regression checks across 8
  suites clean. `test_semantic_fidelity.py` back-nav test updated to the corrected contract.


## [UX-1.2] Priority-ordered fixes + a real bug in my own test harness
Implemented the explicit priority order: relation names executable, Engine Help repetition,
wording, arrow consistency, breadcrumb (no change needed there — already correct).

- **Relation names now executable.** Typing `handler` (or `Handler`, or `Discount Band`)
  resolves to the identical action its current menu number would. New `_menu_lookup()` matches
  case/spacing-insensitively against `self.menu` -- the same dict `_menu_page()` already built
  that page, nothing new stored. Checked before search()/list()/global resolve, matching the
  established action-first parser priority. As a side effect this also resolves the earlier
  Evidence-action-vs-Evidence-entity collision in favor of the action, consistent with that
  priority.
- **Engine Help no longer reprints in full on every `help` call.** Signal used is `self.context`
  (existing state, already gates `_menu_page()`/`_tree()`) -- not a new "have I shown help
  before" flag. Full block when `self.context is None`; a one-line reminder + Knowledge Help
  once an object's open; `help engine` as an explicit way back to the full block.
- **Field-specific wording:** Evidence's absence is now "not available", separate from
  Cardinality's "not documented" -- no longer the same phrase for two different kinds of gap.
- **Arrow consistency:** breadcrumb separator changed from the `>` I'd introduced to `→`,
  matching `rpde_cardinality`'s own pre-existing convention (a genuinely existing choice, not
  a third new one).
- **"Available next actions"**: Knowledge Help now opens with `self.menu` restated as verb +
  label (Open/Show) -- same data `_menu_page()` shows, not new knowledge. Deliberately excludes
  fixed commands like `tree` to keep the Engine Help / Knowledge Help line from blurring again.

**A real bug, found and fixed, not glossed over:** `test_reachability_engine.py`,
`test_reachability_universality.py`, and `test_explorer_ux.py` all had
`passed = sum(1 for _, ok, _ in RESULTS)` -- missing `if ok`. That sums 1 for every row
regardless of pass/fail, so `passed` always equaled `total` and the exit code was always 0,
no matter what actually failed. `regression.py`, `test_cli_dispatch.py`, and my own first file
`test_stabilization.py` all had the correct `if ok` -- the bug was introduced partway through
this session and copy-pasted forward into every file written after that point.
Impact, checked file by file after fixing the bug: `test_reachability_engine.py` had zero
hidden failures (13/13 genuinely). `test_reachability_universality.py` and `test_explorer_ux.py`
did have live failures hiding behind the false "all passed" -- all from my own two most recent
changes in this session (the `→` arrow swap and the two-tier help behavior) breaking assertions
written for the previous behavior, plus one stale test helper (`Evidence` expected "not
documented", product code correctly says "not available") and one test bug (comparing two
sequential calls on the same mutated shell instance instead of two independent ones). All fixed;
every fix verified by explicitly grepping for zero `[FAIL]` lines, not by trusting the summary
line alone this time.
All 217 checks pass across 6 files (102+35+12+13+32+23), each confirmed individually.

## [UX-1.1] Three verification points on the UX pass, one new permanent invariant
- **"Knowledge Help is new" -- new in what sense?** Verified, not just re-asserted: called
  `help` repeatedly and interleaved with navigation, then diffed `vars(shell)` and
  `vars(model)` before/after -- zero new attributes either place. `_knowledge_help()` is
  registry-read -> format -> display, exactly the shape confirmed correct, not the
  new-cache/new-dictionary/new-metadata shape that would have broken the rules.
- **Is "Handler Registry" a hardcoded string?** Scanned `shell.py`'s actual code (excluding
  its docstring) against every real registry class name in the workbook -- zero matches.
  Traced the live call path instead: `self._attrs(eid)["class"]` reads
  `model.universal_graph.node_attrs`, built once at workbook load from the workbook's own
  data, in `workbook_runtime.py` -- nothing in `shell.py` ever names a class.
- **New invariant, now permanent** (`tests/test_explorer_ux.py`): Displayed Knowledge Help
  fields subset-of Existing Registry/Graph. An independent parser (regex over the rendered
  text, not shell.py's own code) plus an independent recomputation (straight from
  `model.universal_graph` / `model.rpde_cardinality`, not by calling `_knowledge_help()`
  again) cross-check every field shown, across 60 random real objects. A relation shown that
  isn't actually on the object, or any field that doesn't match independent recomputation,
  fails. 133 relation-blocks checked, 0 violations.
All 212 checks pass (211 previous + 1 new).

## [UX-1.0] Permanent breadcrumb + two-tier help — pure presentation, zero new state
Requested with explicit constraints: never a second source of truth, never a relation-name-keyed
mapping, help is a view not a database, breadcrumb reuses existing navigation state, "not
documented" is an acceptable answer. Verified against each:

- **Breadcrumb**: `HOME > CMD-002 > ...`, now shown on every `handle()` response (menu, help,
  tree, results — previously only the menu page), not a new tracked state -- still 100% derived
  from the pre-existing `self.crumb` list (`ake/shell.py` already had it; `_crumbline()` already
  existed). Implemented as a single wrapper around the existing dispatch logic (renamed to
  `_dispatch()`, unchanged) so the breadcrumb is added in exactly one place, not scattered across
  every return statement.
- **Engine Help vs Knowledge Help**: Engine Help is the pre-existing static command list
  (back/home/tree/search/...), unchanged, just labeled. Knowledge Help is new and per-object:
  for each relation the CURRENT object actually has, shows target type (from the neighbor's own
  `class` attribute), cardinality (from `model.rpde_cardinality` — already computed once at
  workbook load by `ake/relational_primitive_engine.py`, reused not recomputed), current value,
  and evidence presence (already on each edge). Zero new dictionaries: verified by scanning
  `shell.py`'s actual code (not its docstring, which already mentioned "handler" as illustrative
  prose) for any relation-name-keyed mapping.
- **Honest gaps**: `rpde_cardinality` only covers FK-derived edges, not the dedicated-sheet
  relations a Registry-style workbook like EBIS also has (e.g. `handler`, `produces`) — Knowledge
  Help shows "not documented" for those rather than inventing a value. Confirmed as a genuine,
  pre-existing data gap, not something to paper over.
- **Cross-domain, unmodified**: ran the same `shell.py` against a Financial-Sample-style tabular
  workbook (Segment/Country/Product/Discount Band/Month Name) — Knowledge Help correctly derived
  all five relations with real cardinality, with zero code changes.
- Caught two of my own mistakes before they shipped: (1) an early version double-printed the
  breadcrumb (once from the old inline `_menu_page()` reference, once from the new central
  wrapper) — removed the inline one. (2) my own new test had a false positive — it flagged
  "handler" appearing in `shell.py`'s pre-existing module *docstring* (illustrative prose) as if
  it were a hardcoded mapping in the *code*; fixed the test to scan code only.
All 211 checks pass (194 previous + 17 new, `tests/test_explorer_ux.py`).

## [Derivation-1.1] ReachabilityEngine — 5-point verification round
Requested before accepting the engine as a foundation for shell wiring. Each verified empirically,
not asserted:
- **Full determinism, not just aggregate output**: 8 independent fresh loads, every field checked
  individually (example_source, example_path, relation_pattern, counts, record order) — identical
  every time. Same example every run: `FEAT-032 -> FEAT-059 -> CMD-048 -> HND-048`.
- **Tie-break is the documented rule, not accidental stability**: adversarial case built with two
  candidate source entities deliberately inserted into the graph in the OPPOSITE order from their
  sort order — the lexicographically-first one won across 10 runs regardless, proving `sorted(
  entity_id)` governs, not dict-insertion order.
- **`path_for()`/registry consistency**: checked all 37 real class-level records — `path_for()`
  on every record's own `example_source` never returned None (0 failures). Separately, structurally
  proved (by instrumenting `shortest_path()` itself, not timing) that a registry-gated call on an
  unreachable pair invokes `shortest_path()` zero times — the gate short-circuits, it doesn't just
  happen to return the same answer.
- **Evidence provenance extended**: every record now also carries `algorithm_version` (module-level
  `VERSION`, bumped 1.0->2.0 with the per-entity->class-level redesign), `traversal_strategy`
  (explicit tie-break rule, in the data not just the docstring), and `max_depth` (the actual bound
  used for that record, independent of the engine's current default).
- **Incremental rebuild documented, not implemented (matches scope requested)**: the first-instinct
  rule — "only recompute pairs whose source or target class changed" — turned out to be UNSOUND on
  inspection: a change to an intermediate class can open a new path between two unrelated other
  classes, and that rule would miss it, serving a stale record. Two sound alternatives (dependency
  tracking; radius-based invalidation) are documented in the module docstring. Recommendation:
  don't build either until full rebuild's measured cost (~0.1s on EBIS, ~4s at 5000-entity stress
  scale) actually becomes a problem — the more likely bug source is building incremental
  correctness before it's needed.
Caught mid-edit: an accidental duplicate docstring-closing `"""` broke the module's syntax for one
intermediate step. Caught by re-running the full suite immediately after the edit, before this was
ever packaged — exactly why "run everything after every change" stayed the discipline through 194
checks, not skipped once the codebase got larger.
All 194 checks still pass (158 existing + 13 + 32 new, both reachability suites' assertions kept
in sync with the field additions).

## [Derivation-1.0] ReachabilityEngine — new capability, not wired in yet
New derivation-layer engine (sibling of InvariantEngine/RuleEngine/QueryEngine), answering a
question the explorer's Available/Unavailable menu never could: "no direct edge to Handler --
but is there a path through other registries?" Additive only: `ake/reachability_engine.py` is a
new file, plus one new `shortest_path()` primitive on `UniversalEdgeGraph` (`ake/edge_graph_
engine.py`, alongside the existing `reachable()`). Nothing existing was modified; the Canonical
Registry (`model.catalog` / `model.universal_graph`) is never mutated, verified by snapshot diff.

Two-tier design: `derive()` materializes only CLASS-LEVEL canonical patterns -- one record per
(source_class, target_class) pair with real evidence (an example path, confirmed/sampled instance
counts), O(classes^2) not O(entities x classes). On EBIS: 37 records, not 254 -- an earlier
per-entity version was correct but the wrong shape for a registry (a registry of one-off entries
nobody would query). `path_for(entity, target_class)` resolves an actual per-entity path on
demand, gated behind `derive()`'s output so a planner never blind-searches a pair already known
to go nowhere -- the bounded "limited runtime search" a query planner is allowed, not exhaustive
precompute.

Validated: byte-identical across repeated fresh loads AND across `PYTHONHASHSEED` 0/1/12345
(actually tested, not just reasoned about); zero crashes across empty/cyclic/disconnected/
duplicate-edge/deep-chain/broken-reference/self-loop graphs; runs unmodified on 5 unrelated
domains (Biology/University/Hospital/Manufacturing at the engine level, Library through the full
real `.xlsx` -> auto-detect -> WorkbookModel pipeline); scales to 5000 entities / 40 classes in
~4s. Source contains no EBIS-specific vocabulary (checked both by automated scan and manual
re-read). All 5 existing test suites still pass unchanged (158/158); this adds 45 more
(`tests/test_reachability_engine.py`, `tests/test_reachability_universality.py`).

**Known limitation, disclosed not hidden:** forward-edge-only traversal (matches the pre-existing
`reachable()` primitive's convention) means an entity with zero outgoing edges -- a dimension/leaf
entity in a star schema, e.g. an Author connected to a Publisher only via a shared Book record --
derives nothing, even though a human would call it reachable. Confirmed on the real Library test
(0 derived) and on 10 of EBIS's own 23 catalog classes (secondary/metadata registries like
Registry Audit, Component Status -- not the primary Feature/Component/Handler chain the explorer
actually uses). Never produces a wrong answer -- the failure mode is always "reports nothing,"
never "invents a path" -- but it's a real coverage gap for hub-shaped schemas, not yet fixed.

Not yet wired into `AKE.answer()` or `ake/shell.py`'s menu -- exists and is fully tested, but the
explorer doesn't use it yet.

## [Stabilization-1.1] AKE.answer() crashed for most advertised queries
Found via a live user session hitting `KeyError: 'GET_FAMILY'`. Root cause was bigger than that
one name: `ake/capability_matrix.py`'s `CAPABILITY_UNIVERSE` advertises 29 queries as answerable
(shown in `describe()`'s "available_queries" list), but `ake/algorithm_derivation.py`'s
`QUERY_DEFINITIONS` — the only thing `AKE.answer()` actually runs — only defines 13 of them.
The other 17 (`GET_FAMILY`, `GET_ROLE`, `GET_PURPOSE`, `CHECK_FK`, `IS_ORPHAN`, `GET_INCOMING`,
`GET_OUTGOING`, `IS_ROOT`, `IS_LEAF`, `IS_DUPLICATE`, `MISSING_EVIDENCE`, `EMPTY_FIELDS`,
`GET_READS`, `GET_PUBLISHES`, `GET_OBSERVES`, plus `GET_NAME`/`WHAT_IS`/`GET_SOURCE_ROW`, which
only worked because `ake/shell.py`'s menu has its own separate hardcoded handling for those three)
raised a raw, unhandled `KeyError` the moment they were actually invoked — reachable today via
`AKE_MASTER.py`'s `GET_X <ID>` command, or any direct caller of `AKE.answer()`.
Fixed at the single call site (`AKE.answer()`): an unrecognized `query_name` now returns a clear
`note` instead of raising. Implements none of the missing query logic — GET_FAMILY etc. are still
unsupported, they just fail cleanly now instead of crashing the whole session.
Two other things reported in the same session turned out NOT to be bugs on inspection — recorded
in KNOWN_LIMITATIONS.md rather than changed: breadcrumb-path duplicates on a revisited object, and
typed text always resolving as an entity/ID lookup, never as a menu-action-label match.
Regression: 102/102 + 35/35 (both unchanged) + 12/12 (tests/test_stabilization.py, was 11).

## [Stabilization-1.0] Runtime-path hardening — no architecture change
Found by directly stress-testing load/navigation/edge-case paths end-to-end (subprocess-level,
not just the internal-API regression suite, which stayed green throughout at 102/102 — these
bugs live in the CLI/Colab integration layer, not the engine). All six fixes are error-handling
or entry-point-consistency only; no engine module, algorithm, or data format changed.
- **Missing file**: `AKE_Colab_Shell.py` — the single-cell interactive Colab entry point the
  README (and CHANGELOG's own Product-1.1 entry, and AKE_PRODUCT_CONSTITUTION.md) documented as
  existing was absent from the shipped package. Restored, built only from existing frozen pieces
  (`ake.AKE`, `ake.shell.AKEShell`) — upload `AKE_Runtime.zip` (+ optional workbook), extract,
  launch the live explorer in-process.
- **F-033 zip-as-argument inconsistency**: `AKE_MASTER.py`'s `locate_workbook()` returned an
  explicit `.zip` argument unchanged instead of extracting it (only auto-discovered zips were
  extracted), so `--demo`/`--repl` crashed with a raw `openpyxl.InvalidFileException` when a zip
  was passed directly; batch mode happened to survive only because `ake/runner.py`'s separate,
  already-correct `_find_workbook()` re-resolved it. `AKE_SHELL.py` had no zip handling at all.
  Both now extract a `.zip` argument the same way `ake/runner.py` already did.
- **F-034 KeyboardInterrupt**: `AKE_MASTER.py`'s `repl()` caught `EOFError` but not
  `KeyboardInterrupt`, so Ctrl+C during the interactive REPL crashed with a raw traceback instead
  of exiting cleanly, unlike `ake/shell.py`'s `AKEShell.run()`, which already handled both.
- **F-035 malformed Registry Catalog**: a present-but-incomplete `Registry Catalog` sheet (missing
  a required column) raised a raw `KeyError` instead of falling back to `_infer_catalog()` — the
  same fallback already used when the sheet is missing entirely (F-04). Both cases now degrade the
  same way.
- **F-036 opaque load errors**: `WorkbookModel.__init__` let `BadZipFile` / `InvalidFileException` /
  `FileNotFoundError` propagate raw from openpyxl with no context. Re-raised with a clear,
  actionable one-line message (e.g. flags a `.zip` passed where a workbook was expected).
- Regression: 102/102 (regression.py, unchanged) + 35/35 (test_cli_dispatch.py, unchanged) +
  11/11 new (tests/test_stabilization.py).

## [Runtime-1.4] UX-1 Output UX — batch run output was invisible without the Files panel
- Problem: a successful batch run wrote `ake_out/*.json` and exited 0, but gave no absolute
  path, no way to retrieve everything as one download, and no signal to a Colab user beyond
  a relative-looking directory name — the user had to manually browse the Files panel.
- Fix: at the exact point `ake/runner.py:run()` finishes writing the 7 artifacts + summary.json,
  it now (a) prints an `AKE Finished` banner with the absolute output directory, (b) prints the
  absolute path of every artifact, (c) zips everything in the output directory into a sibling
  `ake_out.zip` and prints that absolute path, (d) prints `file://` links for notebook contexts,
  and (e) when `google.colab` is importable, calls `google.colab.files.download(...)` on the zip
  automatically (a no-op everywhere else, including on any exception from the download call
  itself, so it can never turn a successful compile into a crash). `run()`'s returned summary
  dict gains `output_dir`, `artifacts`, `zip_path`, `colab_download_triggered`.
- Files: ake/runner.py (only file changed — no new module), README.md, tests/regression.py,
  tests/test_cli_dispatch.py (new UX-1 checks).
- Regression: 30/30 (regression.py, +9 new) and 21/21 (test_cli_dispatch.py, +6 new) — output
  directory exists, all 8 expected artifacts exist, `ake_out.zip` is generated beside the output
  directory, the zip contains every one of the 8 artifacts, and the CLI's stdout carries the
  banner, absolute paths, and `file://` links.

## [Runtime-1.3] F-18 dangling Registry Catalog entry crashes edge derivation — FROZEN
- Root cause: `relational_primitive_engine.py:derive_edges()` indexed `self.m.hdr[reg]` directly
  for every catalog-listed Owner registry. Everywhere else in the model (`col()`, `rows()`, the
  discovery/runtime primitive modules) defends against a Registry Catalog row that names a
  registry with no backing sheet — a normal state for a hand-edited real-world workbook (row
  added ahead of the sheet, sheet renamed, typo) — by defaulting to `[]`/`None`. `derive_edges()`
  was the one place that didn't, so a dangling catalog entry raised an uncaught `KeyError` at
  `WorkbookModel.__init__` time, which propagated all the way through `colab_run.py` to exit
  code 1 with no artifacts written.
- Fix: `derive_edges()` now uses `self.m.hdr.get(reg)` and skips (does not derive edges for) a
  catalog-listed registry with no backing sheet, matching the model's established convention.
  Same fix applied to `runtime_primitives.py:walk_execution()`, which had the identical pattern
  (`self.m.hdr[prof]` on a catalog-declared-but-possibly-missing exec sheet) reachable from the
  REPL's execution-preferred entity queries.
- Files: ake/relational_primitive_engine.py, ake/runtime_primitives.py, tests/regression.py (new
  F-18 checks).
- Regression: 22/22 (20 existing + 2 new) — a workbook whose catalog references a registry with
  no matching sheet now builds successfully instead of raising.

## [Runtime-1.2] F-15 AKE_MASTER.py batch-mode dispatch fix — FROZEN
- Root cause: `python AKE_MASTER.py workbook.xlsx` (no other flags) entered the interactive
  REPL. Under non-interactive stdin (subprocess.run from Colab/CI) the REPL's `input()` hits
  `EOFError` immediately, exits 0, and produces no `ake_out/` — a silent no-op, not a crash.
- Fix: an explicit workbook argument now dispatches to a new `batch()` mode by default, which
  delegates to `ake/runner.py:run()` (same function `colab_run.py` uses) — one source of truth
  for artifact generation. `--repl` opts back into the previous interactive-with-explicit-workbook
  behavior; `--demo` and the no-args REPL are unchanged. `--outdir=DIR` overrides the output dir.
- Files: AKE_MASTER.py (dispatch + new `batch()`), README.md (Run section), tests/test_cli_dispatch.py (new).
- Follow-up fix in the same round: batch mode's default `ake_out/` was relative to the *caller's*
  process cwd, not `AKE_MASTER.py`'s own location — a subprocess caller that doesn't set `cwd=`
  would get artifacts written to an unexpected directory, silently. Now anchored to
  `os.path.dirname(os.path.abspath(__file__))` when `--outdir=` isn't given explicitly.
- Regression: 15/15 new checks — batch exits 0 and writes all 8 artifacts without reading stdin;
  `--outdir=` respected; default outdir is cwd-independent; `--demo` and both REPL paths
  unaffected and still produce no `ake_out/`; two independent batch runs produce byte-identical
  artifacts (determinism preserved).

## [IR-1.1] Canonical Property-Graph IR — FROZEN
- Universal Edge Graph promoted to Property Graph (nodes carry has_PK, has_Evidence, name, evidence, metadata, in_execution, has_lifecycle).
- IR-only derivation proven for attribute + relationship + graph invariants, lifecycle/execution/evidence queries, rendering.
- Files: edge_graph_engine.py, workbook_runtime.py (_build_node_attributes).

## [IR-1.0] RPDE (Relational Primitive Derivation) — FROZEN
- FK ≠ Edge: FK observations compiled into typed traversable edges; relation vocabulary + cardinality derived from column semantics.
- Coverage 1/13 → 13/13 owner classes; 0 duplicate/self-loop/dangling; cross-workbook (robotics) verified.
- Files: relational_primitive_engine.py, edge_graph_engine.py.

## [Runtime-1.1] F-14 packaging fix
- ake/runner.py added; colab_run.py is a self-bootstrapping shim; `from colab_run import run` works after unzip.
- Regression: test asserts import + callable.

## [Runtime-1.1] F-04 catalog inference + bundled default templates
- Loader infers a minimal Registry Catalog from structure when the sheet is absent (ID-pattern PK owners, FK detection).
- Default Property/Rule Template/Query Family registries bundled in ake/defaults/ and used when a workbook lacks them.
- Effect: plain single-sheet workbooks now compile (observation + IR + invariants) with no code change.

## [Library-1.0] Universal Runtime Primitive Library + composition model — FROZEN
- 45-primitive library (Capability Catalog) formalized; 100% implemented; 7 categories.
- Composition closure proven: every query→primitive sequence references only library primitives.
- LIFECYCLE_RECONSTRUCT composition defined (library primitives only); execution pending Phase 3.
- Minimality: WALK_GATE/WALK_PIPELINE/FIND_OWNER etc. are compositions, not new primitives.
- Regression 48/48. Next finding: Phase 3 (Command prose → typed IR edges).

## [Compiler-1.1] F-021 Command prose → typed IR edges — FROZEN
- RPDE extended: prose reference columns (Handler/Gate/Pipeline/Bridge/Validator) resolved to canonical entities.
- Resolution: column→target-registry by name-word; annotation-strip; exact/substring/2-token-overlap; within-target-registry only (no global fallback).
- Command edge coverage 9 → 260 (0.08 → 2.43/cmd). CMD-002: handler:HND-026, pipeline:PIPE-001, module:MOD-*.
- LIFECYCLE_RECONSTRUCT composition now executes on Commands — no runtime/primitive/engine changes.
- Fixes: (A) wrong-class edges eliminated (pipeline→PIPE not FEAT), (B) evidence column excluded, (F-18) dangling-catalog guard.
- Graph correctness preserved: 0 duplicate/self-loop/dangling/wrong-class. Regression 53/53. universal_edges 1642→1909.

## [Compiler-1.2] F-022 Prose canonicalization + report — FROZEN
- Handler prose also resolves against Component Registry (conservative exact/fn-token; handler impl = component, not wrong-class): +16 edges (260→276).
- Canonicalization Report artifact (canonicalization_report.json): classifies every command prose ref — resolved_registry / resolved_component / not_found / ABSENT(with token).
- Honest finding: 181 references are genuinely ABSENT from all registries → compiler cannot resolve; requires workbook author to register missing entities or use canonical IDs. This is a SOURCE metadata-quality gap, not a compiler gap.
- No new engines/primitives/algorithms; RPDE resolution extended + report generator. Regression 57/57. 0 wrong-class preserved.

## [Compiler-1.3] F-023 Cross-registry re-verification + '/'-compound fix — FROZEN
- CORRECTION to F-022: "181 absent" was over-claimed. Exact search across ALL registries reclassifies:
  169–174 genuine metadata gap · 7 registered under another entity type · 5 compiler format issues.
- Phase-1 fix: prose resolution now splits '/' compounds → G2/G3 → GATE-002/003 recovered. +13 gate edges (276→289).
- Canonicalization report corrected: separates resolved_registry / resolved_component / registered_other_type / not_found / GENUINE_ABSENT.
- Phase localization: problem occurs only in Phase 1 (matcher format, 5, fixed) + Phase 6 (metadata gap, ~169). Phases 2/4/5 (resolution/primitive/algorithm) clean; Phase 3 (query target-type) = 7 edge cases.
- No new engines/primitives/algorithms. Regression 60/60. 0 wrong-class.

## [Runtime-1.2] F-024 Lifecycle Population Operation (Runtime Engine execution path) — FROZEN
- CORRECTION: this is NOT a new engine. Lifecycle population = execution of the existing LIFECYCLE query via the frozen Query→Primitive Sequence inside the existing Runtime Engine. lifecycle.py is an implementation module.
- Fixed universal lifecycle template (Entry→Handler→Gate→Pipeline→Bridge→Validator→Module→Output→Evidence).
- Per-entity population from the Universal Property Graph + row; consumes frozen composition + IR (no lifecycle change, no new primitive/engine-derivation).
- Empty-stage diagnosis: not_referenced / compiler_missed / registered_other_type / genuine_metadata_gap — "empty ≠ gap".
- Facade: AKE().lifecycle(token). Regression 65/65.

## [Runtime-1.3] M10 Algorithm Derivation (deterministic planner) — FROZEN
- Architecture separation: Relation Inventory + Canonical Query Selection (Query Derivation) SEPARATE from Algorithm Derivation (planner).
- Deterministic planner: primitive sequence derived from Query Definition + Registry Schema + Primitive Library. No hardcoded per-query bindings, no LLM reasoning (verified: derive() has no query-name branches).
- Query Definitions + relation inventory are DATA; planning rules are a small deterministic objective->sequence rule set.
- Proven: GET_HANDLER/GATE/OWNER/CATEGORY/UPSTREAM derive+execute across Command & Feature families; new query (GET_MONITORS) auto-derives with no code change; every derived primitive in the 45-library (closure).
- walk_relationship parameterized by relation; render_tree emits result. Regression 72/72.
- OP-005 realized as deterministic rule-based planner; externalizing planning rules to a registry is future refinement.

## [Runtime-1.3.1] M10 validations — FROZEN
- Query Definitions externalized to data registry (ake/defaults/query_definitions.json); planner loads from JSON.
- V1 name-independence PROVEN: rename-invariance + value-sensitivity + zero GET_* literals in planner logic.
- V2 zero-code PROVEN: Monitors relation (workbook data) + GET_MONITORS (query registry) → derived + executed; planner .py byte-identical (md5 unchanged).
- Freeze statement: deterministic planner + extensibility + zero-code all validated. Planning-rules externalization explicitly deferred (not claimed). Regression 75/75.

## [Validation-1.0] F-026 Capability Universe + Workbook Constitution — FROZEN
- Capability Matrix: 10 categories / 31 canonical question types; per-entity + workbook-wide. Output is a Capability Universe, not an algorithm.
- Validated on EBIS: 1037 entities, all 31 question types answerable somewhere; universal floor (Identity/Integrity/Coverage/Evidence/Graph) for every entity; Control/DataFlow/Classification family-specific.
- Workbook Constitution validated in tiers: Minimum (1 sheet + PREFIX-N PK) = 8/31; Recommended (+FK +Evidence) = 18/31; Full (EBIS) = 31/31; numeric-PK violation = 0 entities.
- Publishable docs (GitHub/open-source ready): README.md, WORKBOOK_CONSTITUTION.md, CAPABILITY_UNIVERSE.md.
- Runner emits capability_universe.json. Regression 81/81 (all historical findings pass).

## [Usability-1.0] F-027 Discovery Mode — FROZEN
- On upload, runner prints a Discovery landing page: registries, entity types (prefix/count/examples), capability categories, and copy-paste query examples — no need to know IDs in advance.
- Facade: overview(), list_entities(prefix), search(term), describe(id). AKE_MASTER REPL commands: overview | help | list <PREFIX> | search <term> | describe <ID> | <ID> | GET_X <ID>.
- Proven on a non-EBIS BIOLOGICAL workbook (Gene/Protein/Pathway) with zero code change: discovery, search('TP53')->GENE-1, describe, queries all work. Regression 81/81.

## [Discovery-1.0] F-028 Discovery Engine -> Registry Universe — FROZEN
- Discovery Engine produces a Registry Universe (registries, entity types, ID patterns, relation types, schema, DERIVED capabilities, search modes). The Discovery Report is a rendered VIEW of it, not a feature.
- Everything derived from the workbook: registry display names (from catalog), entity prefixes, relation vocabulary, and capability availability. No EBIS-specific literals in the engine (verified).
- Capabilities are per-workbook: EBIS = 10/10 available; biological workbook = Control/DataFlow/Ownership/Classification NOT available (derived). Runner emits registry_universe.json; landing page + REPL use the report.
- Regression 86/86.

## [Product-1.0] F-029 Universal Architecture Search Engine (product shell) — FROZEN
- AKE reframed as a Universal Architecture Search Engine: continuous state machine (Load→Discover→Validate→Ready→Query→...→Exit), never terminates until 'exit'.
- Validation + evidence-based Confidence dashboard (duplicate/missing PK, broken FK, empty registries, missing evidence, duplicate names). Confidence derived, not fixed.
- Search-first interpreter (Search→Interpret→Resolve→Answer), verb(object) syntax, resolve-by-name, honest "cannot answer" (no guessing).
- Dynamic help + verbs derived from discovered capabilities (biology hides Control/DataFlow verbs). Developer mode separate/hidden (dev ir|registry|capability|rules).
- Single-cell Colab shell (AKE_Colab_Shell.py) runs in-process; AKE_SHELL.py entry point. GET_NEIGHBORS added to query registry (data). Regression 92/92.

## [Product-1.1] F-030 Classification + verification gate, F-031 Stateful explorer — FROZEN
- Stage-1 Workbook Classification: Architecture Registry / Generic Relational / Business Dataset / Unknown, with a Candidate→Verified→Rejected verification gate carrying evidence + reasons. Fixes the core flaw: business datasets no longer get fabricated "Registries: 0 / Confidence: 75%".
- Two-stage (UKMS) framing: Stage-1 maps any workbook into the internal canonical model; Stage-2 engines consume only the canonical model. New workbook types = new importer, not core changes.
- Stateful architecture explorer: object = page; numbered vertical Available/Unavailable menu; number runs action; result number drills in; breadcrumb + back/home/tree/history. Replaces the stateless CLI.
- Runner is classification-aware; emits classification.json. Verified on EBIS (Architecture/Verified) + Superstore-like business dataset (Business Dataset, no arch queries). Regression 100/100.

## [Product-1.2] F-032 One Universal Explorer + structural TabularImporter — FROZEN
- Removed the separate "Business Dataset mode". Every structurally-analyzable workbook is mapped into the same canonical graph and explored through the same stateful explorer; only graph richness differs.
- Classifier selects a STRUCTURAL importer (Registry/Tabular), never a domain and never a UX. AKE contains no domain-specific logic (verified: no domain names in importers).
- TabularImporter maps a flat table structurally (measure/attribute vs dimension/entity vs near-unique text) into entities+relationships. US_Superstore.xlsx -> 9507 entities (Order/Customer/Region/Category/Product/...) explored by the identical explorer.
- Explorer menu is now relation-driven (derived per object): EBIS shows owner/handler/gate; a tabular workbook shows its own dimensions. Regression 102/102.
