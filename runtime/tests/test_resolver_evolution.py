"""Resolver Evolution regression (Stage 5).

Locks: EntityResolver.classify() combines Language Registry (grammar) + Vocabulary Registry
(workbook, owner-tagged) + entity resolution, with STRICT SEPARATION — the language registry
never resolves entities, the vocabulary never parses grammar, and the resolver only arbitrates.
Reuse: classify is on the EXISTING EntityResolver (no parallel resolver class).

Run: python tests/test_resolver_evolution.py  -> nonzero exit on any failure.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.entity_resolver import EntityResolver

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    r = a.resolver

    # ---- reuse: classify is on the existing EntityResolver, not a new class ----
    check("classify() lives on the existing EntityResolver", hasattr(EntityResolver, "classify"))
    check("resolver has language + vocabulary refs", r.language is not None and r.vocabulary is not None)

    # ---- grammar concept path ----
    c = r.classify("show")
    check("grammar word -> concept", c["kind"] == "concept" and c["canonical"] == "SHOW")
    check("concept result carries NO entity id (separation)", "id" not in c)

    # ---- workbook entity path (owner-tagged, ambiguity preserved) ----
    # find an entity name present in the vocabulary
    sample = next(((eid, at["name"]) for eid, at in a.model.universal_graph.node_attrs.items()
                   if at.get("name")), None)
    if sample:
        eid, name = sample
        cc = r.classify(name)
        check("entity name -> workbook classification", cc["kind"] == "workbook")
        check("workbook candidate carries owner authority", cc["best"].get("owner") is not None)

    # ambiguous name -> multiple candidates
    from collections import Counter
    nc = Counter(str(at["name"]).lower() for at in a.model.universal_graph.node_attrs.values() if at.get("name"))
    amb = next((nm for nm, k in nc.items() if k > 1), None)
    if amb:
        ca = r.classify(amb)
        check("ambiguous entity name -> multiple workbook candidates", len(ca["candidates"]) > 1)

    # ---- direct entity id -> entity authority (resolver's own) ----
    any_id = next(iter(a.model.universal_graph.node_attrs))
    ce = r.classify(any_id)
    check("raw entity id -> entity (resolver authority)", ce["kind"] in ("entity", "workbook"))

    # ---- unresolved -> explicit, never a crash ----
    cu = r.classify("zzz_not_real_banana_xyz")
    check("unknown token -> unresolved (no crash)", cu["kind"] == "unresolved")

    # ---- STRICT SEPARATION ----
    check("language never resolves an entity (concept has no id/class)",
          all(k not in r.classify("count") for k in ("id", "class")))
    # vocabulary never parses grammar: a grammar word is NOT returned as a workbook candidate
    check("grammar word not misfiled as workbook", r.classify("top")["kind"] == "concept")
    # precedence: grammar checked before workbook/entity
    check("grammar precedence over entity resolution", r.classify("show")["kind"] == "concept")

    # ---- resolver still works as before (resolve() untouched) ----
    rr = r.resolve(any_id)
    check("existing resolve() still returns entity", rr.get("id") == any_id or rr.get("candidates"))

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
