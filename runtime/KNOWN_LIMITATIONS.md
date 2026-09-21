# AKE Known Limitations (open — not claimed complete)

| ID | Limitation | Layer | Impact | Status |
|---|---|---|---|---|
| F-05 | Numeric / non-prefixed PKs invisible | Discovery/Loader | non-ID workbooks yield 0 owners | **CLOSED** — structural PK-schema inference + prefix-independent identity registry; numeric PKs resolve, get an owner sheet, derive FK edges, are searchable, and open by typing the bare id. Evidence: `tests/test_canonical_identity.py` ("numeric pk schema inferred", "numeric id resolves to correct class", "numeric owner_sheet works (no prefix regex)", "numeric FK edge derived", "numeric entity is searchable by name", "numeric entity opens by typing bare id"). See IDENTITY_SPEC.md §3. |
| F-06 | Composite PK unsupported (genuine multi-column key, e.g. row identity = Plate+Well across two columns) | Loader | multi-column keys not indexed | **OPEN** — the loader still uses only the first pk column, so two rows sharing that column's value (P1/A1 and P1/A2) collapse to one node, and `resolve('P1')` returns None. Note: `_schema_of` reports a `composite` *label* only for single-cell values containing `::`/`/`/`\|`; it does not assemble a key from multiple columns. No test asserts multi-column composite support (by design — it isn't implemented). |
| F-07 | Custom relationship column names when a Registry Catalog is present (sheet uses e.g. From/Kind/To instead of Source/Relation/Target/Flow) | Workbook Runtime | edge schema hardcoded to Source/Relation/Target/Flow | **OPEN** — worse than silent: a relationship sheet with non-default column names currently raises `TypeError: list indices must be integers or slices, not NoneType` in `_build_relationship_graph` (the column index resolves to None). FK-style edges via the catalog still work; a free-form relationship sheet with custom headers does not. No passing test covers custom relationship headers. |
| F-08 | Duplicate PK values | Resolver / Identity | see split below | **PARTIALLY CLOSED** — depends on whether the duplicate is across registries or within one (these are different problems; see the two rows below). |
| F-08a | Duplicate PK **across registries** (same raw pk in two different registries, e.g. `1` in Alpha Registry and `1` in Beta Registry) | Identity | previously collapsed into one node | **CLOSED** — class-scoped canonical identity `(class, pk)` makes them two distinct nodes; `resolve('1')` returns `ambiguous_id` with both class candidates and never auto-opens the wrong one; display id stays the raw pk (no synthetic `1@Class`). Evidence: `tests/test_canonical_identity.py` ("same pk across classes -> 2 distinct canonical keys", "ambiguous bare pk returns candidates", "canonical selection token resolves to the right class", "colliding pk keeps raw display id"). |
| F-08b | Duplicate PK **within the same registry** (same raw pk appears twice in ONE registry, e.g. `1` twice in Alpha Registry — the original "collapsed to first row" case) | Identity / Loader | silent data loss | **OPEN** — the canonical key is `(class, pk)`, which is identical for both rows, so the graph still keeps only ONE node (now last-row-wins: the second row's data overwrites the first). `resolve('1')` reports `ambiguous_id` but its candidate list contains the *same* surviving row twice rather than two real rows. A within-registry duplicate pk is a malformed workbook (pk should be unique per registry); AKE does not yet detect or preserve both rows. No test asserts within-registry duplicate preservation. |
| F-02 | Name resolution can return wrong-class entity | Resolver | ambiguous names unranked | **CLOSED** — the resolver is type-aware: an exact name that is unique across classes auto-resolves; the same name in two classes returns `ambiguous_name` candidates and never auto-opens an arbitrary class. `Class:name` disambiguates. Evidence: `tests/test_canonical_identity.py` ("ambiguous name does NOT auto-open (id is None)", "ambiguous name returns both class candidates", "Class:name disambiguates to the right class", "shell shows candidates for ambiguous name"). See IDENTITY_SPEC.md §6. |
| Command prose-links | Cross-registry verified: ~169-174 genuine metadata gap + 7 registered-other-type + 5 format(fixed) | Data model (source) | Command edges 0.08→2.70/cmd; ~174 need author registration | PARTIAL (F-021/022/023); residual verified as SOURCE data-quality via exact all-registry search |
| IR refactor | Downstream engines still read workbook in code | Engines | IR-sufficiency proven, not enforced | OPEN (mechanical) |
| Template scope | Bundled defaults cover attribute+relationship kinds only | Derivation | execution/ordering/lifecycle kinds need registry rows | OPEN |
| F-038 | `ReachabilityEngine`/`shortest_path()` traverse forward edges only | Derivation (`ake/reachability_engine.py`) | an entity with zero outgoing edges (a dimension/leaf entity in a star schema) derives no reachability, even when reachable via a shared hub entity; confirmed on 10 of EBIS's own 23 catalog classes (secondary/metadata registries, not the core Feature/Component/Handler chain) | OPEN — fails closed (reports nothing), never reports a wrong path |

Whole-system universality is NOT claimed. Proven: RPDE domain-generality + Property-Graph IR sufficiency (within evaluated workbooks).

## Resolved (see CHANGELOG.md)
| ID | Was | Status |
|---|---|---|
| F-15 | `AKE_MASTER.py workbook.xlsx` entered REPL and silently produced no output under non-interactive stdin | FIXED — batch mode is now the default for an explicit workbook argument |
| — | `AKE_Colab_Shell.py` (documented single-cell interactive entry point) was missing from the package | FIXED — restored |
| F-033 | `AKE_MASTER.py`/`AKE_SHELL.py` didn't extract an explicit `.zip` argument, only auto-discovered zips | FIXED — both now extract like `ake/runner.py` already did |
| F-034 | `AKE_MASTER.py` REPL crashed with a raw traceback on Ctrl+C | FIXED — catches `KeyboardInterrupt` like `ake/shell.py` already did |
| F-035 | A malformed (not missing) Registry Catalog sheet raised a raw `KeyError` | FIXED — falls back to `_infer_catalog()`, same as a missing sheet |
| F-036 | Corrupt/missing workbook raised a raw low-level exception with no context | FIXED — clear, actionable message |
| F-037 | 17 of 29 queries `capability_matrix.py` advertises as supported raised a raw `KeyError` from `AKE.answer()` (only `GET_FAMILY` was reported; the same gap affected `GET_ROLE`, `GET_PURPOSE`, `CHECK_FK`, `IS_ORPHAN`, and 12 others) | FIXED — `AKE.answer()` returns a clear note for any query not in `QUERY_DEFINITIONS`, instead of crashing. The queries themselves are still unimplemented — this only stops the crash. |

## Documented behavior (not bugs, found during live testing)
- **Breadcrumb path can repeat an object.** `Current: A > B > C > A` after revisiting A is
  expected — the breadcrumb shows the actual path taken (like browser history), not a deduplicated
  set. The separate `history` list (shown by the `history` command) is already deduplicated.
- **Typed text at the `AKE >` prompt always attempts entity/ID resolution — it never matches a menu
  action's label.** Typing a menu item's number (e.g. `6`) runs that action; typing its label as
  text (e.g. `Family`) instead searches for an entity named or matching "Family". If the workbook
  happens to have a real entity with that name, you'll land on that entity instead of running the
  action — with no error, since as far as the runtime is concerned that's a normal, successful
  lookup. Use the number.


## UX-1.3 residual (action-dispatch)

| ID | Limitation | Layer | Impact | Status |
|---|---|---|---|---|
| UX-1.3-a | `/_ake/availability` route lives in the launcher gateway, not the `ake_server` package | Server/Gateway boundary (ADR-008) | bare `ake_server` (no gateway) paints entity menus without count badges; menus still work | OPEN (by design; promoting the route into the package is a separate scope decision) |
| UX-1.3-b | Compare/analyze console text still caps printed rows at 80 | Shell render (text pane only) | cosmetic — structured payload + `result_total` carry the full count; dashboard renders all targets | OPEN (cosmetic) |


## UX-1.4 — Canonical identity (items CLOSED)

| ID | Item | Status |
|---|---|---|
| ID-NUM | Numeric primary keys unsupported (discovery/owner-lookup assumed `[A-Z]+-` prefixes; numeric ids invisible to search/nav) | **CLOSED** — structural PK-schema inference + prefix-independent identity registry; numeric pks are first-class. See IDENTITY_SPEC.md. |
| ID-NAME | Name resolution used first cross-registry label match (same name in two classes could open the wrong entity) | **CLOSED** — type-aware resolver returns candidates on cross-class ambiguity; never auto-picks. |
| ID-PKCOLL | Same raw pk across registries collided into one graph node | **CLOSED** — class-scoped canonical identity; colliding pks are distinct nodes; picker uses opaque internal token, raw display id preserved. |

Note: ID-PKCOLL covers the **across-registry** duplicate only (= F-08a). Duplicate PKs **within one registry** (F-08b) are a separate, still-OPEN problem — the `(class, pk)` canonical key is identical for both rows, so one still overwrites the other. See the F-08a / F-08b split in the top table.


## UX-1.5 — Deployment / tunnel

| ID | Item | Status |
|---|---|---|
| DEP-NXDOMAIN | Dashboard URL unreachable (DNS_PROBE_FINISHED_NXDOMAIN / "site can't be reached") right after launch, before edge DNS propagates | **MITIGATED** — launcher waits for real reachability before printing the URL and retries with a fresh subdomain (TUNNEL_DNS_TIMEOUT / TUNNEL_ATTEMPTS). |
| DEP-DROP | Quick tunnel drops mid-session, killing the URL | **MITIGATED** — reconnect watchdog re-establishes a readiness-verified tunnel and updates the URL. |
| DEP-EPHEMERAL | trycloudflare quick tunnels use a NEW random subdomain each run, so the URL is never stable across launches/reconnects | **OPEN (by design)** — ephemeral tunnels have no fixed hostname. For a stable URL, use a named Cloudflare tunnel with a real domain (out of scope for the zero-config quick-tunnel launcher). |


## UX-1.6 — Discovery console

| ID | Item | Status |
|---|---|---|
| CON-DUP | Risk of a second, parallel context model duplicating the registry catalog | **AVOIDED** — the initial ContextEngine was removed; contexts are read directly from model.catalog (no duplicate data). |
| CON-CHAIN-DEPTH | discovery_chain shows one hop (entity -> its related entities grouped by class), not a fully expanded multi-level tree | **OPEN (by design)** — each related entity is itself clickable to descend a level; a single flat multi-hop expansion is intentionally not rendered to keep the view readable. |
| CON-SCOPE-NAMES | Context words resolve against a workbook's own registry nouns/prefixes; a word absent from the workbook (e.g. "store"/"gene" in an EBIS book) resolves to nothing | **BY DESIGN** — vocabulary is dynamic per workbook, never hardcoded; empty context falls back to global search. |


## UX-1.7 — Semantic perspective engine

| ID | Item | Status |
|---|---|---|
| SEM-DEPTH | Discovery was single-hop only (entity -> immediate neighbours) | **CLOSED** — `perspective()` does multi-hop transitive traversal, layered by hop + class band. Evidence: `tests/test_semantic_perspective.py` ("traversal is multi-hop", "reached_count exceeds immediate neighbour count"). |
| SEM-DIRECTION | No notion that A->B differs from B->A | **CLOSED** — `intersect(a,b,direction)` is directional; out vs in and origin A vs B are different questions. Evidence: same test ("intersection out vs in are different questions", "intersect(A,B)/(B,A) attribute paths to different origins"). |
| SEM-HARDCODE | Risk of embedding entity/registry names in the engine | **CLOSED (guarded)** — engine code has zero domain literals; a guard test strips comments+strings and fails on any. Evidence: same test ("engine code contains NO hardcoded domain/registry literals", "no entity-id / registry-name string constants"). |
| SEM-REDERIVE | Risk of re-reading the workbook per query | **CLOSED** — Phase-2 runs only on the in-memory graph; a test answers queries with the workbook path removed. Evidence: same test ("queries still answer with workbook path gone"). |
| SEM-STRENGTH | "Strength" is a derived heuristic (path length x execution x evidence), not a measured physical quantity | **BY DESIGN** — it ranks relatedness within a workbook; it is not a claim about real-world coupling magnitude. |


## Certification Audit v1.0 findings (see AUDIT.md)

| ID | Item | Status |
|---|---|---|
| SCALE-BUILD (RESOLVED) | Phase-1 build is super-linear: `reachability_engine.derive()` probes every candidate entity (741k BFS calls at 20k entities), so a 100k-entity workbook takes ~256s to build (queries stay sub-ms) | **OPEN** — fix: memoise `_class_of`, sample instead of exhaustively confirming class-pairs, and/or reduce on a condensed class graph. Not a blocker; documented. |
| SCALE-SEARCH (RESOLVED) | Name search is a linear owner-row scan (~800ms at 100k entities); IDs are indexed but names are not | **OPEN** — fix: build a lowercased name→(registry,id) index at Phase-1 for O(1) exact/prefix name search. |
| HARDCODE-RPDE (RESOLVED) | `relational_primitive_engine.py` branches on domain literals `"handler"` and `"Component"` (F-022 impl=component fallback); 48/1937 edges on the reference workbook use it | **OPEN (non-blocking)** — correct on EBIS, dead on other workbooks, but domain knowledge in decision logic. Fix: derive the fallback target from the relation's declared FK/target class via `relation_target_map()` instead of literals, then add a code-token guard test. |


## UX-1.8 — Certification fixes + Guided Discovery (status updates)

| ID | Item | Status |
|---|---|---|
| HARDCODE-RPDE | handler/Component literals in RPDE | **RESOLVED** — derived from data (dominant resolving registry); 48 edges preserved, 0 literals. |
| SCALE-BUILD | super-linear Phase-1 build | **RESOLVED** — memoise + sample; 100k build 256s→35.4s. |
| SCALE-SEARCH | linear name search | **RESOLVED** — name index; exact-name 800ms→0ms. |
| GUIDE-DEPTH | suggest_next looks 2 hops out | **BY DESIGN** — chips open the entity to continue exploring deeper; keeps the suggestion set focused and ranked. |


## UX-1.9 — Universal Intent Discovery

| ID | Item | Status |
|---|---|---|
| F-D CONTEXT-BOUNDARY | context treated as a search boundary (query filtered inside its registry) | **RESOLVED** — `discover()` makes context the source node; query resolves globally; `path_between` finds the cross-registry path. Evidence: tests/test_discovery_pipeline.py. |
| PATH-DIR | shortest_path was forward-only | **RESOLVED** — `path_between` is bidirectional (reuses fwd+rev), traverses reverse FKs. |
| EVIDENCE-TIER | relations shown without confidence | **RESOLVED** — L1..L5 tiering + confidence (product of hops) on every path; structural > lexical enforced. |
| TYPO | resolver had no edit-distance | **RESOLVED** — difflib step against discovered names; candidates only. |
| L5-LEXICAL | L5 is lexical similarity, not true semantic/LLM understanding | **BY DESIGN** — labelled "lexical", weighted lowest; a real embedding/LLM tier can slot in later without backend changes. |
