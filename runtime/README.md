# AKE — Universal Engineering Spreadsheet Runtime

AKE turns an **engineering registry workbook** into a queryable, evidence-backed knowledge system.
It reads a workbook, compiles it into a canonical knowledge graph, and answers structured engineering
questions about any entity — with a file:line evidence trail for every answer. Nothing is hardcoded to
one project: the same engine runs on any workbook that follows the Workbook Constitution.

## What AKE does
- Compiles a workbook into a **Universal Property Graph** (typed nodes + typed edges + evidence).
- Derives **invariants, rules, and a query registry** from the workbook (not hand-written).
- Answers **31 canonical question types** across 10 categories (see CAPABILITY_UNIVERSE.md) for any entity.
- Reconstructs an entity's **lifecycle** from evidence and classifies every missing stage by cause.
- Derives each query's **execution plan deterministically** from query definition + registry schema +
  a fixed primitive library (M10) — no per-query code, no LLM guessing.

## What AKE does NOT do
- It does not invent data. If a reference points to an entity that is in **no** registry, AKE reports a
  metadata gap; it will not fabricate an edge.
- It is not a natural-language chatbot. It executes deterministic, evidence-backed operations.
- It does not (yet) externalize its **planning rules** to data (query *definitions* are data; planning
  *rules* are a small deterministic rule set in code).
- It requires the Workbook Constitution (ID-pattern primary keys). Numeric/composite PKs are not yet
  supported (see KNOWN_LIMITATIONS.md).

## Architecture (frozen)
```
Any Workbook
  → Stage 1: Structural importer selection (Registry / Tabular / ...) — never a domain, never a mode
             maps ANY workbook into the Canonical Model (UKMS/IR); same explorer runs on all
  → Discovery Engine → Registry Universe (registries, entity types, relation types, schema, DERIVED capabilities)
                       └─ rendered as the Discovery Report you see on upload (any domain)
  → Discovery Primitives (observe)        → Feature Discovery → Primitive Closure
  → RPDE (FK ≠ Edge: compile typed edges) → Universal Property Graph (Canonical IR)
  → Invariant → Rule → Query Registry     (derived, registry-templated)
  → Relation Inventory → Canonical Query Selection
  → Algorithm Derivation (M10 deterministic planner) → Runtime Engine
  → Evidence-backed Answer
```
Four layers: **Registry = facts · Compiler (RPDE) = knowledge compilation · Property Graph = canonical
knowledge (IR) · Runtime = knowledge execution.**

## Use it — interactive (recommended)
AKE is a **Universal Architecture Search Engine**. Single-cell Colab (Shift+Enter): paste
`AKE_Colab_Shell.py`, upload `AKE_Runtime.zip` (+ optional workbook), and query live:
```
AKE > purpose(FEAT-016)
AKE > owner(CMD-002)
AKE > related(CA50)
AKE > lifecycle(CMD-048)
AKE > search(ignition)
AKE > verify()
AKE > exit
```
Help, verbs, and capabilities are derived from YOUR workbook (see AKE_PRODUCT_CONSTITUTION.md).
Terminal: `python AKE_SHELL.py your_workbook.xlsx`.

## Use it — batch artifacts
```bash
pip install openpyxl
python colab_run.py your_workbook.xlsx          # or a .zip containing one
```
Colab:
```python
!pip -q install openpyxl
import sys; sys.path.insert(0, "AKE_Runtime")
from google.colab import files; up = files.upload()   # your .xlsx or AKE_Runtime.zip
from colab_run import run; run(list(up)[0])            # -> ake_out/*.json
```
Outputs (deterministic JSON): `universal_edges`, `ir_nodes`, `invariants`, `rules`, `queries`,
`canonicalization_report`, `capability_universe`, `summary`.

Programmatic:
```python
from ake import AKE
ake = AKE("your_workbook.xlsx")
ake.capability_universe()                 # what can AKE answer on this workbook?
ake.capabilities("CMD-002")               # capability matrix for one entity
ake.answer("GET_HANDLER", "CMD-002")      # derive + execute -> evidence-backed
ake.lifecycle("CMD-002")                  # populate fixed lifecycle + classify gaps
```

## Adding another workbook tomorrow
No code changes. Drop a new `.xlsx` (or a `.zip` containing one) and run `colab_run.py`; AKE
auto-discovers it, infers a registry catalog if absent, and applies the same pipeline. New relation
types and new canonical queries are **data** additions (Workbook + `ake/defaults/query_definitions.json`).

## Evidence & validation
Every claim in this repo is backed by an automated test. Run:
```bash
python tests/regression.py     # full suite; exits nonzero on any failure
```
See `BASELINE.json` (canonical metrics), `CHANGELOG.md` (versioned findings), `EVIDENCE.md`
(before/after), `FROZEN_FINDINGS.md`, `KNOWN_LIMITATIONS.md`, `WORKBOOK_CONSTITUTION.md`,
`CAPABILITY_UNIVERSE.md`, and `ake/*.md` (per-stage design + freeze notes).

## Repo layout
- `ake/` — engine modules (`workbook_runtime`, `discovery_primitives`, `relational_primitive_engine`
  [RPDE], `edge_graph_engine`, `invariant_engine`, `rule_engine`, `query_engine`, `algorithm_derivation`
  [M10], `runtime_primitives`, `runtime_engine`, `lifecycle`, `capability_matrix`), plus `ake/defaults/`
  (data registries) and `ake/*.md` (design/freeze notes).
- `colab_run.py`, `AKE_MASTER.py` — entry points. `tests/` — regression + verification.

## License
Open source. Use, fork, and run on your own engineering workbooks.
