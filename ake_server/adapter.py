"""Workbook locate/boot for the Server Adapter.

Reuses `AKE_MASTER.py::locate_workbook` for zip/xlsx discovery instead of writing a third
copy of that logic (a second copy already exists at `ake/runner.py::_find_workbook` — see
architecture spec §4.2). Only the pure `locate_workbook()` helper is imported; `boot()`,
`repl()`, `batch()`, and the `__main__` dispatch in AKE_MASTER.py are never called, so
importing this module has no side effects (no stdout banners, no stdin reads).

Nothing under `ake/` is modified. `ake.AKE` is used exactly as documented in the spec's
hardcode audit (§3) — constructed once and read via its existing public methods.
"""
import os
import sys
import shutil
import tempfile

# AKE_MASTER.py and ake/ live one directory above ake_server/.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from AKE_MASTER import locate_workbook  # noqa: E402  (reused, not reimplemented)
from ake import AKE  # noqa: E402


class WorkbookNotFoundError(Exception):
    pass


def boot_shared_ake(workbook_arg=None):
    """Mode 1 (Owner-Controlled): build the one shared AKE instance at server startup.
    Returns (ake, workbook_path, workbook_name)."""
    wb = locate_workbook(workbook_arg)
    if not wb:
        raise WorkbookNotFoundError(
            "No workbook (.xlsx) found. Set AKE_WORKBOOK to an explicit .xlsx/.zip path, "
            "or place one beside AKE_MASTER.py."
        )
    return AKE(wb), wb, os.path.basename(wb)


def boot_ake_from_bytes(filename, data):
    """Mode 2 (User Workspace): persist an uploaded .xlsx/.zip to a fresh temp directory,
    then hand it to the same locate_workbook() used for the on-disk case — an uploaded
    .zip gets its bundled .xlsx extracted the identical way a local .zip does, so this adds
    no second extraction path.

    Returns (ake, workbook_path, workbook_name, cleanup_dirs). cleanup_dirs is the set of
    temp directories the caller must shutil.rmtree() once the session ends: the upload
    tmpdir, plus (for a .zip upload) locate_workbook's own extraction tmpdir — it makes a
    second one internally and we don't reach in to change that, we just track both so
    neither leaks.
    """
    tmpdir = tempfile.mkdtemp(prefix="ake_upload_")
    dest = os.path.join(tmpdir, filename or "upload")
    with open(dest, "wb") as f:
        f.write(data)
    try:
        wb = locate_workbook(dest)
        if not wb:
            raise WorkbookNotFoundError(
                f"'{filename}' is not a .xlsx and contains no .xlsx (zip had none found)."
            )
        cleanup_dirs = {tmpdir, os.path.dirname(os.path.abspath(wb))}
        return AKE(wb), wb, os.path.basename(wb), cleanup_dirs
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
