"""Workbook Validation + evidence-based Confidence. Never silently fails: every check reports.
Confidence is derived from validation evidence, not a fixed number.
"""
import re

ID = re.compile(r'^[A-Z]+-\w')


class WorkbookValidation:
    def __init__(self, model):
        self.m = model

    def checks(self):
        m = self.m
        owners = [r for r, mt in m.catalog.items() if mt["role"].startswith("Owner")]
        # duplicate PKs
        seen, dup_pk = {}, []
        for reg in owners:
            for rr in m.rows(reg):
                if rr and rr[0]:
                    if rr[0] in seen:
                        dup_pk.append(rr[0])
                    seen[rr[0]] = reg
        # broken FKs (FK value that resolves to no entity)
        broken_fk = 0
        for reg in owners:
            hdr = m.hdr.get(reg, [])
            for rr in m.rows(reg):
                if not rr:
                    continue
                for i, h in enumerate(hdr):
                    if h and "(FK)" in str(h) and i < len(rr) and isinstance(rr[i], str):
                        for tok in re.findall(r'[A-Z]+-\w+', rr[i]):
                            if not m.owner_row(tok)[1]:
                                broken_fk += 1
        # empty registries
        empty = [r for r in owners if not [rr for rr in m.rows(r) if rr and rr[0]]]
        # missing evidence (nodes without evidence)
        na = m.universal_graph.node_attrs
        total_nodes = len(na)
        missing_ev = sum(1 for a in na.values() if not a.get("has_Evidence"))
        # duplicate names
        names, dup_names = {}, 0
        for a in na.values():
            nm = (a.get("name") or "").strip().lower()
            if nm:
                if nm in names and names[nm] != a.get("class"):
                    dup_names += 1
                names[nm] = a.get("class")
        return {
            "objects": total_nodes,
            "types": len(owners),
            "relationships": len(m.universal_edges),
            "duplicate_pk": len(set(dup_pk)),
            "broken_fk": broken_fk,
            "empty_registries": len(empty),
            "missing_evidence": missing_ev,
            "missing_evidence_pct": round(100 * missing_ev / total_nodes) if total_nodes else 0,
            "duplicate_names": dup_names,
            "schema_catalog": "Registry Catalog" in m.sheets,
            "schema_evidence": any(m.evidence_col(r) for r in owners),
            "schema_fk": len(m.universal_edges) > 0,
        }

    def confidence(self, c=None):
        c = c or self.checks()
        score = 100.0
        reasons = []
        if c["broken_fk"]:
            score -= min(20, c["broken_fk"] * 2); reasons.append("%d broken foreign key(s)" % c["broken_fk"])
        if c["duplicate_pk"]:
            score -= min(20, c["duplicate_pk"] * 5); reasons.append("%d duplicate ID(s)" % c["duplicate_pk"])
        if c["empty_registries"]:
            score -= min(10, c["empty_registries"] * 3); reasons.append("%d empty registr(y/ies)" % c["empty_registries"])
        if c["missing_evidence_pct"] > 20:
            score -= min(15, (c["missing_evidence_pct"] - 20) // 5); reasons.append("evidence missing on %d%% of objects" % c["missing_evidence_pct"])
        if not c["schema_catalog"]:
            score -= 5; reasons.append("no Registry Catalog (inferred)")
        if not c["schema_fk"]:
            score -= 20; reasons.append("no relationships detected")
        return max(0, round(score)), reasons

    def dashboard(self):
        c = self.checks()
        conf, reasons = self.confidence(c)
        ok = lambda b: "OK" if b else "!!"
        schema_complete = c["schema_catalog"] and c["schema_evidence"] and c["schema_fk"]
        integ_pass = (c["duplicate_pk"] == 0 and c["broken_fk"] == 0)
        L = ["AKE Ready", "",
             "  Objects        : %d %s" % (c["objects"], ok(c["objects"] > 0)),
             "  Types          : %d %s" % (c["types"], ok(c["types"] > 0)),
             "  Relationships  : %d %s" % (c["relationships"], ok(c["relationships"] > 0)),
             "  Schema         : %s %s" % ("Complete" if schema_complete else "Partial", ok(schema_complete)),
             "  Integrity      : %s %s" % ("Passed" if integ_pass else "Issues", ok(integ_pass)),
             "  Confidence     : %d%%" % conf]
        # surface any warnings explicitly (never silent)
        warn = []
        if c["duplicate_pk"]: warn.append("%d duplicate ID(s)" % c["duplicate_pk"])
        if c["broken_fk"]: warn.append("%d broken FK(s)" % c["broken_fk"])
        if c["empty_registries"]: warn.append("%d empty registr(y/ies)" % c["empty_registries"])
        if c["missing_evidence_pct"] > 20: warn.append("evidence missing on %d%% of objects" % c["missing_evidence_pct"])
        if warn:
            L += ["", "  Notes"] + ["    - " + w for w in warn]
        return "\n".join(L)
