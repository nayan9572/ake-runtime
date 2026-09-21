"""ake_server_gateway.py — serves the ake_server API and the web dashboard from one
uvicorn process/port, and adds the owner control plane + observer tap on top of them.

BOUNDARY (ADR-008)
    This file is a SIBLING of `ake_server/`, never a member. It edits nothing inside
    `ake_server/`, `ake/`, or `AKE_MASTER.py`. Everything below is composition over the
    already-built objects `ake_server.api` exposes at import time:

      * `app`   — the FastAPI instance, extended here with additive routes and one ASGI
                  middleware. No existing route's behavior is altered.
      * `store` — the same SessionStore the routes use. `settings.MODE` is read
                  per-request by api.py (api.py:88, api.py:94), and
                  `store.boot_owner_mode()` is re-callable, so both are mutable at
                  runtime WITHOUT touching ake_server. Verified, not assumed.

    Same "reuse via import, never edit" pattern `ake_server/adapter.py` already uses for
    `AKE_MASTER.locate_workbook`.

WHAT THIS ADDS
    1. Control plane (`/_ake/control/*`) — owner-only, token-gated. Lets the Colab
       runtime, not the browser, be the source of truth for mode and workbook.
    2. Observer tap — an ASGI middleware that records HTTP traffic into an in-memory
       feed. Because the owner's terminal calls AKEShell in-process and never crosses
       HTTP, it is invisible to this tap BY CONSTRUCTION — the asymmetry needs no flag.
    3. Availability (`/_ake/availability`) — per-menu-key counts and reasons, derived by
       calling AKEShell's OWN helpers (`_attrs`, `_neighbors`, `_rowdict`). No second
       copy of that knowledge lives here.

SESSION POLICY (owner decision, locked)
    Switching mode or workbook mid-flight does NOT disturb live sessions. `Workspace.ake`
    is bound at session creation, so replacing `store._shared_ake` leaves existing
    sessions on the workbook they opened; only NEW sessions get the new one. A generation
    counter is exposed so the dashboard can tell a user their session is one generation
    behind, without being kicked out of it.

Frontend precedence (first match wins):
  1. AKE_DASHBOARD_DIR env var, if set and it contains an index.html.
  2. A frontend shipped INSIDE ake_server.zip, if one is ever added later — looked for
     under ake_server/{static,frontend,dashboard,public}/index.html — reused as-is.
  3. The bundled dashboard the launcher writes to ake_dashboard/ next to this file.

Run with: python ake_server_gateway.py
"""
import json
import os
import sys
import threading
import time
from collections import deque

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from ake_server.api import app, store          # noqa: E402  (the real, untouched API)
from ake_server.config import settings          # noqa: E402  (read per-request by api.py)
from ake_server.workspace import SessionMode     # noqa: E402

from fastapi import HTTPException, Request       # noqa: E402
from fastapi.responses import JSONResponse        # noqa: E402

try:
    from fastapi.staticfiles import StaticFiles
except ImportError:
    StaticFiles = None


# ============================================================================
# Owner control token — the ONLY thing separating owner from user
# ============================================================================
# The tunnel forwards every request from 127.0.0.1, so a client-IP check cannot tell the
# Colab owner apart from a public visitor. A shared secret can. The launcher generates it
# and keeps it in the Colab process; the dashboard is never given it and never asks.

CONTROL_TOKEN = os.environ.get("AKE_CONTROL_TOKEN") or ""


def _require_owner(request: Request):
    if not CONTROL_TOKEN:
        raise HTTPException(503, "Control plane disabled (no AKE_CONTROL_TOKEN set).")
    if request.headers.get("x-ake-control-token") != CONTROL_TOKEN:
        raise HTTPException(403, "Owner control token required.")


# ============================================================================
# Generation counter — bumped whenever the owner reboots the shared workbook
# ============================================================================

_generation = {"n": 0, "changed_at": None, "reason": "initial"}
_gen_lock = threading.Lock()


def _bump_generation(reason):
    with _gen_lock:
        _generation["n"] += 1
        _generation["changed_at"] = time.time()
        _generation["reason"] = reason
        return _generation["n"]


def _generation_now():
    with _gen_lock:
        return dict(_generation)


# ============================================================================
# Observer feed — HTTP traffic only, therefore dashboard traffic only
# ============================================================================

_FEED_MAX = 500
_feed = deque(maxlen=_FEED_MAX)
_feed_lock = threading.Lock()
_feed_seq = {"n": 0}

