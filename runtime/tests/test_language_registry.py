"""Universal Language Registry regression (Stage 3).

Locks the constitution's Stage-3 rules: the registry owns language concepts only, is
workbook-independent (never resolves entities), has a stable grammar (fixed TYPE + canonical
set) with evolvable + auditable aliases, and every concept's declared opcodes exist in
RuntimePrimitives.

Run: python tests/test_language_registry.py  -> nonzero exit on any failure.
"""
import os, sys, inspect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake.language_registry import UniversalLanguageRegistry, TYPES
from ake.runtime_primitives import RuntimePrimitives

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    r = UniversalLanguageRegistry()

    # ---- 1. concepts resolve, with type + opcodes ----
    for w, canon in [("show", "SHOW"), ("count", "COUNT"), ("top", "TOP"), ("most", "TOP"),
                     ("after", "AFTER"), ("compare", "COMPARE"), ("trace", "TRACE"),
                     ("average", "AVERAGE"), ("unique", "UNIQUE")]:
        c = r.lookup(w)
        check("'%s' -> %s" % (w, canon), c is not None and c.canonical == canon)

    # ---- 2. workbook-independence: entity-ish words MUST NOT resolve here ----
    for w in ["VAR-005", "fuel", "brand", "order", "customer", "ca50", "MOD-001", "handler_name"]:
        check("entity-ish '%s' is NOT a concept (resolver owns it)" % w, not r.is_concept(w))

    # ---- 3. grammar stable: fixed TYPE set; every concept has a valid type ----
    check("TYPE set is the 7 stable grammar types", len(TYPES) == 7)
    all_typed = all(c["type"] in TYPES for c in r.concepts())
    check("every concept has a grammar type", all_typed)

    # ---- 4. BOUNDARY: concepts carry NO execution knowledge (opcodes belong to the planner) ----
    no_exec = all(set(cc.keys()) <= {"canonical", "type"} for cc in r.concepts())
    check("concepts store only canonical+type (no opcodes/kwargs/plan)", no_exec)

    # ---- 5. vocabulary evolves but grammar does not ----
    before = len(r.concepts())
    ok = r.register_alias("purchased", "COUNT", "unit_test")
    check("alias can be registered to an existing concept", ok and r.lookup("purchased").canonical == "COUNT")
    check("registering an alias does NOT create a new canonical concept", len(r.concepts()) == before)
    check("cannot register alias to a non-existent canonical", r.register_alias("z", "NOPE", "s") is False)
    check("alias registration requires a source", r.register_alias("q", "COUNT", "") is False)

    # ---- 6. auditable: every alias has a provenance source ----
    aud = r.audit()
    check("audit lists every alias with a source", all(a.get("source") for a in aud))
    check("core aliases carry source 'core'", any(a["source"] == "core" for a in aud))
    check("learned alias carries its provenance", any(a["source"] == "unit_test" for a in aud))

    # ---- 7. no domain literals in the registry code (workbook-independent by construction) ----
    src = open(os.path.join(ROOT, "ake", "language_registry.py")).read()
    import io, tokenize, re
    toks = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)]
    code = " ".join(toks).lower()
    banned = ["fuel", "ca50", "brand", "customer", "handler", "module", "registry",
              "mod-", "var-", "cmd-"]
    leaked = [w for w in banned if re.search(r"\b" + re.escape(w) + r"\b", code)]
    check("no workbook/domain literals in registry code", not leaked, str(leaked))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)


def run_refactor_checks():
    """Refactor checks: concept/vocabulary separation, versioned grammar, explainability."""
    from ake.language_registry import UniversalLanguageRegistry, GRAMMAR_VERSION
    from ake.vocabulary_registry import VocabularyRegistry
    R = []
    def c(name, cond, detail=""):
        R.append(bool(cond)); print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    r = UniversalLanguageRegistry()
    c("Concept objects carry no alias field", all("aliases" not in cc for cc in r.concepts()))
    c("vocabulary owns aliases (>= concepts)", len(r.vocab.entries(status=None)) >= len(r.concepts()))
    c("grammar is versioned", isinstance(GRAMMAR_VERSION, int) and r.version == GRAMMAR_VERSION)
    c("lookup still resolves concepts", r.lookup("show").canonical == "SHOW")
    c("register_alias works via delegation", r.register_alias("acquire", "COUNT", source="t") and r.lookup("acquire").canonical == "COUNT")
    v = VocabularyRegistry()
    v.add("rev", "total_amount", "ATTRIBUTE", source="Workbook Vocabulary", evidence="total_amount", confidence=0.94, matched_signals=3, total_signals=3)
    c("vocab entry carries confidence+source+version+status+signals",
      all(k in v.entries()[0] for k in ("confidence", "source", "version", "status", "signals")))
    c("deprecate removes from active resolution", v.deprecate("rev") and v.resolve("rev") is None)
    c("deprecated entry stays in history (append-only)", any(h["status"] == "deprecated" for h in v.history("rev")))
    # ambiguity: multiple candidates
    va = VocabularyRegistry()
    va.add("order","Orders","ATTRIBUTE",source="wb",confidence=0.92)
    va.add("order","OrderStatus","ATTRIBUTE",source="wb",confidence=0.81)
    c("ambiguity: word holds multiple candidates", len(va.candidates("order")) == 2)
    c("ambiguity: best candidate first", va.candidates("order")[0].canonical == "Orders")
    c("explain lists alternatives", len(va.explain("order")["alternatives"]) == 1)
    # BOUNDARY: concept is semantics-only; planning knowledge must NOT be here
    c("TOP concept has no opcodes attribute", not hasattr(r.concept("TOP"), "opcodes"))
    c("concept as_dict exposes only canonical+type", set(r.concept("TOP").as_dict().keys()) == {"canonical", "type"})
    v2 = VocabularyRegistry()
    v2.add("revenue", "total_amount", "ATTRIBUTE", source="Workbook Vocabulary", evidence="total_amount", confidence=0.94, reason="alias match", matched_signals=3, total_signals=3)
    ex = v2.explain("revenue")
    c("explain: type ATTRIBUTE", ex["type"] == "ATTRIBUTE")
    c("explain: candidate total_amount", ex["candidate"] == "total_amount")
    c("explain: confidence 0.94", ex["confidence"] == 0.94)
    c("explain: source Workbook Vocabulary", ex["source"] == "Workbook Vocabulary")
    c("explain: reason alias match", ex["reason"] == "alias match")
    c("explain: signals present", ex["signals"] == "3/3")
    c("explain: unknown never throws", v2.explain("zzz")["match"] is False)
    ok = sum(R)
    print("\nrefactor: %d/%d checks passed" % (ok, len(R)))
    return ok == len(R)


if __name__ == "__main__":
    a = run()
    b = run_refactor_checks()
    sys.exit(0 if (a and b) else 1)
