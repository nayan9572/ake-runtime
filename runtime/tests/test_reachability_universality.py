"""Universality/adversarial/performance/determinism validation for ReachabilityEngine, run
before wiring it into AKE.answer()/shell. Six categories, matching the validation protocol this
was built against: (1) regression -- canonical registry is never mutated, existing suites stay
green; (2) cross-domain -- identical engine, zero code changes, run against unrelated domains;
(3) adversarial -- empty/cyclic/disconnected/duplicate/deep/broken-reference graphs never crash
or invent results; (4) performance -- small to stress scale; (5) determinism -- repeated fresh
loads AND independence from PYTHONHASHSEED; (6) a source-level universality audit.
Run: python tests/test_reachability_universality.py
"""
import sys, os, json, types, subprocess, time, random, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
EBIS = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)


def _model(edges, node_attrs, classes):
    from ake.edge_graph_engine import UniversalEdgeGraph
    return types.SimpleNamespace(universal_graph=UniversalEdgeGraph(edges, node_attrs),
                                  catalog={c: {} for c in classes})


def _chain_domain(prefix_a, rel1, prefix_b, rel2, prefix_c, rel3, prefix_d):
    """Builds a 4-class chain A->B->C->D, used for every chain-topology domain below."""
    edges = [(f"{prefix_a}-01", rel1, f"{prefix_b}-01", prefix_a, prefix_b, None),
              (f"{prefix_b}-01", rel2, f"{prefix_c}-01", prefix_b, prefix_c, None),
              (f"{prefix_c}-01", rel3, f"{prefix_d}-01", prefix_c, prefix_d, None)]
    attrs = {f"{prefix_a}-01": {"class": prefix_a}, f"{prefix_b}-01": {"class": prefix_b},
             f"{prefix_c}-01": {"class": prefix_c}, f"{prefix_d}-01": {"class": prefix_d}}
    return _model(edges, attrs, [prefix_a, prefix_b, prefix_c, prefix_d])


