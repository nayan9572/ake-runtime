"""Canonical Intent TREE regression (Priority 2).

Locks: the builder produces a hierarchical IntentNode tree that preserves parent-child scopes
(so 'Brand 1 ke top product aur top 10 customer' keeps two distinct TOP scopes instead of
flattening). The tree carries roles only — no operations, no opcodes. Flat lists remain for
backward compatibility. Tree is built via the resolver (no new resolution logic).

Run: python tests/test_intent_tree.py -> nonzero exit on any failure.
"""
import os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.canonical_intent import IntentNode, CanonicalIntent

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def _count_qualifier_scopes(node):
    """Count scopes (node + descendants) that carry a ranking qualifier."""
    n = 1 if any(q["canonical"] in ("TOP", "BOTTOM") for q in node["qualifiers"]) else 0
    for c in node["children"]:
        n += _count_qualifier_scopes(c)
    return n

def run():
    a = AKE(locate_workbook(None))
    b = a.intent_builder

    d = b.build("Brand 1 ke top product aur top 10 customer details do").as_dict()

    # ---- tree exists and is hierarchical ----
    check("intent carries a tree", d["tree"] is not None)
    check("tree has children (not flat)", d["tree"] and len(d["tree"]["children"]) >= 1)

    # ---- the two TOP scopes are PRESERVED as separate nodes (not collapsed) ----
    check("two distinct ranking scopes preserved in the tree",
          _count_qualifier_scopes(d["tree"]) == 2)

    # ---- each scope keeps its own value (10 belongs to the customer scope) ----
    all_values = []
    def collect(n):
        all_values.extend(n["values"])
        for c in n["children"]: collect(c)
    collect(d["tree"])
    check("scope values preserved (1 and 10 present)", 1 in all_values and 10 in all_values)

    # ---- flat lists still present (backward compatibility) ----
    check("flat qualifiers still present", [q["canonical"] for q in d["qualifiers"]] == ["TOP", "TOP"])
    check("flat as_dict still has all role keys",
          set(["targets", "references", "actions", "qualifiers", "values", "tree"]) <= set(d.keys()))

    # ---- BOUNDARY: tree carries NO operations/opcodes ----
    flat = json.dumps(d["tree"]).lower()
    check("tree has no operations/opcodes",
          not any(x in flat for x in ["op_sort", "op_group", "sort_desc", "op_limit", "operations"]))

    # ---- IntentNode is a pure structure (roles only) ----
    n = IntentNode(label="x")
    check("IntentNode slots are role-only",
          set(IntentNode.__slots__) == {"target", "actions", "qualifiers", "values",
                                        "constraints", "time", "children", "label"})

    # ---- a real EBIS composite also builds a tree ----
    d2 = b.build("top 5 features aur top 3 modules").as_dict()
    check("EBIS composite builds a tree with a child", d2["tree"] and len(d2["tree"]["children"]) >= 1)

    # ---- a simple query still works (single-node tree, no crash) ----
    d3 = b.build("CA50 analyse karo").as_dict()
    check("simple query builds a valid tree", d3["tree"] is not None)


    # ---- BOUNDARY: hierarchy derives from GRAMMAR, not hardcoded connective words ----
    import io, tokenize, re
    src = open(os.path.join(ROOT, "ake", "canonical_intent.py")).read()
    code = " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                     if t.type not in (tokenize.COMMENT, tokenize.STRING)).lower()
    # The real risk is a connective DATA STRUCTURE (a set/list/dict of surface words checked at
    # runtime), not prose in a docstring. Look for a set/list literal containing connective words.
    struct_leak = bool(re.search(r'[\[{][^\]}]*["\'](aur|ke|of|per|and)["\'][^\]}]*[,\]}]', src))
    # and confirm the runtime path never compares a token to a connective string
    compare_leak = bool(re.search(r'(tok|t|word)[^\n]{0,30}(==|in)\s*["\']?(aur|ke|of|per)["\']?', src))
    check("tree builder has NO connective data structure or comparison (grammar-derived only)",
          not struct_leak and not compare_leak)
    # tree still segments by QUALIFIER grammar role (language-independent proof): a synthetic
    # query with a made-up connective still splits at the qualifier
    dz = b.build("top 5 features XYZQNOISE top 3 modules").as_dict()
    def _qs(n):
        c = 1 if any(q["canonical"] in ("TOP","BOTTOM") for q in n["qualifiers"]) else 0
        for ch in n["children"]: c += _qs(ch)
        return c
    check("qualifier-driven segmentation works with an unknown connective", _qs(dz["tree"]) == 2)

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
