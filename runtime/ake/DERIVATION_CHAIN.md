# AKE Derivation Chain — fully registry-driven (templates are data, not code)

```
Workbook → Feature Discovery → Observation → Primitive → Closure
        → Invariant Identification → Invariant Registry
        → Rule Derivation          → Rule Registry
        → Query Derivation         → Universal Query Registry
        → Algorithm Generator      → Runtime
```

## What is code vs data
- **CODE (irreducible ISA):** 10 observation primitives (`discovery_primitives.py`) + 45 runtime executors
  (`runtime_primitives.py`) + a tiny predicate-operator set (not_null/non_empty/matches). These are the
  machine instructions, like a CPU's ADD/LOAD.
- **DATA (workbook registries, engines READ these):**
  | Registry | Drives | Adding a row = |
  |---|---|---|
  | Property Registry | which properties are observed (property·kind·primitive·field·operator) | new observable property, no code |
  | Rule Template Registry | invariant.kind → rule text (purpose/condition/action/severity) | new rule template, no code |
  | Query Family Registry | rule.kind → query name template + opcode pipeline | new query family, no code |

## No-hardcoding status
- `invariant_engine.py` — reads Property Registry. No `has_PK`/`if class==` in code.
- `rule_engine.py` — reads Rule Template Registry. No TEMPLATES dict.
- `query_engine.py` — reads Query Family Registry. No FAMILIES dict, no hardcoded query names.
- Verified: hardcoded template dict = False, hardcoded names = False (all three).

## Extending to a new invariant kind (e.g. execution / lifecycle / ordering)
Add rows to Property Registry (kind=execution + its primitive), Rule Template Registry (kind=execution
template), Query Family Registry (kind=execution families). Engines pick it up with zero code change.

## v17 output (derived_registries_v17.json)
Invariants 36 · Rules 36 · Queries 84 — identical to the hardcoded version, now data-driven.
```python
from ake import AKE
AKE("EBIS_Architecture_Registry_Workbook_v17.xlsx").derive_all()
```
