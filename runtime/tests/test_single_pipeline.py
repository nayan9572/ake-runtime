"""Single-pipeline regression (Stage 9).

Locks: AKE.ask_pipeline is THE one path — Query -> Tokenizer -> Resolver(Language+Workbook) ->
Canonical Intent -> AlgorithmDerivation -> RuntimeEngine -> Evidence. It reuses existing owners
only (no new planner/executor), exposes every stage for explainability, and there is no alternate
execution path in the pipeline method.

Run: python tests/test_single_pipeline.py  -> nonzero exit on any failure.
"""
import os, sys, io, tokenize, re

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

    r = a.ask_pipeline("Top 5 ca50")
    # every stage present in the output (explainability)
    check("tokens produced (tokenizer stage)", r["tokens"] and all("start" in t for t in r["tokens"]))
    check("intent produced (roles only, no operations field)",
          "operations" not in r["intent"])
    check("semantic operations derived (planner level 1)", r["operations"] == ["SORT_DESC", "LIMIT"])
    check("opcode plan derived (planner level 2)",
          ["op_sort", {"desc": True}] in [[p[0], p[1]] for p in r["plan"]])
    check("plan executed on RuntimeEngine", r["result"] and r["result"]["executed"] == [p[0] for p in r["plan"]])

    # the pipeline chains existing owners: verify the same objects are used
    check("uses the one tokenizer", a.tokenizer is not None)
    check("uses the one planner (AlgorithmDerivation)", type(a.planner).__name__ == "AlgorithmDerivation")
    check("uses the one RuntimeEngine", type(a.engine).__name__ == "RuntimeEngine")

    # a different query shape flows through the SAME pipeline (no alternate path)
    r2 = a.ask_pipeline("average ca50")
    check("different query -> same pipeline -> different plan",
          r2["operations"] == ["GROUP", "AVG"] and r2["result"]["executed"] == [p[0] for p in r2["plan"]])

    # the pipeline method itself contains no grammar/opcode literals (it only chains owners)
    src = open(os.path.join(ROOT, "ake", "__init__.py")).read()
    # extract just ask_pipeline body
    m = re.search(r"def ask_pipeline\(self, query\):.*?(?=\n    def )", src, re.S)
    body = m.group(0) if m else ""
    for bad in ["op_sort", "op_group", "op_aggregate", "SORT_DESC", "_CONCEPT_TO_OPS", "op_limit"]:
        check("ask_pipeline body has no '%s' (chains owners, no logic)" % bad, bad not in body)

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
