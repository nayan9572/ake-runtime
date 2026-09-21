# AKE Runtime

**Universal, evidence-backed architecture knowledge and workbook verification runtime.**

AKE (Architecture Knowledge Engine) turns a structured engineering workbook into a self-describing, queryable knowledge system. It discovers workbook structure, compiles a canonical knowledge model and property graph, derives capabilities and query definitions, executes supported queries, and preserves evidence back to the source workbook.

This repository contains the runtime package, the canonical AKE Master Launcher, the bundled EBIS reference workbook, an optional HTTP server adapter, and verification suites.

> **Core principle:** the workbook is the source of knowledge. AKE discovers, compiles, verifies, and executes against that knowledge; it does not silently invent architecture.

---

## Repository layout

The executable runtime is under `runtime/`.

```text
ake-runtime/
├── README.md
├── LICENSE
├── ake_server/                         # repository-level server adapter
└── runtime/
    ├── AKE_MASTER.py                   # canonical single-entry launcher
    ├── AKE_SHELL.py                    # interactive terminal shell
    ├── AKE_Colab_Shell.py              # Colab / local interactive bootstrap
    ├── colab_run.py                    # batch runner
    ├── requirements.txt                # core runtime dependency
    ├── engine_bundle.json              # EBIS engine bundle contract
    ├── ake/                            # core AKE package
    ├── ake_server/                     # runtime-local HTTP adapter
    ├── tests/                          # regression + acceptance suites
    └── EBIS_Architecture_Registry_Workbook_v17.xlsx
```

**Run runtime commands from `runtime/` unless a command explicitly says otherwise.**

---

# Quick start

## 1. Prerequisites

You need a Python 3 environment with `pip`.

Check:

```bash
python --version
python -m pip --version
```

If your system uses `python3` instead of `python`, substitute it in the commands below.

### Termux

```bash
pkg update
pkg install python
python --version
python -m pip --version
```

---

## 2. Clone the repository

```bash
git clone https://github.com/nayan9572/ake-runtime.git
cd ake-runtime
cd runtime
```

---

## 3. Create an isolated Python environment

Recommended:

```bash
python -m venv .venv
```

Activate it.

### Linux / macOS / Termux

```bash
source .venv/bin/activate
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### Windows Command Prompt

```cmd
.venv\Scripts\activate.bat
```

---

## 4. Install the core runtime

From `runtime/`:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The core runtime dependency file currently provides the workbook reader required by AKE.

---

# First run: bundled EBIS reference workbook

The repository includes:

```text
EBIS_Architecture_Registry_Workbook_v17.xlsx
```

No external workbook is required for the first local verification.

### Scripted demo

```bash
python AKE_MASTER.py --demo
```

### Interactive explorer

```bash
python AKE_MASTER.py
```

The launcher searches near itself and can locate the bundled workbook automatically.

Typical interactive commands are:

```text
overview
help
list <PREFIX>
search <term>
describe <ID>
GET_X <ID>
exit
```

The actual entity prefixes, relations, and supported operations depend on the loaded workbook.

---

# AKE Master Launcher

`AKE_MASTER.py` is the canonical local entry point.

Supported forms:

```text
python AKE_MASTER.py
python AKE_MASTER.py workbook.xlsx
python AKE_MASTER.py --demo
python AKE_MASTER.py workbook.xlsx --repl
python AKE_MASTER.py workbook.xlsx --outdir=DIR
```

### Interactive mode

```bash
python AKE_MASTER.py
```

No workbook argument means the launcher auto-locates a workbook it can use.

### Batch mode

```bash
python AKE_MASTER.py workbook.xlsx
```

An explicit workbook path uses **batch mode by default**. It does not enter the interactive `input()` loop.

Artifacts are written under `ake_out/` unless another output directory is supplied.

### Explicit workbook + interactive mode

```bash
python AKE_MASTER.py workbook.xlsx --repl
```

### Custom output directory

```bash
python AKE_MASTER.py workbook.xlsx --outdir=my_output
```

### ZIP input

A supported `.zip` containing an `.xlsx` workbook can also be supplied. The launcher extracts the workbook before loading it.

---

# What AKE_MASTER does

The canonical local flow is:

```text
Workbook
   ↓
AKE_MASTER.py
   ↓
Workbook discovery
   ↓
Structural import / classification
   ↓
Canonical model / IR
   ↓
Registry universe + discovery
   ↓
Property graph
   ↓
Invariants / rules / query definitions
   ↓
Algorithm derivation
   ↓
Runtime execution
   ↓
