"""Phase 2 — Discovery Primitive Engine. P-01..P-10 observation primitives over WorkbookModel."""
import re

class DiscoveryPrimitives:
    def __init__(self, model): self.m = model

    def COUNT_OCCURRENCES(self, eid): return len(self.m.cell_index.get(eid, []))
    def FIND_SHEETS(self, eid): return sorted({h[0] for h in self.m.cell_index.get(eid, [])})
    def FIND_COLUMNS(self, eid): return sorted({f"{h[0]}.{h[2]}" for h in self.m.cell_index.get(eid, [])})
    def FIND_ROWS(self, eid): return [f"{h[0]}:{h[1]}" for h in self.m.cell_index.get(eid, [])]
    def FIND_FILES(self, eid):
        t, row = self.m.owner_row(eid)
        if not row: return []
        out = []
        for i, hh in enumerate(self.m.hdr[t]):
            if hh and "Evidence" in str(hh):
                out += re.findall(r'[\w./]+\.py:\d+', str(row[i]))
        return out
    def RESOLVE_KEYS(self, eid):
        t = self.m.owner_sheet(eid); is_pk = self.m.owner_row(eid)[1] is not None
        fk_in = sorted({s for s in self.FIND_SHEETS(eid) if s != t})
        return {"PK_in": t if is_pk else None, "FK_in": fk_in}
    def GRAPH_NEIGHBORS(self, eid):
        # reads the Universal Edge Graph (RPDE typed edges for ALL classes + dataflow edges)
        return self.m.universal_graph.neighbors(eid)
    def FIND_HIERARCHY(self, eid):
        t, row = self.m.owner_row(eid); parents = []
        if row:
            for i, hh in enumerate(self.m.hdr[t]):
                if hh and "(FK)" in str(hh) and isinstance(row[i], str) and re.match(r'[A-Z]+-', str(row[i])):
                    parents.append({"role": hh, "id": row[i]})
        children = [s for s in self.FIND_SHEETS(eid) if s != t]
        return {"parents": parents, "children": children}
    def FIND_DUPLICATES(self, eid): return {"sheets": self.FIND_SHEETS(eid), "count": len(self.FIND_SHEETS(eid))}
    def READ_METADATA(self, eid):  # D-009: full row
        t, row = self.m.owner_row(eid)
        return self.m.row_dict(t, row) if row else {}

    def observe(self, eid):
        """M1 Observation: run all primitives; ∅ -> UNKNOWN."""
        prims = ["COUNT_OCCURRENCES","FIND_SHEETS","FIND_COLUMNS","FIND_ROWS","FIND_FILES",
                 "RESOLVE_KEYS","GRAPH_NEIGHBORS","FIND_HIERARCHY","FIND_DUPLICATES","READ_METADATA"]
        obs = {}
        for p in prims:
            v = getattr(self, p)(eid)
            obs[p] = v if v not in ([], {}, 0, None) else "UNKNOWN"
        return obs
