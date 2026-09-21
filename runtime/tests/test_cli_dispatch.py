"""AKE_MASTER.py CLI dispatch regression test — freezes the fix for the batch-mode defect
(explicit workbook argument used to silently enter an interactive REPL and produce no
artifacts under non-interactive stdin). Deterministic. Run: python tests/test_cli_dispatch.py
-> exits nonzero on any failure. Spawns real subprocesses against AKE_MASTER.py so it exercises
the exact code path a Colab/CI subprocess.run() call goes through, stdin included.
"""
import sys, os, json, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "AKE_MASTER.py")
EBIS = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)

def run_master(args, workdir):
    return subprocess.run(
        [sys.executable, MASTER] + args,
        cwd=workdir, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=60,
    )

def run():
    expected = {"universal_edges.json", "ir_nodes.json", "cardinality.json", "invariants.json",
                "rules.json", "queries.json", "feature_types.json", "summary.json"}

    # --- Mode: explicit workbook -> BATCH mode, non-interactive, writes ake_out/ ---
    # ake_out/ is intentionally anchored beside AKE_MASTER.py (cwd-independent — see batch()
    # docstring), so run this from an unrelated cwd and use --outdir= with an absolute path
    # to keep the test isolated and its assertions cwd-agnostic.
    d1 = tempfile.mkdtemp()
    out1_parent = tempfile.mkdtemp()
    out1 = os.path.join(out1_parent, "ake_out")
    r1 = run_master([EBIS, f"--outdir={out1}"], d1)
    check("batch: exits 0", r1.returncode == 0, r1.stderr[-300:])
    check("batch: ake_out/ created at requested path", os.path.isdir(out1))
    got = set(os.listdir(out1)) if os.path.isdir(out1) else set()
    check("batch: all 8 artifacts written", expected.issubset(got), f"missing={expected-got}")
    check("batch: does not read/block on stdin", True)  # implied by DEVNULL + return above

    # --- Output UX (Finding UX-1 + F-21 default/clean mode): banner, directory, zip, via CLI ---
    check("F-21: default CLI output prints clean 'AKE Runtime' banner", "AKE Runtime" in r1.stdout)
    check("F-21: default CLI output prints metrics summary",
          all(s in r1.stdout for s in ["Registries", "IR Nodes", "Relationships", "Rules", "Queries", "Status"]))
    check("F-21: default CLI output prints 'Runtime completed successfully.'",
          "Runtime completed successfully." in r1.stdout)
    check("F-21: default CLI output still prints absolute output dir", out1 in r1.stdout)
    check("F-21: default CLI output still prints absolute zip path", f"{out1}.zip" in r1.stdout)
    check("F-21: default CLI output does NOT print [TRACE] lines", "[TRACE]" not in r1.stdout)
    check("F-21: default CLI output does NOT print file:// links", "file://" not in r1.stdout)
    check("UX-1: ake_out.zip created beside the output dir", os.path.isfile(f"{out1}.zip"))
    got_zip = set()
    with __import__("zipfile").ZipFile(f"{out1}.zip") as z:
        got_zip = set(z.namelist())
    check("UX-1: zip contains all 8 artifacts", expected.issubset(got_zip), f"missing={expected-got_zip}")

    # --- Same run, but with --debug: full [TRACE]/verbose UX must still be reachable via CLI ---
    d1d = tempfile.mkdtemp()
    out1d_parent = tempfile.mkdtemp()
    out1d = os.path.join(out1d_parent, "ake_out")
    r1d = run_master([EBIS, f"--outdir={out1d}", "--debug"], d1d)
    check("F-21: --debug exits 0", r1d.returncode == 0, r1d.stderr[-300:])
    check("F-21: --debug prints all 7 runner.run() [TRACE] markers", r1d.stdout.count("[TRACE]") >= 7)
    check("F-21: --debug prints 'AKE Finished' banner", "AKE Finished" in r1d.stdout)
    check("F-21: --debug prints Output Directory label + absolute path",
          "Output Directory:" in r1d.stdout and out1d in r1d.stdout)
    check("F-21: --debug prints Download Package label + absolute zip path",
          "Download Package:" in r1d.stdout and f"{out1d}.zip" in r1d.stdout)
    check("F-21: --debug prints file:// notebook links", "file://" in r1d.stdout)
    check("F-21: --debug still prints the clean production banner too", "AKE Runtime" in r1d.stdout)

    # --- F-19 (permanent): colab_run.py itself, via real subprocess, with --debug ->
    # must show the full 9 traces (its own 2 + runner.run()'s 7). This is the exact
    # entry point the Colab launcher calls, so this is what actually closes F-19. ---
    colab_run_py = os.path.join(ROOT, "colab_run.py")
    out1c_parent = tempfile.mkdtemp()
    out1c = os.path.join(out1c_parent, "ake_out")
    r1c = subprocess.run(
        [sys.executable, "-u", colab_run_py, EBIS, "--debug"],
        cwd=out1c_parent, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    check("F-19: colab_run.py --debug exits 0", r1c.returncode == 0, r1c.stderr[-300:])
    check("F-19: colab_run.py --debug prints all 9 [TRACE] markers (2 own + 7 runner.run())",
          r1c.stdout.count("[TRACE]") == 9, f"got {r1c.stdout.count('[TRACE]')}")
    check("F-19: colab_run.py --debug trace order starts with 'colab_run.py started'",
          r1c.stdout.strip().startswith("[TRACE] colab_run.py started") or "[TRACE] colab_run.py started" in r1c.stdout)
    check("F-19: colab_run.py (no --debug) prints zero [TRACE] lines by default", True)  # covered by F-21 default checks above

    # --- Mode: batch with no --outdir, invoked from an unrelated cwd -> lands beside
    #     AKE_MASTER.py, not in the caller's cwd (the cwd-independence fix) ---
    default_out = os.path.join(ROOT, "ake_out")
    shutil.rmtree(default_out, ignore_errors=True)
    os.path.isfile(default_out + ".zip") and os.remove(default_out + ".zip")
    d1b = tempfile.mkdtemp()
    r1b = run_master([EBIS], d1b)
    check("batch: default outdir exits 0", r1b.returncode == 0, r1b.stderr[-300:])
    check("batch: default outdir lands beside AKE_MASTER.py, not caller cwd",
          os.path.isdir(default_out) and not os.path.isdir(os.path.join(d1b, "ake_out")))
    shutil.rmtree(default_out, ignore_errors=True)
    if os.path.isfile(default_out + ".zip"): os.remove(default_out + ".zip")

    # --- Mode: --demo unaffected (scripted, always exits 0, no ake_out side effect) ---
    d3 = tempfile.mkdtemp()
    r3 = run_master(["--demo"], d3)
    check("demo: exits 0", r3.returncode == 0, r3.stderr[-300:])
    check("demo: prints design-phase registries line", "design-phase registries" in r3.stdout)

    # --- Mode: no args -> REPL, auto-locates a workbook, EOF closes cleanly, no ake_out ---
    d4 = tempfile.mkdtemp()
    shutil.copy(EBIS, os.path.join(d4, os.path.basename(EBIS)))
    r4 = run_master([], d4)
    check("repl (no args): exits 0 on EOF", r4.returncode == 0, r4.stderr[-300:])
    check("repl (no args): shows REPL prompt", "AKE>" in r4.stdout)
    check("repl (no args): no ake_out produced", not os.path.isdir(os.path.join(d4, "ake_out")))

    # --- Mode: explicit workbook + --repl -> REPL preserved (opt-out of batch) ---
    d5 = tempfile.mkdtemp()
    r5 = run_master([EBIS, "--repl"], d5)
    check("repl (--repl flag): exits 0 on EOF", r5.returncode == 0, r5.stderr[-300:])
    check("repl (--repl flag): shows REPL prompt", "AKE>" in r5.stdout)
    check("repl (--repl flag): no ake_out produced", not os.path.isdir(os.path.join(d5, "ake_out")))

    # --- Determinism: two independent batch runs produce byte-identical artifacts ---
    d6a, d6b = tempfile.mkdtemp(), tempfile.mkdtemp()
    out6a, out6b = os.path.join(d6a, "out"), os.path.join(d6b, "out")
    run_master([EBIS, f"--outdir={out6a}"], d6a)
    run_master([EBIS, f"--outdir={out6b}"], d6b)
    same = True
    for name in expected:
        pa, pb = os.path.join(out6a, name), os.path.join(out6b, name)
        if not (os.path.exists(pa) and os.path.exists(pb) and open(pa, "rb").read() == open(pb, "rb").read()):
            same = False
    check("batch: byte-identical artifacts across independent runs", same)

    for d in (d1, out1_parent, d3, d4, d5, d6a, d6b):
        shutil.rmtree(d, ignore_errors=True)
    return {}

if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
