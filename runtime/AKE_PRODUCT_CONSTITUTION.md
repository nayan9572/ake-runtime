# AKE Product Constitution v1

AKE is a **Universal Architecture Search Engine**, not a command runner. One workbook in, a queryable,
self-describing engine out — for any domain.

## Runtime state machine (never terminates until exit)
```
Load → Discover → Validate → Ready → (Query → Answer → Ready)* → Exit
```

## Phase 1 — Input
Accepts `.xlsx` or a `.zip` containing one (future: DB/JSON). No loading logs shown to the user.

## Phase 2 — Discovery (automatic, verified, never silent)
Structure/PK/FK/entity-types/relationship-types/registry/schema/capability/integrity — all detected by the
Discovery Engine into a Registry Universe. Any problem is reported, not hidden.

## Phase 3 — Validation → Ready dashboard (structured, not just text)
```
AKE Ready
  Objects        : 1037 OK
  Types          : 13 OK
  Relationships  : 1938 OK
  Schema         : Complete OK
  Integrity      : Passed OK
  Confidence     : 98%
```
Checks: duplicate/missing PK, broken FK, empty registries, missing evidence, duplicate names. Warnings
are surfaced explicitly under **Notes**.

## Confidence (evidence-based, not a fixed number)
Derived from validation evidence: broken FKs, duplicate IDs, empty registries, evidence coverage, schema
completeness, presence of relationships. An incomplete workbook shows a lower score **with reasons**.

## Help (dynamic — from discovery, never hardcoded)
`help` lists only the questions this workbook can answer, generated from its discovered capabilities and
query registry. A workbook without control-flow never shows `handler(...)`.

## Query language (search-first)
Every input flows **Search → Interpret → Resolve → Answer** — not an if/else command parser. Syntax:
```
purpose(FEAT-021)   describe(observer)   lifecycle(CMD-010)   owner(MOD-004)
related(ca50)       used_by(FEAT-016)    uses(CMD-002)        evidence(CMD-002)
search(<text>)      list(<PREFIX>)       summary()            verify()
```
- Objects resolve by ID **or name** (e.g. `describe(TP53)` → the gene).
- Unsupported question → honest refusal, no guessing:
  `This workbook cannot answer 'handler' because it has no Control relationship.`
- Unknown object → search suggestions.

## Universal rule
Entity types, prefixes, relation types, verbs, help, and capabilities are all **derived from the
workbook**. Nothing (Command, Handler, Gene, Sensor, …) is hardcoded. The workbook's own terminology is
what the user sees.

## Developer mode (separate, hidden by default)
`dev` toggles it. `dev ir | dev registry | dev capability | dev rules | dev summary` expose the Canonical
Graph / IR / Registry Universe / Capability Universe / rules / timing. Normal users never see these.

## Single-cell Colab (Shift+Enter)
One cell: upload → discover → validate → ready → interactive loop (see `AKE_Colab_Shell.py`). The shell
runs in-process so the prompt stays live until you type `exit`.

---

# v1.1 — Two-stage architecture, classification & verification

## Every workbook is a source of knowledge (no assumptions)
AKE never assumes a workbook is an architecture workbook, a business dataset, or that it contains
registries. Its first responsibility is to discover how the knowledge is organized, then translate it
into a canonical model.

## Two-stage design (UKMS)
```
Any Workbook → [Stage 1] Classification + Structure Discovery → Canonical Model (internal UKMS)
             → [Stage 2] Query / Capability / Validation / Confidence / Navigation Engines
```
- **UKMS is the internal canonical model, not a required input format.** Existing registry workbooks (EBIS)
  map in with no extra work; other sources need only an importer/mapper.
- **Part A (universal, never changes):** Entity, Identifier, Attribute, Relationship, Type, Metadata,
  Evidence, Source, Constraint.
- **Part B (domain vocabulary, discovered):** Command/Handler or Patient/Doctor or Invoice/Account — these
  are labels, never hardcoded.
- **Engine boundary:** the Stage-2 engines consume only the canonical model (the Universal Property Graph
  IR); a new workbook type requires a new importer/mapper, not core-engine changes.

## Stage-1 Workbook Classification (with verification gate)
On upload AKE classifies from structural evidence: Architecture Registry Workbook · Generic Relational
Workbook · Business Dataset · Unknown Workbook. Only a **Verified** Architecture Registry Workbook enters
the architecture explorer; others get an honest structural summary (type, sheets, rows, columns) — never a
fabricated "Registries: 0 / Confidence: 75%".

## Verification gates — Candidate → Verified → Rejected
Discovery and Verification are separate. Every important transition ends with a gate that uses structural
evidence and consistency checks (not hardcoded rules):
`classification · structure · UKMS mapping · relationship discovery · capability discovery · query resolution`.
Every discovered fact carries evidence; every promoted fact passes verification; every decision records a
reason. Verification may build in-memory consistency tests but never modifies the source workbook.
Principle: **evidence-driven, not assumption-driven.**

## Stateful architecture explorer (not a stateless CLI)
Each object is a page. Opening an object shows a numbered, vertical menu of exactly what you can ask
(Available) and what you cannot (Unavailable) — derived per object. A number runs that action; a result's
number drills into that object. Breadcrumb + `back | home | tree | history` maintain context, so you never
retype the object:
```
AKE > CMD-008
Current: CMD-008
CMD-008  [Command]
Available
   1. What is   2. Name   3. Purpose   4. Owner   5. Handler ...
Unavailable
   x  Gate   x  Category ...
AKE > 4
Owner of CMD-008
   1. CMD-008 -module-> MOD-032
AKE > 1
Current: CMD-008 > MOD-032   (now MOD-032's page)
```

---

# v1.2 — One Universal Knowledge Explorer (no per-domain, no per-type modes)

## There is exactly one user experience
Every workbook that can be structurally analyzed is mapped into the same internal Universal Knowledge
Graph and explored through the same stateful explorer. There is **no "Business Dataset mode"** and no
per-domain product. The only difference between workbooks is **graph richness**: EBIS exposes
owner/handler/gate; a flat table exposes its own dimensions (e.g. customer/product/region). Same explorer,
same navigation, same verification.

