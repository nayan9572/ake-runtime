"""Relationship-count (M2 planner semantic execution) regression.

Locks: a nested counting query ("Family me kitne Feature hain") derives COUNT_RELATED (not OPEN),
carries the relation + child prefix from the model (not hardcoded), and returns a real count value.
Also: ranking a class loads its member rows. Owner: AlgorithmDerivation (semantics) + ExecutionCompiler
(opcode) + RuntimePrimitives (count_related / class-load).

Run: python tests/test_relationship_count.py -> nonzero on any failure.
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ake import AKE
from AKE_MASTER import locate_workbook

R = []
def check(n, c, d=""):
    R.append(bool(c)); print("  [%s] %s%s" % ("PASS" if c else "FAIL", n, ("  (%s)" % d) if d else "")); return bool(c)

def run():
    a = AKE(locate_workbook(None))

    # nested count derives COUNT_RELATED with model-derived relation + prefix
    intent = a.intent_builder.build("Family me kitne Feature hain")
    et = a.planner.derive_execution_tree(intent)
    check("nested count derives COUNT_RELATED (not OPEN)", "COUNT_RELATED" in et.operations)
    check("relation derived from model (features)", et.params.get("relation") == "features")
    check("child class prefix derived (FEAT)", et.params.get("target_prefix") == "FEAT")
    check("relation/prefix are NOT hardcoded in planner",
          "features" not in open(os.path.join(ROOT, "ake", "algorithm_derivation.py")).read().lower().split("def _resolve_relationship_count")[0])

    # executes to a real value
    r = a.ask_pipeline("Family me kitne Feature hain")
    res = r["result"] or {}
    check("count executes to an integer value", isinstance(res.get("result"), int))
    check("count value is correct (2 features related to Family)", res.get("result") == 2)

    # ranking a class loads member rows
    r2 = a.ask_pipeline("top 5 features")
    res2 = r2["result"] or {}
    check("ranking a class loads member rows", len(res2.get("rows", []) or []) > 0)
    check("LIMIT caps rows at 5", len(res2.get("rows", []) or []) <= 5)

    # count_related reuses walk_relationship / model edges (single traversal owner)
    import inspect
    from ake.runtime_primitives import RuntimePrimitives
    src = inspect.getsource(RuntimePrimitives.count_related)
    check("count_related reuses walk_relationship or universal_edges (no new traversal)",
          "walk_relationship" in src or "universal_edges" in src)

    p = sum(R); print("\n%d/%d checks passed" % (p, len(R))); return p == len(R)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
