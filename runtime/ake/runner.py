"""AKE runner (importable). Colab: from colab_run import run."""
import os, sys, glob, json, zipfile, tempfile
try:
    sys.stdout.reconfigure(line_buffering=True)  # non-tty stdout (piped, e.g. Colab subprocess)
    sys.stderr.reconfigure(line_buffering=True)  # defaults to full buffering; force line flush
except (AttributeError, ValueError):
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ake import AKE


def _find_workbook(source=None):
    if source and source.endswith(".xlsx") and os.path.exists(source): return source
    if source and source.endswith(".zip") and os.path.exists(source):
        d = tempfile.mkdtemp()
        with zipfile.ZipFile(source) as z: z.extractall(d)
        xs = glob.glob(os.path.join(d, "**", "*.xlsx"), recursive=True)
        if xs: return sorted(xs, key=lambda p: ("v" not in p, p))[0]
    here = os.path.dirname(os.path.abspath(__file__))
    for pat in ([source] if source else []) + [os.path.join(here, "*.xlsx"), "*.xlsx"]:
        if not pat: continue
        xs = [f for f in glob.glob(pat) if "~$" not in f]
        if xs: return xs[0]
    return None

def run(source=None, outdir="ake_out", debug=None):
    if debug is None:
        debug = os.environ.get("AKE_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")

    def trace(msg):
        if debug:
            print(f"[TRACE] {msg}", flush=True)

    trace("entering runner.run()")
    wb = _find_workbook(source)
    if not wb: raise SystemExit("No workbook found. Pass a .xlsx or a .zip containing one.")
    os.makedirs(outdir, exist_ok=True)
    ake = AKE(wb); m = ake.model; G = m.universal_graph
    closure = ake.closure(); derived = ake.derive_all()
    trace("workbook loaded")

    art = {
        "universal_edges.json": [{"source": s, "relation": r, "target": t, "src_class": sc, "tgt_class": tc, "evidence": ev}
                                 for s, r, t, sc, tc, ev in m.universal_edges],
        "ir_nodes.json": {k: {kk: (vv if kk != "metadata" else None) for kk, vv in v.items()} for k, v in G.node_attrs.items()},
        "cardinality.json": m.rpde_cardinality,
        "invariants.json": derived["invariants"], "rules.json": derived["rules"], "queries.json": derived["queries"],
        "feature_types.json": {k: v["detected_in"] for k, v in closure["features"].items()},
        "canonicalization_report.json": ake.model._rpde.canonicalization_report() if hasattr(ake.model, "_rpde") else {},
        "capability_universe.json": __import__("ake.capability_matrix", fromlist=["CapabilityMatrix"]).CapabilityMatrix(ake.model).workbook_universe(),
        "registry_universe.json": ake.registry_universe(),
        "classification.json": __import__("ake.classifier", fromlist=["WorkbookClassifier"]).WorkbookClassifier(ake.model).classify(),
    }
    for name, data in art.items():
        json.dump(data, open(os.path.join(outdir, name), "w"), indent=1, ensure_ascii=False)
    trace("artifacts generated")

    summary = {
        "workbook": os.path.basename(wb),
        "registries": len(m.catalog), "ir_nodes": len(G.node_attrs), "universal_edges": len(m.universal_edges),
        "feature_only_edges": len(m.edges), "relation_vocabulary": sorted(set(e[1] for e in m.universal_edges)),
        "invariants": len(derived["invariants"]), "rules": len(derived["rules"]), "queries": len(derived["queries"]),
        "closure_feature_types": len(closure["features"]), "closed": closure["closed"],
    }
    json.dump(summary, open(os.path.join(outdir, "summary.json"), "w"), indent=1)
    trace("summary written")
    if debug:
        # Full machine-readable dump — debug only. Production mode shows the same
        # numbers as human-readable metrics below instead; the JSON itself always
        # lives in summary.json regardless of mode.
        print("AKE compiled:", json.dumps(summary, indent=1))
        print(f"\nartifacts -> {outdir}/ :", ", ".join(art) + ", summary.json")
        sys.stdout.flush()

    # --- Output UX (Finding UX-1) ---
    # Everything below reads only what was just written above (the 7 files in `art`
    # plus summary.json) — no new module, no new layer, just the same run() finishing
    # its job by telling the user where the output actually is instead of leaving them
    # to search the Files panel.
    trace("output writer entered")
    outdir_abs = os.path.abspath(outdir)
    artifact_paths = sorted(os.path.join(outdir_abs, name) for name in list(art) + ["summary.json"])
    zip_path = outdir_abs.rstrip(os.sep) + ".zip"
    trace("creating ake_out.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in artifact_paths:
            zf.write(p, arcname=os.path.basename(p))

    colab_download_triggered = False
    colab_download_error = None
    try:
        from google.colab import files as colab_files  # only present inside Colab
    except ImportError:
        colab_files = None
    if colab_files is not None:
        try:
            colab_files.download(zip_path)
            colab_download_triggered = True
        except Exception as e:  # never let download UX crash a successful run
            colab_download_error = str(e)

    # --- Production banner (always shown): short, scannable, git/docker-style ---
    bar = "=" * 60
    print(bar)
    print("AKE Runtime")
    print(bar)
    print()
    print("\u2713 Workbook loaded")
    print(f"  {os.path.basename(wb)}")
    print()
    print("\u2713 Compilation successful")
    print()
    print("Summary")
    print("--------")
    print(f"{'Registries':16}: {summary['registries']}")
    print(f"{'IR Nodes':16}: {summary['ir_nodes']}")
    print(f"{'Relationships':16}: {summary['universal_edges']}")
    print(f"{'Rules':16}: {summary['rules']}")
    print(f"{'Queries':16}: {summary['queries']}")
    status = "CLOSED \u2713" if summary["closed"] else "OPEN"
    print(f"{'Status':16}: {status}")
    print()
    # --- Discovery landing page: rendered view of the Discovery Engine's Registry Universe ---
    try:
        from ake.classifier import WorkbookClassifier
        _cl = WorkbookClassifier(ake.model)
        _cd = _cl.dashboard()
        if _cd is not None:            # non-architecture: honest summary, skip architecture report
            print(_cd); print()
        else:
            print(ake.discovery_report()); print()
    except Exception:
        pass
    print("Output")
    print("------")
    print(f"\U0001F4C1 {outdir_abs}")
    print()
    print(f"Generated Files ({len(artifact_paths)})")
    for p in artifact_paths:
        print(f"\u2022 {os.path.basename(p)}")
    print()
    print("ZIP")
    print("---")
    zip_note = ""
    if colab_download_triggered:
        zip_note = "  (downloaded)"
    elif colab_download_error is not None:
        zip_note = "  (auto-download unavailable — saved above)"
    print(f"{zip_path} \u2713{zip_note}")
    print()
    print("Runtime completed successfully.")

    # --- Debug-only verbose diagnostics: full paths, file:// links, raw exception ---
    if debug:
        print(f"\n{bar}\nAKE Finished\n{bar}\n")
        print("Output Directory:")
        print(outdir_abs)
        print("\nGenerated Artifacts:")
        for p in artifact_paths:
            print(p)
        print("\nDownload Package:")
        print(zip_path)
        print("\nOpen directly (notebook-clickable):")
        for p in artifact_paths + [zip_path]:
            print(f"file://{p}")
        if colab_download_error is not None:
            print(f"\n[AKE] Colab auto-download unavailable ({colab_download_error}); the zip is still at:\n{zip_path}")
        print(f"\n{bar}\n")
    sys.stdout.flush()

    summary["output_dir"] = outdir_abs
    summary["artifacts"] = artifact_paths
    summary["zip_path"] = zip_path
    summary["colab_download_triggered"] = colab_download_triggered
    trace("exiting runner.run()")
    return summary

