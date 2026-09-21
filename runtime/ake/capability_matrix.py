"""Universal Capability Validation — the Capability Universe of AKE for a given workbook.

For an (entity | workbook) it answers: which canonical engineering questions can AKE answer, and with
what evidence. Output is a Capability Matrix, not an algorithm. Every capability is grounded in the
Universal Property Graph (relations) + node attributes + integrity primitives — no guessing.

Previously CAPABILITY_UNIVERSE was a hardcoded dict of EBIS-specific categories (Control={handler,
gate,...}, DataFlow={produces,consumes,...}). A biology workbook would show "GET_HANDLER: unsupported"
which is meaningless. Now the relation-specific capabilities are DERIVED from the workbook's actual
relation types. The universal capabilities (Identity, Relationships, Dependency, Integrity, Coverage,
Evidence) apply to every workbook regardless of domain.
"""

# Universal capabilities that exist for every workbook regardless of domain.
# These do NOT reference any specific relation or registry name.
_UNIVERSAL_CAPABILITIES = {
    "Identity":      [("WHAT_IS", "attribute", "metadata"), ("GET_NAME", "attribute", "name"),
                      ("GET_PURPOSE", "attribute", "metadata")],
    "Relationships": [("GET_NEIGHBORS", "graph", "*"), ("GET_INCOMING", "graph", "*in"),
                      ("GET_OUTGOING", "graph", "*out")],
    "Dependency":    [("GET_UPSTREAM", "graph", "*in"), ("GET_DOWNSTREAM", "graph", "*out"),
                      ("IS_ROOT", "graph", "*"), ("IS_LEAF", "graph", "*")],
    "Integrity":     [("CHECK_FK", "integrity", "validate"), ("IS_ORPHAN", "integrity", "validate"),
                      ("IS_DUPLICATE", "integrity", "validate")],
    "Coverage":      [("MISSING_EVIDENCE", "coverage", "coverage"), ("EMPTY_FIELDS", "coverage", "coverage")],
    "Evidence":      [("GET_EVIDENCE", "attribute", "evidence"), ("GET_SOURCE_ROW", "attribute", "evidence")],
}


def derive_capability_universe(model):
    """Build the full capability universe from the workbook's actual relation types.
    Universal capabilities are constant. Relation-specific capabilities (one GET_<REL>
    per relation type found in the graph) are derived at workbook load — no hardcoded
    relation names. A biology workbook gets GET_HABITAT, GET_PREDATOR, GET_DIET.
    An EBIS workbook gets GET_HANDLER, GET_GATE, etc. No code change needed."""
    caps = dict(_UNIVERSAL_CAPABILITIES)
    # Collect all unique relation types from the graph
    rels = set()
    for s, rel, t, sc, tc, ev in model.universal_edges:
        rels.add(rel)
    # One capability per relation type, grouped under "Relations" (workbook-specific)
    if rels:
        rel_caps = []
        for rel in sorted(rels):
            qname = "GET_%s" % rel.upper().replace(" ", "_")
            rel_caps.append((qname, "relation", rel))
        caps["Relations (workbook)"] = rel_caps
    return caps


# CAPABILITY_UNIVERSE is now a function, not a constant. For backward compatibility,
# code that imports it as a dict gets the universal subset (non-relation capabilities).
CAPABILITY_UNIVERSE = _UNIVERSAL_CAPABILITIES


class CapabilityMatrix:
    def __init__(self, model):
        self.m = model
        self._universe = derive_capability_universe(model)

    def _relations_of(self, eid):
        return set(e["relation"] for e in self.m.universal_graph.neighbors(eid))

    def for_entity(self, eid):
        rels = self._relations_of(eid)
        attrs = self.m.universal_graph.node_attrs.get(eid, {})
        has_row = bool(self.m.owner_row(eid)[1])
        out = {}
        for cat, qs in self._universe.items():
            out[cat] = []
            for q, kind, src in qs:
                if kind == "attribute":
                    ok = has_row if src == "metadata" else (bool(attrs.get("name")) if src == "name"
                         else bool(attrs.get("evidence")))
                    ev = attrs.get("class", "owner registry") if src != "evidence" else (attrs.get("evidence") or "—")
                elif kind == "relation":
                    ok = any(src in str(r) for r in rels)
                    ev = "Relationship/IR (%s)" % src if ok else "relation absent"
                elif kind == "graph":
                    ok = bool(rels)
                    ev = "Universal Property Graph" if ok else "no edges"
                elif kind == "integrity":
                    ok = has_row
                    ev = "integrity primitives"
                else:
                    ok = has_row
                    ev = "coverage analysis"
                out[cat].append({"question": q, "supported": ok, "evidence": ev})
        return {"entity": eid, "class": attrs.get("class"), "capabilities": out}

    def workbook_universe(self):
        owners = [r for r, mt in self.m.catalog.items() if mt["role"].startswith("Owner")]
        allq = [(cat, q) for cat, qs in self._universe.items() for q, _, _ in qs]
        support = {q: 0 for _, q in allq}
        per_family = {}
        total = 0
        for reg in owners:
            ents = [r[0] for r in self.m.rows(reg) if r and r[0]]
            fam_support = {q: 0 for _, q in allq}
            for eid in ents:
                total += 1
                cm = self.for_entity(eid)
                for cat, items in cm["capabilities"].items():
                    for it in items:
                        if it["supported"]:
                            support[it["question"]] += 1
                            fam_support[it["question"]] += 1
            per_family[reg] = {"n": len(ents),
                               "answerable_question_types": sum(1 for _, q in allq if fam_support[q] > 0)}
        return {"total_entities": total, "total_question_types": len(allq),
                "answerable_somewhere": sum(1 for _, q in allq if support[q] > 0),
                "per_question": support, "per_family": per_family,
                "categories": {c: len(qs) for c, qs in self._universe.items()}}
