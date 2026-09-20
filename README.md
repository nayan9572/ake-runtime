# AKE Runtime

**Universal, evidence-backed architecture knowledge and workbook verification runtime.**

AKE (Architecture Knowledge Engine) turns a structured engineering workbook into a **self-describing, queryable knowledge system**. It discovers how the workbook is organized, compiles its entities and relationships into a canonical internal representation, derives capabilities and query definitions, and answers supported questions with an evidence trail back to the source workbook.

The same runtime can be used to inspect an existing architecture registry workbook, validate a new workbook against the Workbook Constitution, explore relationships, reconstruct lifecycle information, and expose the engine through a standalone HTTP server.

> **Core principle:** AKE does not invent architecture. The workbook is the source of knowledge; AKE discovers, compiles, verifies, and executes queries against that knowledge.

---

## What AKE is

AKE is a **Universal Architecture Search Engine / architecture knowledge runtime** for structured workbooks.

It provides a complete path from workbook to verified, executable knowledge:

```text
Workbook
   ↓
Stage 1 — Classification + Structure Discovery
   ↓
Canonical Model (internal UKMS / Universal Knowledge Model)
   ↓
Discovery + Registry Universe
   ↓
Canonical Graph / IR
   ↓
Derived Invariants / Rules / Query Registry
   ↓
Intent → Execution Tree → Compilation
   ↓
Runtime Execution
   ↓
Evidence-backed Answer
```

The engine is intentionally **domain-neutral**. Terms such as `Command`, `Handler`, `Feature`, `Patient`, `Invoice`, or `Sensor` are workbook vocabulary, not hard-coded engine concepts.

---

## What AKE is NOT

AKE is not:

- a generic chatbot that guesses answers;
- an LLM-based architecture hallucination layer;
- the runtime authority for an external system;
- a command runner that executes arbitrary user instructions against a system;
- a replacement for a domain simulator or CFD/physics engine;
- a mechanism for silently repairing incomplete source data.

When the workbook does not contain the structure required for a question, AKE reports that limitation instead of fabricating an answer.

---

## Design constitution

The runtime follows a set of frozen architectural rules. The most important are:

### 1. Workbook-first knowledge

The workbook is the source of facts. AKE may derive canonical representations, indexes, graph edges, invariants, capabilities, and execution plans from those facts, but it must not silently invent source entities or relationships.

### 2. Dynamic vocabulary

Entity types, prefixes, relationship types, verbs, help text, and capabilities are derived from the discovered workbook structure. Domain nouns are not embedded in the engine as decision branches.

### 3. One canonical pipeline

Natural-language or structured requests flow through one authority path:

```text
Input
 → Tokenization / Vocabulary
 → Canonical Intent
 → Intent Tree
 → Algorithm Derivation
 → Execution Tree
 → Execution Compiler
 → Runtime
 → Answer
```

Discovery is an execution substrate consumed by this pipeline; it is not a second competing query authority.

### 4. Planner owns execution structure

The planner owns semantic decomposition and the execution hierarchy. Runtime executes the compiled plan and does not reconstruct the hierarchy.

```text
Canonical Intent Builder
        ↓
    Intent Tree
        ↓
Algorithm Derivation
        ↓
   Execution Tree
        ↓
Execution Compiler
        ↓
   Opcode Plan
        ↓
 Runtime Engine
```

### 5. Evidence-backed answers

Where an answer is available from workbook evidence, the runtime can retain the source registry and source-row/file:line context needed to explain where the information came from.

### 6. Ambiguity is explicit

If a token maps to more than one entity or identity, AKE returns candidates rather than choosing silently.

### 7. Runtime queries are in-memory

After Phase 1 construction, query execution operates on the compiled in-memory model rather than reopening the workbook for each question.

---

# Architecture

## Two-stage architecture

AKE treats every workbook as an unknown input source first.

```text
                    ANY WORKBOOK
                         │
                         ▼
        ┌─────────────────────────────────┐
        │ Stage 1                         │
        │ Classification + Discovery     │
        │                                 │
        │ structure / PK / FK / types    │
        │ relations / schema / evidence  │
        └─────────────────────────────────┘
                         │
                         ▼
               Canonical Model
                  (UKMS / IR)
                         │
                         ▼
        ┌─────────────────────────────────┐
        │ Stage 2                         │
        │ Knowledge + Runtime             │
        │                                 │
        │ graph / capability / query      │
        │ validation / navigation / plan │
        │ execution / evidence            │
        └─────────────────────────────────┘
                         │
                         ▼
                 Verified Answers
```

