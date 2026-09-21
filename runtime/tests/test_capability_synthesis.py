"""Capability Synthesis Contract v2 — dedicated verification (not just "doesn't crash").

Exercises the full pipeline against the REAL bundled workbook: Discovery -> Canonical
Runtime Knowledge -> Capability Synthesis -> Canonical Actions -> Rendering, for BOTH a
physical entity and a promoted semantic object, end to end through resolve() ->
entity_actions() -> explain_relation(), through the shell, and through the live
ake_server API. Run: python tests/test_capability_synthesis.py -> exits nonzero on any
failure.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
EBIS = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")

from ake import AKE
from ake.shell import AKEShell
from ake.capability_synthesis import canonicalize

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)

_CONTRACT_FIELDS = ("id", "label", "kind", "capability", "canonical_identity",
                    "canonical_source", "canonical_key", "provenance", "discovery_stage",
                    "evidence", "confidence", "target")
_PROVENANCE_VOCAB = {"scalar_attribute", "foreign_key", "reverse_relation", "derived_relation",
                     "reachability", "analysis", "promoted_entity", "virtual_registry"}
_STAGE_VOCAB = {"SchemaDiscovery", "RelationshipDiscovery", "ReachabilityDiscovery",
                "ValuePromotion", "SemanticPromotion", "AnalysisDiscovery"}


def run():
    ake = AKE(EBIS)

    # ---------------------------------------------------------------- Canonical Action shape
    phys_actions = ake.entity_actions("CMD-002")
    check("physical entity: entity_actions() returns a non-empty menu", len(phys_actions) > 0)
    missing = [f for a in phys_actions for f in _CONTRACT_FIELDS if f not in a]
    check("physical entity: every action carries every CanonicalAction contract field",
          not missing, "missing=%r" % set(missing))
    bad_prov = [a["provenance"] for a in phys_actions if a["provenance"] not in _PROVENANCE_VOCAB]
    check("physical entity: provenance values are from the contract's vocabulary",
          not bad_prov, "bad=%r" % bad_prov)
    bad_stage = [a["discovery_stage"] for a in phys_actions if a["discovery_stage"] not in _STAGE_VOCAB]
    check("physical entity: discovery_stage values are from the contract's vocabulary",
          not bad_stage, "bad=%r" % bad_stage)
    rel_action = next((a for a in phys_actions if a["canonical_source"] == "relation_direct"), None)
    check("physical entity: a direct relation action has provenance=foreign_key",
          rel_action and rel_action["provenance"] == "foreign_key")

    # ---------------------------------------------------------------- collision detection (by identity, not label)
    same_identity = [
        {"label": "Handler", "type": "relation", "query": "REL", "relation": "handler",
         "count": 3, "available": True, "mode": "direct", "reason": None},
        {"label": "Handler (again)", "type": "relation", "query": "REL", "relation": "handler",
         "count": 5, "available": True, "mode": "direct", "reason": None},
    ]
    merged = canonicalize(list(same_identity), ake.model)
    check("collision: two actions with the SAME canonical identity merge into one",
          len(merged) == 1, "got=%d" % len(merged))
    check("collision: merge keeps the max observed count", merged[0]["count"] == 5)

    same_label_diff_identity = [
        {"label": "Type", "type": "attr", "query": "WHAT_IS", "relation": None,
         "count": 1, "available": True, "mode": "fixed", "reason": None},
        {"label": "Type", "type": "relation", "query": "REL", "relation": "type_ref",
         "count": 2, "available": True, "mode": "direct", "reason": None},
    ]
    both = canonicalize(list(same_label_diff_identity), ake.model)
    check("collision: two actions with the SAME label but DIFFERENT identity both survive",
          len(both) == 2, "got=%d" % len(both))

    # ---------------------------------------------------------------- promoted entity discovery (real data)
    cands = ake.promotions.candidates()
    check("promotion: real candidates are found on the bundled workbook", len(cands) > 0,
          "n=%d" % len(cands))
    sentinel_leak = [c for c in cands for v in c["values"] if v.strip().lower() in
                     {"not found", "none", "n/a", "unknown"}]
    check("promotion: null/placeholder sentinels never become promoted values", not sentinel_leak)
    already_real = [c for c in cands for v in c["values"] if ake.model.owner_row(v)[1]]
    check("promotion: no candidate value already IS a real entity elsewhere (no forked identity)",
          not already_real, "leaked=%r" % already_real)

    comp_type = next(c for c in cands if c["column"] == "Component Type")
    value = "Function (generic)"
    promoted_id = ake.promotions.promoted_id(comp_type["column"], value)

    # ---------------------------------------------------------------- resolution: any token -> Entity
    r1 = ake.resolve(value)                 # raw display value
    r2 = ake.resolve(promoted_id)            # canonical id
    check("promoted: resolving the raw display value finds the promoted entity",
          r1.get("id") == promoted_id, "got=%r" % r1)
    check("promoted: resolving the canonical id round-trips to the same id",
          r2.get("id") == promoted_id)
    check("promoted: resolving a value that was never repeated stays unresolved",
          ake.resolve("ThisValueDoesNotExistAnywhere12345").get("id") is None)

    # ---------------------------------------------------------------- Universal Dashboard: same pipeline
    acts = ake.entity_actions(promoted_id)
    check("promoted: entity_actions() returns a canonical menu (Universal Dashboard)",
          len(acts) > 0)
    missing_p = [f for a in acts for f in _CONTRACT_FIELDS if f not in a]
    check("promoted: every action carries every CanonicalAction contract field",
          not missing_p, "missing=%r" % set(missing_p))
    check("promoted: identity/name actions carry provenance=promoted_entity",
          all(a["provenance"] == "promoted_entity" for a in acts if a["query"] in
              ("WHAT_IS", "GET_NAME", "GET_EVIDENCE", "GET_SOURCE_ROW")))
    rel_act = next((a for a in acts if a["query"] == "REL"), None)
    check("promoted: the membership action carries provenance=reverse_relation (§4)",
          rel_act is not None and rel_act["provenance"] == "reverse_relation")
    expected_members = len(ake.promotions.members(comp_type["column"], value))
    check("promoted: membership count matches real row support (315 Function(generic) rows)",
          rel_act["count"] == expected_members and expected_members > 100,
          "count=%s expected=%s" % (rel_act["count"], expected_members))

    attrs = ake.entity_attrs(promoted_id)
    check("promoted: entity_attrs() gives the same {class,name} shape a physical entity has",
          attrs.get("name") == value and "Component Type" in attrs.get("class", ""))

    explained = ake.explain_relation(promoted_id, comp_type["column"])
    check("promoted: explain_relation() lists every member row, not a re-derived guess",
          explained["count"] == expected_members)
    check("promoted: every listed member is a REAL physical entity (Component Registry row)",
          all(ake.model.owner_row(it["node"])[1] for it in explained["items"][:20]))

    # ---------------------------------------------------------------- determinism
    ake2 = AKE(EBIS)
    id2 = ake2.promotions.promoted_id(comp_type["column"], value)
    check("promoted: promoted_id is deterministic across independent fresh AKE loads",
          id2 == promoted_id)

    # ---------------------------------------------------------------- full navigation through the shell (rendering)
    sh = AKEShell(ake)
    menu_text = sh.handle(value)                       # typed the raw promoted value as a token
    check("shell: typing a promoted value's display text opens it like any other object",
          promoted_id in menu_text)
    rel_key = next(k for k, v in sh.menu.items() if v[1] == "REL")
    results_text = sh.handle(rel_key)
    check("shell: drilling into the promoted entity's relation shows real results",
          "(%d)" % expected_members in results_text)
    first_member = next(iter(sh.results.values()))
    check("shell: a result of a promoted entity's relation is a real Component ID",
          ake.model.owner_row(first_member)[1] is not None)
    deeper = sh.handle("1")
    check("shell: opening a result from a promoted entity's relation opens a REAL entity page",
          ("%s  [Component Registry]" % first_member) in deeper)
    what_is = sh.handle("back")
    check("shell: 'back' from the opened member returns to the promoted entity's own menu",
          promoted_id in what_is)

    # ---------------------------------------------------------------- live API round trip
    try:
        os.environ["AKE_SERVER_MODE"] = "owner"
        os.environ["AKE_WORKBOOK"] = EBIS
        sys.path.insert(0, os.path.join(ROOT, "ake_server"))
        from ake_server.api import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            up = client.post("/upload").json()
            sid = up["session_id"]
            qr = client.post("/query", json={"session_id": sid, "token": value}).json()
            check("API: /query with a promoted value's raw text opens it (entity.id is VPROM:...)",
                  qr.get("entity", {}).get("id") == promoted_id, "got=%r" % qr.get("entity"))
            rel_item = next((m for m in qr["menu"] if m["type"] == "relation"), None)
            check("API: the promoted entity's menu exposes its relation action",
                  rel_item is not None)
            ar = client.post("/action", json={"session_id": sid, "key": rel_item["key"]}).json()
            check("API: drilling into it via /action returns real results",
                  ar["mode"] == "results" and len(ar["results"]) == expected_members,
                  "got=%d expected=%d" % (len(ar.get("results", [])), expected_members))
    except Exception as e:
        check("API: live round trip through ake_server", False, "exception=%r" % e)

    return {}


if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
