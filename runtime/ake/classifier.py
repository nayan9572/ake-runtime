"""Stage-1 Workbook Classification with a verification gate.

AKE never assumes a workbook is an architecture workbook. It classifies from structural evidence and
promotes the classification through Candidate -> Verified -> Rejected, recording reasons. Only a Verified
Architecture Registry Workbook enters the architecture Query Engine; other types get an honest summary.
"""
import re

PK = re.compile(r"^[A-Z]{2,6}-[A-Za-z0-9]+$")


class WorkbookClassifier:
    def __init__(self, model):
        self.m = model

    def evidence(self):
        sheets = [s for s in self.m.sheets if s != "Registry Catalog"]
        pk_sheets, total_sheets, total_rows, max_cols = 0, 0, 0, 0
        for s in sheets:
            rows = [r for r in self.m.sheets[s][1:] if r and any(c is not None for c in r)]
            if not rows:
                continue
            total_sheets += 1
            total_rows += len(rows)
            max_cols = max(max_cols, len(self.m.hdr.get(s, [])))
            col0 = [r[0] for r in rows if r and r[0] is not None]
            if col0 and sum(1 for v in col0 if isinstance(v, str) and PK.match(str(v))) / len(col0) >= 0.7:
                pk_sheets += 1
        entities = len([1 for r, mt in self.m.catalog.items() if mt["role"].startswith("Owner")
                        for rr in self.m.rows(r) if rr and rr[0]])
        return {"sheets": total_sheets, "rows": total_rows, "columns": max_cols,
                "registry_catalog": "Registry Catalog" in self.m.sheets,
                "id_pattern_sheets": pk_sheets,
                "id_pattern_ratio": round(pk_sheets / total_sheets, 2) if total_sheets else 0.0,
                "entities": entities, "relationships": len(self.m.universal_edges)}

    def classify(self):
        e = self.evidence()
        # --- Candidate: Architecture Registry Workbook ---
        if e["registry_catalog"] or e["id_pattern_ratio"] >= 0.5:
            reasons, verdict = [], "Verified"
            if e["entities"] == 0:
                verdict = "Rejected"; reasons.append("no PREFIX-N entity IDs recognized")
            elif e["relationships"] == 0 and e["id_pattern_sheets"] <= 1:
                verdict = "Candidate"; reasons.append("entities found but no relationships between them")
            else:
                reasons.append("%d entity types, %d entities, %d relationships%s"
                               % (e["id_pattern_sheets"], e["entities"], e["relationships"],
                                  ", registry catalog present" if e["registry_catalog"] else ""))
            if verdict != "Rejected":
                return {"type": "Architecture Registry Workbook", "verdict": verdict, "evidence": e, "reasons": reasons}
            # rejected as architecture -> fall through to other types

        # --- Generic Relational Workbook: multiple sheets that reference each other ---
        if e["sheets"] >= 2 and e["relationships"] > 0:
            return {"type": "Generic Relational Workbook", "verdict": "Verified", "evidence": e,
                    "reasons": ["%d linked sheets, %d cross-references" % (e["sheets"], e["relationships"])]}

        # --- Business Dataset: few sheets, many attribute rows, no entity-ID pattern / cross-refs ---
        if e["rows"] >= 50 and e["id_pattern_ratio"] < 0.5 and e["relationships"] == 0:
            return {"type": "Business Dataset", "verdict": "Verified", "evidence": e,
                    "reasons": ["%d sheet(s), %d rows, %d columns; no entity-ID pattern or cross-sheet references"
                                % (e["sheets"], e["rows"], e["columns"])]}

        return {"type": "Unknown Workbook", "verdict": "Candidate", "evidence": e,
                "reasons": ["insufficient structural evidence to classify"]}

    def is_architecture(self):
        c = self.classify()
        return c["type"] == "Architecture Registry Workbook" and c["verdict"] in ("Verified", "Candidate")

    def dashboard(self):
        c = self.classify()
        e = c["evidence"]
        L = ["AKE Ready", "",
             "  Workbook Type  : %s  (%s)" % (c["type"], c["verdict"])]
        if c["type"] == "Architecture Registry Workbook":
            return None  # architecture path renders the full validation dashboard elsewhere
        # non-architecture: honest structural summary, no fabricated registry/integrity metrics
        L += ["  Sheets         : %d" % e["sheets"],
              "  Rows           : %d" % e["rows"],
              "  Columns        : %d" % e["columns"]]
        L += ["", "  Why"] + ["    - " + r for r in c["reasons"]]
        if c["type"] == "Business Dataset":
            L += ["", "  This is a data table, not an architecture registry. AKE's architecture queries",
                  "  (owner, handler, lifecycle, ...) do not apply. Column/row exploration only."]
        elif c["type"] == "Unknown Workbook":
            L += ["", "  AKE could not confirm a known structure. See the Workbook Constitution for the",
                  "  minimum an architecture workbook needs (PREFIX-N IDs, relationships, evidence)."]
        return "\n".join(L)
