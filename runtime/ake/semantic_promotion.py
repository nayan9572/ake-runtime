"""Semantic Promotion — promoted semantic objects as logical projections over Canonical
Runtime Knowledge (Canonical Capability Synthesis Contract v2, §8/§11).

A promoted semantic object is a recurring attribute VALUE inside an existing Owner
registry (e.g. a "Brand" column with repeated text, not yet its own registry) treated,
on demand, as an entity in its own right. It is never stored as a second graph or a
second registry: every method here recomputes its answer directly from `model.rows()`
and `model.catalog` — the exact same Canonical Runtime Knowledge Discovery already
produced. `_cache` is a plain memoization of that computation (a performance detail,
per §8/§11), not an independent source of truth — it is never written back into
`model.universal_graph`, so it can never perturb node/edge counts Discovery already
froze.

No hardcoded column names, registry names, or domain vocabulary: promotion candidates
are found purely from repetition evidence (a value shared by >=2 rows) in columns that
are not already a PK or an FK (an FK column already has a first-class target registry
via ordinary RelationshipDiscovery — promoting it too would fork the semantic model,
which §11 forbids).
"""
import re

_PREFIX = "VPROM"
_META_HEADER_HINTS = ("evidence", "source", "reference", "citation")
# Null/placeholder sentinels -- a generic data-quality convention (not domain vocabulary):
# a repeated sentinel like "Not Found" is missing-data, not a recurring semantic concept,
# and must not be synthesized into a promoted entity. Deliberately excludes workflow
# states like "pending"/"tbd" -- those are real domain values (e.g. an Order's Status),
# not placeholders for absent data.
_NULL_SENTINELS = {"not found", "none", "n/a", "na", "null", "unknown",
                   "-", "—", "unspecified"}


def _slug(s):
    return re.sub(r'[^A-Z0-9]+', '_', str(s).upper()).strip('_')


def _is_sentinel(v):
    return str(v).strip().lower() in _NULL_SENTINELS


