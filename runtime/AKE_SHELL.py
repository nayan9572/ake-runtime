#!/usr/bin/env python3
"""AKE interactive shell entry point.  python AKE_SHELL.py [workbook.xlsx] [--dev]
Runs in-process (input() works in Colab and terminals). Continuous until 'exit'."""
import sys, os, glob, zipfile, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ake import AKE
from ake.shell import AKEShell

def _xlsx_from_zip(zp):
    d = tempfile.mkdtemp()
    with zipfile.ZipFile(zp) as z:
        z.extractall(d)
    xs = [f for f in glob.glob(os.path.join(d, "**", "*.xlsx"), recursive=True) if "~$" not in f]
    return sorted(xs, key=lambda p: ("v" not in p, p))[0] if xs else None

def _find_wb(arg=None):
    if arg and arg.endswith(".xlsx") and os.path.exists(arg): return arg
    if arg and arg.endswith(".zip") and os.path.exists(arg):   # FIX: extract, don't hand the zip
        wb = _xlsx_from_zip(arg)                                # straight to openpyxl
        if wb: return wb
    if arg and os.path.exists(arg): return arg
    here = os.path.dirname(os.path.abspath(__file__))
    for pat in ([arg] if arg else []) + [os.path.join(here, "*.xlsx"), "*.xlsx"]:
        if not pat: continue
        xs = [f for f in glob.glob(pat) if "~$" not in f]
        if xs: return xs[0]
    return None

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    wb = _find_wb(args[0] if args else None)
    if not wb: sys.exit("No workbook (.xlsx) found.")
    AKEShell(AKE(wb), dev="--dev" in sys.argv).run()
