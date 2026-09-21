"""Lifecycle Population Operation (implementation module — NOT a new architectural engine).

Populates a lifecycle view per entity from its actual workbook data: what relation types this
entity participates in, which are filled, which are empty and why. Previously this used a
FIXED 9-stage template hardcoded to EBIS registry names (Handler, Gate, Pipeline, Bridge,
Validator, Module, Output, Evidence). That template made lifecycle meaningless on any non-EBIS
workbook — a biology workbook showed "Handler: not_referenced" which is not a gap, it's a
concept that doesn't exist in that domain.

Now lifecycle stages are DERIVED from the entity's actual relations + three universal stages
(Entry, Output, Evidence) that apply to every workbook. A Tiger in a biology workbook shows
stages for Habitat, Predator, Diet. A Command in EBIS shows Handler, Gate, Pipeline, etc.
No code change needed when the workbook changes.
"""
import re


class LifecycleOperation:
    def __init__(self, model):
        self.m = model

    def _col_for(self, rd, stage):
        return next((c for c in rd if stage.lower() in str(c).lower()), None)

    def _diagnose_empty(self, rd, stage):
        col = self._col_for(rd, stage)
        val = str(rd.get(col, "")).strip() if col else ""
        if not val or val.lower() in ("not found", "none", "n/a", ""):
            return "not_referenced"
        # Value present in the row but no graph edge → something the edge compiler missed
        loc = self.m._rpde._exact_anywhere(val) if hasattr(self.m, '_rpde') else None
        if loc:
            return "compiler_missed"
        return "genuine_metadata_gap"

    def _derive_stages(self, eid):
        """Derive lifecycle stages from the entity's actual relation types + universal stages.
        No hardcoded registry or relation names. The stages are exactly what this entity
        participates in, ordered: Entry, [each unique relation type], Output, Evidence."""
        stages = ["Entry"]
        # Unique relation types this entity has (stable order from graph neighbors)
        seen = set()
        for e in self.m.universal_graph.neighbors(eid):
            rel = e["relation"]
            if rel not in seen:
                seen.add(rel)
                stages.append(rel.replace("_", " ").title())
        stages += ["Output", "Evidence"]
        return stages

    def populate(self, eid):
        t = self.m.owner_sheet(eid); row = self.m.owner_row(eid)[1]
        rd = self.m.row_dict(t, row) if row else {}
        edges = self.m.universal_graph.neighbors(eid)
        stages = self._derive_stages(eid)
        out = []
        for stage in stages:
            if stage == "Entry":
                v = str(rd.get(self._col_for(rd, "Entry") or "", "")).strip()
                filled = [v] if v and v.lower() != "not found" else []
                out.append({"stage": stage, "filled": filled,
                            "status": "filled" if filled else self._diagnose_empty(rd, stage)})
            elif stage == "Output":
                v = str(rd.get(self._col_for(rd, "Output") or "", "")).strip()
                filled = [v] if v and v.lower() not in ("not found", "none") else []
                out.append({"stage": stage, "filled": filled,
                            "status": "filled" if filled else "not_referenced"})
            elif stage == "Evidence":
                ev = str(rd.get(self._col_for(rd, "Evidence") or "", "")).strip()
                hits = re.findall(r'[\w./]+\.py:\d+', ev) if ev else []
                # For non-code evidence, accept any non-empty string
                if not hits and ev and ev.lower() not in ("not found", "none", "n/a"):
                    hits = [ev]
                out.append({"stage": stage, "filled": hits,
                            "status": "filled" if hits else "missing"})
            else:
                # Relation stage: check edges whose relation matches this stage name
                rel_lower = stage.lower().replace(" ", "_")
                se = [(e["node"], e.get("evidence")) for e in edges
                      if e["relation"].lower().replace(" ", "_") == rel_lower
                      or rel_lower in e["relation"].lower()]
                out.append({"stage": stage, "filled": [x[0] for x in se],
                            "evidence": [x[1] for x in se if x[1]][:1],
                            "status": "filled" if se else self._diagnose_empty(rd, stage)})
        return {"entity": eid, "class": t, "lifecycle": out}

LifecyclePopulator = LifecycleOperation