## The classifier selects a STRUCTURAL importer, never a domain, never a UX
AKE contains **no** domain-specific logic and recognizes **no** business domain as a special case. Every
workbook is an unknown knowledge source. Discovery is based purely on structural evidence: identifiers,
references, attributes, metadata, relationships, hierarchy, graph connectivity, constraints. The classifier
picks a structural strategy only:
```
Registry  · Tabular  · Relational  · (extensible) Graph / Hierarchical / Mixed
```
Importers are structural, never domain-named. Adding support for a new structural shape is a new
importer; adding a new subject area (finance, medical, logistics, anything unseen) requires **no** code —
the same structural discovery builds the graph.

## Tabular mapping (structural, domain-free)
For a flat table each column is typed by evidence alone: numeric/date/constant -> attribute (measure);
categorical (repeated, not near-unique) -> entity type (one entity per distinct value); near-unique text
-> attribute. Each row becomes a Record entity linked to the dimension-value entity of every dimension
column, with row-level evidence. The result is the same canonical graph the registry path yields, so the
identical explorer, capability engine, validation, confidence, and verification all operate unchanged.

---

# PART II — ACCEPTED FINAL ARCHITECTURE (governing; load into working memory every task)

This section is ACCEPTED and governs every future implementation. Do not summarize or
reinterpret. If an implementation conflicts with it, the implementation is presumed wrong until
architectural evidence proves otherwise. Change only on architectural evidence, never convenience.

Task order, always: (1) load this, (2) implement only the requested stage, (3) verify,
(4) regression, (5) report Bug / Root Cause / Implementation / Verification / Regression / Next
Required Stage — nothing else.

## Accepted pipeline
```
Natural Query → Tokenizer → Universal Language Registry → Workbook Knowledge Registry
  → Canonical Intent → AlgorithmDerivation (single planner) → Canonical Plan
  → RuntimeEngine (single executor) → UniversalGraph → Evidence → Answer
```

## Invariant authorities (one owner each)
- Resolver: `EntityResolver` (+ `CanonicalIdentity`) — only it resolves workbook entities.
- Planner: `AlgorithmDerivation` — all plans originate here.
- Executor: `RuntimeEngine.run` — executes opcode plans only; never plans/parses/resolves.
- Graph: one `UniversalEdgeGraph`, built once; never re-derived per query.
- Evidence: `attach_evidence` + `_rel_source` + `EVIDENCE_TIERS` (structural > lexical, weakest-link).

## Hard rules
No parallel systems. Parser grammar STABLE (vocabulary evolves, parser does not).
Workbook-independent (no hardcoded workbook/entity/alias names). Learned vocabulary requires
evidence + provenance + confidence + lifecycle; never grows from arbitrary user queries.

## Stage 1 — verified owner survey (from code)
- ABSENT (no owner; must be created): Tokenizer, Universal Language Registry, Canonical Intent Builder.
- EXISTS, must be EXPANDED not duplicated: EntityResolver (consume registries), AlgorithmDerivation
  (accept Canonical Intent), RuntimePrimitives (5 stub opcodes already made real — 360/360),
  WorkbookModel/importers (Knowledge Registry derived at load), evidence system.
- Executor/Graph correct as-is.
- Stage 4 vector retrieval = offline sklearn TF-IDF + char-n-gram + NearestNeighbors kNN over
  workbook vocabulary; honestly labelled lexical/vector retrieval, NOT neural embeddings (runtime
  has sklearn/numpy/scipy only).

## Stage ledger
1 Survey ✅ · 2 Operation inventory + 5 stub opcodes real ✅ · 3 Universal Language Registry ·
4 Workbook Knowledge Registry · 5 Living Vocabulary Registry · 6 Resolver evolution ·
7 Canonical Intent Builder · 8 AlgorithmDerivation expansion · 9 Dashboard single prompt +
Engineering Mode · 10 Reuse audit before every new layer.

---

# PART III — Stage 3 refinement (ACCEPTED, evidence-driven)

Three corrections were accepted after challenge, and are now governing:

1. **Concept set = semantic roles only (BOUNDARY).** Canonical concepts carry ONLY canonical +
   type. The Language Registry stores NO opcodes, kwargs, plan fragments, or runtime parameters.
   The concept→opcode transformation (TOP → sort desc + limit; AVERAGE → group + aggregate avg) is
   AlgorithmDerivation's EXCLUSIVE responsibility (Stage 7). Rationale: grammar assigns roles;
   the planner turns roles into primitives. Putting opcodes in the registry created a second owner
   of execution mapping and violated one-capability-one-owner — corrected.

2. **Versioned Grammar (not "stable forever").** The TYPE set and canonical concept set MAY grow
   (e.g. future CAUSE / GOAL / PROBABILITY / UNCERTAINTY). They are versioned via `GRAMMAR_VERSION`;
   within a version the meaning is fixed. "Grammar stable" is replaced by "grammar versioned".

3. **Concept ⁄ Vocabulary separation (two owners).** The Language Registry stores ONLY canonical
   concepts (+ their opcodes + type). Every human surface word is an alias owned by the Living
   **Vocabulary Registry** (`ake/vocabulary_registry.py`), each entry carrying word, canonical,
   type, source, evidence, confidence, version, status (active/deprecated/rejected). The Language
   Registry preserves all prior APIs (`lookup`, `register_alias`, `audit`, `concepts`,
   `is_concept`) by delegating alias storage to the Vocabulary Registry.

**Explainability layer (required product behaviour):** `VocabularyRegistry.explain(word)` returns
`{word, type, candidate, confidence, source, reason, status}` — e.g. `Revenue → ATTRIBUTE →
candidate total_amount → confidence 0.94 → source Workbook Vocabulary → reason alias match`.

Ownership after Stage 3: Language Registry = concepts (versioned grammar). Vocabulary Registry =
all aliases + lifecycle + explainability. Neither resolves workbook entities (Resolver owns that).


---

# PART IV — Pre-Stage-4 architecture corrections (ACCEPTED, governing)

1. Concept → opcode is 1:N and parameterised, but that mapping lives in AlgorithmDerivation
   (Stage 7), NOT in the Language Registry. The registry is semantics-only.
2. Vocabulary is ambiguity-aware: a word holds a LIST of candidates; each candidate carries its
   own confidence/evidence/source/reason. Resolution picks the best later (Stage 5/6).
