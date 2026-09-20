"""Workspace — the per-session unit the SessionStore holds.

Review suggestion (structural change #4): the SessionStore should not hand routes a raw
`ake` reference — it should hand them a Workspace that wraps ake + shell + provenance
(workbook, mode, timestamps). Routes go through the Workspace's own fields, never reach
past it to construct a second AKEShell or bypass session bookkeeping.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Set


class SessionMode(str, Enum):
    OWNER = "owner"          # shares the one server-wide AKE instance (Mode 1)
    WORKSPACE = "workspace"  # owns a private AKE instance, built from its own upload (Mode 2)


@dataclass
class Workspace:
    session_id: str
    mode: SessionMode
    ake: object                     # ake.AKE — shared (OWNER) or private (WORKSPACE)
    shell: object                   # ake.shell.AKEShell — always private to this session
    workbook_path: str
    workbook_name: str
    owns_ake: bool                  # True only for WORKSPACE — governs the concurrency lock
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cleanup_dirs: Optional[Set[str]] = None  # temp dirs to remove on expiry (WORKSPACE only)

    def touch(self):
        self.last_seen = datetime.now(timezone.utc)
