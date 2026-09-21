"""Discovery-console context regression — locks the "AKE>" context/discovery behaviour.

Verifies that contexts are derived from the EXISTING registry catalog (not a duplicate
model), resolve dynamically (name / prefix / singular / startswith), scope queries to one
registry, and that context+entity yields a structural discovery chain. Also checks the
special 'relation' mode. Deterministic, self-contained. Run:
  python tests/test_context_discovery.py   -> exits nonzero on any failure.
"""
import os, sys

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

    # ---- contexts come from the catalog, not a parallel model ----
    ctxs = a.contexts()
    tokens = {c["token"] for c in ctxs}
    check("contexts() returns the owner registries + relation mode",
          "relation" in tokens and len(ctxs) >= 2, "%d contexts" % len(ctxs))
    # every registry context maps to a real catalog registry
    reg_ctxs = [c for c in ctxs if c["kind"] == "registry"]
    catalog_owners = {reg for reg, mt in a.model.catalog.items() if mt["role"].startswith("Owner")}
    check("every registry context maps to a catalog owner registry",
          all(c["registry"] in catalog_owners for c in reg_ctxs))
    check("context count matches catalog owner-registry count",
          len(reg_ctxs) == len(catalog_owners), "%d vs %d" % (len(reg_ctxs), len(catalog_owners)))

    # ---- dynamic resolution (no hardcoded vocabulary) ----
    # pick the first owner registry and derive its expected aliases from the catalog itself
    reg0 = next(iter(catalog_owners))
    mt0 = a.model.catalog[reg0]
    noun0 = a._entity_noun(mt0["role"]) or reg0.split()[0]
    check("resolve_context by entity noun", a.resolve_context(noun0) == reg0, "%s -> %s" % (noun0, a.resolve_context(noun0)))
    check("resolve_context by registry name", a.resolve_context(reg0) == reg0)
    if mt0.get("prefix") and mt0["prefix"] != "\u2014":
        check("resolve_context by pk prefix", a.resolve_context(mt0["prefix"]) == reg0)
    check("resolve_context 'relation' -> relation mode", a.resolve_context("relation") == a.RELATION_CONTEXT)
    check("resolve_context unknown word -> None", a.resolve_context("zzznotacontextzzz") is None)

    # ---- scoped query stays within the registry ----
    rows0 = [r[0] for r in a.model.rows(reg0) if r and r[0]]
    hits = a.query_in_context(reg0, "")
    check("query_in_context('') returns the whole registry",
          len(hits) == len(rows0) and all(h["class"] == reg0 for h in hits))
    if rows0:
        one = str(rows0[0])
        exact = a.query_in_context(reg0, one)
        check("query_in_context exact id hits that id first", exact and exact[0]["id"] == one)

    # ---- discovery chain is structural ----
    # find any entity that has neighbours
    g = a.model.universal_graph
    ent = next((e for e in g.node_attrs if g.neighbors(e)), None)
    check("found an entity with relations for chain test", ent is not None)
    if ent:
        chain = a.discovery_chain(ent)
        check("discovery_chain returns identity + chain",
              chain and chain["identity"]["id"] == str(ent) and isinstance(chain["chain"], list))
        # chain links are grouped by (direction, relation, class) with counts
        if chain["chain"]:
            link = chain["chain"][0]
            check("chain link has direction/relation/target_class/count/items",
                  all(k in link for k in ("direction", "relation", "target_class", "count", "items")))
            check("chain link count >= items shown (cap-aware)", link["count"] >= len(link["items"]))
        # totals match neighbour count
        total = sum(l["count"] for l in chain["chain"])
        check("chain totals match neighbour count", total == len(g.neighbors(ent)), "%d vs %d" % (total, len(g.neighbors(ent))))

    # ---- relation view ----
    if ent:
        rv = a.relation_view(ent)
        check("relation_view returns incoming/outgoing buckets",
              rv and "incoming" in rv and "outgoing" in rv)
        check("relation_view totals match neighbour count",
              len(rv["incoming"]) + len(rv["outgoing"]) == len(g.neighbors(ent)))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
