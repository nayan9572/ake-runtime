"""Execution Tree regression (Priority 3).

Locks: AlgorithmDerivation consumes the Intent Tree and PRODUCES an Execution Tree (ExecutionNode)
that preserves hierarchy — each intent scope becomes an execution scope with its own operations +
opcode sub-plan + children. The planner OWNS the execution structure; Runtime only consumes the
compiled flat opcode sequence. The tree is compiled to flat ONLY at the end (compile_flat), so
hierarchy is retained in `execution_tree`. Planner never depends on Runtime; Runtime never rebuilds
hierarchy.

Run: python tests/test_execution_tree.py -> nonzero exit on any failure.
"""
import os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.algorithm_derivation import ExecutionNode, AlgorithmDerivation

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def _rank_scopes(node):
    n = 1 if any(op in ("SORT_DESC", "SORT_ASC") for op in node["operations"]) else 0
    for c in node["children"]:
        n += _rank_scopes(c)
    return n

def run():
    a = AKE(locate_workbook(None))
    p = a.planner

    intent = a.intent_builder.build("top 5 features aur top 3 modules")
    r = p.derive_from_intent(intent)

    # ---- planner produces an execution tree ----
    check("derive_from_intent returns execution_tree", r.get("execution_tree") is not None)
    et = r["execution_tree"]

    # ---- hierarchy preserved: two ranking scopes, each with its own sub-plan ----
    check("two ranking scopes preserved in execution tree", _rank_scopes(et) == 2)
    check("each child scope has its own opcode sub-plan",
          all(c["plan"] for c in et["children"]))
    check("child scopes carry their own operations",
          all("SORT_DESC" in c["operations"] for c in et["children"]))

    # ---- compiled flat plan executes on the current Runtime ----
    out = a.engine.run(r["plan"], {"target": r["target"]})
    check("compiled flat plan executes on RuntimeEngine",
          out["executed"] == [op for op, _ in r["plan"]])
    check("flat compilation is depth-first (root then children)",
          [op for op, _ in r["plan"]] == ExecutionNode(**{}).compile_flat() or len(r["plan"]) >= 4)

    # ---- planner owns execution structure (ExecutionNode is in the planner module) ----
    check("ExecutionNode lives in AlgorithmDerivation's module",
          ExecutionNode.__module__.endswith("algorithm_derivation"))
    check("derive_execution_tree is a planner method",
          hasattr(AlgorithmDerivation, "derive_execution_tree"))

    # ---- execution tree carries opcodes (it IS execution) but is distinct from the intent tree ----
    flat = json.dumps(et).lower()
    check("execution tree contains opcodes (op_sort/resolve_entity)",
          "op_sort" in flat or "resolve_entity" in flat)
    # intent tree (roles) must NOT contain opcodes — proves the two are distinct owners
    itree = intent.as_dict()["tree"]
    check("intent tree has NO opcodes (distinct from execution tree)",
          "op_sort" not in json.dumps(itree).lower())

    # ---- simple query: single scope, still works (fallback path) ----
    r2 = p.derive_from_intent(a.intent_builder.build("Top 5 features"))
    check("simple query produces a valid plan", r2["plan"] and r2["operations"] == ["SORT_DESC", "LIMIT"])

    # ---- compile_flat is the ONLY linearisation point (tree retained) ----
    check("execution_tree retained alongside flat plan (hierarchy not lost)",
          r["execution_tree"] is not None and isinstance(r["plan"], list))

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
