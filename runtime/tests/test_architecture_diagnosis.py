"""Architecture Diagnosis regression.

Locks: the diagnosis layer produces a layer-by-layer validation + health score, is LAZY (built on
first use), reuses existing owners (no new tokenizer/planner/runtime), renders nothing, and applies
the correct blame rules — Grammar is NOT blamed for words that never reached it; correct refusal is
NOT_APPLICABLE/NOT_REACHED, not FAIL; hierarchical flattening is detected as a Planner FAIL.

Run: python tests/test_architecture_diagnosis.py -> nonzero exit on any failure.
"""
import os, sys

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

    # ---- lazy: not built until first diagnose() ----
    check("diagnosis owner is lazy (None until used)", a._diagnosis is None)
    dg = a.diagnose("CA50 analyse karo")
    check("diagnosis owner built on first use", a._diagnosis is not None)

    # ---- shape: stages + health ----
    check("returns stages + health", "stages" in dg and "health" in dg)
    names = [s["stage"] for s in dg["stages"]]
    check("all pipeline layers present",
          names == ["Tokenizer", "Vocabulary", "Grammar", "Canonical Intent", "Planner", "Runtime"])
    check("every stage has owner + status + root_cause key",
          all(set(["stage", "owner", "status", "expected", "actual", "root_cause", "evidence"]) <= set(s) for s in dg["stages"]))

    # ---- health is an architecture score (0-100) with a band ----
    h = dg["health"]
    check("health score in 0..100", h["score"] is None or (0 <= h["score"] <= 100))
    check("health band is green/yellow/red/n/a", h["band"] in ("green", "yellow", "red", "n/a"))

    # ---- blame rule: 'analyse' unknown -> Vocabulary flags it; Grammar not FAILED for missing input ----
    vocab = next(s for s in dg["stages"] if s["stage"] == "Vocabulary")
    gram = next(s for s in dg["stages"] if s["stage"] == "Grammar")
    check("Vocabulary owns the missing-alias root cause",
          vocab["status"] in ("PARTIAL", "FAIL") and "alias" in (vocab["root_cause"] or ""))
    check("Grammar is NOT marked FAIL for words it never received", gram["status"] != "FAIL")

    # ---- hierarchy now PRESERVED via the planner's execution tree (Priority 3) ----
    dg2 = a.diagnose("top 5 features aur top 3 modules")
    planner = next(s for s in dg2["stages"] if s["stage"] == "Planner")
    check("Planner PASS: hierarchy preserved in execution tree (2 ranking scopes)",
          planner["status"] == "PASS" and planner["evidence"].get("ranking_scopes_in_tree") == 2)
    check("Planner owner is AlgorithmDerivation", planner["owner"] == "AlgorithmDerivation")

    # ---- a clean executable query scores high and reaches Runtime ----
    dg3 = a.diagnose("CA50 ko affect karne wale top 5 variables batao")
    rt = next(s for s in dg3["stages"] if s["stage"] == "Runtime")
    check("executable query reaches Runtime with PASS", rt["status"] == "PASS")
    check("executable query health is green", dg3["health"]["band"] == "green")

    # ---- diagnosis renders nothing (returns data only) ----
    check("diagnosis returns a dict, no HTML", isinstance(dg, dict) and "html" not in dg)

    passed = sum(RESULTS)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
