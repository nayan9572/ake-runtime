"""Semantic perspective engine regression — Phase-2 multi-hop capabilities.

Locks: multi-hop transitive traversal (not one hop), hop/class layering, directed
intersection where out != in and origin matters, and a derived (non-hardcoded) result table
whose columns follow the data. Everything runs on the already-derived graph — this test also
asserts no per-query workbook re-read (the engine only touches model.universal_graph).

Run: python tests/test_semantic_perspective.py  -> nonzero exit on any failure.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ake import AKE
from AKE_MASTER import locate_workbook

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def run():
    a = AKE(locate_workbook(None))
    g = a.model.universal_graph

    # pick a well-connected entity deterministically: the one with the most neighbours
    origin = max(g.node_attrs, key=lambda n: len(g.neighbors(n)))

    # ---- 1. multi-hop (strictly more than one hop) ----
    p = a.perspective(origin, direction="both", max_hops=6)
    check("perspective returns an origin + reached set", p and p["reached_count"] > 0)
    hops_seen = set(p["layers"].keys())
    check("traversal is multi-hop (reaches beyond hop 1)", any(h > 1 for h in hops_seen),
          "hops=%s" % sorted(hops_seen))
    # a 1-hop-only view would equal len(neighbors); multi-hop must exceed it on a connected graph
    check("reached_count exceeds immediate neighbour count (transitive, not one hop)",
          p["reached_count"] > len(g.neighbors(origin)),
          "%d > %d" % (p["reached_count"], len(g.neighbors(origin))))
    check("entities are grouped into class bands", len(p["bands"]) >= 1)
    # every reached entity has a relation path back to origin (evidence trail)
    all_have_path = all(info["relation_path"] for band in p["bands"].values() for info in band)
    check("every reached entity has a relation path (evidence trail)", all_have_path)

    # ---- 2. direction changes the result ----
    out_p = a.perspective(origin, direction="out", max_hops=6)
    in_p = a.perspective(origin, direction="in", max_hops=6)
    check("out and in perspectives differ (direction is meaningful)",
          out_p["reached_count"] != in_p["reached_count"] or
          set(out_p["bands"]) != set(in_p["bands"]),
          "out=%d in=%d" % (out_p["reached_count"], in_p["reached_count"]))

    # ---- 3. directed intersection: origin matters, out != in ----
    # choose two distinct connected entities
    conn = sorted(g.node_attrs, key=lambda n: -len(g.neighbors(n)))[:6]
    A, B = conn[0], conn[1]
    io = a.intersect(A, B, direction="out", max_hops=6)
    ii = a.intersect(A, B, direction="in", max_hops=6)
    check("intersection returns a shared set", io is not None and "shared" in io)
    check("intersection out vs in are different questions",
          io["shared_count"] != ii["shared_count"] or
          {s["id"] for s in io["shared"]} != {s["id"] for s in ii["shared"]},
          "out_shared=%d in_shared=%d" % (io["shared_count"], ii["shared_count"]))
    # A->B and B->A path attribution differ in direction (engineering meaning)
    ab = a.intersect(A, B, direction="out", max_hops=8)
    ba = a.intersect(B, A, direction="out", max_hops=8)
    check("intersect(A,B) and intersect(B,A) attribute paths to different origins",
          ab["a"]["id"] == ba["b"]["id"] and ab["b"]["id"] == ba["a"]["id"])
    # each shared entity records BOTH a path from A and a path from B
    if io["shared"]:
        s0 = io["shared"][0]
        check("shared entity carries a path from each side",
              "from_a" in s0 and "from_b" in s0 and "combined_distance" in s0)

    # ---- 4. derived table: columns follow the data, not hardcoded ----
    t = a.derive_table(p)
    check("table always has Entity + Strength", "Entity" in t["columns"] and "Strength" in t["columns"])
    check("Owner column present iff class info exists",
          ("Owner" in t["columns"]) == any(i.get("class") for band in p["bands"].values() for i in band))
    check("Evidence column present iff evidence exists",
          ("Evidence" in t["columns"]) == any(i.get("has_evidence") for band in p["bands"].values() for i in band))
    check("rows sorted strongest first",
          all(t["rows"][i]["Strength"] >= t["rows"][i+1]["Strength"] for i in range(len(t["rows"])-1)))
    check("strength is normalised 0..1", all(0.0 <= r["Strength"] <= 1.0 for r in t["rows"]))
    # intersection table too
    ti = a.derive_table(io)
    check("intersection derives a table with a Relationship column",
          "Entity" in ti["columns"] and (not io["shared"] or "Relationship" in ti["columns"]))
    check("table records what it was derived from",
          t.get("derived_from") == "perspective" and ti.get("derived_from") == "intersection")

    # ---- 5. graph-only (no per-query workbook read) ----
    # the engine holds only the model; assert it exposes no file path use by checking it
    # answers after we blank the workbook path attribute (simulating the file being gone).
    saved = getattr(a.model, "path", None)
    try:
        if hasattr(a.model, "path"):
            a.model.path = "/nonexistent/gone.xlsx"
        p2 = a.perspective(origin, direction="both", max_hops=3)
        check("queries still answer with workbook path gone (pure in-memory)", p2 and p2["reached_count"] > 0)
    finally:
        if saved is not None:
            a.model.path = saved

    # ---- 6. permanent guard: no domain vocabulary hardcoded in the engine's CODE ----
    # Strip comments + string literals from the engine source; assert no entity/registry name
    # survives in executable tokens. This locks the "names are discovered, never embedded"
    # property against future edits.
    import io as _io, tokenize as _tok, re as _re
    eng_src = open(os.path.join(ROOT, "ake", "semantic_perspective.py")).read()
    code_tokens = []
    for t in _tok.generate_tokens(_io.StringIO(eng_src).readline):
        if t.type in (_tok.COMMENT, _tok.STRING):
            continue
        code_tokens.append(t.string)
    code_only = " ".join(code_tokens).lower()
    banned = ["ca50", "ca10", "fuel", "handler", "command", "module", "feature",
              "variable", "registry", "combustion", "thermo", "spray", "observer",
              "difc", "theta", "wiebe", "knock", "octane", "ethanol",
              "mod-", "cmd-", "feat-", "var-", "hnd-", "comp-"]
    leaked = [w for w in banned if w in code_only]
    check("engine code contains NO hardcoded domain/registry literals", not leaked,
          ("leaked: %s" % leaked) if leaked else "clean")
    # also assert no string constant looks like an entity id or a registry name
    import ast as _ast
    idlike = [n.value for n in _ast.walk(_ast.parse(eng_src))
              if isinstance(n, _ast.Constant) and isinstance(n.value, str)
              and (_re.search(r"[A-Z]{2,}-\d", n.value) or _re.search(r"\bRegistry\b", n.value))]
    check("no entity-id / registry-name string constants in engine", not idlike,
          ("found: %s" % idlike) if idlike else "clean")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
