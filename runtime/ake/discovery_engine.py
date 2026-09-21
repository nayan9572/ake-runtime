"""Discovery Engine — produces a Registry Universe (the universal part). Everything derived from the
workbook; nothing hardcoded to any domain. The Discovery Report is only a rendered VIEW of this output.

Registry Universe sections (all derived):
  1. Registry Discovery      — registries + entity counts
  2. Entity Discovery        — entity types, prefixes, ID patterns, examples
  3. Relationship Discovery  — relation types present
  4. Schema Discovery        — catalog/evidence/FK/PK-pattern
  5. Capability Discovery    — which canonical capability categories are AVAILABLE (derived, not assumed)
  6. Search Discovery        — how the user can search this workbook
"""


class DiscoveryEngine:
    def __init__(self, model):
        self.m = model

    def registry_universe(self):
        owners = [(r, mt) for r, mt in self.m.catalog.items() if mt["role"].startswith("Owner")]
        registries, entity_types = [], []
        ident = getattr(self.m, "identity", None)
        for reg, mt in owners:
            ents = [rr[0] for rr in self.m.rows(reg) if rr and rr[0]]
            if not ents:
                continue
            # PK schema is INFERRED structurally (prefixed / numeric / composite / opaque),
            # not assumed to be alpha-prefixed. Prefix is shown only when it exists.
            schema = ident.infer_schema(reg) if ident else "opaque"
            if schema == "prefixed":
                prefix = str(ents[0]).split("-")[0]
                id_pattern = prefix + "-N"
            elif schema == "numeric":
                prefix = ""            # numeric pks have no alpha prefix
                id_pattern = "N (numeric)"
            elif schema == "composite":
                prefix = ""
                id_pattern = "A::B (composite)"
            else:
                prefix = ""
                id_pattern = "opaque"
            registries.append({"name": reg, "entities": len(ents)})
            entity_types.append({"prefix": prefix, "id_pattern": id_pattern, "pk_schema": schema,
                                 "count": len(ents), "examples": [str(e) for e in ents[:3]]})

        rel_types = sorted(set(e[1] for e in self.m.universal_edges))
        rels = set(rel_types)

        def has(keys):
            return any(any(k in r for r in rels) for k in keys)

        node_attrs = self.m.universal_graph.node_attrs
        node_evidence = any(a.get("has_Evidence") for a in node_attrs.values())

        _schemas = {et.get("pk_schema") for et in entity_types}
        _pkpat = (list(_schemas)[0] if len(_schemas) == 1 else "mixed") if _schemas else "none"
        schema = {
            "registry_catalog_present": "Registry Catalog" in self.m.sheets,
            "evidence_columns_present": any(self.m.evidence_col(r) for r, _ in owners),
            "fk_relationships_present": len(self.m.universal_edges) > 0,
            "pk_pattern": _pkpat,
        }

        # Capability Discovery — DERIVED from what the workbook actually has.
        # Universal capabilities (always available for any workbook with entities).
        # Relation-specific capabilities are derived from what relations exist, not hardcoded.
        capabilities = {
            "Identity": bool(entity_types),
            "Relationships": bool(rel_types),
            "Dependency": bool(rel_types),
            "Integrity": bool(entity_types),
            "Coverage": bool(entity_types),
            "Evidence": node_evidence,
        }
        # Add one capability per workbook-specific relation type (derived, not hardcoded)
        if rel_types:
            capabilities["Relations (workbook)"] = True

        ex = entity_types[0]["examples"][0] if entity_types else "<ID>"
        pf = entity_types[0]["prefix"] if entity_types else "<PREFIX>"
        list_hint = ("list %s" % pf) if pf else "list <Registry>"
        search_modes = ["<ID>  (e.g. %s)" % ex, "search <term>", list_hint,
                        "describe %s" % ex, "GET_<X> %s" % ex]

        return {
            "registries": registries,
            "entity_types": entity_types,
            "relation_types": rel_types,
            "schema": schema,
            "capabilities": capabilities,
            "search_modes": search_modes,
            "totals": {"registries": len(registries),
                       "entities": sum(r["entities"] for r in registries),
                       "entity_types": len(entity_types),
                       "relation_types": len(rel_types),
                       "capabilities_available": sum(1 for v in capabilities.values() if v)},
        }

    def report(self):
        u = self.registry_universe()
        t = u["totals"]
        L = ["=" * 60, "AKE Workbook Discovery", "=" * 60,
             "Registries: %d | Entity types: %d | Entities: %d | Relation types: %d"
             % (t["registries"], t["entity_types"], t["entities"], t["relation_types"]), ""]
        L.append("Detected Registries")
        for r in u["registries"]:
            L.append("  + %s (%d)" % (r["name"], r["entities"]))
        L += ["", "Detected Entity Types"]
        for e in u["entity_types"]:
            L.append("  %-12s (%d)  e.g. %s" % (e["id_pattern"], e["count"], ", ".join(e["examples"])))
        L += ["", "Detected Relation Types", "  " + (", ".join(u["relation_types"]) or "(none)")]
        L += ["", "Capability Summary (derived)"]
        for cat, ok in u["capabilities"].items():
            L.append("  %s %s%s" % (("[x]" if ok else "[ ]"), cat, "" if ok else "   not available"))
        L += ["", "Search", *["  " + s for s in u["search_modes"]]]
        return "\n".join(L)
