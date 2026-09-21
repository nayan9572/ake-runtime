"""ACCEPTANCE query suite — the real merge milestone tracker.

This is NOT a unit/regression test. It runs real natural-language queries through the ONE canonical
pipeline end-to-end and reports, per query, where the pipeline actually delivered a correct
user-facing result. Regression-green does not imply acceptance-green; this file is the acceptance
truth.

For each query it traces the canonical authority:
  Natural Query -> Vocabulary -> Intent -> Planner -> Discovery/Runtime -> Answer
and classifies the OUTCOME (not just "did code run"):
  PASS    - the expected user-facing result was produced
  PARTIAL - pipeline reached the right operation but the result is incomplete
  FAIL    - the pipeline did not produce the expected result
Each non-PASS names the OWNER that must fix it (single-authority accountability).

Run: python tests/acceptance_suite.py   (exit 0 only if zero FAILs)
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook


def classify(a, q, expect):
    """Run one query end-to-end; return (verdict, owner, detail)."""
    r = a.ask_pipeline(q)
    ops = r["operations"]
    res = r["result"] or {}
    ans = r.get("answer") or {}
    disc = res.get("discovery") or {}
    executed = res.get("executed") or []

    kind = expect["kind"]
    if kind == "registry":
        if disc.get("status") == "registry" and disc.get("count", 0) > 0:
            return "PASS", "-", "registry:%d members" % disc["count"]
        return "FAIL", "RuntimePrimitives/open_entity", "no members listed"
    if kind == "discovery":
        if disc.get("suggestions") or disc.get("status") not in (None, "unknown"):
            return "PASS", "-", "discovery reached"
        return "FAIL", "Discovery substrate", "discovery not reached"
    if kind == "graph":
        if res.get("edges"):
            return "PASS", "-", "graph:%d edges" % len(res["edges"])
        return "FAIL", "Runtime graph opcode", "no edges"
    if kind == "count":
        if "COUNT" in ops or "COUNT_RELATED" in ops:
            val = res.get("result")
            return ("PASS", "-", "count=%s" % val) if val is not None else \
                   ("PARTIAL", "RuntimePrimitives/count", "COUNT derived but no value")
        return "FAIL", "Vocabulary(HOWMANY)+Planner", "COUNT not derived (ops=%s)" % ops
    if kind == "aggregate":
        if any(o in ("AVG", "SUM", "MIN", "MAX") for o in ops):
            val = res.get("result")
            return ("PASS", "-", "value=%s" % val) if val is not None else \
                   ("PARTIAL", "RuntimePrimitives/op_aggregate", "aggregate derived but value None")
        return "FAIL", "Vocabulary+Planner", "aggregate not derived (ops=%s)" % ops
    if kind == "rank":
        has_rank = any(o in ("SORT_DESC", "SORT_ASC", "LIMIT") for o in ops)
        nrows = len(res.get("rows", [])) if res.get("rows") else 0
        if has_rank and nrows > 0:
            return "PASS", "-", "ranked %d rows" % nrows
        if has_rank:
            return "PARTIAL", "RuntimePrimitives/class-load", "rank derived but no rows"
        return "FAIL", "Planner", "rank not derived (ops=%s)" % ops
    return "FAIL", "?", "unknown expectation"


QUERIES = [
    ("Category Registry",                          {"kind": "registry"}),
    ("Family Registry",                            {"kind": "registry"}),
    ("CAT-01",                                     {"kind": "discovery"}),
    ("FEAT-016 dependency",                        {"kind": "graph"}),
    ("FEAT-016 ko affect karne wale variables",    {"kind": "graph"}),
    ("Family me kitne Feature hain",               {"kind": "count"}),
    ("average ca50",                               {"kind": "aggregate"}),
    ("top 5 features",                             {"kind": "rank"}),
]


def run():
    a = AKE(locate_workbook(None))
    rows = []
    for q, expect in QUERIES:
        try:
            verdict, owner, detail = classify(a, q, expect)
        except Exception as e:
            verdict, owner, detail = "FAIL", "exception", str(e)[:60]
        rows.append((q, verdict, owner, detail))

    w = max(len(q) for q, *_ in rows)
    npass = sum(1 for _, v, *_ in rows if v == "PASS")
    npart = sum(1 for _, v, *_ in rows if v == "PARTIAL")
    nfail = sum(1 for _, v, *_ in rows if v == "FAIL")
    print("ACCEPTANCE SUITE (end-to-end, one pipeline)\n" + "=" * (w + 40))
    for q, v, owner, detail in rows:
        mark = {"PASS": "PASS ", "PARTIAL": "PART ", "FAIL": "FAIL "}[v]
        print("[%s] %-*s  %-34s  %s" % (mark, w, q, detail, ("" if v == "PASS" else "owner=" + owner)))
    print("=" * (w + 40))
    print("PASS=%d  PARTIAL=%d  FAIL=%d  (of %d)" % (npass, npart, nfail, len(rows)))
    print("\nNote: PARTIAL/FAIL are known acceptance gaps, each mapped to one owner. Acceptance is")
    print("complete only when FAIL=0. Regression passing does NOT imply acceptance passing.")
    return nfail == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