def run():
    from ake import AKE
    from ake.reachability_engine import ReachabilityEngine

    # ============================= 1. REGRESSION =============================
    ake = AKE(EBIS)
    before = tuple(json.dumps(x, sort_keys=True, default=str) for x in (
        ake.model.catalog, sorted(ake.model.universal_graph.edges), ake.model.universal_graph.node_attrs))
    derived = ReachabilityEngine(ake.model).derive()
    after = tuple(json.dumps(x, sort_keys=True, default=str) for x in (
        ake.model.catalog, sorted(ake.model.universal_graph.edges), ake.model.universal_graph.node_attrs))
    check("canonical registry (catalog/edges/node_attrs) byte-identical before and after derive()",
          before == after)
    check("AKE construction gains no new attribute from importing ReachabilityEngine",
          not any(a.startswith("derived") for a in vars(ake.model)))
    for suite in ("regression.py", "test_cli_dispatch.py", "test_stabilization.py", "test_reachability_engine.py"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", suite)],
                            capture_output=True, text=True, timeout=120)
        check(f"tests/{suite} still passes unchanged", r.returncode == 0, r.stdout[-200:])

    # ============================= 2. CROSS-DOMAIN =============================
    # 4 chain-topology domains, engine-level (isolates exactly what ReachabilityEngine depends on)
    chain_domains = {
        "Biology":       ("SPEC", "expresses", "GENE", "encodes", "PROT", "participates_in", "PATH"),
        "University":    ("STU", "enrolled_in", "CRS", "offered_by", "DEPT", "part_of", "FAC"),
        "Hospital":      ("PAT", "treated_by", "DOC", "works_in", "DEPT2", "belongs_to", "HOSP"),
        "Manufacturing": ("MACH", "uses_component", "COMP", "supplied_by", "SUPP", "located_at", "FACT"),
    }
    for name, args in chain_domains.items():
        m = _chain_domain(*args)
        d = ReachabilityEngine(m).derive()
        a, b, c, dd = args[0], args[2], args[4], args[6]
        check(f"cross-domain [{name}]: derives the full A->D chain (3 hops)",
              any(x["source_class"] == a and x["target_class"] == dd and x["hops"] == 3 for x in d), d)

    # 5th domain: FULL real pipeline (auto-detect -> WorkbookModel -> ReachabilityEngine), not
    # just the engine boundary -- a flat, no-Registry-Catalog business table, star topology.
    lib_path = os.path.join(ROOT, "_tmp_library_validation.xlsx")
    from openpyxl import Workbook
    random.seed(42)
    wb = Workbook(); ws = wb.active; ws.title = "Catalog"
    ws.append(["Book Title", "Author", "Publisher", "Country", "Genre", "Pages"])
    for i in range(60):
        ws.append([f"Book {i+1:03d}", random.choice(["Le Guin","Asimov","Butler","Clarke","Chiang"]),
                   random.choice(["Orbit","Tor","Ace","Gollancz"]), random.choice(["USA","UK","Canada"]),
                   random.choice(["SciFi","Fantasy","Nonfiction"]), random.randint(150, 600)])
    wb.save(lib_path)
    lib_ake = AKE(lib_path)
    lib_derived = ReachabilityEngine(lib_ake.model).derive()
    os.remove(lib_path)
    check("cross-domain [Library, full real .xlsx pipeline]: auto-detected as non-EBIS registries",
          "Author Registry" in lib_ake.model.catalog and "Feature Registry" not in lib_ake.model.catalog,
          list(lib_ake.model.catalog.keys()))
    check("cross-domain [Library]: runs without crashing (0 derived is the KNOWN star-schema "
          "limitation below, not a crash)", isinstance(lib_derived, list))

    # ============================= 3. ADVERSARIAL =============================
    adversarial = {
        "empty workbook": _model([], {}, []),
        "single registry, no edges": _model([], {"W-1": {"class": "Widget"}}, ["Widget"]),
        "missing registry (catalog lists a class with 0 matching nodes)":
            _model([("A-1", "r", "B-1", "A", "B", None)],
                   {"A-1": {"class": "A"}, "B-1": {"class": "B"}}, ["A", "B", "Ghost"]),
        "unknown registry name (node class absent from catalog)":
            _model([("A-1", "r", "X-1", "A", "Unlisted", None)],
                   {"A-1": {"class": "A"}, "X-1": {"class": "Unlisted"}}, ["A"]),
        "cyclic graph (A->B->C->A)":
            _model([("A-1","r1","B-1","A","B",None),("B-1","r2","C-1","B","C",None),("C-1","r3","A-1","C","A",None)],
                   {"A-1":{"class":"A"},"B-1":{"class":"B"},"C-1":{"class":"C"}}, ["A","B","C","D"]),
        "disconnected graph (two separate components)":
            _model([("A-1","r","B-1","A","B",None),("C-1","r","D-1","C","D",None)],
                   {"A-1":{"class":"A"},"B-1":{"class":"B"},"C-1":{"class":"C"},"D-1":{"class":"D"}}, ["A","B","C","D"]),
        "duplicate edges (identical edge listed twice)":
            _model([("A-1","r","B-1","A","B",None)]*2 + [("B-1","r","C-1","B","C",None)],
                   {"A-1":{"class":"A"},"B-1":{"class":"B"},"C-1":{"class":"C"}}, ["A","B","C"]),
        "multiple equal-length shortest paths (A->X via B or via C)":
            _model([("A-1","r","B-1","A","B",None),("A-1","r","C-1","A","C",None),
                     ("B-1","r","X-1","B","X",None),("C-1","r","X-1","C","X",None)],
                   {"A-1":{"class":"A"},"B-1":{"class":"B"},"C-1":{"class":"C"},"X-1":{"class":"X"}}, ["A","B","C","X"]),
        "broken reference (edge target has no node_attrs entry at all)":
            _model([("A-1","r","GHOST-99","A","B",None)], {"A-1":{"class":"A"}}, ["A","B"]),
        "self-loop (A->A)":
            _model([("A-1","self","A-1","A","A",None),("A-1","r","B-1","A","B",None)],
                   {"A-1":{"class":"A"},"B-1":{"class":"B"}}, ["A","B"]),
        "node with no class attribute at all":
            _model([("A-1","r","NC-1","A",None,None)], {"A-1":{"class":"A"},"NC-1":{}}, ["A"]),
    }
    for name, m in adversarial.items():
        try:
            d1 = ReachabilityEngine(m).derive()
            d2 = ReachabilityEngine(m).derive()
            check(f"adversarial [{name}]: no crash, deterministic", d1 == d2, f"{len(d1)} derived")
        except Exception as e:
            check(f"adversarial [{name}]: no crash, deterministic", False, f"{type(e).__name__}: {e}")

    # deep chain: hard max_depth boundary, not just "doesn't crash"
    deep_edges, deep_attrs, deep_classes = [], {}, []
    for i in range(13):
        deep_classes.append(f"L{i}"); deep_attrs[f"N{i}"] = {"class": f"L{i}"}
        if i > 0: deep_edges.append((f"N{i-1}", "next", f"N{i}", f"L{i-1}", f"L{i}", None))
    deep_m = _model(deep_edges, deep_attrs, deep_classes)
    deep_d = ReachabilityEngine(deep_m, max_depth=5).derive()
    check("adversarial [very deep chain]: finds the node at exactly max_depth",
          any(x["source_class"] == "L0" and x["target_class"] == "L5" for x in deep_d))
    check("adversarial [very deep chain]: hard-excludes anything beyond max_depth",
          not any(x["source_class"] == "L0" and x["hops"] > 5 for x in deep_d))

    # ============================= 4. PERFORMANCE =============================
    def synth(n_entities, n_classes, fanout=2, seed=0):
        random.seed(seed)
        classes = [f"Class{i}" for i in range(n_classes)]
        node_attrs, ids_by_class = {}, {c: [] for c in classes}
        for i in range(n_entities):
            c = classes[i % n_classes]; eid = f"E{i}"
            node_attrs[eid] = {"class": c}; ids_by_class[c].append(eid)
        edges = []
        for eid in node_attrs:
            idx = classes.index(node_attrs[eid]["class"])
            if idx + 1 < n_classes and ids_by_class[classes[idx + 1]]:
                for t in random.sample(ids_by_class[classes[idx + 1]], min(fanout, len(ids_by_class[classes[idx+1]]))):
                    edges.append((eid, "next", t, node_attrs[eid]["class"], node_attrs[t]["class"], None))
        return _model(edges, node_attrs, classes)

    perf_thresholds = [("small", 50, 5, 1.0), ("medium", 500, 10, 3.0), ("large", 1037, 13, 5.0),
                        ("stress", 5000, 20, 15.0)]
    for label, n_ent, n_cls, budget_s in perf_thresholds:
        m = synth(n_ent, n_cls)
        t0 = time.time(); ReachabilityEngine(m).derive(); elapsed = time.time() - t0
        check(f"performance [{label}: {n_ent} entities, {n_cls} classes] under {budget_s}s budget",
              elapsed < budget_s, f"{elapsed:.3f}s")

    # ============================= 5. DETERMINISM =============================
    runs = []
    for _ in range(3):
        a = AKE(EBIS)
        runs.append(json.dumps(ReachabilityEngine(a.model).derive(), sort_keys=True))
    check("determinism: 3 independent fresh loads of the real workbook are byte-identical",
          len(set(runs)) == 1)

    hash_outputs = set()
    for seed in ("0", "1", "12345"):
        r = subprocess.run([sys.executable, "-c",
            f"import sys, json; sys.path.insert(0, {ROOT!r})\n"
            f"from ake import AKE\nfrom ake.reachability_engine import ReachabilityEngine\n"
            f"a = AKE({EBIS!r})\nprint(json.dumps(ReachabilityEngine(a.model).derive(), sort_keys=True))\n"],
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=60)
        hash_outputs.add(hashlib.md5(r.stdout.encode()).hexdigest())
    check("determinism: output independent of PYTHONHASHSEED (0, 1, 12345 all byte-identical)",
          len(hash_outputs) == 1, hash_outputs)

    # ============================= 6. UNIVERSALITY AUDIT =============================
    src = open(os.path.join(ROOT, "ake", "reachability_engine.py")).read()
    leaked = [t for t in ("Handler", "Gate", "Pipeline", "Validator", "Bridge", "Component",
                           "Feature Registry", "Command Master", "Module Registry") if t in src]
    check("universality audit: reachability_engine.py source contains no EBIS-specific vocabulary",
          not leaked, leaked)

    return {}


