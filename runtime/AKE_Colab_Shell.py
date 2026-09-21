"""AKE — single-cell interactive Colab entry point (recommended; see README.md).

Paste this whole cell into Colab and press Shift+Enter:
  1. Upload AKE_Runtime.zip (a workbook .xlsx is optional — a bundled one is used if you
     skip it; EBIS_Architecture_Registry_Workbook_v17.xlsx ships inside AKE_Runtime.zip).
  2. The runtime is extracted and put on sys.path.
  3. The live AKE Explorer starts in this cell — input() stays live until you type 'exit'.

Outside Colab (no google.colab available) this looks for AKE_Runtime.zip / *.xlsx already
on disk in the current directory instead of prompting an upload, so the same file also
works as a plain local script: `python AKE_Colab_Shell.py`.

This is a thin bootstrap only — it contains no engine logic. It locates the runtime +
workbook and then hands off to the same ake.AKE / ake.shell.AKEShell used by AKE_SHELL.py.
"""
import os, sys, glob, zipfile, tempfile


def _extract_runtime(zip_path):
    """Unzip an AKE_Runtime.zip-style bundle and return the dir that directly contains
    ake/, so it can be sys.path-inserted. Tolerant of both the shipped single top-level
    'AKE_Runtime/' wrapper folder and a flat zip with no wrapper."""
    d = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(d)
    if os.path.isdir(os.path.join(d, "ake")):
        return d
    for name in os.listdir(d):
        sub = os.path.join(d, name)
        if os.path.isdir(sub) and os.path.isdir(os.path.join(sub, "ake")):
            return sub
    return d  # best effort — sys.path insert below still gets tried


def _get_uploads():
    """Return {filename: local_path} for the runtime bundle (+ optional workbook).
    In Colab this prompts the upload dialog; outside Colab it looks at the cwd."""
    try:
        from google.colab import files
    except ImportError:
        files = None
    if files is not None:
        print("Upload AKE_Runtime.zip (workbook .xlsx optional — a bundled workbook is "
              "used if you skip it). Pick a file in the dialog below and wait for it to finish;\n"
              "interrupting the cell while it's waiting will just cancel the upload, not crash anything.")
        try:
            uploaded = files.upload()
        except KeyboardInterrupt:
            sys.exit("\nUpload cancelled. Re-run this cell and choose a file in the dialog "
                      "that appears — no need to interrupt while it's waiting.")
        return {name: os.path.abspath(name) for name in uploaded}
    found = {}
    for pat in ("AKE_Runtime.zip", "*.zip", "*.xlsx"):
        for f in glob.glob(pat):
            found.setdefault(f, os.path.abspath(f))
    return found


def _find_workbook_in(root, explicit_xlsx=None):
    if explicit_xlsx:
        return explicit_xlsx
    if root:
        xs = [f for f in glob.glob(os.path.join(root, "**", "*.xlsx"), recursive=True) if "~$" not in f]
        if xs:
            return sorted(xs, key=lambda p: ("v" not in p, p))[0]
    return None


def main():
    uploads = _get_uploads()
    if not uploads:
        sys.exit("No files uploaded/found. Need AKE_Runtime.zip (workbook .xlsx optional).")

    zip_path = next((p for n, p in uploads.items() if n.lower().endswith(".zip")), None)
    xlsx_path = next((p for n, p in uploads.items() if n.lower().endswith(".xlsx") and "~$" not in n), None)

    if zip_path is None and xlsx_path is None:
        sys.exit("Uploaded file(s) were neither a .zip nor a .xlsx — nothing to run.")

    root = _extract_runtime(zip_path) if zip_path else os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from ake import AKE
    from ake.shell import AKEShell

    wb = _find_workbook_in(root, xlsx_path)
    if not wb:
        sys.exit("No workbook (.xlsx) found — none was uploaded and none is bundled in the zip.")

    AKEShell(AKE(wb)).run()   # in-process: input() stays live until 'exit'


if __name__ == "__main__":
    main()
