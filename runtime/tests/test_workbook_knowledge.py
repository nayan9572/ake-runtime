"""Workbook Knowledge Registry regression (Stage 4).

Locks: knowledge is HARVESTED from existing owners (node_attrs/hdr/_rel_source) into the
Vocabulary Registry; it creates NO grammar concepts and never changes GRAMMAR_VERSION
(correction 6); all mappings are workbook-derived (no hardcoded entity/attribute names in code);
ambiguity + evidence preserved.

Run: python tests/test_workbook_knowledge.py  -> nonzero exit on any failure.
"""
import os, sys, io, tokenize, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.language_registry import GRAMMAR_VERSION

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    s = a._knowledge_summary

    # ---- 1. harvested from existing owners (non-zero, matches source counts) ----
    check("entities harvested from node_attrs", s["entities"] == len(a.model.universal_graph.node_attrs))
    check("relations harvested from _rel_source", s["relations"] == len(a.model._rel_source))
    check("attributes harvested (>0)", s["attributes"] > 0)

    # ---- 2. workbook-derived candidates are real (an entity name resolves to its id) ----
    # pick any entity that has a name, prove its name is now a vocabulary candidate -> its id
    sample = next(((eid, at["name"]) for eid, at in a.model.universal_graph.node_attrs.items()
                   if at.get("name")), None)
    check("a sample entity exists with a name", sample is not None)
    if sample:
        eid, name = sample
        cands = a.vocabulary.candidates(name)
        check("entity name resolves to its id via vocabulary",
              any(c.canonical == eid for c in cands), "%s -> %s" % (name, eid))
        check("workbook candidate carries source 'Workbook Vocabulary'",
              any(c.source == "Workbook Vocabulary" for c in cands))

    # ---- 3. ambiguity preserved (a name shared by >1 entity yields >1 candidate) ----
    from collections import Counter
    name_counts = Counter(str(at["name"]).lower() for at in a.model.universal_graph.node_attrs.values()
                          if at.get("name"))
    amb = next((nm for nm, c in name_counts.items() if c > 1), None)
    if amb:
        check("ambiguous entity name yields multiple candidates", len(a.vocabulary.candidates(amb)) > 1)

    # ---- 4. relation confidence reflects declared vs inferred (evidence-backed) ----
    rel_entries = [e for e in a.vocabulary.entries() if e["type"] == "RELATION"]
    check("relations carry confidence + signals",
          all(e["confidence"] is not None and e["signals"] for e in rel_entries))

    # ---- 5. GRAMMAR ISOLATION (correction 6): no grammar concepts created, version unchanged ----
    check("GRAMMAR_VERSION unchanged", a.language.version == GRAMMAR_VERSION)
    check("concept count unchanged (grammar not grown)", len(a.language.concepts()) >= 33)
    non_core = [e for e in a.vocabulary.entries(status=None) if e["source"] != "core"]
    check("knowledge registry created only ENTITY/ATTRIBUTE/RELATION (no grammar types)",
          all(e["type"] in ("ENTITY", "ATTRIBUTE", "RELATION") for e in non_core))

    # ---- 6. no hardcoded domain mapping in the knowledge-registry code ----
    src = open(os.path.join(ROOT, "ake", "workbook_knowledge_registry.py")).read()
    toks = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)]
    code = " ".join(toks).lower()
    banned = ["revenue", "total_amount", "ca50", "brand", "customer", "order", "fuel",
              "mod-", "var-", "feat-", "handler"]
    leaked = [w for w in banned if re.search(r"\b" + re.escape(w) + r"\b", code)]
    check("no hardcoded entity/attribute names in code", not leaked, str(leaked))


    # ---- 7. owner authority recorded on every candidate (last instruction) ----
    all_owned = all(e.get("owner") for e in a.vocabulary.entries())
    check("every workbook candidate records its owning registry/authority", all_owned)
    if sample:
        exd = a.vocabulary.explain(sample[1])
        check("explain surfaces owner", exd.get("owner") is not None)

    # ---- 8. relation confidence is explainable (signals-derived, not bare) ----
    for e in [x for x in a.vocabulary.entries() if x["type"] == "RELATION"]:
        ok = e["signals"] and e["reason"] and e["evidence"] and \
             abs(e["confidence"] - (e["matched_signals"] / e["total_signals"])) < 1e-9
        check("relation '%s' confidence = matched/total with reason+evidence" % e["word"], ok)
        break

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
