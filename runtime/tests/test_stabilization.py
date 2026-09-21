"""Stabilization regression test — freezes fixes for runtime-path defects found by direct
stress-testing (load/navigation/edge cases), separate from tests/regression.py (internal
API-level, 102/102) and tests/test_cli_dispatch.py (batch-mode CLI dispatch, 35/35), neither
of which exercised these integration-level paths. No engine/architecture change; all six
fixes are error-handling / consistency-of-existing-behavior only. Run:
python tests/test_stabilization.py -> exits nonzero on any failure.
"""
import sys, os, shutil, subprocess, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "AKE_MASTER.py")
SHELL_ENTRY = os.path.join(ROOT, "AKE_SHELL.py")
COLAB_SHELL = os.path.join(ROOT, "AKE_Colab_Shell.py")
EBIS = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)

def _make_runtime_zip():
    """A zip laid out like the shipped AKE_Runtime.zip: one top-level wrapper folder
    containing ake/, the entry-point scripts, and the workbook."""
    d = tempfile.mkdtemp()
    zpath = os.path.join(d, "AKE_Runtime.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(ROOT):
            if os.sep + "__pycache__" in base or base.endswith("__pycache__"):
                continue
            for f in files:
                if f.endswith(".pyc"):
                    continue
                full = os.path.join(base, f)
                arc = os.path.join("AKE_Runtime", os.path.relpath(full, ROOT))
                z.write(full, arcname=arc)
    return zpath, d


def run():
    zip_path, zip_workdir = _make_runtime_zip()

    # --- Fix 1: locate_workbook() must extract an explicit .zip arg, not return it as-is ---
    workdir = tempfile.mkdtemp()
    local_zip = os.path.join(workdir, "AKE_Runtime.zip")
    shutil.copy(zip_path, local_zip)
    r = subprocess.run([sys.executable, MASTER, "AKE_Runtime.zip", "--demo"],
                        cwd=workdir, capture_output=True, text=True, timeout=60)
    check("AKE_MASTER --demo with explicit .zip arg exits 0", r.returncode == 0, r.stderr[-300:])
    check("AKE_MASTER --demo with explicit .zip arg does not raise InvalidFileException",
          "InvalidFileException" not in r.stderr)
    shutil.rmtree(workdir, ignore_errors=True)

    # --- Fix 2: repl() must catch KeyboardInterrupt like AKEShell.run() already does ---
    workdir = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, "-c",
        f"import sys; sys.path.insert(0, {ROOT!r}); import builtins\n"
        f"builtins.input = lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt())\n"
        f"import AKE_MASTER as M\n"
        f"ake = M.boot({EBIS!r})\n"
        f"M.repl(ake)\n"
        f"print('REPL_EXITED_CLEANLY')\n"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    check("AKE_MASTER repl() exits cleanly on KeyboardInterrupt",
          "REPL_EXITED_CLEANLY" in r.stdout, r.stderr[-300:])
    shutil.rmtree(workdir, ignore_errors=True)

    # --- Fix 3: AKE_SHELL.py must extract an explicit .zip arg too ---
    workdir = tempfile.mkdtemp()
    local_zip = os.path.join(workdir, "AKE_Runtime.zip")
    shutil.copy(zip_path, local_zip)
    r = subprocess.run([sys.executable, SHELL_ENTRY, "AKE_Runtime.zip"],
                        cwd=workdir, input="exit\n", capture_output=True, text=True, timeout=60)
    check("AKE_SHELL.py with explicit .zip arg exits 0", r.returncode == 0, r.stderr[-300:])
    check("AKE_SHELL.py with explicit .zip arg does not raise InvalidFileException",
          "InvalidFileException" not in r.stderr)
    shutil.rmtree(workdir, ignore_errors=True)

    # --- Fix 4: a malformed (not missing) Registry Catalog sheet must fall back to
    # inference instead of raising a raw KeyError ---
    from openpyxl import Workbook
    bad_wb = tempfile.mktemp(suffix=".xlsx")
    wb = Workbook(); ws = wb.active; ws.title = "Registry Catalog"
    ws.append(["Registry (self)", "PK Prefix"])  # missing "Role in Model"
    ws.append(["Widgets", "WID"])
    wb.save(bad_wb)
    sys.path.insert(0, ROOT)
    from ake.workbook_runtime import WorkbookModel
    try:
        m = WorkbookModel(bad_wb)
        check("malformed Registry Catalog falls back to inference (no crash)", True)
    except KeyError as e:
        check("malformed Registry Catalog falls back to inference (no crash)", False, str(e))
    os.remove(bad_wb)

    # --- Fix 5: corrupt / missing file must raise a clear, actionable message ---
    corrupt = tempfile.mktemp(suffix=".xlsx")
    with open(corrupt, "wb") as f:
        f.write(b"not a real xlsx")
    try:
        WorkbookModel(corrupt)
        check("corrupt .xlsx raises a clear error", False, "did not raise")
    except Exception as e:
        check("corrupt .xlsx raises a clear error", "not a valid .xlsx" in str(e), str(e))
    os.remove(corrupt)

    missing = "/tmp/__ake_stabilization_does_not_exist__.xlsx"
    try:
        WorkbookModel(missing)
        check("missing workbook raises a clear error", False, "did not raise")
    except FileNotFoundError as e:
        check("missing workbook raises a clear error", "Workbook not found" in str(e), str(e))

    # --- Fix 6: AKE_Colab_Shell.py exists and runs the same end-to-end flow, using only
    # a bundled runtime zip (the documented "recommended" path) ---
    check("AKE_Colab_Shell.py exists (was documented but missing)", os.path.isfile(COLAB_SHELL))
    if os.path.isfile(COLAB_SHELL):
        workdir = tempfile.mkdtemp()
        shutil.copy(COLAB_SHELL, workdir)
        shutil.copy(zip_path, os.path.join(workdir, "AKE_Runtime.zip"))
        r = subprocess.run([sys.executable, "AKE_Colab_Shell.py"],
                            cwd=workdir, input="CMD-002\nexit\n",
                            capture_output=True, text=True, timeout=60)
        check("AKE_Colab_Shell.py runs end-to-end from a zip-only upload, exits 0",
              r.returncode == 0, r.stderr[-300:])
        check("AKE_Colab_Shell.py session actually opened the requested object",
              "CMD-002" in r.stdout)
        shutil.rmtree(workdir, ignore_errors=True)

    # --- Fix 7: EVERY query capability_matrix.py advertises as supported must not crash
    # AKE.answer() (17 of 29 did: GET_FAMILY, GET_ROLE, GET_PURPOSE, CHECK_FK, IS_ORPHAN, ...) ---
    from ake.capability_matrix import CAPABILITY_UNIVERSE
    sys.path.insert(0, ROOT)
    from ake import AKE as _AKE
    _ake = _AKE(EBIS)
    advertised = sorted(set(q for qs in CAPABILITY_UNIVERSE.values() for q, _, _ in qs))
    crashed = []
    for q in advertised:
        try:
            _ake.answer(q, "CMD-002")
        except KeyError:
            crashed.append(q)
    check("every capability_matrix.py-advertised query is crash-safe via AKE.answer()",
          not crashed, f"still crash: {crashed}")

    shutil.rmtree(zip_workdir, ignore_errors=True)
    return {}


if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
