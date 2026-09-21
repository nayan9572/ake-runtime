"""Rule Derivation Engine. Registry-driven (reads Rule Template Registry). No hardcoded templates."""
class RuleEngine:
    def __init__(self, model):
        self.m = model; self.tpl = self._load()
    def _load(self):
        s = "Rule Template Registry"; h = self.m.hdr.get(s, []); rows = self.m.rows(s)
        if len(rows) == 0 or not h:
            import os, json
            d = json.load(open(os.path.join(os.path.dirname(__file__), "defaults", "rule_template_registry.json")))
            h = d["header"]; rows = d["rows"]
        ci = {n: h.index(n) for n in h if n}
        out = {}
        for r in rows:
            if r and r[0]:
                out[r[ci["Kind"]]] = {"purpose": r[ci["Purpose Template"]], "condition": r[ci["Condition Template"]],
                                      "action": r[ci["Action Template"]], "severity": r[ci["Severity"]]}
        return out
    def derive(self, invariants):
        rules = []; n = 0
        for inv in invariants:
            t = self.tpl.get(inv["kind"])
            if not t: continue
            n += 1
            fmt = {"scope": inv["scope"], "property": inv["property"].replace("references::", "").strip(),
                   "target": inv["target"] or "referent"}
            rules.append({"id": f"RULE-{n:03d}", "kind": inv["kind"], "scope": inv["scope"],
                          "purpose": t["purpose"].format(**fmt), "condition": t["condition"].format(**fmt),
                          "action": t["action"].format(**fmt), "severity": t["severity"],
                          "evidence": inv["id"], "property": fmt["property"], "target": fmt["target"]})
        return rules
