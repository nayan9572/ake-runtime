"""Canonical Intent regression (Stage 6, corrected).

Locks the refined boundary: the builder assembles SEMANTIC ROLES ONLY (targets/references/
actions/questions/qualifiers/constraints/time/values). It does NOT derive operation sequences and
does NOT emit opcodes — concept→operation derivation is algorithmic knowledge owned by
AlgorithmDerivation (Stage 7). Builder reuses the resolver and is workbook-independent.

Run: python tests/test_canonical_intent.py  -> nonzero exit on any failure.
"""
import os, sys, json, io, tokenize, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.canonical_intent import CanonicalIntent, CanonicalIntentBuilder

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    b = a.intent_builder

    d = b.build("Top 10 customers who bought Brand 1 after 2023").as_dict()

    # ---- roles captured ----
    check("TOP captured as qualifier role", any(q["canonical"] == "TOP" for q in d["qualifiers"]))
    check("numeric values captured (10, 2023)", 10 in d["values"] and 2023 in d["values"])
    check("time role recorded (AFTER)", any(t["op"] == "AFTER" for t in d["time"]))

    # ---- BOUNDARY: NO operations field, NO derivation in the intent ----
    check("intent has NO 'operations' field (derivation is the planner's job)",
          "operations" not in d)
    check("CanonicalIntent slots contain no 'operations'", "operations" not in CanonicalIntent.__slots__)

    # ---- BOUNDARY: no semantic-operation names AND no opcodes anywhere ----
    flat = json.dumps(d).lower()
    op_names = ["sort_desc", "sort_asc", "group", "distinct", "aggregate"]
    check("no derived semantic-operation names in intent", not any(o in flat for o in op_names))
    opcode_markers = ["op_sort", "op_group", "op_limit", "op_aggregate", "kwargs", "render_table"]
    check("no runtime opcodes/kwargs in intent", not any(m in flat for m in opcode_markers))

    # ---- builder does not own an operation-derivation map ----
    import ake.canonical_intent as ci
    check("builder module has no _CONCEPT_OPS map", not hasattr(ci, "_CONCEPT_OPS"))
    check("builder has no _derive_operations method", not hasattr(CanonicalIntentBuilder, "_derive_operations"))

    # ---- roles still assembled for varied queries (universality of ROLE capture) ----
    d2 = b.build("average ca50").as_dict()
    check("AVERAGE captured as action role", any(x["canonical"] == "AVERAGE" for x in d2["actions"]))
    d3 = b.build("compare MOD-002 MOD-007").as_dict()
    check("COMPARE captured as action role", any(x["canonical"] == "COMPARE" for x in d3["actions"]))
    check("two entities captured (target + reference)", len(d3["targets"]) + len(d3["references"]) >= 2)

    # ---- reuse + independence ----
    check("builder reuses the existing resolver", b.resolver is a.resolver)
    src = open(os.path.join(ROOT, "ake", "canonical_intent.py")).read()
    toks = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)]
    code = " ".join(toks).lower()
    banned = ["customer", "brand", "revenue", "ca50", "fuel", "order", "mod-", "var-", "feat-"]
    dleak = [w for w in banned if re.search(r"\b" + re.escape(w) + r"\b", code)]
    check("no domain literals in builder code", not dleak, str(dleak))

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
