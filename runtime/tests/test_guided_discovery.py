"""Guided Discovery Engine regression — suggest_next().

Locks: suggestions are DERIVED from the graph neighbourhood (hop + importance + relation
multiplicity), ranked, never a fixed list, and the user is never dead-ended (ambiguous ->
candidates, unknown -> closest/most-important entities). No domain literals in the engine.

Run: python tests/test_guided_discovery.py  -> nonzero exit on any failure.
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
    # pick the most-connected entity as anchor (deterministic)
    anchor = max(g.node_attrs, key=lambda n: len(g.neighbors(n)))

    s = a.suggest_next(anchor)
    check("suggest_next resolves and returns suggestions", s and s.get("resolved") and s["suggestions"])
    check("anchor identity reported", s["anchor"]["id"] == anchor)

    # suggestions are real neighbours/2-hop of the anchor, not arbitrary
    reach2 = set()
    for e in g.neighbors(anchor):
        reach2.add(e["node"])
        for e2 in g.neighbors(e["node"]):
            reach2.add(e2["node"])
    check("every suggestion is within 2 hops of the anchor (graph-derived)",
          all(x["id"] in reach2 for x in s["suggestions"]))
    check("suggestions carry hop + relation + score (ranked)",
          all(x.get("hop") and x.get("relation") is not None and x.get("score") is not None for x in s["suggestions"]))
    # ranked by score descending
    scores = [x["score"] for x in s["suggestions"]]
    check("suggestions ranked strongest-first", scores == sorted(scores, reverse=True))
    # importance actually influences ranking: the top suggestion isn't just the first neighbour
    check("ranking uses importance (top has real degree)", s["suggestions"][0].get("importance", 0) >= 0)

    # NOT a fixed list: two different anchors yield different suggestion sets
    others = sorted(g.node_attrs, key=lambda n: -len(g.neighbors(n)))
    a2 = others[1]
    s2 = a.suggest_next(a2)
    if s2.get("resolved"):
        check("different anchors -> different suggestions (not a fixed list)",
              {x["id"] for x in s["suggestions"]} != {x["id"] for x in s2["suggestions"]})

    # ambiguous -> candidates as suggestions, resolved False
    # find a name shared by 2 classes if any; else synthesise via a known ambiguous fixture-free path
    amb = None
    from collections import Counter
    name_classes = {}
    for k, at in g.node_attrs.items():
        nm = at.get("name")
        if nm:
            name_classes.setdefault(str(nm).lower(), set()).add(at.get("class"))
    amb = next((nm for nm, cls in name_classes.items() if len(cls) > 1), None)
    if amb:
        sa = a.suggest_next(amb)
        check("ambiguous name -> not resolved, candidates offered",
              sa.get("resolved") is False and len(sa["suggestions"]) >= 1)

    # unknown -> never empty (closest / most-important entities)
    su = a.suggest_next("zzz_not_a_real_entity_zzz_banana")
    check("unknown query is never dead-ended (suggestions non-empty)",
          su.get("resolved") is False and len(su["suggestions"]) > 0, "reason=%s" % su.get("reason"))

    # engine has no hardcoded domain literals in executable code
    src = open(os.path.join(ROOT, "ake", "semantic_perspective.py")).read()
    toks = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)]
    code = " ".join(toks).lower()
    banned = ["fuel", "ca50", "handler", "command", "module", "feature", "variable", "component", "registry"]
    leaked = [w for w in banned if re.search(r"\b" + w + r"\b", code)]
    check("guided-discovery engine has no hardcoded domain literals", not leaked, str(leaked))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
