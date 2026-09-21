#!/usr/bin/env python3
"""AKE_MASTER — single-entry launcher for the Universal Engineering Spreadsheet Runtime.
Flow: locate workbook -> build Canonical Model -> load registries -> (design: discovery+derivation)
-> runtime (Entity Resolver -> Query Discovery -> Algorithm Generator -> Runtime) -> Result.

CLI dispatch (three modes, one entry point):
  python AKE_MASTER.py                        -> interactive REPL (auto-locates a workbook)
  python AKE_MASTER.py workbook.xlsx          -> BATCH mode: runs the full discovery+derivation
                                                  pipeline non-interactively and writes ake_out/.
                                                  This is the mode subprocess-driven callers
                                                  (Colab, CI) must use — no stdin is read.
  python AKE_MASTER.py --demo [workbook.xlsx] -> scripted demo mode
  python AKE_MASTER.py workbook.xlsx --repl   -> interactive REPL against an explicit workbook
                                                  (opt back into the pre-batch-mode behavior)
  python AKE_MASTER.py workbook.xlsx --outdir=DIR -> batch mode, custom output directory

Rationale: previously, supplying an explicit workbook path with no other flag dropped into the
REPL's input() loop. Under non-interactive stdin (e.g. subprocess.run from a Colab cell) that
loop hits EOFError immediately and exits 0 having produced no artifacts and no error — a silent
no-op that looked like success. Batch mode is now the default for "workbook.xlsx" so the
canonical entry point is safe to call from scripts; --repl opts back into the old behavior.
"""
import sys, os, glob, zipfile, tempfile
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    pass
from ake import AKE

def _xlsx_from_zip(zp):
    """Extract the first .xlsx found inside a zip (bundled workbook or an uploaded zip
    that contains one). Preference: a path with 'v' in it (version tag) sorts first,
    matching the existing convention in ake/runner.py::_find_workbook."""
    d = tempfile.mkdtemp()
    with zipfile.ZipFile(zp) as z:
        z.extractall(d)
    xs = glob.glob(os.path.join(d, "**", "*.xlsx"), recursive=True)
    xs = [f for f in xs if "~$" not in f]
    return sorted(xs, key=lambda p: ("v" not in p, p))[0] if xs else None

def locate_workbook(arg=None):
    if arg and arg.endswith(".xlsx") and os.path.exists(arg): return arg
    if arg and arg.endswith(".zip") and os.path.exists(arg):   # FIX: an explicit .zip arg must be
        wb = _xlsx_from_zip(arg)                                # extracted too, not returned as-is
        if wb: return wb
    if arg and os.path.exists(arg): return arg                  # any other explicit path: trust caller
    here = os.path.dirname(os.path.abspath(__file__))
    for pat in ("*.xlsx", os.path.join(here, "*.xlsx")):
        xs = [f for f in glob.glob(pat) if "~$" not in f]
        if xs: return xs[0]
    for zp in glob.glob(os.path.join(here, "*.zip")):          # unzip if workbook bundled
        wb = _xlsx_from_zip(zp)
        if wb: return wb
    return None

def boot(arg=None):
    wb = locate_workbook(arg)
    if not wb: sys.exit("No workbook (.xlsx) found beside AKE_MASTER.py")
    print(f"[AKE] workbook: {os.path.basename(wb)}")
    ake = AKE(wb)
    c = ake.closure()
    print(f"[AKE] canonical model: {len(ake.model.catalog)} registries, {len(ake.model.edges)} edges")
    print(f"[AKE] feature discovery: {len(c['features'])} feature-types, closure={c['closed']}")
    return ake

def show_entity(ake, token, prefer=None):
    r = ake.query_entity(token, prefer)
    e = r["entity"]
    if not e.get("id"):
        print(f"  '{token}' -> unresolved", ("candidates: "+", ".join(c['name'] for c in e.get('candidates',[]))) if e.get('candidates') else "")
        return
    print(f"  Entity: {e['id']}  [{e['class']}]  (resolved by {e['how']})")
    print("  Applicable queries (derived from entity features):")
    for q in r["applicable"]: print(f"     {q['id']} {q['name']}")
    sel = r["selected"]; res = r["result"]
    if sel:
        print(f"  -> ran {sel['name']} | pipeline: {'-'.join(sel['pipeline'])}")
        out = res.get("result")
        if isinstance(out, dict) and "edges" in out: print("     edges:", out["edges"][:4])
        elif isinstance(out, dict): print("     result:", {k: out[k] for k in list(out)[:4]})
        elif isinstance(out, list): print(f"     {len(out)} rows")
        if res.get("evidence"): print("     evidence:", list(res["evidence"].items())[:2])

