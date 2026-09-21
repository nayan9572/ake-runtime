"""SessionStore — owns every live Workspace.

Mode 1 (owner): one shared AKE instance; every session gets its own cheap AKEShell wrapping
it (spec §5 — "the shell holds only a handful of small lists/dicts, not a copy of the
graph"). Mode 2 (workspace): every session gets its own private AKE, built from its own
upload.

Concurrency stance (spec §5 / finding 1.6 — "plausibly thread-safe by construction, not yet
verified under load"): one AKEShell per session already serializes everything *within* a
session for free. What's shared across sessions in Mode 1 is the single underlying AKE/
model — `shared_ake_lock` is held by callers (see api.py) around every call that reaches
into it, until a real concurrency stress test says the lock is unnecessary. This is the
"cheap insurance" the spec recommended, not a performance-tuned solution.
"""
import shutil
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict

from ake.shell import AKEShell

from .adapter import boot_shared_ake, boot_ake_from_bytes
from .config import settings
from .workspace import Workspace, SessionMode


class SessionLimitError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class SessionStore:
    def __init__(self):
        self._workspaces: Dict[str, Workspace] = {}
        self._book_lock = threading.Lock()       # guards self._workspaces bookkeeping only
        self.shared_ake_lock = threading.Lock()   # guards calls INTO the shared Mode-1 AKE
        self._shared_ake = None
        self._shared_workbook_path = None
        self._shared_workbook_name = None

    # ---- Mode 1 boot (called once at server startup) ----
    def boot_owner_mode(self, workbook_arg=None):
        self._shared_ake, self._shared_workbook_path, self._shared_workbook_name = \
            boot_shared_ake(workbook_arg)

    @property
    def shared_workbook_name(self):
        return self._shared_workbook_name

    # ---- session lifecycle ----
    def create_owner_session(self) -> Workspace:
        if self._shared_ake is None:
            raise RuntimeError("Owner-Controlled mode is not booted (boot_owner_mode() first).")
        self._expire_stale()
        sid = uuid.uuid4().hex
        ws = Workspace(
            session_id=sid, mode=SessionMode.OWNER,
            ake=self._shared_ake, shell=AKEShell(self._shared_ake),
            workbook_path=self._shared_workbook_path, workbook_name=self._shared_workbook_name,
            owns_ake=False,
        )
        with self._book_lock:
            self._workspaces[sid] = ws
        return ws

    def create_workspace_session(self, filename: str, data: bytes) -> Workspace:
        self._expire_stale()
        with self._book_lock:
            active = sum(1 for w in self._workspaces.values() if w.mode == SessionMode.WORKSPACE)
        if active >= settings.MAX_WORKSPACE_SESSIONS:
            raise SessionLimitError(
                f"Workspace session cap reached ({settings.MAX_WORKSPACE_SESSIONS} concurrent "
                "in-memory workbooks). Try again once another session ends or expires."
            )
        ake, wb_path, wb_name, cleanup_dirs = boot_ake_from_bytes(filename, data)
        sid = uuid.uuid4().hex
        ws = Workspace(
            session_id=sid, mode=SessionMode.WORKSPACE,
            ake=ake, shell=AKEShell(ake),
            workbook_path=wb_path, workbook_name=wb_name,
            owns_ake=True, cleanup_dirs=cleanup_dirs,
        )
        with self._book_lock:
            self._workspaces[sid] = ws
        return ws

    def get(self, session_id: str) -> Workspace:
        with self._book_lock:
            ws = self._workspaces.get(session_id)
        if ws is None:
            raise SessionNotFoundError(session_id)
        ws.touch()
        return ws

    def end(self, session_id: str):
        with self._book_lock:
            ws = self._workspaces.pop(session_id, None)
        self._cleanup(ws)

    def active_count(self) -> int:
        with self._book_lock:
            return len(self._workspaces)

    def _expire_stale(self):
        now = datetime.now(timezone.utc)
        with self._book_lock:
            stale_ids = [sid for sid, w in self._workspaces.items()
                         if (now - w.last_seen).total_seconds() > settings.SESSION_TTL_SECONDS]
            stale = [self._workspaces.pop(sid) for sid in stale_ids]
        for ws in stale:
            self._cleanup(ws)

    @staticmethod
    def _cleanup(ws):
        if ws and ws.cleanup_dirs:
            for d in ws.cleanup_dirs:
                shutil.rmtree(d, ignore_errors=True)
