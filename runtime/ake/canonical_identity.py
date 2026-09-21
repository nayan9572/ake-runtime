"""Canonical Identity — the single, immutable registry of entity identity (IR-only).

WHY
    Entity identity used to BE the raw primary-key string (row[0]). Three weaknesses:
      1. loader/discovery assumed alpha-prefixed IDs (`MOD-`), so NUMERIC pks (`1001`)
         resolved to no owner sheet — invisible to menu/relations/search.
      2. two registries reusing the same raw pk (`1`) collided into one graph node.
      3. name resolution returned the FIRST cross-registry label match with no class
         awareness, so the same name in two classes opened the WRONG entity.

CONTRACT (immutable registry with a FIXED public API — nothing else in the runtime may
reach into its internals; every identity question goes through these methods):

    infer_schema(registry)   -> 'prefixed'|'numeric'|'composite'|'opaque'|'empty'
    is_numeric(registry)     -> bool
    is_composite(registry)   -> bool
    canonical_id(token)      -> canonical key 'CID-...'  (or None)
    display_id(token)        -> STABLE display id (the raw pk; NEVER a synthetic '1@Class')
    owner(token)             -> owning registry (prefix-INDEPENDENT)  (or None)
    resolve(token)           -> {'status': 'unique'|'ambiguous'|'unknown',
                                  'canonical','display','registry','pk',   # when unique
                                  'candidates':[{canonical,registry,pk,name}]}  # when ambiguous
    translate(token)         -> {'display','canonical','registry','pk'} | None
    classes_for_pk(pk)       -> [registry, ...]
    node_key(token)          -> the graph node key for an entity  (display id == raw pk)

INTERFACE STABILITY (locked)
    display_id is ALWAYS the raw pk. Prefixed workbooks (EBIS v17) are bit-identical. A pk
    reused across classes is NOT given a synthetic visible id; instead `resolve()` reports
    status='ambiguous' and the caller shows a candidate picker. Disambiguation is carried by
    the canonical key internally + an opaque selection token (canonical), never by mutating
    the user-visible id.

NO DOMAIN VOCABULARY
    Schema inference is structural (shape of the pk column) — no prefix whitelist.
"""
import hashlib
import re
from types import MappingProxyType

_PREFIXED = re.compile(r'^([A-Za-z][A-Za-z0-9]*)-(.+)$')
_NUMERIC = re.compile(r'^\d+$')


def _schema_of(values):
    """Structural pk-schema inference from a sample of a registry's pk column."""
    sample = [str(v) for v in values if v not in (None, "")][:50]
    if not sample:
        return "empty"
    if all(_PREFIXED.match(v) for v in sample):
        return "prefixed"
    if all(_NUMERIC.match(v) for v in sample):
        return "numeric"
    if all(("::" in v or "/" in v or "|" in v) for v in sample):
        return "composite"
    return "opaque"


def canonical_key(cls, pk):
    """Stable, class-scoped, collision-free identity: sha1('class::pk'). Deterministic."""
    return "CID-" + hashlib.sha1(("%s::%s" % (cls, pk)).encode("utf-8")).hexdigest()[:16]


