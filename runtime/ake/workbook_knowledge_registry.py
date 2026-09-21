"""Workbook Knowledge Registry (Stage 4).

The proven gap (see survey): every piece of workbook knowledge already has an owner —
WorkbookModel.sheets/hdr (loader), .catalog/.owner_by_prefix (registry builder), node_attrs
(name + metadata), col()/hdr (schema), _rel_source/universal_edges (relations/FK). What is
MISSING is a component that HARVESTS those existing owners into the Living Vocabulary Registry as
candidates. This class is only that harvester. It:

  * creates NO new discovery (reuses model.catalog, node_attrs, hdr, _rel_source),
  * creates NO grammar concepts and never touches GRAMMAR_VERSION (correction 6),
  * writes ONLY into the Vocabulary Registry, with source "Workbook Vocabulary",
  * hardcodes NO mapping — every alias/candidate comes from the scanned workbook.

The mapping Revenue→total_amount is therefore never in code: it appears only if a workbook column
named (or aliased to) 'revenue' resolves to 'total_amount' during scan. The Resolver (Stage 5)
later chooses among the candidates by evidence.

Vocabulary TYPES produced here (data categories, NOT grammar): ENTITY, ATTRIBUTE, RELATION.
"""

ENTITY = "ENTITY"
ATTRIBUTE = "ATTRIBUTE"
RELATION = "RELATION"
SOURCE = "Workbook Vocabulary"


class WorkbookKnowledgeRegistry:
    """Derives workbook terminology from existing owners and grows the Vocabulary Registry.
    Runs once at load, after the graph is built. Reuse-only; owns no data of its own."""

    def __init__(self, model, vocabulary):
        self.m = model
        self.vocab = vocabulary

    def build(self):
        """Harvest entities, attributes, and relations from existing owners into the vocabulary.
        Idempotent-friendly: append-only vocabulary supersedes prior same-canonical entries.
        Returns a small summary count for verification."""
        n_entity = self._harvest_entities()
        n_attr = self._harvest_attributes()
        n_rel = self._harvest_relations()
        n_reg = self._harvest_registries()
        return {"entities": n_entity, "attributes": n_attr, "relations": n_rel, "registries": n_reg}

    # ---- REGISTRY names (from catalog — existing owner) ----------------------------------
    def _harvest_registries(self):
        """Harvest each registry's NAME (a catalog key, often multi-word like 'Category Registry')
        as an ENTITY phrase so the tokenizer keeps it as one token and it resolves to the registry.
        Also harvest the registry's CLASS name (from the role, e.g. 'Owner (entity: Feature)') and
        its plural, so 'Feature'/'features' resolve to that class/registry. Reuses the existing
        catalog owner; creates no new discovery."""
        import re as _re
        cat = getattr(self.m, "catalog", {}) or {}
        n = 0
        for reg, meta in cat.items():
            if not reg:
                continue
            self.vocab.add(str(reg), str(reg), ENTITY, source=SOURCE, owner=str(reg),
                           confidence=1.0, reason="registry name", evidence=str(reg),
                           matched_signals=1, total_signals=1)
            n += 1
            # class name from an Owner role: "Owner (entity: Feature)"
            role = str(meta.get("role", ""))
            m = _re.search(r"entity:\s*([A-Za-z][A-Za-z0-9_ ]*?)\s*\)", role)
            if m and role.startswith("Owner"):
                cls = m.group(1).strip()
                for form in {cls, cls + "s", cls.lower(), cls.lower() + "s"}:
                    self.vocab.add(form, str(reg), ENTITY, source=SOURCE, owner=str(reg),
                                   confidence=0.9, reason="class name", evidence=role,
                                   matched_signals=1, total_signals=1)
                    n += 1
        return n

    # ---- ENTITY names (from node_attrs — existing owner) ---------------------------------
    def _harvest_entities(self):
        g = getattr(self.m, "universal_graph", None)
        if g is None:
            return 0
        n = 0
        for eid, a in g.node_attrs.items():
            name = a.get("name")
            if not name:
                continue
            # canonical = the entity id (already globally unique within this workbook). The
            # owning registry (class) is recorded as owner so resolution knows which authority
            # produced this candidate. If the same name occurs in several registries, each is a
            # SEPARATE candidate (different canonical id + owner) — ambiguity is preserved, and a
            # namespaced form is available as owner.name for callers that want it.
            owner = a.get("class")
            self.vocab.add(str(name), str(eid), ENTITY, source=SOURCE, owner=owner,
                           confidence=1.0, reason="entity name in %s" % (owner or "?"),
                           evidence=str(eid), matched_signals=1, total_signals=1)
            n += 1
        return n

    # ---- ATTRIBUTE / column names (from hdr of owner registries — existing owner) --------
    def _harvest_attributes(self):
        cat = getattr(self.m, "catalog", {}) or {}
        n = 0
        for reg, meta in cat.items():
            if not str(meta.get("role", "")).startswith("Owner"):
                continue
            header = self.m.hdr.get(reg, []) if hasattr(self.m, "hdr") else []
            for col_name in header:
                if not col_name:
                    continue
                # a column name is a surface word; canonical = registry.column (unique per owner).
                # The SAME column name in N registries therefore yields N candidates, each owned by
                # its registry — no single forced mapping (observation 2).
                canonical = "%s.%s" % (reg, col_name)
                self.vocab.add(str(col_name), canonical, ATTRIBUTE, source=SOURCE, owner=reg,
                               confidence=1.0, reason="column of %s" % reg,
                               evidence=str(col_name), matched_signals=1, total_signals=1)
                n += 1
        return n

    # ---- RELATION names (from _rel_source — existing owner) ------------------------------
    def _harvest_relations(self):
        rel_source = getattr(self.m, "_rel_source", {}) or {}
        n = 0
        for rel, src in rel_source.items():
            if not rel:
                continue
            # Confidence is EXPLAINABLE, not a bare score. It is derived from how many independent
            # provenance signals back the relation:
            #   signal 1: the relation exists in the graph (always true here)          -> +1
            #   signal 2: it is DECLARED (relationship sheet / FK column), not inferred -> +1
            # confidence = matched_signals / total_signals. Declared => 2/2 = 1.0;
            # inferred (prose name resolution) => 1/2 = 0.5. Reason + evidence recorded.
            declared = (src == "declared")
            matched = 2 if declared else 1
            total = 2
            reason = ("declared relation (relationship sheet or FK column)" if declared
                      else "inferred relation (prose name resolution)")
            evidence = "catalog.fks / relationship sheet" if declared else "prose column resolution"
            self.vocab.add(str(rel), str(rel), RELATION, source=SOURCE, owner=(self.m.rel_sheet if declared else "prose"),
                           confidence=matched / total, reason=reason, evidence=evidence,
                           matched_signals=matched, total_signals=total)
            n += 1
        return n
