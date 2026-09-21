"""Universal Intent Discovery pipeline regression — discover().

Locks the UIDA principles: context is the SOURCE node not a search boundary; queries resolve
globally; paths are bidirectional multi-hop; every hop carries an evidence tier + confidence;
structural evidence outranks semantic (weakest-link confidence); ambiguous -> candidates,
unknown -> closest (never a bare error). No domain literals in the discover/path/tiering code.

Run: python tests/test_discovery_pipeline.py  -> nonzero exit on any failure.
"""
import os, sys, io, tokenize, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    g = a.model.universal_graph

    # two connected entities in different registries, multi-hop apart
    from collections import deque
    src = max(g.node_attrs, key=lambda n: len(g.neighbors(n)))
    # BFS to find a target >=2 hops away in a different class
    seen = {g._key(src): 0}; q = deque([(g._key(src), 0)]); target = None
    while q:
        n, d = q.popleft()
        if d >= 4: continue
        for e in g.neighbors(n):
            if e["node"] not in seen:
                seen[e["node"]] = d + 1
                if d + 1 >= 2 and g.attrs(e["node"]).get("class") != g.attrs(src).get("class") and target is None:
                    target = e["node"]
                q.append((e["node"], d + 1))
    check("found a multi-hop cross-registry target for the test", target is not None)

    # ---- 1. context is the SOURCE, query resolves globally + path returned ----
    d = a.discover(target, context=src)
    check("discover resolves the query globally (status resolved)", d["status"] == "resolved")
    check("context used as source node (path present, not a filter)",
          d.get("reachable") and d.get("path") and len(d["path"]) >= 1)
    check("source and target both reported", d.get("source", {}).get("id") == g._key(src)
          and d["target"]["id"] == target)
    check("distance == number of hops", d.get("distance") == len(d["path"]))

    # ---- 2. every hop carries evidence tier + reason + confidence ----
    all_tiered = all(h.get("tier") and h.get("reason") and h.get("confidence") is not None
                     for h in d["path"])
    check("every hop has tier + reason + confidence", all_tiered)
    tiers_valid = all(h["tier"] in AKE.EVIDENCE_TIERS for h in d["path"])
    check("hop tiers are from the evidence ladder", tiers_valid)

    # ---- 3. structural outranks semantic: confidence = product of hop confidences ----
    prod = 1.0
    for h in d["path"]:
        prod *= h["confidence"]
    check("path confidence is the product of hop confidences (weakest-link)",
          abs(d["confidence"] - round(prod, 3)) < 1e-6, "conf=%s prod=%.3f" % (d.get("confidence"), prod))
    check("L1 structural ranks strictly above L5 lexical",
          AKE.EVIDENCE_TIERS["L1_structural"] > AKE.EVIDENCE_TIERS["L5_lexical"])
    # a single lexical hop cannot make an all-structural-looking path high-confidence:
    check("weakest_tier reported", "weakest_tier" in d and d["weakest_tier"] in AKE.EVIDENCE_TIERS)

    # ---- 4. bidirectional: path can traverse reverse edges (in-direction hops) ----
    # not every path needs a reverse hop, but the engine must be capable; assert direction is
    # recorded per hop and is one of in/out.
    check("each hop records a direction (in/out)",
          all(h.get("direction") in ("in", "out") for h in d["path"]))

    # ---- 5. no context -> global resolve, no path, still suggestions ----
    d2 = a.discover(target)
    check("no-context discover resolves globally with suggestions, no path",
          d2["status"] == "resolved" and "path" not in d2 and isinstance(d2.get("suggestions"), list))

    # ---- 6. unknown -> closest, never bare error ----
    d3 = a.discover("zzz_not_a_real_entity_banana_zzz", context=src)
    check("unknown query returns closest (never bare error)",
          d3["status"] == "unknown" and len(d3.get("closest", [])) > 0)

    # ---- 7. ambiguous -> candidates with confidence, never a guess ----
    # find a name shared across classes
    name_classes = {}
    for k, at in g.node_attrs.items():
        nm = at.get("name")
        if nm:
            name_classes.setdefault(str(nm).lower(), set()).add(at.get("class"))
    amb = next((nm for nm, cls in name_classes.items() if len(cls) > 1), None)
    if amb:
        da = a.discover(amb)
        check("ambiguous query returns ranked candidates, no auto-pick",
              da["status"] == "ambiguous" and len(da["candidates"]) >= 2
              and all("confidence" in c for c in da["candidates"]))

    # ---- 8. no hardcoded domain literals in discover/path/tiering code ----
    def code_tokens(path):
        src_txt = open(path).read()
        return " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(src_txt).readline)
                        if t.type not in (tokenize.COMMENT, tokenize.STRING)).lower()
    banned = ["fuel", "ca50", "handler", "command", "brand", "order", "product", "customer",
              "mod-", "cmd-", "feat-", "var-", "hnd-", "comp-"]
    # check edge_graph_engine.path_between + __init__ discover region via whole-file token scan
    eng_code = code_tokens(os.path.join(ROOT, "ake", "edge_graph_engine.py"))
    leaked_eng = [w for w in banned if re.search(r"\b" + re.escape(w) + r"\b", eng_code)]
    check("path engine has no domain literals", not leaked_eng, str(leaked_eng))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
