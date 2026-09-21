"""RP-04 — Invariant Identification Engine. Registry-driven (reads Property Registry).
No hardcoded property names/kinds. Only the observation primitives (ISA) are in code."""
import re
from .discovery_primitives import DiscoveryPrimitives

def _apply(op, val, target=None):
    if op == "not_null": return val is not None and val != "UNKNOWN"
    if op == "non_empty": return bool(val) and val != "UNKNOWN"
    if op == "matches": return bool(re.search(str(target or ""), str(val)))
    return bool(val)

class InvariantEngine:
    def __init__(self, model, threshold=1.0):
        self.m = model; self.threshold = threshold; self.dp = DiscoveryPrimitives(model)
        self.props = self._load_property_registry()

    def _load_property_registry(self):
        s = "Property Registry"; h = self.m.hdr.get(s, [])
        rows = self.m.rows(s)
        if len(rows) == 0 or not h:            # AKE default (bundled) when workbook lacks it
            import os, json
            d = json.load(open(os.path.join(os.path.dirname(__file__), "defaults", "property_registry.json")))
            h = d["header"]; rows = d["rows"]
        ci = {n: h.index(n) for n in h if n}
        out = []
        for r in rows:
            if r and r[0]:
                out.append({"property": r[ci["Property"]], "kind": r[ci["Kind"]],
                            "primitive": r[ci["Primitive"]], "field": r[ci.get("Field", -1)],
                            "operator": r[ci["Operator"]], "value": r[ci.get("Value", -1)]})
        return out

    def _eval_attribute(self, eid, p):
        res = getattr(self.dp, p["primitive"])(eid)
        if p["field"] and isinstance(res, dict): res = res.get(p["field"])
        return _apply(p["operator"], res, p["value"])

    def discover(self):
        invs = []; n = 0
        classes = [reg for reg, meta in self.m.catalog.items() if meta["role"].startswith("Owner")]
        for cls in classes:
            entities = [r for r in self.m.rows(cls) if r and r[0]]
            if not entities: continue
            support = {}   # (property,kind,target) -> true count
            for r in entities:
                eid = r[0]
                for p in self.props:
                    if p["kind"] == "relationship":
                        # generic FK-column expansion via FIND_HIERARCHY (targets from data)
                        for par in self.dp.FIND_HIERARCHY(eid).get("parents", []):
                            tgt = self.m.owner_sheet(par["id"])
                            key = (f"references::{par['role']}", "relationship", tgt)
                            support[key] = support.get(key, 0) + 1
                    else:
                        key = (p["property"], p["kind"], None)
                        support.setdefault(key, 0)
                        if self._eval_attribute(eid, p): support[key] += 1
            for (prop, kind, tgt), cnt in support.items():
                s = cnt / len(entities)
                if s >= self.threshold:
                    n += 1
                    invs.append({"id": f"INV-{n:03d}", "scope": cls, "property": prop, "kind": kind,
                                 "target": tgt, "support": f"{cnt}/{len(entities)}", "confidence": round(s, 3)})
        return invs