# Paths whose request/response pair is worth showing the owner. /health and the control
# plane itself are deliberately excluded — polling noise, not user activity.
_TAPPED = ("/query", "/action", "/back", "/home", "/search", "/upload")


def _record(path, req_body, resp_body, status):
    try:
        req = json.loads(req_body.decode("utf-8")) if req_body else {}
    except Exception:
        req = {}
    try:
        resp = json.loads(resp_body.decode("utf-8")) if resp_body else {}
    except Exception:
        resp = {}

    # What the user "typed", expressed the way the terminal would have received it.
    if path == "/query":
        asked = req.get("token")
    elif path == "/action":
        asked = req.get("key")
    elif path == "/search":
        asked = "search(%s)" % req.get("term", "")
    elif path == "/upload":
        asked = "<open session>"
    else:
        asked = path.lstrip("/")

    entry = {
        "session_id": (resp.get("session_id") or req.get("session_id") or "")[:8],
        "path": path,
        "asked": asked,
        "status": status,
        "at": time.time(),
        # `text` is exactly what AKEShell.handle() returned — the same string the terminal
        # would have printed for the same input. Nothing is re-rendered here.
        "text": resp.get("text"),
        "entity": (resp.get("entity") or {}).get("id"),
        "workbook": resp.get("workbook_name"),
    }
    with _feed_lock:
        _feed_seq["n"] += 1
        entry["seq"] = _feed_seq["n"]
        _feed.append(entry)


