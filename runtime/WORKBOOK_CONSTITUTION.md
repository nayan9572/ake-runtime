# AKE Workbook Constitution

AKE runs on any workbook that satisfies this constitution. Capability scales with structure. All tiers
below are **empirically validated** (see the numbers in each tier and `tests/regression.py`).

## Rule 0 — Entity identity (MANDATORY)
Every entity sheet must have, in **column 0**, a **unique primary key** of the form `PREFIX-N`
(uppercase letters, hyphen, then alphanumerics) — e.g. `CMD-001`, `HND-026`, `FEAT-016`.
This is how AKE identifies entities and links references. Numeric or composite keys are **not** yet
supported and will yield zero recognized entities.

## Tier 1 — MINIMUM (validated: 8/31 question types)
- ≥1 sheet with a `PREFIX-N` PK in column 0.
No catalog, FK, or evidence required. AKE infers a registry catalog from structure and answers:
Identity, Integrity, Coverage. Relations and evidence are limited.

## Tier 2 — RECOMMENDED (validated: 18/31 question types)
Add:
- An **Evidence** column (values like `file.py:123`) per entity sheet.
- **Foreign-key columns** named with `(FK)` (e.g. `Module (FK)`) whose values are other entities' PKs,
  **or** references by exact entity **name**.
Now answerable additionally: Ownership, Relationships, Dependency, Evidence.

## Tier 3 — FULL (validated on EBIS: 31/31 question types)
Add:
- A **`Registry Catalog`** sheet that self-describes each registry (role, PK column, PK prefix, FK edges,
  evidence column, whether it is the relationship/execution provider).
- A **relationship provider** sheet (Source/Relation/Target/Flow) and/or FK columns across families.
- An **execution profile** sheet (per-entity stage matrix) to populate execution/lifecycle stages.
All 10 categories / 31 canonical question types become answerable.

## Optional AKE control sheets (data, not code)
- `Property Registry`, `Rule Template Registry`, `Query Family Registry` — if absent, AKE uses bundled
  defaults (`ake/defaults/`). Include them to customize invariant/rule/query derivation for your domain.

## Validation summary (reproducible)
| Tier | Structure | Answerable question types |
|---|---|---|
| Minimum | 1 sheet + `PREFIX-N` PK | 8 / 31 |
| Recommended | + Evidence + FK/name refs | 18 / 31 |
| Full (EBIS) | + Registry Catalog + Relationship + Execution | 31 / 31 |
| Violation | numeric PK | 0 entities (constitution not met) |
