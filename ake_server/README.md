# ake_server — Server Adapter

Implements `AKE_Server_Architecture_Specification_v1.md` end to end. Verified against the
bundled `EBIS_Architecture_Registry_Workbook_v17.xlsx` in both modes (owner + workspace) —
not just written to match the spec's file:line citations, actually run against them.

**Zero edits to `ake/`, `AKE_MASTER.py`, `AKE_SHELL.py`, `AKE_Colab_Shell.py`,
`colab_run.py`, or `demo.py`.** This package is a sibling folder; the DO-NOT boundary is
enforced by directory structure, not just discipline.

## Layout

```
ake_server/
  adapter.py          workbook locate/boot — imports AKE_MASTER.locate_workbook, doesn't reimplement it
  workspace.py         Workspace dataclass — what the SessionStore actually holds (not a raw AKE ref)
  session_manager.py    SessionStore — TTL, workspace-session cap, shared-AKE lock
  events.py              event derivation from AKEShell's own before/after state
  schemas.py               transport protocol v1 (pydantic) — see the paired .md doc
  responses.py               builds NavState off shell.menu/crumb/hist/context, never off shell.handle()'s text
  api.py                       the routes
  main.py                       standalone entrypoint (python -m ake_server.main)
```

## Run it

```bash
pip install fastapi uvicorn python-multipart openpyxl
python -m ake_server.main            # http://0.0.0.0:8000
```

### Mode (env vars)

| Var | Default | Meaning |
|---|---|---|
| `AKE_SERVER_MODE` | `owner` | `owner` = Mode 1 (one shared workbook, set at boot) &nbsp;·&nbsp; `workspace` = Mode 2 (every session uploads its own) |
| `AKE_WORKBOOK` | *(auto-locate)* | Mode 1 only — explicit `.xlsx`/`.zip` path. Unset = same auto-discovery `AKE_MASTER.py` already does (first `.xlsx`/`.zip` beside it). |
| `AKE_MAX_WORKSPACE_SESSIONS` | `20` | Mode 2 only — hard cap on concurrent in-memory workbook graphs (flagged in spec §2 as needed before shipping Mode 2). |
| `AKE_SESSION_TTL_SECONDS` | `3600` | Both modes — idle sessions past this age are swept (and, in Mode 2, their temp files removed) on the next `/upload` call. |
| `AKE_INCLUDE_DEBUG_TEXT` | `true` | Include `shell.handle()`'s raw text render alongside the structured JSON (open decision §7.4 — default kept ON; override per-request with `"debug": false` in the POST body). |
| `AKE_CORS_ORIGINS` | `*` | Comma-separated allow-list for the browser frontend's origin. |
| `AKE_SERVER_HOST` / `AKE_SERVER_PORT` | `0.0.0.0` / `8000` | uvicorn bind address. |

Mode 1 is the default, matching the spec's own recommendation on open decision §7.2
("recommend Mode 1 first — cheaper, matches your brief directly"). Flip
`AKE_SERVER_MODE=workspace` to run Mode 2 instead — same code, no redeploy-time branching.

## Deployment path

Matches spec §6 exactly — only the transport underneath `ake_server/api.py` changes:

**Colab (today):**
```bash
pip install fastapi uvicorn python-multipart pyngrok  # or use Colab's built-in cloudflared support
python -m ake_server.main &
cloudflared tunnel --url http://localhost:8000
```
`cloudflared` prints a `https://<random>.trycloudflare.com` URL — point the browser
frontend's API base at that.

**Docker/VPS (later):** same `python -m ake_server.main`, put a real reverse proxy /
persistent `cloudflared tunnel run` in front of it instead of the throwaway quick-tunnel
above. Nothing in `ake_server/` changes between the two — that's the point of the adapter
boundary.

## Open decision still outstanding (spec §7.1)

Adding `--server` as a fourth branch to `AKE_MASTER.py`'s own dispatch was flagged in the
spec as needing your sign-off (Launcher vs. Runtime, under your own DO-NOT rule).
**Not done here** — `ake_server/main.py` is a fully standalone entrypoint instead, so
nothing about that decision blocks running this. If you confirm it's Launcher-territory,
wiring it in later is one additive line in `AKE_MASTER.py`'s `if __name__` block calling
`ake_server.main.main()`.

## Concurrency stance (spec §5 / finding 1.6)

`SessionStore.shared_ake_lock` is held around every call into the shared Mode-1 `AKE`
instance (`/query`, `/action`, `/back`, `/home`, `/search`, `/upload`'s
`registry_universe()` call). This is the "cheap insurance" the spec recommended — it has
**not** been through the 20-cycle concurrent-load stress test the spec calls for before
calling finding 1.6 verified rather than plausible. Treat the lock as a safety net, not a
substitute for that test.

## What's *not* here

- A frontend. This is the adapter only.
- WebSocket/SSE push. `events.py` derives an `event` per response (same-request diff); true
  multi-client "someone else moved this session" push would sit on top of `SessionStore`
  later without changing any route's contract.
- Auth. Every route trusts whatever `session_id` it's given — fine behind a Cloudflare
  quick tunnel for one user, not fine multi-tenant. Add an auth dependency in `api.py`
  before that changes.