class _ObserverMiddleware:
    """Pure ASGI middleware. It copies the bytes flowing past in both directions and
    forwards them untouched — it never buffers-and-replays, so no downstream handler can
    be starved of its request body. Anything not on _TAPPED short-circuits immediately."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") not in _TAPPED:
            return await self.inner(scope, receive, send)

        req_chunks = []
        resp_chunks = []
        status_holder = {}

        async def recv():
            message = await receive()
            if message.get("type") == "http.request":
                req_chunks.append(message.get("body", b""))
            return message

        async def snd(message):
            t = message.get("type")
            if t == "http.response.start":
                status_holder["code"] = message.get("status")
            elif t == "http.response.body":
                resp_chunks.append(message.get("body", b""))
            await send(message)

        await self.inner(scope, recv, snd)
        try:
            _record(scope["path"], b"".join(req_chunks), b"".join(resp_chunks),
                    status_holder.get("code"))
        except Exception:
            pass  # the tap must never be able to break a user's request


# ============================================================================
# Availability — derived through AKEShell's own helpers, never re-derived here
# ============================================================================

def _availability_for(ws):
    """For the session's currently open object, report per-menu-key availability.

    Reads from AKE.entity_actions() — the same canonical source the shell's own menu uses.
    Before this change, the gateway re-derived counts independently from shell._neighbors/
    _attrs/_rowdict, creating a second copy of availability logic that diverged from the
    shell (gateway didn't know about multi-hop discovered relations, reporting count=0 for
    items the shell would successfully navigate). Now both surfaces read the same data."""
    shell = ws.shell
    if not shell.context or shell.mode != "menu":
        return {"context": shell.context, "items": {}}

    eid = shell.context
    actions = ws.ake.entity_actions(eid)
    items = {}
    for act in actions:
        key = act["key"]
        reason = act.get("reason")
        if act["mode"] == "discovered":
            # count=-1 means class-level reachable; tell the dashboard it's available
            items[key] = {"label": act["label"], "count": act["count"],
                          "available": True, "mode": "discovered", "reason": None}
        else:
            items[key] = {"label": act["label"], "count": act["count"],
                          "available": act["available"], "mode": act["mode"],
                          "reason": reason}
    return {"context": eid, "items": items}


# ============================================================================
# Additive routes — registered BEFORE the StaticFiles mount below
# ============================================================================

@app.get("/_ake/availability")
def availability(session_id: str):
    from ake_server.session_manager import SessionNotFoundError
    try:
        ws = store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(404, "Unknown session_id '%s'." % session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else _NullLock()
    with lock:
        data = _availability_for(ws)
    gen = _generation_now()
    data["session_id"] = session_id
    data["generation"] = gen["n"]
    data["workbook_name"] = ws.workbook_name
    data["server_workbook_name"] = store.shared_workbook_name
    # Locked policy: a live session is never kicked when the owner switches. It is only
    # TOLD that the server has moved on, so the user can choose to reload.
    data["stale"] = bool(
        ws.mode == SessionMode.OWNER
        and store.shared_workbook_name
        and store.shared_workbook_name != ws.workbook_name
    )
    return data


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@app.get("/_ake/public_state")
def public_state():
    """Unauthenticated, safe-to-expose view: what mode the server is in and which workbook
    NEW sessions will get. Carries no token, no paths, no feed."""
    gen = _generation_now()
    return {
        "mode": settings.MODE,
        "workbook_name": store.shared_workbook_name if settings.MODE == "owner" else None,
        "generation": gen["n"],
        "active_sessions": store.active_count(),
    }


@app.get("/_ake/control/state")
def control_state(request: Request):
    _require_owner(request)
    gen = _generation_now()
    return {
        "mode": settings.MODE,
        "workbook_name": store.shared_workbook_name,
        "workbook_path": getattr(store, "_shared_workbook_path", None),
        "generation": gen["n"],
        "generation_reason": gen["reason"],
        "active_sessions": store.active_count(),
        "feed_len": len(_feed),
    }


@app.post("/_ake/control/mode")
async def control_mode(request: Request):
    _require_owner(request)
    body = await request.json()
    mode = (body.get("mode") or "").strip().lower()
    if mode in ("user", "workspace"):
        mode = "workspace"
    elif mode == "owner":
        mode = "owner"
    else:
        raise HTTPException(400, "mode must be 'owner' or 'user'.")

    if mode == "owner" and store.shared_workbook_name is None:
        # Owner mode needs a booted shared workbook; boot it the same way api.py's own
        # lifespan does, through the identical SessionStore method.
        try:
            store.boot_owner_mode(settings.WORKBOOK_ARG)
        except Exception as e:
            raise HTTPException(400, "Cannot enter owner mode: %s" % e)
        _bump_generation("owner boot")

    settings.MODE = mode
    return {"mode": settings.MODE, "generation": _generation_now()["n"],
            "note": "Live sessions keep the workbook they opened; only new sessions change."}


@app.post("/_ake/control/workbook")
async def control_workbook(request: Request):
    _require_owner(request)
    body = await request.json()
    path = (body.get("path") or "").strip()
    if not path:
        raise HTTPException(400, "path is required.")
    if not os.path.exists(path):
        raise HTTPException(400, "No such file: %s" % path)
    try:
        # Same call api.py's lifespan makes at startup. locate_workbook() inside it also
        # accepts a .zip and extracts the .xlsx — no second discovery path added here.
        store.boot_owner_mode(path)
    except Exception as e:
        raise HTTPException(400, "Could not load workbook: %s" % e)
    settings.WORKBOOK_ARG = path
    gen = _bump_generation("workbook switched to %s" % os.path.basename(path))
    return {"workbook_name": store.shared_workbook_name, "generation": gen,
            "note": "Live sessions keep the previous workbook; only new sessions get this one."}


@app.get("/_ake/control/feed")
def control_feed(request: Request, since: int = 0, limit: int = 100):
    _require_owner(request)
    with _feed_lock:
        rows = [e for e in _feed if e["seq"] > since][-limit:]
        latest = _feed_seq["n"]
    return {"entries": rows, "latest": latest}


# ============================================================================
# Dashboard mount — LAST, so every route above still wins
# ============================================================================

_CANDIDATE_DIRS = [
    os.environ.get("AKE_DASHBOARD_DIR") or "",
    os.path.join(_HERE, "ake_server", "static"),
    os.path.join(_HERE, "ake_server", "frontend"),
    os.path.join(_HERE, "ake_server", "dashboard"),
    os.path.join(_HERE, "ake_server", "public"),
    os.path.join(_HERE, "ake_dashboard"),
]


def _pick_dashboard_dir():
    for d in _CANDIDATE_DIRS:
        if d and os.path.isfile(os.path.join(d, "index.html")):
            return d
    return None


_dashboard_dir = _pick_dashboard_dir()

if _dashboard_dir and StaticFiles is not None:
    app.mount("/", StaticFiles(directory=_dashboard_dir, html=True), name="dashboard")
    DASHBOARD_SOURCE = _dashboard_dir
else:
    DASHBOARD_SOURCE = None

# The observer wraps the fully-assembled app, so it sees the real routes and the static
# mount alike — and still filters down to _TAPPED before doing any work.
app = _ObserverMiddleware(app)


def main():
    import uvicorn
    host = os.environ.get("AKE_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("AKE_SERVER_PORT", "8000"))
    if DASHBOARD_SOURCE:
        print("[ake_server_gateway] serving dashboard from: %s" % DASHBOARD_SOURCE)
    else:
        print("[ake_server_gateway] no dashboard found — API only")
    print("[ake_server_gateway] control plane: %s" % ("enabled" if CONTROL_TOKEN else "DISABLED"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