### Stage 1: input classification and structure discovery

AKE first determines how the workbook is organized. It does **not** assume that every `.xlsx` file is an architecture registry workbook.

Typical classifications include:

- Architecture Registry Workbook
- Generic Relational Workbook
- Business Dataset
- Unknown Workbook

Only a workbook that satisfies the relevant verification gates is treated as an architecture registry input for the full architecture explorer. Other workbooks can still receive an honest structural summary instead of a fabricated architecture model.

### Stage 2: universal knowledge execution

Once the source is represented in the canonical model, the common engines operate on that representation rather than on workbook-specific code paths.

---

# Canonical knowledge model

AKE internally works with a universal set of concepts:

```text
Entity
Identifier
Attribute
Relationship
Type
Metadata
Evidence
Source
Constraint
```

Domain-specific vocabulary is discovered from the workbook.

Examples:

```text
Command / Handler / Feature / Module

or

Patient / Doctor / Department

or

Invoice / Account / Customer
```

The engine should not need a different core implementation for each vocabulary.

---

# Discovery and compilation pipeline

The principal compilation path is:

```text
Workbook
  → Structural Importer
  → Discovery Engine
  → Registry Universe
  → Discovery Primitives
  → Feature Discovery / Primitive Closure
  → RPDE (typed relationship compilation)
  → Universal Property Graph
  → Invariants
  → Rules
  → Query Registry
  → Relation Inventory
  → Canonical Query Selection
  → Algorithm Derivation (M10 planner)
  → Runtime Engine
  → Evidence-backed Answer
```

### RPDE

The Relational Primitive / Data-layer stage converts workbook foreign-key-like structure into typed canonical edges. An FK is not automatically treated as a semantic edge without the necessary relationship interpretation.

### Universal Property Graph

The graph is the canonical knowledge representation used by downstream discovery and query execution. It is not a second copy of the workbook and is not independently edited by user-facing components.

### Invariants and rules

Invariants and rules are derived from the compiled model. Query definitions live in data registries where appropriate, allowing new workbook relationships and query families to extend the capability surface without rewriting every engine component.

---

# Capability universe

AKE exposes a capability universe rather than pretending every question works for every workbook.

The reference EBIS workbook bundled with this release demonstrates **10 capability categories / 31 canonical question types**:

| Category | Question types |
|---|---|
| Identity | `WHAT_IS`, `GET_NAME`, `GET_PURPOSE` |
| Ownership | `GET_OWNER` |
| Relationships | `GET_NEIGHBORS`, `GET_INCOMING`, `GET_OUTGOING` |
| Control | `GET_HANDLER`, `GET_GATE`, `GET_PIPELINE`, `GET_BRIDGE`, `GET_VALIDATOR` |
| Data Flow | `GET_PRODUCERS`, `GET_CONSUMERS`, `GET_READS`, `GET_PUBLISHES`, `GET_OBSERVES` |
| Dependency | `GET_UPSTREAM`, `GET_DOWNSTREAM`, `IS_ROOT`, `IS_LEAF` |
| Classification | `GET_CATEGORY`, `GET_FAMILY`, `GET_ROLE` |
| Integrity | `CHECK_FK`, `IS_ORPHAN`, `IS_DUPLICATE` |
| Coverage | `MISSING_EVIDENCE`, `EMPTY_FIELDS` |
| Evidence | `GET_EVIDENCE`, `GET_SOURCE_ROW` |

For a different workbook, the capability universe changes with the workbook's actual relations and metadata.

Check it with:

```python
ake.capability_universe()
ake.capabilities("<ENTITY-ID>")
```

Unsupported questions are reported as unsupported or as a metadata gap; they are not guessed.

---

# Workbook Constitution

The engine has a separate **Workbook Constitution** that defines the structural contract expected by the architecture-registry pathway.

Important principles include:

- stable entity identity;
- discoverable primary-key structure;
- consistent references between registries;
- explicit relationships rather than hidden assumptions;
- evidence/source information where required;
- deterministic schema discovery;
- sufficient metadata for classification and verification.