def demo(ake):
    print("\n=== ENTITY-FIRST DEMO (Entity != Query) ===")
    for tok, prefer in [("CA50","PRODUCERS"), ("FEAT-016","NEIGHBORS"), ("engine chalao","EXECUTION"), ("LHV","PRODUCERS")]:
        print(f"\ninput: {tok!r}"); show_entity(ake, tok, prefer)
    d = ake.derive_all()
    print(f"\n[design-phase registries] invariants={len(d['invariants'])} rules={len(d['rules'])} queries={len(d['queries'])}")

def _print_overview(ake):
    print(ake.discovery_report())

def repl(ake):
    _print_overview(ake)
    print("\nCommands: overview | help | list <PREFIX> | search <term> | describe <ID> | <ID> | GET_X <ID> | :quit")
    while True:
        try: line = input("AKE> ").strip()
        except (EOFError, KeyboardInterrupt): break
        if not line: continue
        low = line.lower()
        if low in (":quit", "quit", "exit"): break
        if low == "overview": _print_overview(ake); continue
        if low == "help":
            import ake.algorithm_derivation as _AD
            print("Entity prefixes:", ", ".join(sorted({i["prefix"] for i in ake.overview()["entity_types"].values()})))
            print("Queries:", ", ".join(_AD.QUERY_DEFINITIONS.keys())); continue
        if low.startswith("list "):
            ids = ake.list_entities(line.split(None, 1)[1])
            print(f"Found {len(ids)}:", ", ".join(map(str, ids[:60])) + (" ..." if len(ids) > 60 else "")); continue
        if low.startswith("search "):
            for eid, nm in ake.search(line.split(None, 1)[1]): print(f"  {eid}  {nm}")
            continue
        if low.startswith("describe "):
            d = ake.describe(line.split(None, 1)[1])
            if d.get("note"): print(" unresolved.", "candidates:", d.get("candidates")); continue
            print(f"  {d['id']} [{d['class']}]  name: {d['name']}")
            print(f"  available : {', '.join(d['available_queries'])}")
            print(f"  unavailable: {', '.join(d['unavailable_queries'])}"); continue
        if line.split()[0].upper().startswith("GET_") or line.split()[0].upper().startswith("VALIDATE"):
            parts = line.split(); q = parts[0].upper(); tok = parts[1] if len(parts) > 1 else ""
            r = ake.answer(q, tok); res = r.get("result")
            if r.get("note") and res is None: print(f"  {q}({tok}):", r["note"]); continue
            print(f"  {q}({tok}):", res.get("edges") if isinstance(res, dict) else res); continue
        show_entity(ake, line)

def batch(wb_arg, outdir="ake_out", debug=None):
    """Non-interactive mode: locate workbook, run the full discovery+derivation pipeline,
    write ake_out/ artifacts, and return the summary dict. Reads no stdin. Reuses
    ake/runner.py:run() so there is a single source of truth for artifact generation
    shared with colab_run.py.

    A relative outdir is anchored to AKE_MASTER.py's own directory, not the caller's
    process cwd. A subprocess caller that doesn't set cwd= would otherwise get ake_out/
    written into whatever directory it happened to be launched from, silently, which is
    the same "correct exit code, wrong/missing output" failure mode this fix targets."""
    from ake.runner import run as runner_run
    wb = locate_workbook(wb_arg)
    if not wb: sys.exit("No workbook (.xlsx) found beside AKE_MASTER.py")
    if not os.path.isabs(outdir):
        outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), outdir)
    return runner_run(wb, outdir=outdir, debug=debug)

if __name__ == "__main__":
    argv = sys.argv[1:]
    flags = [a for a in argv if a.startswith("--")]
    positional = [a for a in argv if not a.startswith("--")]
    wb_arg = positional[0] if positional else None
    debug_flag = "--debug" in flags

    if "--demo" in flags:
        ake = boot(wb_arg)
        demo(ake)
    elif wb_arg and "--repl" not in flags:
        # Explicit workbook, no --repl override -> batch mode (see module docstring).
        outdir = next((f.split("=", 1)[1] for f in flags if f.startswith("--outdir=")), "ake_out")
        batch(wb_arg, outdir=outdir, debug=debug_flag)
    else:
        ake = boot(wb_arg)
        repl(ake)