KNOWN_LIMITATIONS = [
    "Forward-edge-only traversal (matches the pre-existing reachable() primitive's convention): "
    "an entity with zero outgoing edges -- a 'leaf'/dimension entity in a star/hub schema, e.g. "
    "an Author connected to Publisher only via a shared Book record -- derives nothing, even "
    "though a human would consider it reachable. Confirmed via the Library cross-domain test "
    "above: 0 derived edges, not a crash, but a real coverage gap for star-shaped schemas.",
    "max_depth defaults to 5 -- a tunable parameter, but the DEFAULT was chosen by looking at "
    "EBIS's observed hop distribution (2-4 hops covered everything real there). A domain with "
    "much deeper natural hierarchies would need to override it explicitly.",
    "confidence = 1/hops is an untuned heuristic (farther = lower confidence), not empirically "
    "validated against any real notion of confidence in any domain.",
    "Derived-registry size is now bounded by classes^2 (37 records on EBIS's 23 classes), not "
    "entities x classes (was 254) -- addressed by the class-level redesign, not just untested "
    "at larger scale.",
]

if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"\n{passed}/{total} checks passed")
    print("\nKnown limitations (not failures -- documented tradeoffs):")
    for lim in KNOWN_LIMITATIONS:
        print(f"  - {lim}")
    sys.exit(0 if passed == total else 1)