The constitution is intentionally separate from the engine so that the workbook contract can be reviewed independently.

See:

- [`WORKBOOK_CONSTITUTION.md`](WORKBOOK_CONSTITUTION.md)
- [`IDENTITY_SPEC.md`](IDENTITY_SPEC.md)

---

# How to test YOUR workbook

This is the primary workflow for users who want to bring a workbook into AKE.

## 1. Prepare the workbook

Use an `.xlsx` file. A `.zip` containing a workbook is also supported by the included runner paths.

The workbook should have:

- stable identifiers;
- consistent references;
- meaningful registry/table names;
- relationship columns where relationships actually exist;
- evidence/source information where your verification process requires it.

Start with the Workbook Constitution rather than trying to mimic the bundled EBIS workbook column-for-column.

## 2. Run structural discovery

Terminal:

```bash
python AKE_SHELL.py path/to/your_workbook.xlsx
```

For batch processing:

```bash
python colab_run.py path/to/your_workbook.xlsx
```

Or pass a supported ZIP containing the workbook.

The first stage should tell you what AKE discovered instead of assuming what the workbook is.

## 3. Inspect the verification result

A useful verification pass should establish at least:

```text
Workbook classification
Primary-key structure
Entity / registry counts
Relationship counts
Schema completeness
Integrity findings
Evidence coverage
Derived capability universe
Confidence and reasons
```

Do not treat a single confidence number as proof of correctness. Read the findings and evidence behind it.

## 4. Explore the discovered knowledge

Interactive examples:

```text
help
summary()
verify()
search(<text>)
list(<PREFIX>)
describe(<ENTITY>)
related(<ENTITY>)
lifecycle(<ENTITY>)
evidence(<ENTITY>)
```

The exact vocabulary is workbook-derived, so your workbook may expose different relation names and entity prefixes.

## 5. Test an entity by ID or name

Programmatically:

```python
from ake import AKE

ake = AKE("your_workbook.xlsx")

print(ake.capability_universe())
print(ake.capabilities("YOUR-ID"))
print(ake.answer("GET_EVIDENCE", "YOUR-ID"))
print(ake.lifecycle("YOUR-ID"))
```

Names can also be used where supported by the resolver.

If a name is ambiguous, the resolver returns candidates rather than silently opening the wrong entity.

## 6. Verify that answers remain evidence-backed

For each important question you are testing, inspect:

```text
Question
Resolved entity
Supported capability
Returned result
Source registry
Source row / evidence
Any warning or metadata gap
```

This is particularly important when introducing a new workbook format.

---

# Verification philosophy

AKE separates **regression testing** from **acceptance testing**.

### Regression testing

Regression tests verify engine behavior, invariants, identity, query execution, server contracts, and other implementation-level guarantees.

Run:

```bash
python tests/regression.py
```

The repository also contains focused suites such as:

```text
tests/test_canonical_identity.py
tests/test_workbook_knowledge.py
tests/test_unified_authority.py
tests/test_execution_tree.py
tests/test_guided_discovery.py
tests/test_semantic_perspective.py
...
```

### Acceptance testing

The acceptance suite checks the **user-facing outcome of real end-to-end queries** through the canonical pipeline.

Run:

```bash
python tests/acceptance_suite.py
```

A regression-green runtime is not automatically acceptance-green for every natural-language workload. Acceptance gaps should remain visible and mapped to an owner instead of being hidden behind unit-test counts.

---

# Reference baseline

The bundled EBIS workbook is used as a reference fixture for the current runtime baseline. The repository records canonical metrics in [`BASELINE.json`](BASELINE.json).

The baseline is a **regression reference**, not a promise that every future workbook will have the same counts.

Examples of reference dimensions include:

- Universal Property Graph edge count
- IR node count
- relation vocabulary size
- invariants
- runtime primitive coverage
- lifecycle stages
- canonical query counts
- capability question types
- discovery/verification feature presence

For your own workbook, compare behavior and contract satisfaction rather than expecting EBIS-specific counts.

---

# Identity and ambiguity

AKE uses an internal canonical identity model so that display identifiers do not need to become artificial user-facing identifiers.

Important behaviors:

