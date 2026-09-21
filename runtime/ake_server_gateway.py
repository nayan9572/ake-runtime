"""Launcher control-plane gateway for AKE.

Deployment/orchestration state only. This module deliberately does not add launcher
controls to ake_server.api and does not implement AKE queries.

Phase 1 contract consumed by AKE_Master_Launcher.py:
GET  /_ake/control/state
GET  /_ake/control/feed?since=N&limit=N
POST /_ake/control/mode       {"mode": "owner"|"workspace"|"user"}
POST /_ake/control/workbook   {"path": "..."}
The launcher supplies x-ake-control-token.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


@dataclass
class ControlPlane:
    token: str
    mode: str = "owner"
    workbook_name: Optional[str] = None
    workbook_path: Optional[str] = None
    active_sessions: int = 0
    generation: int = 0
    generation_reason: str = "initial"
    active_sessions_provider: Optional[Callable[[], int]] = None
    mode_provider: Optional[Callable[[], str]] = None
    workbook_provider: Optional[Callable[[], Optional[str]]] = None
    apply_mode: Optional[Callable[[str], str]] = None
    apply_workbook: Optional[Callable[[str], str]] = None
    _seq: int = 0
    _feed: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))
    _feed_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _check_token(self, supplied: Optional[str]) -> None:
        if not supplied or supplied != self.token:
            raise HTTPException(status_code=403, detail="Invalid control token.")

    @staticmethod
    def _normalize_mode(value: str) -> str:
        value = (value or "").strip().lower()
        if value == "user":
            return "workspace"
        if value not in ("owner", "workspace"):
            raise HTTPException(400, "mode must be 'owner' or 'workspace'.")
        return value

    def state(self) -> dict[str, Any]:
        mode = self.mode_provider() if self.mode_provider is not None else self.mode
        workbook_name = (
            self.workbook_provider()
            if self.workbook_provider is not None
            else self.workbook_name
        )
        active_sessions = (
            self.active_sessions_provider()
            if self.active_sessions_provider is not None
            else self.active_sessions
        )
        return {
            "mode": mode,
            "workbook_name": workbook_name,
            "workbook_path": self.workbook_path,
            "generation": self.generation,
            "generation_reason": self.generation_reason,
            "active_sessions": int(active_sessions),
            "feed_len": len(self._feed),
        }

    def public_state(self) -> dict[str, Any]:
        mode = self.mode_provider() if self.mode_provider is not None else self.mode
        workbook_name = self.workbook_provider() if self.workbook_provider is not None else self.workbook_name
        active_sessions = self.active_sessions_provider() if self.active_sessions_provider is not None else self.active_sessions
        return {
            "mode": mode,
            "workbook_name": workbook_name if mode == "owner" else None,
            "generation": self.generation,
            "active_sessions": int(active_sessions),
        }

    def feed(self, since: int = 0, limit: int = 100) -> dict[str, Any]:
        since = max(0, int(since))
        limit = max(1, min(int(limit), 100))
        with self._feed_lock:
            return {
                "entries": [e for e in self._feed if e["seq"] > since][-limit:],
                "latest": self._seq,
            }

    def record(self, *, session_id=None, asked=None, entity=None, workbook=None,
               at: Optional[float] = None) -> dict[str, Any]:
        self._seq += 1
        entry = {
            "seq": self._seq,
            "at": float(time.time() if at is None else at),
            "session_id": session_id,
            "asked": asked,
            "entity": entity,
            "workbook": workbook,
        }
        with self._feed_lock:
            self._feed.append(entry)
        return entry

    def set_mode(self, requested: str) -> dict[str, Any]:
        mode = self._normalize_mode(requested)
        if self.apply_mode is not None:
            mode = self._normalize_mode(self.apply_mode(mode))
        self.mode = mode
        return {"mode": self.mode, "generation": self.generation,
                "note": "Live sessions keep the workbook they opened; only new sessions change."}

    def set_workbook(self, path: str) -> dict[str, Any]:
        path = os.path.abspath(os.path.expanduser((path or "").strip()))
        if not path:
            raise HTTPException(400, "path is required.")
        if self.apply_workbook is not None:
            workbook_name = self.apply_workbook(path)
        else:
            if not os.path.isfile(path):
                raise HTTPException(400, "Workbook path does not exist.")
            workbook_name = os.path.basename(path)
        self.workbook_name = workbook_name
        self.workbook_path = path
        self.generation += 1
        self.generation_reason = "workbook switched to %s" % os.path.basename(path)
        return {"workbook_name": self.workbook_name, "generation": self.generation,
                "note": "Live sessions keep the previous workbook; only new sessions get this one."}


class ModeRequest(BaseModel):
    mode: str


class WorkbookRequest(BaseModel):
    path: str


def bind_runtime_state(control: ControlPlane, store: Any, settings_obj: Any = None) -> ControlPlane:
    """Bind read-only control state to the real AKE SessionStore.

    This keeps launcher controls outside ake_server.api. The launcher can import the
    existing API app and store, bind them here, then attach the control routes.
    Mode/workbook mutations remain explicit callbacks because changing deployment mode
    is a process/orchestration concern, not a SessionStore mutation.
    """
    control.active_sessions_provider = store.active_count
    control.workbook_provider = lambda: store.shared_workbook_name
    control.workbook_path_provider = lambda: getattr(store, "_shared_workbook_path", None)
    if settings_obj is not None:
        control.mode_provider = lambda: settings_obj.MODE
    return control


def bind_runtime_mutations(control: ControlPlane, store: Any, settings_obj: Any) -> ControlPlane:
    bind_runtime_state(control, store, settings_obj)

    def apply_mode(mode: str) -> str:
        if mode == "owner" and store.shared_workbook_name is None:
            try:
                store.boot_owner_mode(settings_obj.WORKBOOK_ARG)
            except Exception as e:
                raise HTTPException(400, "Cannot enter owner mode: %s" % e)
            control.generation += 1
            control.generation_reason = "owner boot"
        settings_obj.MODE = mode
        return settings_obj.MODE

    def apply_workbook(path: str) -> str:
        if not os.path.exists(path):
            raise HTTPException(400, "No such file: %s" % path)
        try:
            store.boot_owner_mode(path)
        except Exception as e:
            raise HTTPException(400, "Could not load workbook: %s" % e)
        settings_obj.WORKBOOK_ARG = path
        return store.shared_workbook_name

    control.apply_mode = apply_mode
    control.apply_workbook = apply_workbook
    return control


_TAPPED = ("/query", "/action", "/back", "/home", "/search", "/upload")


class ObserverMiddleware:
    """ASGI observer matching the launcher-embedded HTTP tap."""

    def __init__(self, inner: Any, control: ControlPlane):
        self.inner = inner
        self.control = control

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") not in _TAPPED:
            return await self.inner(scope, receive, send)

        req_chunks, resp_chunks, status_holder = [], [], {}

        async def recv():
            message = await receive()
            if message.get("type") == "http.request":
                req_chunks.append(message.get("body", b""))
            return message

        async def snd(message):
            if message.get("type") == "http.response.start":
                status_holder["code"] = message.get("status")
            elif message.get("type") == "http.response.body":
                resp_chunks.append(message.get("body", b""))
            await send(message)

        await self.inner(scope, recv, snd)
        try:
            req = json.loads(b"".join(req_chunks).decode("utf-8")) if req_chunks else {}
        except Exception:
            req = {}
        try:
            resp = json.loads(b"".join(resp_chunks).decode("utf-8")) if resp_chunks else {}
        except Exception:
            resp = {}

        path = scope["path"]
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

        try:
            entry = control.record(
                session_id=resp.get("session_id") or req.get("session_id"),
                asked=asked,
                entity=(resp.get("entity") or {}).get("id"),
                workbook=resp.get("workbook_name"),
            )
            entry.update({
                "path": path,
                "status": status_holder.get("code"),
                "text": resp.get("text"),
            })
        except Exception:
            pass




def attach_runtime_app(
    control: ControlPlane,
    api_app: FastAPI,
    store: Any,
    settings_obj: Any = None,
    observe: bool = True,
) -> FastAPI:
    """Compose the existing API with the launcher-equivalent control/observer layer."""
    if settings_obj is not None:
        bind_runtime_mutations(control, store, settings_obj)
    else:
        bind_runtime_state(control, store)
    app = create_gateway_app(control, api_app=api_app, store=store)
    return ObserverMiddleware(app, control) if observe else app


def create_gateway_app(control: ControlPlane, api_app: Optional[FastAPI] = None) -> FastAPI:
    """Attach launcher control routes to an existing AKE API app."""
    app = api_app or FastAPI(title="AKE Gateway")

    def auth(token: Optional[str]) -> None:
        control._check_token(token)

    if store is not None:
        @app.get("/_ake/public_state")
        def public_state():
            return control.public_state()

        @app.get("/_ake/availability")
        def availability(session_id: str):
            try:
                ws = store.get(session_id)
            except Exception:
                raise HTTPException(404, "Unknown session_id '%s'." % session_id)
            shell = ws.shell
            if not shell.context or shell.mode != "menu":
                data = {"context": shell.context, "items": {}}
            else:
                items = {}
                for act in ws.ake.entity_actions(shell.context):
                    items[act["key"]] = {
                        "label": act["label"], "count": act["count"],
                        "available": True if act["mode"] == "discovered" else act["available"],
                        "mode": act["mode"],
                        "reason": None if act["mode"] == "discovered" else act.get("reason"),
                    }
                data = {"context": shell.context, "items": items}
            data.update({
                "session_id": session_id,
                "generation": control.generation,
                "workbook_name": ws.workbook_name,
                "server_workbook_name": store.shared_workbook_name,
                "stale": bool(store.shared_workbook_name and
                              store.shared_workbook_name != ws.workbook_name),
            })
            return data

    @app.get("/_ake/control/state")
    def control_state(x_ake_control_token: Optional[str] = Header(default=None)):
        auth(x_ake_control_token)
        return control.state()

    @app.get("/_ake/control/feed")
    def control_feed(
        since: int = 0,
        limit: int = 5,
        x_ake_control_token: Optional[str] = Header(default=None),
    ):
        auth(x_ake_control_token)
        return control.feed(since=since, limit=limit)

    @app.post("/_ake/control/mode")
    def control_mode(
        req: ModeRequest,
        x_ake_control_token: Optional[str] = Header(default=None),
    ):
        auth(x_ake_control_token)
        return control.set_mode(req.mode)

    @app.post("/_ake/control/workbook")
    def control_workbook(
        req: WorkbookRequest,
        x_ake_control_token: Optional[str] = Header(default=None),
    ):
        auth(x_ake_control_token)
        return control.set_workbook(req.path)

    return app
