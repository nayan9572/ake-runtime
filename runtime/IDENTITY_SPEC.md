# AKE — Canonical Identity Specification (IDENTITY_SPEC.md)

Status: implemented (UX-1.4). Governs how every runtime module identifies, resolves, and
looks up entities. This is a **contract**: the runtime routes all identity questions through
the `CanonicalIdentity` registry API below and never re-derives identity from raw strings.

---

## 1. Problem this replaces

Entity identity used to *be* the raw primary-key string (`row[0]`). Three failures followed:

1. **Prefix assumption.** Discovery and the owner-sheet lookup assumed alpha-prefixed IDs
   (`MOD-`, `CMD-`, `FEAT-`) via a `[A-Z]+-` regex. A pure-numeric pk (`1001`) resolved to
   no owner sheet — no menu, no relations, invisible to search.
2. **Numeric PK weakness.** FK detection, edge derivation, and cell indexing only recognised
   `[A-Z]+-\w` tokens, so numeric foreign keys produced no edges, and numeric ids arrived as
   `int` from one code path and `str` from another (the same entity keyed two ways).
3. **Heuristic name resolution.** Name lookup returned the *first* cross-registry label match
   with no class awareness. The same name in two classes opened the wrong entity.

---

## 2. Model

Identity is the **composite `(class, pk)`**, reduced to a stable, collision-free
**canonical key**:

```
canonical_key(class, pk) = "CID-" + sha1(f"{class}::{pk}")[:16]
```

Deterministic across runs/processes and class-scoped, so a numeric pk `1` in two registries
yields two different canonical keys.

Three identity forms and their roles:

| Form | Example | Where it appears |
|---|---|---|
| **display id** | `MOD-002`, `1001`, `1` | everything the user sees/types: search, nav, commands, bookmarks, API, crumbs. Always the raw pk. |
| **canonical key** | `CID-4530bf1ca8872e32` | internal identity + graph node key **only for colliding pks**; the opaque selection token behind an ambiguity picker. Never shown. |
| **node key** | raw pk, or canonical for collisions | the key under which a node lives in the graph. Obtained via `node_key()` / `node_key_for()`; callers never index the graph with a raw string. |

**Interface stability (locked).** display id is *always* the raw pk. Prefixed workbooks
(EBIS v17) are bit-identical: `display_id("MOD-002") == "MOD-002"`, zero ambiguous pks, all
schemas `prefixed`. The canonical scheme is an internal implementation detail reached only
through the API.

---

## 3. PK schema inference (structural, no domain vocabulary)

Each owner registry's pk column is classified by *shape*, never a prefix whitelist:

| schema | rule | example |
|---|---|---|
| `prefixed` | every pk matches `ALPHA-...` | `MOD-002` |
| `numeric` | every pk is digits | `1001` |
| `composite` | every pk contains `::`, `/`, or `\|` | `A::B` |
| `opaque` | anything else | GUIDs, free text |
| `empty` | no pks | — |

---

## 4. The `CanonicalIdentity` registry (immutable, fixed API)

Built once at model load from owner rows, then **frozen** (`__slots__`, `MappingProxyType`
backing maps, `__setattr__` raises after construction). No module may reach into its
internals; every identity question goes through this API:

```
infer_schema(registry)   -> 'prefixed'|'numeric'|'composite'|'opaque'|'empty'
is_numeric(registry)     -> bool
is_composite(registry)   -> bool
canonical_id(token)      -> 'CID-...' when the token denotes exactly one entity, else None
canonical_for(reg, pk)   -> class-scoped canonical key (authoritative constructor)
display_id(token)        -> stable display id (raw pk); NEVER a synthetic 'pk@Class'
owner(token)             -> owning registry, prefix-independent (None if unknown/ambiguous)
resolve(token)           -> {'status':'unique'|'ambiguous'|'unknown', ...}   (never guesses)
translate(token)         -> {'display','canonical','registry','pk'} | None
classes_for_pk(pk)       -> [registry, ...]
node_key(token)          -> graph node key (raw pk, or canonical for a colliding pk)
node_key_for(reg, pk)    -> graph node key for a specific (registry, pk)
is_ambiguous(pk)         -> bool
schema_report()          -> {registry: schema}
```