class SemanticPromotion:
    def __init__(self, model):
        self.m = model
        self._cache = None  # memoized candidates() — a cache, not a second authority

    # ---- discovery: derived from the workbook's own repetition, nothing hardcoded ----

    def _owners(self):
        return [(r, mt) for r, mt in self.m.catalog.items() if mt["role"].startswith("Owner")]

    def candidates(self):
        """One candidate per (registry, column) whose values repeat across >=2 rows and
        are not already a PK or FK column (those are already first-class entities via
        ordinary RelationshipDiscovery). Every candidate carries the support it was
        derived from, so every promoted action can cite real evidence.

        Two data-quality filters, both generic (no domain vocabulary):
        - null/placeholder sentinels ("Not Found", "None", ...) are dropped from the
          repeated-value set -- missing data is not a semantic concept to promote.
        - a column where a meaningful share of values are ';'-joined lists is skipped
          entirely: a cell like "ORCH; DIFC; sensitivity" is several values packed into
          one string, not one atomic categorical value, so promoting it whole would
          misrepresent the row as if it named a single recurring thing."""
        if self._cache is not None:
            return self._cache
        out = []
        for reg, _mt in self._owners():
            rows = self.m.rows(reg)
            header = self.m.hdr.get(reg, [])
            if not rows or not header:
                continue
            for ci, h in enumerate(header):
                if h is None or ci == 0:          # column 0 is always the PK (codebase convention)
                    continue
                hl = str(h).lower()
                if "(fk)" in hl or any(x in hl for x in _META_HEADER_HINTS):
                    continue
                vals = [r[ci] for r in rows if r and ci < len(r) and r[ci] not in (None, "")]
                if len(vals) < 2:
                    continue
                if sum(1 for v in vals if ";" in str(v)) / len(vals) > 0.2:
                    continue                      # list-shaped column, not atomic values
                distinct_vals = list({str(v) for v in vals})
                if any(self.m.owner_row(v)[1] for v in distinct_vals[:50]):
                    continue                      # values already ARE real entities elsewhere
                                                   # (e.g. RPDE already derived a typed edge for
                                                   # this exact column) -- promoting them too
                                                   # would fork an already-canonical identity
                counts = {}
                for v in vals:
                    if _is_sentinel(v):
                        continue
                    counts[str(v)] = counts.get(str(v), 0) + 1
                repeated = {v: c for v, c in counts.items() if c >= 2}
                if not repeated:
                    continue
                # Genuine categorical repetition only -- not near-unique free text.
                if len(counts) > max(3, int(0.6 * len(vals))):
                    continue
                out.append({
                    "registry": reg, "column": str(h), "column_index": ci,
                    "values": repeated, "support": len(vals),
                })
        self._cache = out
        return out

    def promoted_id(self, column, value):
        return "%s:%s:%s" % (_PREFIX, _slug(column), _slug(value))

    def is_promoted(self, token):
        return str(token).startswith(_PREFIX + ":")

    def _find(self, predicate):
        for cand in self.candidates():
            for value in cand["values"]:
                if predicate(cand, value):
                    return cand, value
        return None, None

    def _lookup(self, promoted_id):
        return self._find(lambda c, v: self.promoted_id(c["column"], v) == promoted_id)

    # ---- resolution: any input token -> promoted Entity (mirrors EntityResolver) ----

    def resolve(self, token):
        token = str(token).strip()
        if self.is_promoted(token):
            cand, value = self._lookup(token)
            if cand:
                return {"id": token, "class": "%s (promoted)" % cand["column"], "how": "id"}
            return None
        cand, value = self._find(lambda c, v: v.lower() == token.lower())
        if cand:
            return {"id": self.promoted_id(cand["column"], value),
                    "class": "%s (promoted)" % cand["column"], "how": "promoted"}
        return None

    def members(self, column, value):
        """Owner-row IDs whose column has this value -- the reverse relation a promoted
        entity is defined by."""
        out = []
        for cand in self.candidates():
            if cand["column"] != column:
                continue
            ci = cand["column_index"]
            for r in self.m.rows(cand["registry"]):
                if r and ci < len(r) and str(r[ci]) == str(value):
                    out.append(r[0])
        return out

    # ---- Universal Dashboard surface: same shapes AKE.entity_actions()/explain_relation() use ----

    def entity_view(self, promoted_id):
        """Attribute view for a promoted entity -- same shape as
        model.universal_graph.node_attrs.get(eid, {}) for a physical one."""
        cand, value = self._lookup(promoted_id)
        if not cand:
            return None
        return {"class": "%s (promoted)" % cand["column"], "name": value, "evidence": None}

    def source_row(self, promoted_id):
        cand, value = self._lookup(promoted_id)
        if not cand:
            return {}
        members = self.members(cand["column"], value)
        return {"Column": cand["column"], "Value": value, "Registry": cand["registry"],
                "Members": len(members)}

    def actions(self, promoted_id):
        """Canonical menu for a promoted entity -- pre-canonicalization shape, identical
        field names to AKE.entity_actions()'s physical-entity actions so a single
        canonicalize() call (ake/capability_synthesis.py) handles both uniformly."""
        cand, value = self._lookup(promoted_id)
        if not cand:
            return []
        members = self.members(cand["column"], value)
        n = len(members)
        conf = round(cand["values"][value] / cand["support"], 3) if cand["support"] else 1.0
        return [
            {"label": "What is", "type": "attr", "query": "WHAT_IS", "relation": None,
             "count": 1, "available": True, "mode": "fixed", "reason": None,
             "_promoted": True, "_provenance": "promoted_entity", "_stage": "SemanticPromotion",
             "_capability": "Identity", "_confidence": conf},
            {"label": "Name", "type": "attr", "query": "GET_NAME", "relation": None,
             "count": 1, "available": True, "mode": "fixed", "reason": None,
             "_promoted": True, "_provenance": "promoted_entity", "_stage": "SemanticPromotion",
             "_capability": "Identity"},
            {"label": cand["registry"], "type": "relation", "query": "REL", "relation": cand["column"],
             "count": n, "available": n > 0, "mode": "promoted",
             "reason": None if n else "No rows carry this value.",
             "_promoted": True, "_provenance": "reverse_relation", "_stage": "SemanticPromotion",
             "_capability": "Relationships", "_target": cand["registry"]},
            {"label": "Evidence", "type": "meta", "query": "GET_EVIDENCE", "relation": None,
             "count": 1, "available": True, "mode": "fixed", "reason": None,
             "_promoted": True, "_provenance": "promoted_entity", "_stage": "SemanticPromotion",
             "_capability": "Evidence", "_evidence": {"support": cand["support"],
                                                       "count": cand["values"][value]}},
            {"label": "Source row", "type": "meta", "query": "GET_SOURCE_ROW", "relation": None,
             "count": 1, "available": True, "mode": "fixed", "reason": None,
             "_promoted": True, "_provenance": "promoted_entity", "_stage": "SemanticPromotion",
             "_capability": "Evidence"},
        ]

    def explain(self, promoted_id, rel):
        """Same result shape as AKE.explain_relation() for a physical entity."""
        cand, value = self._lookup(promoted_id)
        if not cand:
            return {"entity": promoted_id, "relation": rel, "mode": "empty", "count": 0,
                    "items": [], "reason": "Unknown promoted entity."}
        if rel != cand["column"]:
            return {"entity": promoted_id, "relation": rel, "mode": "empty", "count": 0,
                    "items": [], "reason": "No '%s' relationship on this promoted object." % rel}
        member_ids = self.members(cand["column"], value)
        g = self.m.universal_graph
        items = []
        for mid in member_ids:
            a = g.node_attrs.get(mid, {})
            items.append({"node": mid, "name": a.get("name"), "class": a.get("class"),
                          "relation": rel, "evidence": "%s=%s" % (cand["column"], value)})
        return {"entity": promoted_id, "relation": rel,
                "mode": "direct" if items else "empty", "count": len(items), "items": items}