Result + evidence
```

`AKE_MASTER.py` uses the shared runtime runner for batch artifact generation rather than maintaining a separate artifact-generation path.

---

# Direct interactive shell

`AKE_SHELL.py` is the direct terminal shell entry point.

```bash
python AKE_SHELL.py
```

Or:

```bash
python AKE_SHELL.py path/to/your_workbook.xlsx
```

Developer inspection mode:

```bash
python AKE_SHELL.py path/to/your_workbook.xlsx --dev
```

Use `AKE_MASTER.py` as the default starting point; use `AKE_SHELL.py` when you specifically want the direct shell entry point.

---

# Colab and notebook workflows

The runtime includes:

```text
AKE_Colab_Shell.py
colab_run.py
```

`AKE_Colab_Shell.py` is a thin bootstrap for an interactive AKE session. It can accept an uploaded runtime bundle and optional workbook, extract the runtime, locate the workbook, and start the same AKE shell.

Batch runner:

```bash
python colab_run.py path/to/your_workbook.xlsx
```

Programmatic use:

```python
from colab_run import run

summary = run("path/to/your_workbook.xlsx")
print(summary)
```

The batch runner produces deterministic JSON artifacts and a ZIP package.

---

# EBIS engine bundle

The runtime includes:

```text
engine_bundle.json
ake_ebis_adapter.py
```

The bundle declares:

```text
engine_id: ake
engine_version: 1.0
launcher: ake_ebis_adapter.start
input: workbook_path
output: handle
```

The adapter is intentionally thin:

```text
workbook_path
    ↓
ake_ebis_adapter.start(...)
    ↓
AKE(workbook_path)
    ↓
live AKE handle
```

The bundled reference workbook is:

```text
EBIS_Architecture_Registry_Workbook_v17.xlsx
```

---

# HTTP server adapter

The repository also ships an HTTP adapter under `runtime/ake_server/`.

It is a transport layer around AKE, not a second architecture engine:

```text
Client
  ↓
ake_server
  ↓
AKE runtime
  ↓
canonical model / graph / planner / runtime
```

## Server is not a browser dashboard

The shipped server package is an **HTTP API adapter**. It does not contain a browser frontend.

Therefore:

```bash
python -m ake_server.main
```

starts the API server, but it does **not** by itself open or display a browser dashboard.

A separate frontend/client is required for a graphical browser interface.

## Install server dependencies

From `runtime/`:

```bash
python -m pip install fastapi uvicorn python-multipart openpyxl
```

## Start the server

```bash
python -m ake_server.main
```

Default bind address:

```text
http://0.0.0.0:8000
```

Owner mode is the default. Workspace operation is also supported.

For the exact route and environment-variable contract, see:

```text
runtime/ake_server/README.md
```

---

# Workbook-first knowledge model

AKE works with universal concepts such as:

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

Domain vocabulary is discovered from workbook structure rather than being hard-coded into the core runtime.

Example vocabularies may differ between workbooks:

```text
Command / Handler / Feature / Module
```

or:

```text
Patient / Doctor / Department
```

The runtime is designed around discovered structure rather than one fixed domain vocabulary.

---

# Discovery and execution pipeline

The principal path is:

```text
Workbook
  → Structural Importer
  → Discovery Engine
  → Registry Universe
  → Discovery Primitives
  → Feature Discovery / Primitive Closure
  → RPDE
  → Universal Property Graph
  → Invariants
  → Rules
  → Query Registry
  → Relation Inventory
  → Canonical Query Selection
  → Algorithm Derivation
  → Runtime Engine
  → Evidence-backed Result
```

The planner defines the execution structure; the runtime executes the resulting plan.

---

# Capability universe

AKE exposes a capability universe rather than assuming every question is valid for every workbook.

Examples include:

| Category | Examples |
|---|---|
| Identity | `WHAT_IS`, `GET_NAME`, `GET_PURPOSE` |
| Ownership | `GET_OWNER` |
| Relationships | `GET_NEIGHBORS`, `GET_INCOMING`, `GET_OUTGOING` |
| Control | `GET_HANDLER`, `GET_GATE`, `GET_PIPELINE` |
| Data flow | `GET_PRODUCERS`, `GET_CONSUMERS`, `GET_READS` |
| Dependency | `GET_UPSTREAM`, `GET_DOWNSTREAM` |
| Classification | `GET_CATEGORY`, `GET_FAMILY`, `GET_ROLE` |
| Integrity | `CHECK_FK`, `IS_ORPHAN`, `IS_DUPLICATE` |
| Coverage | `MISSING_EVIDENCE`, `EMPTY_FIELDS` |
| Evidence | `GET_EVIDENCE`, `GET_SOURCE_ROW` |

For the exact capabilities of a loaded workbook:

```python
from ake import AKE

