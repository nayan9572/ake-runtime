"""Server configuration, read once from the environment at process start.

Open decision #2 from the architecture spec (Mode 1 vs Mode 2) is resolved here as a
*deployment-time* choice, not a hardcoded one — AKE_SERVER_MODE picks it, defaulting to
"owner" per the spec's own recommendation ("recommend Mode 1 first"). Both code paths are
implemented; flipping the env var is the only thing needed to run Mode 2 instead.
"""
import os


def _bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # "owner"     -> Mode 1: one shared AKE booted once at startup from AKE_WORKBOOK
    #                (or auto-located beside AKE_MASTER.py). /upload takes no file.
    # "workspace" -> Mode 2: every session uploads its own workbook; its own private AKE.
    MODE = os.environ.get("AKE_SERVER_MODE", "owner").strip().lower()

    # Mode 1 only: explicit workbook/zip path. None -> AKE_MASTER.locate_workbook's own
    # auto-discovery (first .xlsx/.zip found beside AKE_MASTER.py).
    WORKBOOK_ARG = os.environ.get("AKE_WORKBOOK") or None

    # Mode 2 only: hard cap on concurrent in-memory workbook graphs (spec §2 — "N full
    # in-memory IR graphs simultaneously — worth a memory ceiling / session cap").
    MAX_WORKSPACE_SESSIONS = int(os.environ.get("AKE_MAX_WORKSPACE_SESSIONS", "20"))

    # Both modes: idle-session TTL sweep (spec §5 — "session TTL... before this ships").
    SESSION_TTL_SECONDS = int(os.environ.get("AKE_SESSION_TTL_SECONDS", "3600"))

    # Open decision #4 from the spec: keep shell.handle()'s text render in the payload for
    # a debug/dev pane, or JSON-only. Default ON (cheap, and every client can just ignore
    # the field); callers can drop it per-request via POST body {"debug": false}.
    INCLUDE_DEBUG_TEXT_DEFAULT = _bool("AKE_INCLUDE_DEBUG_TEXT", True)

    CORS_ALLOW_ORIGINS = [o.strip() for o in os.environ.get("AKE_CORS_ORIGINS", "*").split(",")]


settings = Settings()

if settings.MODE not in ("owner", "workspace"):
    raise RuntimeError(
        f"AKE_SERVER_MODE must be 'owner' or 'workspace', got {settings.MODE!r}."
    )