3. Confidence is always evidence-backed: never a bare number. Every candidate stores confidence +
   reason + evidence + matched_signals (e.g. 3/3) + source.
4. Vocabulary is append-only with full lifecycle: ACTIVE / DEPRECATED / REJECTED / SUPERSEDED.
   Nothing is overwritten; complete history is auditable (add supersedes prior same-canonical
   ACTIVE, keeping it in history).
5. **Stage-4 rule (BEFORE building the Workbook Knowledge Registry):** first audit
   workbook_runtime.py + the catalog, identify existing owners (loader, catalog, model.rows,
   owner_by_prefix, evidence_col, _rel_source), and REUSE existing authority. Create new ownership
   only if a genuine gap is proven.
6. **Grammar isolation:** the Workbook Knowledge Registry must NEVER create grammar concepts,
   modify GRAMMAR_VERSION, or add grammar rules. Its ONLY job is to grow the Vocabulary Registry
   with workbook knowledge (ATTRIBUTE/entity/relation aliases, source "Workbook Vocabulary").
   Grammar remains versioned and independent.

Boundary summary: Grammar assigns semantic roles. Vocabulary grows (workbook-independent core +
workbook-derived aliases). Resolver combines them (Stage 5). Canonical Intent carries roles, not
opcodes (Stage 6). AlgorithmDerivation alone turns roles into opcode sequences (Stage 7).
RuntimeEngine executes (Stage 8). One capability, one owner, at every layer.

---

# Stage 4 — Workbook Knowledge Registry (DONE)

Owner survey (proven): Loader=`WorkbookModel.sheets/hdr`; Registry builder=`catalog`/`owner_by_prefix`;
Schema=`col()`/`hdr`/`canonical_schema_discovery`; Alias=`node_attrs["name"]`/`_name_search_index`;
Metadata=`node_attrs["metadata"]=row_dict`; FK=`RelationalPrimitiveEngine.derive_edges`+`catalog[].fks`;
Relations=`_rel_source`/`universal_edges`. All reused. Proven gap: nothing fed these into the
Vocabulary Registry.

Implementation: `ake/workbook_knowledge_registry.py` (`WorkbookKnowledgeRegistry`) — harvests
ENTITY (node_attrs name→id), ATTRIBUTE (owner-registry hdr column names→registry.column), RELATION
(_rel_source rel→rel, declared 1.0 / inferred 0.7) into the shared Vocabulary Registry with source
"Workbook Vocabulary". Wired at load in `AKE.__init__` (self.vocabulary/language/knowledge).

Guarantees held: reuse-only (no new discovery); grammar isolation (0 concepts created,
GRAMMAR_VERSION unchanged); no hardcoded mapping (Revenue→total_amount only emerges if a workbook
column/alias makes it so). Verified: 1037 entities / 80 attributes / 33 relations harvested;
ambiguity preserved (ca50→FEAT-016,VAR-005); tests/test_workbook_knowledge.py 12/12; regression 392/14.

---

# Stage 4 provenance refinements (ACCEPTED)

1. **Owner authority on every candidate.** Each vocabulary Candidate records `owner` — the owning
   registry/object that produced it (entities: their registry/class; attributes: their registry;
   declared relations: the relationship sheet; inferred: "prose"; grammar aliases: "grammar").
   Surfaced in candidates(), entries(), explain() (+ alternatives). Resolution always knows which
   canonical authority stands behind each candidate.
2. **Entities are namespaced by owner, not merged.** The same name in N registries yields N
   separate candidates (distinct canonical id + owner); a namespaced form owner.name is available.
   Merging (if ever wanted) is the Resolver's job (Stage 5), not the harvester's.
3. **Attributes: one candidate per registry.** A column name appearing in N owner registries
   yields N ATTRIBUTE candidates, each canonical = registry.column, each owned by its registry.
4. **Explainable confidence (no bare scores).** Relation confidence = matched_signals/total_signals
   with reason + evidence: declared = 2/2 = 1.0 (relationship sheet / FK column, evidence
   catalog.fks); inferred = 1/2 = 0.5 (prose name resolution). The earlier hardcoded 0.7 is removed.

---

# Stage 5 — Resolver Evolution (DONE)

Owner: existing `EntityResolver` — extended, not replaced (classify() added; resolve() untouched).
Given optional language + vocabulary refs at construction (wired in AKE.__init__ after the
registries build).

`EntityResolver.classify(token)` combines, in order with strict separation:
  1) Language Registry — grammar CONCEPT? (registry decides; resolver only asks) -> kind=concept
  2) Vocabulary Registry — workbook candidates (ENTITY/ATTRIBUTE/RELATION), owner-tagged, ambiguity
     preserved -> kind=workbook (best + all candidates)
  3) resolve() — the resolver's own entity authority -> kind=entity | ambiguous | unresolved

Strict separation (verified): language never returns an entity id; vocabulary never parses grammar;
grammar has precedence; resolver arbitrates only. No parallel resolver authority.

Verified: show/top/count->concept; ca50->workbook (2 owner-tagged candidates); evidence(file:line)
->workbook (11 candidates); MOD-002->entity; unknown->unresolved. tests/test_resolver_evolution.py
13/13; regression 408/16.

---

# Stage 6 — Canonical Intent Builder (DONE)

New owner (none existed): `ake/canonical_intent.py` — `CanonicalIntentBuilder` + `CanonicalIntent`.
Turns a natural query into a complete SEMANTIC intent via the resolver's classify() per token.

Intent carries SEMANTIC ROLES ONLY: Targets, References, Actions, Questions, Qualifiers,
Constraints, Time, Values, Unresolved. NO operations field, NO opcodes.

Boundary (REFINED after challenge): concept→operation-sequence derivation (e.g. TOP→SORT_DESC+LIMIT,
NEAREST→DISTANCE+SORT_ASC+LIMIT, SIMILAR→EMBED+SEARCH+RANK+LIMIT) is ALGORITHMIC KNOWLEDGE and must
have ONE owner — AlgorithmDerivation (Stage 7). If the builder derived operations it would
gradually absorb planning knowledge and create a second planning authority. So the builder
assembles roles only; the planner derives BOTH the semantic operation sequence AND the opcode plan.
The semantic-operation vocabulary is NOT a fixed 3-item list — it is whatever the canonical
operation inventory supports, derived per query at Stage 7.

