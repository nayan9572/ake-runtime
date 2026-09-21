"""Tests for ReachabilityEngine (ake/reachability_engine.py) and the shortest_path() primitive
it's built on (ake/edge_graph_engine.py). New capability, so kept separate from
tests/test_stabilization.py (which locks in bug fixes to existing behavior, not new features).
Covers the two-tier design: derive() (class-level, materialized) and path_for() (per-entity,
on-demand). Run: python tests/test_reachability_engine.py -> exits nonzero on any failure.
"""
import sys, os, json, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
EBIS = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)


def _biology_model():
    """A graph with zero vocabulary overlap with EBIS -- no Feature/Component/Module/Handler
    anywhere -- to prove the engine has no EBIS-specific assumption baked in, by construction."""
    from ake.edge_graph_engine import UniversalEdgeGraph
    edges = [
        ("SPEC-01", "expresses",       "GENE-01", "Species Registry", "Gene Registry",    None),
        ("GENE-01", "encodes",         "PROT-01", "Gene Registry",    "Protein Registry", None),
        ("PROT-01", "participates_in", "PATH-01", "Protein Registry", "Pathway Registry", None),
        ("GENE-02", "encodes",         "PROT-02", "Gene Registry",    "Protein Registry", None),
    ]
    node_attrs = {
        "SPEC-01": {"class": "Species Registry", "name": "Zebrafish"},
        "GENE-01": {"class": "Gene Registry",    "name": "shha"},
        "GENE-02": {"class": "Gene Registry",    "name": "pax6"},
        "PROT-01": {"class": "Protein Registry", "name": "Sonic hedgehog"},
        "PROT-02": {"class": "Protein Registry", "name": "Pax6"},
        "PATH-01": {"class": "Pathway Registry", "name": "Hedgehog signaling"},
    }
    catalog = {c: {} for c in ("Species Registry", "Gene Registry", "Protein Registry", "Pathway Registry")}
    return types.SimpleNamespace(universal_graph=UniversalEdgeGraph(edges, node_attrs), catalog=catalog)


def run():
    from ake import AKE
    from ake.reachability_engine import ReachabilityEngine

    # --- no hardcoded EBIS vocabulary anywhere in the engine's own source ---
    src = open(os.path.join(ROOT, "ake", "reachability_engine.py")).read()
    ebis_terms = ["Handler", "Gate", "Pipeline", "Validator", "Bridge", "Component", "Feature Registry",
                  "Command Master", "Module Registry"]
    leaked = [t for t in ebis_terms if t in src]
    check("reachability_engine.py contains no EBIS-specific vocabulary", not leaked, f"found: {leaked}")

    # --- derive() is class-level: one record per (source_class, target_class), not per entity ---
    bio_derived = ReachabilityEngine(_biology_model()).derive()
    check("derives correctly on a non-engineering (Biology) synthetic domain",
          any(d["source_class"] == "Species Registry" and d["target_class"] == "Pathway Registry"
              and d["hops"] == 3 for d in bio_derived), bio_derived)
    check("does not derive a class pair that's already fully direct (Gene -> Protein is direct)",
          not any(d["source_class"] == "Gene Registry" and d["target_class"] == "Protein Registry"
                  for d in bio_derived))
    check("every record carries real evidence (example path + confirm/sample counts)",
          all("example_path" in d and "confirmed_instances" in d and "sampled_instances" in d
              for d in bio_derived))

    # --- path_for(): on-demand per-entity resolution, gated behind the class-level registry ---
    eng = ReachabilityEngine(_biology_model())
    cl = eng.derive()
    hit = eng.path_for("SPEC-01", "Pathway Registry", class_level_registry=cl)
    check("path_for() resolves a real per-entity path when the class pair is known reachable",
          hit is not None and hit[0][0] == "SPEC-01" and hit[0][-1] == "PATH-01", hit)
    gated = eng.path_for("SPEC-01", "Nonexistent Registry", class_level_registry=cl)
    check("path_for() short-circuits (returns None, no search) for a class pair not in the registry",
          gated is None)

    # --- correctness + determinism on the real workbook ---
    runs = []
    for _ in range(2):
        a = AKE(EBIS)                      # fresh load each time -- no shared state across runs
        runs.append(json.dumps(ReachabilityEngine(a.model).derive(), sort_keys=True))
    check("derive() is byte-identical across independent fresh loads of the same workbook",
          runs[0] == runs[1])

    ake = AKE(EBIS)
    derived = ReachabilityEngine(ake.model).derive()
    n_classes = len(ake.model.catalog)
    check("class-level output is bounded by classes^2, not entities x classes",
          len(derived) <= n_classes * n_classes, f"{len(derived)} records, {n_classes} classes")
    check("every derived hop count is within max_depth", all(1 <= d["hops"] <= 5 for d in derived))
    check("no derived record targets the entity's own class",
          all(d["target_class"] != d["source_class"] for d in derived))
    check("confirmed_instances never exceeds sampled_instances",
          all(d["confirmed_instances"] <= d["sampled_instances"] for d in derived))

    # --- purely additive: existing graph/model surface is untouched ---
    check("UniversalEdgeGraph.reachable() (pre-existing) still works unchanged",
          len(ake.model.universal_graph.reachable("CMD-002", depth=2)) > 0)
    check("AKE construction does not eagerly run ReachabilityEngine (additive/opt-in only)",
          not hasattr(ake, "derived"))

    return {}


if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
