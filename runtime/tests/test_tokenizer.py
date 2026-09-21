"""Tokenizer regression (Stage 8).

Locks: the tokenizer is a DUMB lexical front-end. It splits raw text into ordered tokens,
preserves multi-word phrases that exist in the vocabulary (read-only), keeps offsets, and does
NOTHING else — no entity/attribute/relation resolution, no grammar classification, no intent, no
planning, no runtime. It never learns; it consumes the current vocabulary. Workbook-independent.

Run: python tests/test_tokenizer.py  -> nonzero exit on any failure.
"""
import os, sys, io, tokenize as _pytok, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook
from ake.tokenizer import Tokenizer, Token

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    tk = a.tokenizer

    # ---- single words: unchanged, in order, with offsets ----
    toks = tk.tokenize("Top 10 ca50 after 2023")
    check("single words split correctly", [t.norm for t in toks] == ["top", "10", "ca50", "after", "2023"])
    check("offsets preserved (start<end, ascending)",
          all(t.start < t.end for t in toks) and [t.start for t in toks] == sorted(t.start for t in toks))
    check("each token has text+norm+start+end", all(set(t.as_dict().keys()) == {"text", "norm", "start", "end"} for t in toks))

    # ---- multi-word phrase from the vocabulary preserved as ONE token ----
    mw = next((at["name"] for at in a.model.universal_graph.node_attrs.values()
               if at.get("name") and " " in str(at["name"])), None)
    if mw:
        q = "show %s count" % mw
        tt = tk.tokenize(q)
        check("known multi-word phrase kept as one token", any(t.norm == tk._norm(mw) for t in tt),
              "phrase=%r" % mw)
        # the phrase token spans the original text exactly
        pt = next(t for t in tt if t.norm == tk._norm(mw))
        check("phrase token offsets span the original phrase", q[pt.start:pt.end].lower() == mw.lower())

    # ---- unknown adjacent words are NOT merged (no phrase in vocabulary) ----
    tu = tk.tokenize("zza zzb zzc")
    check("unknown adjacent words stay separate", [t.norm for t in tu] == ["zza", "zzb", "zzc"])

    # ---- tokenizer never resolves / classifies: tokens are lexical only ----
    check("tokens carry no kind/type/canonical (no interpretation)",
          all(not hasattr(t, "kind") and not hasattr(t, "type") and not hasattr(t, "canonical") for t in toks))

    # ---- read-only: tokenizing does not add to the vocabulary (no learning) ----
    before = len(a.vocabulary.entries(status=None))
    tk.tokenize("some brand new phrase that is not in vocab")
    after = len(a.vocabulary.entries(status=None))
    check("tokenizing does not modify the vocabulary (no learning)", before == after)

    # ---- vocabulary-driven: a tokenizer with a fresh vocab preserves a newly-added phrase, no code change ----
    from ake.vocabulary_registry import VocabularyRegistry
    v = VocabularyRegistry()
    v.add("purchase order line", "SOME-ID", "ENTITY", source="Workbook Vocabulary", confidence=1.0)
    tk2 = Tokenizer(vocabulary=v)
    check("newly-added phrase preserved without tokenizer changes",
          any(t.norm == "purchase order line" for t in tk2.tokenize("show purchase order line count")))

    # ---- workbook-independence: no hardcoded names in tokenizer code ----
    src = open(os.path.join(ROOT, "ake", "tokenizer.py")).read()
    toks_code = [t.string for t in _pytok.generate_tokens(io.StringIO(src).readline)
                 if t.type not in (_pytok.COMMENT, _pytok.STRING)]
    code = " ".join(toks_code).lower()
    banned = ["customer", "brand", "revenue", "ca50", "fuel", "order items", "mod-", "var-",
              "resolve_entity", "classify", "derive_plan"]
    leaked = [w for w in banned if w in code]
    check("no hardcoded names or resolver/planner calls in tokenizer", not leaked, str(leaked))


    # ---- Obs 1: greedy longest-match picks the LONGEST nested phrase ----
    from ake.vocabulary_registry import VocabularyRegistry as _VR
    vg = _VR()
    for p in ["purchase", "purchase order", "purchase order line"]:
        vg.add(p, "ID", "ENTITY", source="Workbook Vocabulary", confidence=1.0)
    tkg = Tokenizer(vocabulary=vg)
    check("greedy longest-match: 'Purchase Order Line Status' -> [purchase order line, status]",
          [t.norm for t in tkg.tokenize("Purchase Order Line Status")] == ["purchase order line", "status"])

    # ---- Obs 2: tokenizer uses only the single phrase_exists() API (no registry internals) ----
    tsrc = open(os.path.join(ROOT, "ake", "tokenizer.py")).read()
    check("tokenizer calls phrase_exists (single API)", "phrase_exists" in tsrc)
    check("tokenizer does not call candidates()/resolve() (no internals)",
          ".candidates(" not in tsrc and ".resolve(" not in tsrc)
    check("phrase_exists returns a bool only (meaning-free)",
          type(a.vocabulary.phrase_exists("anything")) is bool)

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
