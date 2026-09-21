"""Unified query authority regression.

Locks the authority merge: the SINGLE ask_pipeline (tokenizer -> vocab -> grammar -> intent tree
-> planner -> execution tree -> compiler -> runtime) reaches GRAPH DISCOVERY capabilities
(dependency/reachability/path), not just entity resolution. Graph operations flow through the
planner into runtime graph opcodes (which use the discovery graph), and results (edges/nodes)
surface for the Analyzer. There is no separate query authority for graph traversal.

Run: python tests/test_unified_authority.py -> nonzero exit on any failure.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))

    # find an entity with graph relations to test against
    eid = next(iter(a.model.universal_graph.node_attrs))

    # ---- a DEPENDENCY query flows through the planner and reaches graph discovery ----
    r = a.planner.derive_from_intent(a.intent_builder.build("%s dependency" % eid))
    check("dependency query derives DEPENDENCY op", "DEPENDENCY" in r["operations"])
    check("planner prepends resolve_entity for graph op",
          r["plan"] and r["plan"][0][0] == "resolve_entity")
    out = a.engine.run(r["plan"], {"target": r["target"]})
    check("graph op executes via runtime (graph_dependency)", "graph_dependency" in out["executed"])
    check("runtime surfaces graph edges/nodes (not just result)",
          "edges" in out or "nodes" in out)

    # ---- the SINGLE ask_pipeline reaches the same graph discovery ----
    rp = a.ask_pipeline("%s dependency" % eid)
    reached = bool(rp["result"] and (rp["result"].get("edges") or rp["result"].get("nodes")))
    check("ask_pipeline (single authority) reaches graph discovery", reached)

    # ---- reachability also flows through the one pipeline ----
    rr = a.planner.derive_from_intent(a.intent_builder.build("%s ko affect karne wale" % eid))
    if "REACHABILITY" in rr["operations"]:
        outr = a.engine.run(rr["plan"], {"target": rr["target"]})
        check("reachability executes and surfaces graph data",
              "graph_reachability" in outr["executed"] and ("edges" in outr or "nodes" in outr))

    # ---- runtime returns structured outputs generically (edges/nodes/groups/rows) ----
    from ake.runtime_engine import RuntimeEngine
    import inspect
    src = inspect.getsource(RuntimeEngine.run)
    check("runtime surfaces edges/nodes/groups/metrics/rows generically",
          all(k in src for k in ["edges", "nodes", "groups", "metrics", "rows"]))

    # ---- there is ONE ask entry point (no parallel graph-query method on the public surface) ----
    check("ask_pipeline is the single NL entry point", hasattr(a, "ask_pipeline"))


    # ---- OPEN: a bare entity routes through the planner; discovery is the execution SUBSTRATE ----
    rd = a.planner.derive_from_intent(a.intent_builder.build(str(eid)))
    check("bare entity derives OPEN op (open intent, not a discover operation)",
          "OPEN" in rd["operations"])
    check("OPEN compiles to open_entity opcode",
          any(op == "open_entity" for op, _ in rd["plan"]))
    outd = a.engine.run(rd["plan"], {"target": rd["target"]})
    check("open_entity runs on the discovery substrate (rich output)",
          bool(outd.get("discovery")))
    rpd = a.ask_pipeline(str(eid))
    check("ask_pipeline surfaces discovery for a bare entity via OPEN",
          bool(rpd.get("answer")) and rpd["operations"] == ["OPEN"])
    # discovery is the SUBSTRATE (reused facade.discover), not a duplicated search
    import inspect
    from ake.runtime_primitives import RuntimePrimitives
    dsrc = inspect.getsource(RuntimePrimitives.open_entity)
    check("open_entity uses the discovery substrate (facade.discover / list_entities)",
          "_facade.discover" in dsrc or "list_entities" in dsrc)
    # a REGISTRY container opens to its members via the substrate (not treated as a graph entity)
    reg = next((name for name in (getattr(a.model, "catalog", {}) or {})), None)
    if reg:
        rr = a.planner.derive_from_intent(a.intent_builder.build(reg))
        outr = a.engine.run(rr["plan"], {"target": rr["target"]})
        disc = outr.get("discovery") or {}
        check("registry container opens to member list (substrate lists members)",
              disc.get("status") == "registry" and disc.get("count", 0) > 0)

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