class CanonicalIdentity:
    """Built ONCE from the model's owner rows, then frozen. All internal maps are exposed
    only through the public API above; the backing dicts are wrapped read-only so no caller
    can mutate identity after construction (immutable registry)."""

    __slots__ = ("_schema", "_by_canonical", "_display_to_canonical", "_owner_by_pk",
                 "_owner_of", "_ambiguous", "_frozen")

    def __init__(self, model):
        schema, by_canonical, disp2canon, owner_by_pk, owner_of = {}, {}, {}, {}, {}
        owners = [(reg, meta) for reg, meta in model.catalog.items()
                  if meta.get("role", "").startswith("Owner")]

        for reg, _ in owners:
            col0 = [r[0] for r in model.rows(reg) if r and r[0] not in (None, "")]
            schema[reg] = _schema_of(col0)

        for reg, _ in owners:
            for r in model.rows(reg):
                if r and r[0] not in (None, ""):
                    owner_by_pk.setdefault(str(r[0]), [])
                    if reg not in owner_by_pk[str(r[0])]:
                        owner_by_pk[str(r[0])].append(reg)
        ambiguous = frozenset(pk for pk, regs in owner_by_pk.items() if len(regs) > 1)

        for reg, _ in owners:
            for r in model.rows(reg):
                if not r or r[0] in (None, ""):
                    continue
                pk = str(r[0])
                ck = canonical_key(reg, pk)
                name = str(r[1]) if len(r) > 1 and r[1] not in (None, "") else None
                by_canonical[ck] = {"registry": reg, "pk": pk, "name": name}
                # display id is ALWAYS the raw pk (no synthetic '1@Class'); the canonical key
                # carries disambiguation for colliding pks.
                disp2canon.setdefault(pk, []).append(ck)
                owner_of.setdefault(pk, [])
                if reg not in owner_of[pk]:
                    owner_of[pk].append(reg)

        # freeze
        self._schema = MappingProxyType(dict(schema))
        self._by_canonical = MappingProxyType({k: MappingProxyType(v) for k, v in by_canonical.items()})
        self._display_to_canonical = MappingProxyType({k: tuple(v) for k, v in disp2canon.items()})
        self._owner_by_pk = MappingProxyType({k: tuple(v) for k, v in owner_by_pk.items()})
        self._owner_of = MappingProxyType({k: tuple(v) for k, v in owner_of.items()})
        self._ambiguous = ambiguous
        self._frozen = True

    def __setattr__(self, k, v):
        if getattr(self, "_frozen", False):
            raise AttributeError("CanonicalIdentity is immutable")
        object.__setattr__(self, k, v)

    # ------------------------------------------------------------------ schema
    def infer_schema(self, registry):
        return self._schema.get(registry, "empty")

    def is_numeric(self, registry):
        return self.infer_schema(registry) == "numeric"

    def is_composite(self, registry):
        return self.infer_schema(registry) == "composite"

    def schema_report(self):
        return dict(self._schema)

    # ------------------------------------------------------------------ identity
    def _canon_keys_for(self, token):
        """All canonical keys a token could denote (token may be a canonical key, or a raw
        pk that maps to one or more classes)."""
        t = str(token)
        if t in self._by_canonical:
            return [t]
        return list(self._display_to_canonical.get(t, ()))

    def canonical_id(self, token):
        """Canonical key when the token denotes exactly one entity, else None (ambiguous or
        unknown -> use resolve())."""
        keys = self._canon_keys_for(token)
        return keys[0] if len(keys) == 1 else None

    def display_id(self, token):
        """Stable display id (== raw pk). Accepts a canonical key, raw pk, or display id."""
        t = str(token)
        if t in self._by_canonical:
            return self._by_canonical[t]["pk"]
        return t  # a raw pk/display id is already the display id

    def owner(self, token):
        """Owning registry, prefix-INDEPENDENT. None if unknown or ambiguous."""
        t = str(token)
        if t in self._by_canonical:
            return self._by_canonical[t]["registry"]
        regs = self._owner_of.get(t, ())
        return regs[0] if len(regs) == 1 else (regs[0] if regs and t not in self._ambiguous else None)

    def classes_for_pk(self, pk):
        return list(self._owner_by_pk.get(str(pk), ()))

    def is_ambiguous(self, pk):
        return str(pk) in self._ambiguous

    def canonical_for(self, registry, pk):
        """Class-scoped canonical key for a (registry, pk) pair — unambiguous even when the
        raw pk collides across classes. This is the authoritative identity constructor."""
        return canonical_key(registry, str(pk))

    def node_key_for(self, registry, pk):
        """Graph node key for a specific (registry, pk): raw pk when unique, canonical when
        that pk collides across classes (so the two rows are distinct nodes)."""
        pk = str(pk)
        return canonical_key(registry, pk) if pk in self._ambiguous else pk

    def node_key(self, token):
        """Graph node key. UNIQUE pk -> display id (== raw pk); prefixed/numeric workbooks
        unchanged. COLLIDING pk -> canonical CID- token, so the two entities are DISTINCT
        graph nodes. Single source of truth: callers never index the graph with a raw
        untranslated string."""
        t = str(token)
        if t in self._by_canonical:
            info = self._by_canonical[t]
            return t if info["pk"] in self._ambiguous else info["pk"]
        return t

    def translate(self, token):
        """Full identity record for an unambiguous token, else None."""
        ck = self.canonical_id(token)
        if not ck:
            return None
        info = self._by_canonical[ck]
        return {"display": info["pk"], "canonical": ck, "registry": info["registry"], "pk": info["pk"]}

    def resolve(self, token):
        """Identity resolution with explicit ambiguity. Never guesses among classes."""
        keys = self._canon_keys_for(token)
        if len(keys) == 1:
            info = self._by_canonical[keys[0]]
            return {"status": "unique", "canonical": keys[0], "display": info["pk"],
                    "registry": info["registry"], "pk": info["pk"], "name": info["name"]}
        if len(keys) > 1:
            return {"status": "ambiguous",
                    "candidates": [{"canonical": k, "registry": self._by_canonical[k]["registry"],
                                    "pk": self._by_canonical[k]["pk"], "name": self._by_canonical[k]["name"]}
                                   for k in keys]}
        return {"status": "unknown"}
