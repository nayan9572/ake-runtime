"""Query Discovery — given an ENTITY, derive the applicable queries from its observed features.
Not hardcoded per entity: each present feature -> an applicable runtime query (bound pipeline)."""
from .discovery_primitives import DiscoveryPrimitives
class QueryDiscovery:
    def __init__(self, model): self.m = model; self.dp = DiscoveryPrimitives(model)
    def applicable(self, entity):
        eid = entity["id"]; cls = entity["class"]; out = []
        def add(name, pipeline, kwargs=None): out.append({"name": name, "pipeline": pipeline, "bind": kwargs or {}})
        hier = self.dp.FIND_HIERARCHY(eid); neigh = self.dp.GRAPH_NEIGHBORS(eid)
        # owner(s) via each FK the entity has
        for par in hier.get("parents", []):
            add(f"OWNER_via_{par['role']}", ["resolve_entity","walk_parent","attach_evidence","render_tree"])
            break
        # producers / consumers (data-flow) if data edges present
        if any(n["flow"] == "Data" and n["dir"] == "in" for n in neigh):
            add("PRODUCERS", ["resolve_entity","walk_dataflow","attach_evidence","render_graph"], {"direction":"in"})
        if any(n["flow"] == "Data" and n["dir"] == "out" for n in neigh):
            add("CONSUMERS", ["resolve_entity","walk_dataflow","attach_evidence","render_graph"], {"direction":"out"})
        # neighbors / dependencies if any edges
        if neigh:
            add("NEIGHBORS", ["resolve_entity","walk_relationship","attach_evidence","render_graph"])
        # execution stages if entity appears in an exec-provider profile
        prof = next((s for s in self.m.exec_sheets() if "Profile" in s), None)
        if prof and any(r and r[0] == eid for r in self.m.rows(prof)):
            add("EXECUTION_STAGES", ["resolve_entity","walk_execution","render_timeline"])
        # lifecycle / gap if a lifecycle row exists
        lc = next((s for s in self.m.sheets if "Lifecycle Status" in s), None)
        if lc and any(r and r[0] == eid for r in self.m.rows(lc)):
            add("LIFECYCLE_GAP", ["resolve_entity","walk_lifecycle","walk_dataflow","walk_execution","gap_analysis","render_table"])
        # evidence always if present
        if self.dp.FIND_FILES(eid):
            add("EVIDENCE", ["resolve_entity","attach_evidence","render_table"])
        # LIFECYCLE reconstruction = composition of library primitives (ordered hop traversal + evidence)
        prof2 = next((s for s in self.m.exec_sheets() if "Profile" in s), None)
        has_exec = prof2 and any(r and r[0] == eid for r in self.m.rows(prof2))
        if has_exec or neigh:
            add("LIFECYCLE_RECONSTRUCT",
                ["resolve_entity","walk_execution","walk_relationship","attach_evidence","render_timeline"])
        for i, q in enumerate(out, 1): q["id"] = f"AQ-{i:02d}"
        return out
    def select(self, queries, prefer=None):
        if prefer:
            for q in queries:
                if prefer.upper() in q["name"].upper(): return q
        return queries[0] if queries else None