`resolve()` is the single ambiguity authority:
- `unique`  → `{canonical, display, registry, pk, name}`
- `ambiguous` → `{candidates:[{canonical, registry, pk, name}, ...]}` — **no auto-pick**
- `unknown` → `{}`

---

## 5. Graph lookups are routed (never raw)

`UniversalEdgeGraph` holds a reference to the identity registry and normalises every access:

```
graph._key(token) = identity.node_key(token)      # display -> canonical -> node key
graph.neighbors(token) / graph.attrs(token) / graph.reachable(token)  all route through _key
```

Node attributes and edge endpoints are built with `node_key_for(class, pk)`, so a colliding
pk becomes two distinct nodes keyed by canonical, while unique/numeric/prefixed pks stay
keyed by the raw pk (v17 unchanged). Callers in `ake/__init__.py` use `graph.attrs(...)`
rather than `node_attrs.get(...)`; the shell translates context/crumb through `display_id`
so the internal canonical token never surfaces.

Contract: **no module indexes the graph with a raw, untranslated string.** `graph["1001"]`
direct access is disallowed; go through `neighbors()/attrs()` (which call `node_key`).

---

## 6. Type-aware resolution (resolver behaviour)

`EntityResolver.resolve(token)` order:

1. **Direct ID** via `identity.resolve()` — unique → open; ambiguous pk → candidates.
2. **`Class:name`** explicit scope — type-aware, unambiguous by construction.
3. **Exact name** across owner classes — auto-resolve only if globally unique; two+ classes
   → candidates (`ambiguous_name`). This is the "same name, different class" fix.
4. **Promoted** semantic object (email/phone/serial/etc.).
5. **Fuzzy** substring → candidates only.

Ambiguity is never resolved by guessing. The shell renders candidates as
"Multiple entities found for 'X' — pick one:" with **Registry per line** and the raw pk as
the visible id.

---

## 7. Ambiguous display — no synthetic IDs (locked UX)

When a raw pk collides across classes the user still sees the raw pk. There is **no
`1@Alpha Registry` visible identifier**. The picker looks like:

```
Multiple entities found for '1' — pick one:

   1. 1  AlphaOne
      Registry : Alpha Registry
   2. 1  BetaOne
      Registry : Beta Registry
```

Selection is carried by an **opaque internal canonical token** (`CID-...`) stored as the
result-row value; picking a row opens the correct class. The canonical token never appears
in the header, crumb, or any user-facing surface.

---

## 8. Verification

`tests/test_canonical_identity.py` (27 checks) locks:
- canonical key class-scoped + deterministic; schema inference correct;
- numeric identity: schema inferred, id resolves, prefix-independent `owner()`, FK edges
  derived, searchable, string-typed node keys, opens by bare id, relation walk works;
- name collision: no auto-open, both candidates, `Class:name` disambiguation, shell picker;
- pk collision: two distinct canonical keys, raw display id preserved (no synthetic id),
  candidates returned, canonical selection token opens the right class;
- prefixed workbook (v17): 0 ambiguous pks, display id == raw pk, resolve unchanged, all
  schemas `prefixed`.

Full regression **299/299** across 9 suites; real launcher→gateway→dashboard HTTP
verification **22/22** (v17 UX unchanged).

---

## 9. Backward compatibility summary

| Property | Prefixed workbook (v17) | Numeric workbook | Collision |
|---|---|---|---|
| display id | raw pk (unchanged) | raw pk | raw pk (no synthetic) |
| node key | raw pk | raw pk (str-normalised) | canonical (per class) |
| resolve | unchanged | works (was impossible) | candidates |
| search / nav / API | unchanged | works | candidates |

Existing prefixed IDs remain stable display identifiers and continue to work everywhere; the
canonical identity is an internal detail introduced without requiring any workbook or user
change.