Reuse: builder delegates all token classification to the existing resolver; owns no entity logic
and no operation derivation. Verified: "Top 10 … after 2023" -> qualifiers[TOP], values[10,2023],
time[AFTER], and NO operations/opcodes in the intent. tests/test_canonical_intent.py 14/14.

---

# Stage 7 — AlgorithmDerivation expansion (DONE)

Canonical Operation Inventory (single source of truth): `ake/operation_inventory.py`. Defines the
complete semantic-operation vocabulary (OPERATIONS: GROUP, COUNT, SUM, AVG, MIN, MAX, FILTER, JOIN,
SORT_ASC, SORT_DESC, LIMIT, DISTINCT, COMPARE, PATH, DEPENDENCY, REACHABILITY, EXPLAIN, SEARCH,
SHOW) AND each op's realization to a real RuntimePrimitives opcode (SORT_DESC->(op_sort,{desc:True});
AVG->(op_aggregate,{fn:avg}); LIMIT->(op_limit,{n:<value>}); …). Every realization verified against
RuntimePrimitives.

Owner: AlgorithmDerivation (single planning authority) — the ONLY planner exposed to the
architecture. Its derivation methods `_derive_operations()` (level 1) and `derive_from_intent()`
(level 2) live directly on the class. The operation inventory (ake/operation_inventory.py) and the
concept→operation map (_CONCEPT_TO_OPS) are INTERNAL data assets of this owner — imported only by
algorithm_derivation.py, not parallel architectural owners. `IntentPlanner` is a thin internal
delegating alias, not a separate planner. The two levels under this one owner:
  * Level 1 (semantic planning): `_derive_operations()` — roles -> semantic operations via the
    internal _CONCEPT_TO_OPS (which references inventory constants, so vocabulary is not duplicated).
  * Level 2 (execution planning): `derive_from_intent()` — operations -> opcode plan via the internal
    inventory realize(). Returns {operations, plan, target}; plan is (opcode, kwargs) for RuntimeEngine.

Provenance of the 19 operations (evidence): a semantic grouping of the 47 RuntimePrimitives opcodes
(COUNT/SUM/AVG/MIN/MAX -> op_aggregate via fn; SORT_ASC/DESC -> op_sort via desc; the other ~33
primitives are internals not surfaced). Documented in operation_inventory.py.

Boundary held (verified): concept→operation and operation→opcode knowledge exists ONLY in
algorithm_derivation + operation_inventory. CanonicalIntent has no operation map; Language Registry
holds no opcodes. Full chain verified end-to-end: "Top 10 ca50" -> roles -> [SORT_DESC,LIMIT] ->
[(op_sort,{desc:True}),(op_limit,{n:10})] -> executed on RuntimeEngine. tests/test_intent_planning.py
14/14; regression 439/18.

---

# Stage 8 — Tokenizer (DONE)

Survey: no dedicated tokenizer owner existed — only an inline `.split()` in the intent builder.
Genuine gap. New owner created: `ake/tokenizer.py` (`Tokenizer` + `Token`).

ONE responsibility: raw text -> ordered tokens. It preserves multi-word phrases that exist in the
Vocabulary Registry (greedy longest-match, read-only existence check only), and keeps character
offsets (text/norm/start/end). It does NOT resolve entities/attributes/relations, classify grammar,
infer operations, build intent, plan, or execute — those keep their owners.

Never learns: the Vocabulary Registry learns; the tokenizer only consumes the latest vocabulary. A
new workbook phrase ("Purchase Order Line") is preserved automatically because it is in the
vocabulary — no tokenizer change (verified). Workbook-independent (no hardcoded names, no
resolver/planner calls in code).

Wiring: AKE builds Tokenizer(vocabulary) and passes it to the CanonicalIntentBuilder, which now
consumes tokens (original text, preserving case for exact-ID resolution) instead of splitting
itself. Verified: multi-word entity name kept as one token and flows through to a single target;
single words unchanged; offsets preserved; tokenizing doesn't mutate vocabulary.
tests/test_tokenizer.py 10/10; regression 449/19.

Pipeline now complete front-to-back: Natural Query -> Tokenizer -> Language Registry -> Workbook
Knowledge Registry -> Resolver -> Canonical Intent (roles) -> AlgorithmDerivation (ops+plan) ->
RuntimeEngine.

# Stage 8 refinements (ACCEPTED)

1. Greedy longest-match proven for nested phrases: with "purchase", "purchase order", "purchase
   order line" all in vocabulary, "Purchase Order Line Status" -> [purchase order line, status]
   (longest wins, not a shorter prefix). Locked in tests/test_tokenizer.py.
2. Single vocabulary API: the Tokenizer consults ONLY `VocabularyRegistry.phrase_exists(phrase)`
   which returns a bool. The tokenizer never calls candidates()/resolve() and never learns which
   underlying vocabulary (universal grammar vs workbook) backs a phrase — that abstraction stays
   behind phrase_exists(). Verified by code scan + behaviour.

---

# Stage 9 — Dashboard single prompt (DONE)

Survey: no endpoint ran the full Stage 1-8 pipeline (existing /discover used the older path). New
single entry point added; existing controls reused, not duplicated.

One public interface: "Ask AKE" [ Ask anything… ]. The ask-box calls ONE endpoint, /ask, which
routes to a single owner-method `AKE.ask_pipeline(query)`:
  Query -> Tokenizer -> Resolver(Language + Workbook vocab, via the builder) -> Canonical Intent
  (roles) -> AlgorithmDerivation.derive_from_intent (semantic operations + opcode plan) ->
  RuntimeEngine.run -> result + evidence. Returns tokens/intent/operations/plan/result/answer for
  explainability.

Engineering Mode: Context/Perspective/Intersect/entity+registry selection and the source-node
path box moved under a collapsed "Engineering Mode" panel. They remain available internally but are
not the public path.

Boundaries held (verified): the dashboard makes NO direct RuntimeEngine/planner/grammar calls (code
scan: no engine.run, no derive_from_intent, no op_* , no _CONCEPT_TO_OPS); it calls /ask only; one
public prompt (single askInput). ask_pipeline chains owners only (its body contains no opcode or
concept-map literals). No alternate execution path.

