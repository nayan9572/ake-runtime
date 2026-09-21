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

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


@dataclass
class ControlPlane:
    token: str
    mode: str = "owner"
    workbook_name: Optional[str] = None
    active_sessions: int = 0
    apply_mode: Optional[Callable[[str], str]] = None
    apply_workbook: Optional[Callable[[str], str]] = None
    _seq: int = 0
    _feed: list[dict[str, Any]] = field(default_factory=list)

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
        return {
            "mode": self.mode,
            "workbook_name": self.workbook_name,
            "active_sessions": int(self.active_sessions),
        }

    def feed(self, since: int = 0, limit: int = 5) -> dict[str, Any]:
        since = max(0, int(since))
        limit = max(1, min(int(limit), 100))
        return {
            "entries": [e for e in self._feed if e["seq"] > since][-limit:],
            "next_seq": self._seq,
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
        self._feed.append(entry)
        if len(self._feed) > 1000:
            del self._feed[:-1000]
        return entry

    def set_mode(self, requested: str) -> dict[str, Any]:
        mode = self._normalize_mode(requested)
        if self.apply_mode is not None:
            mode = self._normalize_mode(self.apply_mode(mode))
        self.mode = mode
        return {"mode": self.mode}

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
        return {"workbook_name": self.workbook_name}


class ModeRequest(BaseModel):
    mode: str


class WorkbookRequest(BaseModel):
    path: str


def create_gateway_app(control: ControlPlane, api_app: Optional[FastAPI] = None) -> FastAPI:
    """Attach launcher control routes to an existing AKE API app."""
    app = api_app or FastAPI(title="AKE Gateway")

    def auth(token: Optional[str]) -> None:
        control._check_token(token)

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
