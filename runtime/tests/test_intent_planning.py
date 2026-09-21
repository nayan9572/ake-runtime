"""AlgorithmDerivation intent-planning regression (Stage 7).

Locks: AlgorithmDerivation is the SOLE owner that turns intent roles into semantic operations
(level 1) and then into an opcode plan (level 2). Operation vocabulary comes from the canonical
Operation Inventory (single source of truth). No other layer holds concept→operation or
operation→opcode knowledge. The derived plan executes on RuntimeEngine (executor unchanged).

Run: python tests/test_intent_planning.py  -> nonzero exit on any failure.
"""
import os, sys, io, tokenize, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.operation_inventory import OPERATIONS, realize
from ake.algorithm_derivation import AlgorithmDerivation

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    b, p = a.intent_builder, a.planner

    # ---- level 1: roles -> semantic operations (from the inventory) ----
    r = p.derive_from_intent(b.build("Top 10 ca50"))
    check("TOP -> [SORT_DESC, LIMIT]", r["operations"] == ["SORT_DESC", "LIMIT"])
    check("all derived ops are in the canonical inventory", all(o in OPERATIONS for o in r["operations"]))

    # ---- level 2: operations -> opcode plan ----
    check("SORT_DESC -> (op_sort, desc=True)", ("op_sort", {"desc": True}) in r["plan"])
    check("LIMIT 10 -> (op_limit, n=10)", ("op_limit", {"n": 10}) in r["plan"])

    r2 = p.derive_from_intent(b.build("average ca50"))
    check("AVERAGE -> [GROUP, AVG]", r2["operations"] == ["GROUP", "AVG"])
    check("AVG -> (op_aggregate, fn=avg)", ("op_aggregate", {"fn": "avg"}) in r2["plan"])

    r3 = p.derive_from_intent(b.build("total ca50"))
    check("TOTAL -> [SUM] -> (op_aggregate, fn=sum)",
          r3["operations"] == ["SUM"] and ("op_aggregate", {"fn": "sum"}) in r3["plan"])

    r4 = p.derive_from_intent(b.build("lowest ca50"))
    check("BOTTOM/lowest -> [SORT_ASC, LIMIT]", r4["operations"] == ["SORT_ASC", "LIMIT"])

    # ---- the opcode plan actually executes on RuntimeEngine (executor unchanged) ----
    plan = p.derive_from_intent(b.build("Top 5 ca50"))
    out = a.engine.run(plan["plan"], {"target": plan["target"] or next(iter(a.model.universal_graph.node_attrs))})
    check("derived plan executes on RuntimeEngine", out["executed"] == [o for o, _ in plan["plan"]])

    # ---- inventory is the single source of truth: every op realizes to real opcodes ----
    import inspect
    from ake.runtime_primitives import RuntimePrimitives
    prim = {n for n, _ in inspect.getmembers(RuntimePrimitives, inspect.isfunction)}
    bad = [(op, name) for op in OPERATIONS for name, _ in realize(op, [1]) if name not in prim]
    check("every inventory operation realizes to a real opcode", not bad, str(bad))

    # ---- SINGLE OWNER: concept→op and op→opcode maps exist ONLY in algorithm_derivation ----
    def has_mapping(modfile):
        src = open(os.path.join(ROOT, "ake", modfile)).read()
        return "_CONCEPT_TO_OPS" in src or "SORT_DESC" in src and "op_sort" in src
    check("canonical_intent.py has NO concept→operation map",
          "_CONCEPT_TO_OPS" not in open(os.path.join(ROOT, "ake", "canonical_intent.py")).read()
          and "_CONCEPT_OPS" not in open(os.path.join(ROOT, "ake", "canonical_intent.py")).read())
    # language registry must not know opcodes
    lang = open(os.path.join(ROOT, "ake", "language_registry.py")).read()
    toks = [t.string for t in tokenize.generate_tokens(io.StringIO(lang).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)]
    check("language_registry.py holds no opcode names", "op_sort" not in " ".join(toks))
    # planner owns both levels
    ad = open(os.path.join(ROOT, "ake", "algorithm_derivation.py")).read()
    check("AlgorithmDerivation owns concept→op map (_CONCEPT_TO_OPS)", "_CONCEPT_TO_OPS" in ad)
    check("the exposed planner IS AlgorithmDerivation", type(a.planner).__name__ == "AlgorithmDerivation")
    check("AKE exposes no separate intent_planner owner", not hasattr(a, "intent_planner"))
    check("derivation methods live ON AlgorithmDerivation", hasattr(AlgorithmDerivation, "derive_from_intent") and hasattr(AlgorithmDerivation, "_derive_operations"))
    # operation_inventory is imported ONLY by algorithm_derivation (internal asset, not a public owner)
    import subprocess
    importers = subprocess.run(["grep","-rl","operation_inventory","ake/"], capture_output=True, text=True).stdout.split()
    non_ad = [f for f in importers if "algorithm_derivation" not in f and "operation_inventory" not in f]
    check("operation_inventory imported only by AlgorithmDerivation (internal)", not non_ad, str(non_ad))

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