ake = AKE("your_workbook.xlsx")
print(ake.capability_universe())
```

---

# Programmatic use

From `runtime/`:

```python
from ake import AKE

ake = AKE("your_workbook.xlsx")

print(ake.overview())
print(ake.capability_universe())
print(ake.search("ignition"))
print(ake.describe("FEAT-016"))
print(ake.lifecycle("CMD-002"))
print(ake.answer("GET_HANDLER", "CMD-002"))
```

Unified natural-language pipeline:

```python
result = ake.ask_pipeline("FEAT-016 dependency")
print(result)
```

Ambiguous identity should surface candidates rather than silently choosing one.

---

# Verification and tests

Run these from `runtime/`.

### Regression suite

```bash
python tests/regression.py
```

### Acceptance suite

```bash
python tests/acceptance_suite.py
```

The acceptance suite sends real natural-language queries through the canonical pipeline and reports:

```text
PASS
PARTIAL
FAIL
```

A regression-green runtime is not automatically acceptance-green for every natural-language workload.

Focused tests are under:

```text
runtime/tests/
```

---

# Testing your workbook

Recommended flow:

```text
Prepare workbook
      ↓
Run AKE_MASTER.py
      ↓
Inspect structural discovery
      ↓
Inspect registry / relationship / schema findings
      ↓
Inspect capability universe
      ↓
Run representative queries
      ↓
Inspect results and evidence
```

For important answers, inspect:

```text
Question
Resolved entity
Supported capability
Returned result
Source registry
Source row / evidence
Warnings or metadata gaps
```

---

# Workbook Constitution and limitations

Relevant documents include:

```text
runtime/WORKBOOK_CONSTITUTION.md
runtime/AKE_PRODUCT_CONSTITUTION.md
runtime/IDENTITY_SPEC.md
runtime/KNOWN_LIMITATIONS.md
runtime/COMPATIBILITY.md
runtime/FROZEN_FINDINGS.md
runtime/EVIDENCE.md
```

Important boundaries:

- AKE does not silently invent missing workbook facts.
- A confidence value is not, by itself, proof of correctness.
- Regression-green is not proof that every natural-language workload is acceptance-green.
- The HTTP server adapter is not a browser frontend.
- Workbook-specific capabilities depend on the actual source workbook.

---

# Repository boundary

The current repository contains both:

```text
ake_server/
runtime/ake_server/
```

The canonical executable runtime documented by this README is under `runtime/`.

Use runtime-relative commands after:

```bash
cd runtime
```

Do not mix repository-root paths with runtime-relative commands.

---

# Recommended entry points

| Goal | Command |
|---|---|
| First local verification | `python AKE_MASTER.py --demo` |
| Interactive AKE | `python AKE_MASTER.py` |
| Explicit workbook, interactive | `python AKE_MASTER.py workbook.xlsx --repl` |
| Explicit workbook, batch | `python AKE_MASTER.py workbook.xlsx` |
| Direct shell | `python AKE_SHELL.py` |
| Colab interactive | `python AKE_Colab_Shell.py` |
| Batch artifacts | `python colab_run.py workbook.xlsx` |
| EBIS adapter | `engine_bundle.json` + `ake_ebis_adapter.py` |
| HTTP API | `python -m ake_server.main` |
| Regression | `python tests/regression.py` |
| Acceptance | `python tests/acceptance_suite.py` |

---

# License

See `LICENSE` for the repository license terms.


## Two runtime entry points

The repository intentionally keeps two distinct launchers under runtime/:

| Entry point | Purpose |
|---|---|
| `python AKE_MASTER.py` | Canonical local AKE runtime, batch, and REPL workflow |
| `python AKE_Master_Launcher.py` | Server/dashboard deployment workflow with launcher control plane and optional public tunnel |

The Master Launcher assembles the tracked AKE runtime and server adapter, uses the bundled EBIS workbook when no workbook is supplied, generates its gateway/dashboard fallback assets, and can expose the server through a Cloudflare quick tunnel.

The tracked runtime tree is the source of truth for repository-local execution. The Colab ZIP upload path remains supported for the launcher artifact, but an old ZIP must not silently replace the checked-out runtime/ source.

For launcher-specific verification:

```bash
cd runtime
pytest -q tests/test_launcher_integration.py
```

The integration suite uses isolated temporary workspaces and does not require a public tunnel.