Robustness fix: RuntimeEngine seeds ctx["rows"]=[] and op_group tolerates it, so aggregation plans
(GROUP/AVG on an unseeded ctx) never KeyError. Verified: "average ca50" executes [op_group,
op_aggregate]. HTTP 22/22; /ask end-to-end OK; tests/test_single_pipeline.py 15/15; regression
468/20.

---

# Stage 9 — Audit closure (single rendering authority PROVEN)

Reuse-first survey (evidence, done before code): the render path is
  /query -> shell.handle -> ake.analyze() [analysis builder] -> shell.last_analysis
  -> build_nav_state (responses.py:83) [presentation-model owner] -> NavState
  -> renderEntity/renderAnalysis [renderer].
The Analysis Builder and Analysis Model ALREADY EXIST (ake.analyze + build_nav_state); no new
owner was created.

Render leak CLOSED: renderAsk + public debug cards removed. Ask calls goToken(target) so it
terminates in the SAME NavState path as entity-open and navigation. Proven over HTTP: /query FEAT-016
and /ask "CA50 analyse karo"->target->/query return identical NavState (mode, entity). /ask returns
data only (no HTML). Execution trace lives ONLY in Engineering Mode (#askTrace), never #stage.

Root-cause (rows): planner prepends resolve_entity when a target + row-consuming op exist, so rows
are seeded by the owning opcode ("average ca50" -> [resolve_entity, op_group, op_aggregate]);
ctx["rows"]=[] is only a defensive default.

Analyzer boundary VERIFIED: build_nav_state/_ui_hints assemble a model from structural facts; no
business rules; renderer chooses visual form. One rendering authority.

Workbook-independence PROVEN on a new Medical workbook (Patient/Condition/Medication/Department):
same pipeline, zero code changes; vocabulary emerged medical (lisinopril->MED-001); grammar
unchanged (33 concepts, v1); Ask end-to-end -> Analyzer. Regression 468/20.

---

# Architecture Diagnosis Layer + Health Score (DONE)

Survey: no health/validation-score owner existed (evidence-tiering + path confidence exist and are
reused, not duplicated). New single owner: ake/architecture_diagnosis.py (ArchitectureDiagnosis).

Purpose: a canonical DIAGNOSIS MODEL per query — layer-by-layer validation (Tokenizer, Vocabulary,
Grammar, Canonical Intent, Planner, Runtime) with each layer's verdict + owner + root cause, plus a
HEALTH SCORE (architecture-validation score, NOT AI confidence).

Blame rules (enforced): sequential — a downstream layer is judged only if upstream delivered valid
input (a word absent from vocabulary does NOT fail Grammar → Grammar=NOT_REACHED/"no grammar concept
matched", root cause stays on Vocabulary). Correct refusal (workbook lacks entities, no fabrication)
= NOT_APPLICABLE/NOT_REACHED, excluded from the score — architectural success, not failure.
Hierarchical flattening (>=2 ranking qualifiers collapsing to fewer LIMITs) = Planner FAIL, owner
AlgorithmDerivation — provable independent of workbook.

Verdicts: PASS / PARTIAL / FAIL / NOT_APPLICABLE / NOT_REACHED. Health = mean(PASS=1,PARTIAL=.5,
FAIL=0) over scored layers; band green>=85 / yellow>=55 / red.

Lazy + single rendering authority: `AKE.diagnose(query)` builds the owner on first use only.
Endpoints: /ask carries a lightweight health band; /diagnose returns the full lazy layer trace.
The diagnosis renders nothing — it returns a model the existing Analyzer/Renderer display. Three
canonical models (analysis / health / diagnosis) flow to ONE Analyzer + ONE Renderer.

Verified: CA50 analyse karo → 70% yellow (Vocabulary PARTIAL: "analyse" alias missing, Grammar not
blamed); executable impact query → 92% green, reaches Runtime PASS; composite query → Planner FAIL
(hierarchy flattened). tests/test_architecture_diagnosis.py 14/14; HTTP 22/22; regression 482/21.

---

# Architecture Correction — Before Further Implementation (ACCEPTED, governing)

The acceptance audit exposed MISSING CAPABILITIES, not bugs. Rules:

1. Vocabulary grows, Grammar stays stable. If a query fails because a semantic word (analyse,
   dependency) is unknown, do NOT blame Grammar — verify sequentially; if Vocabulary can't resolve
   the word, Grammar never received input. Fix belongs to the Vocabulary Registry (approved
   aliases). Grammar unchanged.
2. Preserve hierarchical intent. CanonicalIntent is currently flat (Targets/Qualifiers/Values).
   Natural language is hierarchical. Intent must EVOLVE INTO A TREE preserving parent-child
   relationships; AlgorithmDerivation consumes the hierarchy rather than reconstructing it. This is
   the single most critical gap — a flat intent forces the planner to flatten.
3. Planner evolves, not Vocabulary. Vocabulary resolves meaning only; hierarchical execution is
   exclusively AlgorithmDerivation's responsibility.
4. Correct refusal is NOT a failure. No required entities in the workbook -> NOT_APPLICABLE (no
   hallucination), not a pipeline failure.
5. Ambiguity lives in Vocabulary: word -> [candidate1, candidate2, ...]; final resolution happens
   later using context + Canonical Intent, not inside the Vocabulary Registry.

Priority order: (1) expand Vocabulary aliases; (2) evolve Canonical Intent into a tree;
(3) upgrade AlgorithmDerivation to consume the tree; (4) expand workbook vocabulary (plurals, class
aliases); (5) validate continuously via the Architecture Diagnosis Layer.

Architecture rule: do NOT patch downstream layers to compensate for missing upstream capabilities.
Always verify sequentially; a downstream layer is diagnosed only if upstream delivered valid input.

---

# Priority 1 — Vocabulary aliases (DONE)

Reuse-first proof (before adding ANALYZE): ake.analyze() is a DISTINCT runtime operation
(operation='analyze', returns identity+observations) — not SHOW (list), EXPLAIN (causal reason),
or FIND (search). No existing concept could absorb it, so a new concept is justified.

Owner: vocabulary (via Language Registry seed words). Added: "dependency"/"dependencies" to the
existing DEPEND concept (pure alias, grammar structure unchanged). Added ANALYZE concept
("analyze/analyse/analysis/inspect/examine") — a genuinely missing semantic action; GRAMMAR_VERSION
bumped 1→2 (a concept added), but the 7 grammar TYPES are UNCHANGED. Planner maps ANALYZE→SHOW,
DEPEND→DEPENDENCY (both ops+opcodes already existed). Result: "CA50 analyse karo" and "FEAT-016
dependency graph" now derive operations; health 70%→92% green. Sequential fix at the correct
owner (Vocabulary), Grammar untouched in structure.

# Priority 2 — Canonical Intent TREE (DONE, foundational; GRAMMAR-DERIVED)

Reuse-first survey (before building): no existing owner (AlgorithmDerivation, shell, responses,
runtime) preserves parsed-intent hierarchy — a genuine gap; the tree owner belongs in Canonical
Intent. AlgorithmDerivation currently consumes the FLAT d.get("qualifiers"/"values").

Owner: Canonical Intent Builder (extended, additive). Added IntentNode (a scope: target + its
qualifiers/values/actions + children) and CanonicalIntent.tree.

CRITICAL CORRECTION (first attempt used hardcoded connective words aur/ke/of/per — a
language-specific PARSER RULE, rejected): hierarchy is now derived from GRAMMAR SIGNALS ONLY. Rule:
a QUALIFIER concept opens a new scope; other tokens attach to the current scope; a second entity in
a scope nests as a child. Connectives classify to no grammar role and are simply ignored — NO
surface-word dictionary. Language-independent (proven: an unknown connective still segments by the
QUALIFIER role).
  "Brand 1 ke top product aur top 10 customer" -> root └ children (TOP), (TOP, val 10) — two
  distinct ranking scopes, not one flattened LIMIT.
Tree carries ROLES ONLY (no operations/opcodes). Flat lists remain for backward compatibility
(planner unchanged until Priority 3). Verified: tests/test_intent_tree.py 12/12 (incl. no-connective
-dictionary guard + language-independence); regression 494/22.

Ownership rule for Priority 3: the tree OWNER stays Canonical Intent. AlgorithmDerivation will
CONSUME the tree (Intent Tree -> Execution Tree -> Opcode Graph, all in the planner), never build
it, and must not flatten the tree before planning.

Next: Priority 3 — AlgorithmDerivation consumes the tree (hierarchical planning) so composite
queries produce nested plans instead of flat ones. Then Priority 4 (workbook plural/class aliases),
Priority 5 (continuous ADL validation).

---

# Priority 3 — Architecture rule (ACCEPTED, governing) BEFORE any code

The planner defines the execution model; Runtime adapts to the planner, NEVER the reverse. Priority
3 is a PLANNER architecture survey, not a Runtime capability survey.

Ownership chain (fixed):
  Canonical Intent -> Intent Tree -> AlgorithmDerivation -> Execution Tree -> Opcode Graph -> Runtime
  Planner owns: semantic decomposition, execution hierarchy, execution graph.
  Runtime owns: execution only. Runtime never reconstructs hierarchy.

Rules:
  1. Start the survey from AlgorithmDerivation (input, output, any existing execution-graph/node
     abstraction) — NOT from Runtime.
  2. Never ask "can Runtime execute nested plans?" first. Ask "what execution structure should the
     planner produce?" THEN verify whether Runtime already supports it; if not, EVOLVE Runtime.
     Never simplify the planner because Runtime is currently flat.
  3. Intent Tree != Execution Tree. The planner consumes the Intent Tree and PRODUCES the Execution
     Tree; both derivations live in the planner (one owner).
  4. Survey existing graph structures (UniversalGraph, dependency graph, plan graph, node graph)
     before creating an Execution Tree — expand if one fits, don't duplicate.
  5. Planner never depends on Runtime limitations.

---

# Priority 3 — Hierarchical planning (DONE, planner-first)

Planner-first survey (evidence, before code): planner INPUT = flat d.get("qualifiers"/"values"/
"targets") (intent tree ignored); OUTPUT = flat (opcode) list; NO execution-graph/node abstraction
existed. Existing graphs (UniversalEdgeGraph = knowledge graph, not execution) don't fit — genuine
gap, new ExecutionNode owned by the planner.

Owner: AlgorithmDerivation. Added ExecutionNode (the EXECUTION TREE: per-scope target + operations
+ opcode sub-plan + children) and methods derive_execution_tree (Intent Tree -> Execution Tree) +
_scope_operations/_scope_plan/_exec_node_from_scope. derive_from_intent now:
  Intent Tree (roles/hierarchy) -> Execution Tree (hierarchy PRESERVED, per-scope sub-plans)
  -> compile_flat() -> flat opcode plan for the current RuntimeEngine.
The execution_tree is returned so hierarchy is never lost; `plan` is its depth-first compilation.
compile_flat() is the ONLY linearisation point — when Runtime gains nested execution, replace the
compiler only; the planner's execution model does not change.

Ownership held: planner OWNS the execution structure (ExecutionNode in algorithm_derivation);
Runtime CONSUMES the compiled flat sequence and never rebuilds hierarchy; planner never depends on
Runtime's current flatness. Intent Tree (roles, no opcodes) is DISTINCT from Execution Tree
(opcodes) — proven by test.

Diagnosis updated: hierarchy preservation is validated from the EXECUTION TREE (ranking scopes),
not the flat op list. "top 5 features aur top 3 modules" -> Planner PASS (2 ranking scopes), health
92% green. Verified: execution tree executes on Runtime; tests/test_execution_tree.py 12/12; HTTP
22/22; regression 506/23.

Remaining priorities: (4) workbook plural/class aliases; (5) continuous ADL validation.

---

# Priority 3 completion — level separation + four transformation owners (DONE)

Correction (ExecutionNode was mixing levels — it held the opcode plan). Fixed: the four
transformations now each have ONE owner:
  Canonical Intent Builder : Natural Language -> Intent Tree (roles)
  AlgorithmDerivation      : Intent Tree -> Execution Tree (execution SEMANTICS: operations+values
                             per scope, NO opcodes)
  ExecutionCompiler        : Execution Tree -> opcode plan (the ONLY opcode emitter)
  RuntimeEngine            : opcode plan -> result

ExecutionNode slots = (scope, target, operations, values, children) — no `plan`, no opcodes (proven
by test). ExecutionCompiler (in algorithm_derivation, planner-module-owned; planner holds an
instance, does not emit opcodes itself) turns the tree into a flat opcode plan; when Runtime becomes
a DAG, ONLY the compiler changes. Runtime never recompiles; planner never emits opcodes.

Mandatory 4-representation check PASSED ("Top runtime modules and top runtime variables"): hierarchy
survives Intent Tree (2 scopes) -> Execution Tree (2) -> Compiled Plan (2 op_sort) -> Runtime (2).
Diagnosis validates each transformation (intent_scopes -> exec_scopes -> compiled_sorts); a drop at
any step is a Planner FAIL with the exact counts.

# Authority merge — single query pipeline reaches graph discovery (core DONE)

Problem: two parallel query authorities (old discover() with graph capabilities; new ask_pipeline
with NL+planner but only entity resolution). Correction: ONE canonical pipeline; discovery is the
planner's CONSUMER, not a parallel entry point.

Evidence-based finding: the graph opcodes (graph_dependency/reachability/shortest_path) ALREADY
delegate to the discovery graph (walk_relationship / universal_edges). So unification was routing,
not duplication. Fixes: (1) ExecutionCompiler seeds resolve_entity for graph ops (they read
ctx["target"]); (2) RuntimeEngine.run now surfaces structured outputs generically
(edges/nodes/groups/metrics/rows/candidates), not just result. Now the single ask_pipeline routes
graph queries through planner -> execution tree -> compiler -> runtime graph opcodes -> discovery
graph, and edges/nodes surface for the ONE Analyzer. Verified: "FEAT-016 dependency" -> 4 edges/5
nodes via ask_pipeline; reachability -> 5 edges/6 nodes. tests/test_unified_authority.py 8/8;
HTTP 22/22; regression 502/24.

Remaining: fully route the dashboard's single prompt so graph results render in the existing
Analyzer (UI wiring), then Priority 4 (workbook plural/class aliases) and Priority 5 (continuous ADL).

---

# Authority merge — OPEN/DISCOVER routing (UI + backend, DONE)

Problem (from screenshots): the merge was backend-only. The ASK box resolved a token and STOPPED;
the old panel's Discovery/Suggestions/Context/graph ran as a SECOND authority. Merge happened too
late (at the Analyzer). Correct merge point is BEFORE Discovery: Discovery must be the planner's
downstream consumer.

Fix (single canonical authority): a scope with a TARGET but NO analytical operation is an
OPEN/DISCOVER intent. Added DISCOVER to the operation inventory (realizes to discover_entity), which
REUSES facade.discover() — the existing Discovery Engine — so it is a consumer, not a parallel
search. The planner now defaults to DISCOVER for a bare-entity scope. RuntimeEngine surfaces the
discovery output; ask_pipeline's answer prefers the in-plan discovery (Discovery inside the one
pipeline, not a side call). Dashboard renders the rich discovery view (suggestions/path) through the
one discovery renderer, or opens the entity in the Analyzer — one render authority.

Flow now: Natural Query -> Tokenizer -> Vocabulary -> Grammar -> Intent Tree -> Planner ->
Execution Tree -> Compiler -> (DISCOVER -> Discovery Engine | analytical ops -> Runtime) -> ONE
Analyzer/Renderer. Verified: "CAT-01" -> operations [DISCOVER] -> discover_entity -> Discovery
Engine -> suggestions surfaced via ask_pipeline; discover_entity reuses facade.discover (no
duplicate). HTTP 22/22; tests/test_unified_authority.py 13/13; regression 507/24.

---

# Issue #6 correction — Discovery is an execution SUBSTRATE, not an operation (DONE)

Error corrected: I had added DISCOVER as a planner OPERATION. Wrong. Discovery is the execution
SUBSTRATE — the layer operations run ON (graph, members, neighbours, evidence). The planner emits
SEMANTIC operations (OPEN/COUNT/PATH/DEPENDENCY/COMPARE...); Discovery is what those execute
against.

Fixes:
  * DISCOVER operation -> renamed to OPEN (a semantic operation: open/inspect). open_entity opcode.
  * open_entity runs OPEN via the discovery substrate: a graph ENTITY -> facade.discover (rich card
    + suggestions + path); a REGISTRY CONTAINER (catalog name) -> list_entities(prefix) members.
    So "Category Registry" opens to its 13 members (CAT-01..CAT-13), like the old panel — registry
    containers and graph entities are no longer treated the same.
  * Vocabulary longest-match: _harvest_registries() harvests 23 registry names as ENTITY phrases,
    so "Category Registry" is ONE token that resolves to the registry (was splitting before).

# Acceptance suite — the real merge milestone tracker (tests/acceptance_suite.py)

Regression-green != acceptance-green. Added a first-class ACCEPTANCE suite that runs real NL queries
end-to-end through the ONE pipeline (Vocabulary -> Intent -> Planner -> Discovery/Runtime -> Answer)
and classifies the USER-FACING outcome PASS/PARTIAL/FAIL with the OWNER of each gap. Acceptance is
complete only when FAIL=0; this is separate from unit/regression counts.

Current acceptance scoreboard (EBIS workbook): PASS=5 PARTIAL=2 FAIL=1.
  PASS: Category Registry (13 members), Family Registry (12), CAT-01 (discovery), FEAT-016
        dependency (4 edges), FEAT-016 reachability (5 edges).
  PARTIAL: "average ca50" (AVG derived, op_aggregate value None -> RuntimePrimitives);
           "top 5 features" (rank derived, plural "features" not class-resolved -> Vocabulary).
  FAIL: "Family me kitne Feature hain" (COUNT+FILTER not derived; "kitne"/"hain" not concepts ->
        Vocabulary HOWMANY + Planner class-filter).

Verified: unified authority (OPEN + substrate + registry members) 14/14; HTTP 22/22; regression
508/24. Remaining acceptance gaps each mapped to one owner; close them before adding features.

---

# Stage 9 completion — 5 MANDATORY milestones (governing, no features until all close)

Feature development is FROZEN until all five close. Acceptance != regression; visual != JSON.

M1. Single Query Authority Merge — old Discovery panel + new ASK box become ONE search box, ONE
    pipeline, ONE analyzer, ONE renderer. Merge the code, do not hide one panel.
M2. Planner Semantic Completion — planner must EXECUTE semantics, not fall back to OPEN. COUNT,
    FILTER, GROUP, nested execution must derive. Signal of the gap: "Family me kitne Feature hain"
    -> OPEN (wrong; expected Entity=Family -> child=Feature -> COUNT).
M3. Discovery Capability Merge — ALL old Discovery capabilities preserved and verified: entity open,
    registry open, reverse graph, forward graph, owner, family, category, relationship, dependency,
    reachability, neighbours, suggestions, registry hierarchy. Not just Category Registry.
M4. Acceptance Suite Expansion — 50-100 real EBIS queries covering every capability (entity/registry
    open, reverse/forward graph, owner, family, category, relationship, dependency, reachability,
    aggregate, count, average, top-N, filter, compare, nested, multi-hop, class, registry). Permanent
    benchmark.
M5. Dashboard Verification — acceptance must verify Pipeline -> Analyzer Model -> Dashboard Render
    -> Visual, not JSON alone. One Analyzer renders entity/registry/graph/aggregate/list/evidence/
    suggestions. ADL report auto-generated after each acceptance query (per-stage PASS/FAIL/owner).

Stage 9 is architecturally complete ONLY when M1-M5 all pass. Only then may new capabilities be added.

---

# Milestone progress (this session) — M2 partial, acceptance FAIL=0

M2 (Planner Semantic Completion) — advanced, not complete:
  * Vocabulary: added how-many aliases (kitne/kitna/how many) to the existing COUNT concept
    (grammar structure unchanged); "total" deliberately NOT added (maps to SUM per existing
    contract). Class-name harvest: _harvest_registries now also registers each Owner registry's
    CLASS name + plural (from role "Owner (entity: X)"), so "Feature"/"features" resolve to the
    Feature Registry class.
  * Result: "Family me kitne Feature hain" now derives COUNT (was OPEN) — the execution tree is
    structurally correct: root(Family, [GROUP,COUNT]) + child(Feature-class). Acceptance FAIL 1->0.

Still OPEN (remaining M2 work): nested COUNT must produce a VALUE — count the child-class entities
RELATED to the parent (walk_relationship Family->Feature then count). op_aggregate/op_count return
None because rows aren't the related children yet. Owner: Planner (emit relationship-filtered count)
+ RuntimePrimitives (op_count value). "average ca50" and "top 5 features" are the same shape:
operation derives, runtime value/target-class resolution incomplete.

Acceptance scoreboard: PASS=5 PARTIAL=3 FAIL=0. Regression 508/24; HTTP pending re-verify.
Milestones M1,M3,M4,M5 not yet started this session. NO features added.

---

# M2 — Planner Semantic Execution (DONE, nested count + class ranking)

Owner: AlgorithmDerivation (semantics) + ExecutionCompiler (opcode) + RuntimePrimitives (execution).

Nested count: added COUNT_RELATED operation. Planner detects the pattern (root scope has COUNT/
aggregate + a CHILD scope names a class) in _resolve_relationship_count and rewrites the root to
COUNT_RELATED, carrying relation + child prefix DERIVED FROM THE MODEL edges (_relation_between,
filtered by parent+child class prefixes) — not hardcoded. count_related opcode (RuntimePrimitives)
REUSES the universal edges: instance-level walks from the seeded parent and counts reached
child-class nodes; class-level (no specific parent instance) counts distinct child entities related
to any parent-class instance via the relation. "Family me kitne Feature hain" -> COUNT_RELATED
(relation=features, prefix=FEAT) -> count=2 (verified against ground truth).

Class ranking: resolve_entity now loads a registry/class token's MEMBER ROWS, so ranking/aggregating
a CLASS has rows. "top 5 features" -> 5 member rows (LIMIT honoured).

ExecutionNode gained a `params` slot (per-operation semantic kwargs like relation/target_prefix);
the compiler injects node.params into the opcode kwargs. Level split preserved (node = semantics +
params; compiler = opcodes).

Acceptance: PASS=7 PARTIAL=1 FAIL=0 (only "average ca50" PARTIAL — needs a numeric column to
average; genuinely different data shape). tests/test_relationship_count.py 9/9; regression 517/25;
HTTP 22/22. M2 milestone query executes end-to-end with a real value.

Remaining milestones: M4 (expand acceptance to 50-100), M3 (verify all discovery capabilities via
the one pipeline), M1 (UI merge to one box), M5 (visual + ADL per query).

---

# M1 (Single UI Authority) + M5 (Visual Verification) + Contrast (DONE)

CRITICAL contrast bug fixed (product-blocking, user-reported "text invisible"): inputs and several
elements used color:var(--ink) — but --ink (#0A0E13) is a near-BLACK background token, giving ~1.06:1
contrast (invisible). Root-cause fix: all 6 color:var(--ink) text usages -> var(--paper); defined the
undefined --field token (#0D141B); added ONE global rule for input/textarea/select color=--paper +
visible ::placeholder (--placeholder #7A8B9B) + caret. Raised --faint #4C5C6C (2.4-2.8:1, FAILED AA)
to #8496A6 (5.5-6.4:1, passes AA); brightened --dim to #A9B8C7. Signal button + is-off state
tokenized. Remaining hardcoded colors are semantic evidence-tier badges, all >=5.4:1 (pass AA).

M1 single search authority: collapsed FIVE parallel inputs (askInput, askContext, contextInput,
entityInput, intersectB + perspective) into ONE public search box (askInput -> /ask). The old
context/entity/perspective controls moved INSIDE Engineering Mode as developer-only fallbacks — not
competing public authorities. Everyday queries go through the single Ask box -> planner -> discovery/
runtime -> one Analyzer/Renderer.

M5 visual + API verification (Playwright + ASGI): screenshotted the live dashboard on mobile width
with real queries. Verified visually: one clean search box, readable text throughout, registry members
render (Category Registry -> CAT-01..CAT-13), count renders (Family me kitne Feature -> COUNT_RELATED,
2), Engineering Mode trace shows tokens/operations/plan in contained monospace. API: all query types
flow through the SINGLE /ask endpoint (registry:13, count=2, edges:4, all health=green).

Launcher re-embedded (roundtrip verified). Regression 517/25 all clean; HTTP 22/22.