- prefixed IDs remain stable where available;
- numeric IDs can be supported through structural schema inference;
- the same raw ID can exist in different classes without collapsing those entities;
- same-name collisions return candidates rather than guessing;
- `Class:name` style disambiguation can be used where applicable;
- internal canonical identity tokens remain an implementation detail.

See [`IDENTITY_SPEC.md`](IDENTITY_SPEC.md) for the full identity contract.

---

# Query architecture

AKE follows a planner-first execution model.

```text
Natural / Structured Input
         ↓
      Tokenizer
         ↓
     Vocabulary
         ↓
      Grammar
         ↓
 Canonical Intent
         ↓
     Intent Tree
         ↓
Algorithm Derivation
         ↓
   Execution Tree
         ↓
Execution Compiler
         ↓
   Opcode Plan
         ↓
 Runtime Engine
         ↓
 Structured Result
         ↓
     One Renderer
```

The important boundary is:

> **Planner defines the execution structure; runtime executes the resulting plan.**

This prevents the runtime's current implementation constraints from dictating the knowledge model.

---

# Interactive shell

The shell is intended to be a human-facing architecture exploration surface.

Typical commands include:

```text
help
summary()
verify()
search(ignition)
list(FEAT)
describe(FEAT-016)
owner(MOD-004)
related(CA50)
lifecycle(CMD-048)
evidence(CMD-002)
back
home
exit
```

The exact action set is discovered from the workbook where the action depends on workbook knowledge.

Developer mode is available for inspecting internal representations such as the registry universe, IR, capability universe, rules, and timing information.

---

# Server adapter

`ake_server/` exposes the runtime over HTTP without rewriting the AKE core.

Run it with:

```bash
pip install -r requirements.txt
python -m ake_server.main
```

Default address:

```text
http://0.0.0.0:8000
```

The server adapter supports owner-mode and workspace-mode operation. See [`ake_server/README.md`](ake_server/README.md) for the complete environment-variable contract and deployment notes.

### Important server boundary

The server is an adapter around the runtime. It does not become a second architecture engine.

```text
Client
  ↓
ake_server
  ↓
AKE runtime
  ↓
canonical model / graph / planner / runtime
```

---

# Deployment

## Local

```bash
git clone https://github.com/nayan9572/ake-runtime.git
cd ake-runtime

python -m venv .venv
# activate the environment using your platform's command
pip install -r requirements.txt

python AKE_SHELL.py path/to/workbook.xlsx
```

## Colab

The repository includes `AKE_Colab_Shell.py` and `colab_run.py` for notebook-oriented workflows.

Typical flow:

```python
!pip -q install openpyxl
import sys
sys.path.insert(0, "runtime")

from google.colab import files
up = files.upload()

from colab_run import run
run(list(up)[0])
```

The resulting batch artifacts are written as JSON outputs under `ake_out/` in the runner workflow.

## HTTP deployment

Run the standalone adapter:

```bash
python -m ake_server.main
```

Then place an appropriate reverse proxy or tunnel in front of port `8000` for remote access.

For production or multi-tenant use, add authentication and use a persistent deployment/tunnel strategy rather than relying on an ephemeral quick tunnel.

---

# Repository structure

```text
ake-runtime/
├── README.md
├── LICENSE
├── requirements.txt
│
├── runtime/
│   ├── AKE_MASTER.py              # main runtime entry point
│   ├── AKE_SHELL.py               # terminal exploration shell
│   ├── AKE_Colab_Shell.py         # notebook-oriented interactive shell
│   ├── colab_run.py                # batch runner
│   ├── AKE_PRODUCT_CONSTITUTION.md
│   ├── WORKBOOK_CONSTITUTION.md
│   ├── IDENTITY_SPEC.md
│   ├── EVIDENCE.md
│   ├── AUDIT.md
│   ├── BASELINE.json
│   ├── CAPABILITY_UNIVERSE.md
│   │
│   ├── ake/
│   │   ├── workbook_runtime.py
│   │   ├── discovery_engine.py
│   │   ├── discovery_primitives.py
│   │   ├── relational_primitive_engine.py
│   │   ├── edge_graph_engine.py
│   │   ├── invariant_engine.py
│   │   ├── rule_engine.py
│   │   ├── query_engine.py
│   │   ├── algorithm_derivation.py
│   │   ├── runtime_primitives.py
│   │   ├── runtime_engine.py
│   │   ├── canonical_identity.py
│   │   ├── state_contract_scanner.py
│   │   └── ...
│   │
│   ├── ake_server/
│   │   ├── api.py
│   │   ├── adapter.py
│   │   ├── schemas.py
│   │   ├── session_manager.py
│   │   └── main.py
│   │
│   └── tests/
│       ├── regression.py
│       ├── acceptance_suite.py
│       └── focused test suites
│
└── docs/
    └── additional architecture / audit documentation
```

