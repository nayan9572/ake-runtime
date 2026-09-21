"""Query Derivation Engine. Registry-driven (reads Query Family Registry). No hardcoded query families."""
import re
def slug(s): return re.sub(r'[^A-Z0-9]+', '_', str(s).upper()).strip('_')
class QueryEngine:
    def __init__(self, model):
        self.m = model; self.fam = self._load()
    def _load(self):
        s = "Query Family Registry"; h = self.m.hdr.get(s, []); rows = self.m.rows(s)
        if len(rows) == 0 or not h:
            import os, json
            d = json.load(open(os.path.join(os.path.dirname(__file__), "defaults", "query_family_registry.json")))
            h = d["header"]; rows = d["rows"]
        ci = {n: h.index(n) for n in h if n}
        fam = {}
        for r in rows:
            if r and r[0]:
                fam.setdefault(r[ci["Kind"]], []).append((r[ci["Query Name Template"]],
                    [p.strip() for p in re.split(r'→|\|', str(r[ci["Opcode Pipeline"]])) if p.strip()]))
        return fam
    def derive(self, rules):
        queries = []; n = 0
        for rule in rules:
            for name_tpl, pipeline in self.fam.get(rule["kind"], []):
                n += 1
                name = name_tpl.format(PROP=slug(rule["property"]), SCOPE=slug(rule["scope"]), TARGET=slug(rule["target"]))
                queries.append({"id": f"QUERY-{n:03d}", "name": name, "kind": rule["kind"],
                                "from_rule": rule["id"], "scope": rule["scope"], "pipeline": " → ".join(pipeline)})
        return queries