The exact committed tree may evolve. The architecture boundaries should not.

---

# Documentation map

| Document | Purpose |
|---|---|
| [`AKE_PRODUCT_CONSTITUTION.md`](AKE_PRODUCT_CONSTITUTION.md) | Product/runtime rules and governing architecture decisions |
| [`WORKBOOK_CONSTITUTION.md`](WORKBOOK_CONSTITUTION.md) | Workbook contract and source-data expectations |
| [`IDENTITY_SPEC.md`](IDENTITY_SPEC.md) | Canonical identity, numeric IDs, collisions, resolver contract |
| [`CAPABILITY_UNIVERSE.md`](CAPABILITY_UNIVERSE.md) | Canonical capability categories and question types |
| [`EVIDENCE.md`](EVIDENCE.md) | Evidence and validation record |
| [`AUDIT.md`](AUDIT.md) | Engineering certification findings and resolutions |
| [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | Known/open limitations and boundaries |
| [`COMPATIBILITY.md`](COMPATIBILITY.md) | Compatibility behavior and supported contracts |
| [`CHANGELOG.md`](CHANGELOG.md) | Versioned findings and changes |
| [`ake_server/README.md`](ake_server/README.md) | HTTP adapter, deployment, modes, and server boundary |

---

# Known limitations and honest boundaries

The repository documents limitations rather than treating them as invisible edge cases.

Examples include:

- some advanced natural-language acceptance cases may remain partial even when the underlying engine regression suite is green;
- the current runtime planner/compiler boundary still documents implementation constraints explicitly;
- the server adapter does not provide authentication by default;
- ephemeral quick tunnels do not provide a stable production hostname;
- real-browser visual testing is separate from Python/ASGI verification;
- some large-workbook behaviors depend on scale and should be benchmarked with the target dataset.

See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) and [`AUDIT.md`](AUDIT.md) before treating a result as production certification.

---

# Reproducibility and evidence

When reporting an AKE result, prefer to include:

```text
AKE version / commit
Workbook identity / hash
Workbook classification
Validation result
Capability queried
Entity queried
Answer
Evidence location
Warnings / limitations
Test suite result
```

That turns a conversational result into a reproducible engineering record.

---

# Extending AKE to a new workbook type

The preferred extension path is:

```text
New source format
      ↓
Importer / Mapper
      ↓
Canonical Model
      ↓
Existing universal engines
```

Do **not** duplicate the core query/runtime engine for each domain.

When the workbook introduces a new relation or canonical question, prefer data/configuration additions where the existing architecture supports them rather than adding domain-specific branching in core decision logic.

---

# Safety of interpretation

AKE is designed to make its uncertainty visible:

- unknown entities should remain unknown;
- ambiguous identities should remain ambiguous until resolved;
- unsupported questions should remain unsupported;
- missing evidence should be reported as missing evidence;
- incomplete schema should lower confidence and surface reasons;
- structural heuristics should be distinguishable from measured domain quantities.

This is central to the project's engineering contract.

---

# Current reference runtime

The bundled reference material was built around the EBIS architecture registry workbook and includes:

- a reference workbook;
- canonical identity handling;
- universal graph and discovery layers;
- deterministic planning/execution;
- interactive shell and Colab entry points;
- standalone HTTP adapter;
- regression and acceptance suites;
- engineering audit and evidence documents.

The reference workbook is a fixture and example — **not a prerequisite for using AKE with your own workbook**.

---

# License

See [`LICENSE`](LICENSE).

---

## Quick start summary

For the fastest path from a workbook to a verification result:

```bash
pip install -r requirements.txt
python AKE_SHELL.py your_workbook.xlsx
```

Then start with:

```text
verify()
summary()
help
search(<text>)
```

The goal is simple: **upload a workbook, discover what it actually contains, verify the structure, and query only what the evidence supports.**
