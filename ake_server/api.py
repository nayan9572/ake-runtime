"""ake_server API — routes wired directly to AKE / AKEShell.

Endpoint -> call mapping matches architecture spec §4.3 exactly:
  POST /upload         -> locate/boot -> AKE(wb) or shared AKE -> store session -> registry_universe()
  POST /query           -> shell.handle(token)
  POST /action           -> shell.handle(key)          (menu number or relation label — both
                                                          already work via shell._menu_lookup)
  POST /back              -> shell.handle("back")
  POST /home               -> shell.handle("home")
  POST /search               -> ake.search(term) directly — shell not involved
  GET  /session/{id}          -> read shell.context/menu/crumb/hist directly, no handle() call
  GET  /health                  -> trivial
  DELETE /session/{id}           -> bonus: explicit session end (frees a Mode-2 workbook early)
  POST /export/{id}               -> bonus: ake/runner.py::run() as a SEPARATE batch export
                                     path — never on the live-query path (spec §2, critical
                                     finding). Runs against the session's own workbook file,
                                     not its live AKE instance, in a throwaway directory.
"""
import os
import tempfile
from contextlib import asynccontextmanager, nullcontext
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .config import settings
from .session_manager import SessionStore, SessionLimitError, SessionNotFoundError
from .workspace import SessionMode
from .schemas import (
    NavState, SearchResponse, SearchResultItem, UploadResponse, HealthResponse,
    QueryRequest, ActionRequest, SessionRequest, SearchRequest,
    ContextListResponse, ContextQueryRequest, ContextQueryResponse,
    PerspectiveRequest, PerspectiveResponse, IntersectRequest, IntersectResponse,
    SuggestRequest, SuggestResponse,
    DiscoverRequest, DiscoverResponse,
    AskRequest, AskResponse,
    DiagnoseRequest, DiagnoseResponse,
)
from .responses import build_nav_state

store = SessionStore()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Mode 2 (workspace) boots nothing here — every session brings its own workbook.
    if settings.MODE == "owner":
        store.boot_owner_mode(settings.WORKBOOK_ARG)
    yield


app = FastAPI(title="AKE Server Adapter", version="1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_workspace(session_id: str):
    try:
        return store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(404, f"Unknown session_id '{session_id}'.")


def _include_text(debug_override):
    return settings.INCLUDE_DEBUG_TEXT_DEFAULT if debug_override is None else debug_override


def _run_on_shell(ws, line, include_text):
    """Call shell.handle(line), holding the shared-AKE lock only for OWNER-mode sessions
    (spec §5 concurrency stance). WORKSPACE sessions own a private AKE — no lock needed,
    since nothing else touches it."""
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    prev_context, prev_mode = ws.shell.context, ws.shell.mode
    with lock:
        raw = ws.shell.handle(line)
    return build_nav_state(ws.session_id, ws.shell, raw, prev_context, prev_mode, include_text)


# ---------------------------------------------------------------- health / upload

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        mode=settings.MODE,
        active_sessions=store.active_count(),
        workbook_name=store.shared_workbook_name if settings.MODE == "owner" else None,
    )


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(default=None)):
    if settings.MODE == "owner":
        if file is not None:
            raise HTTPException(
                400,
                "Server is in Owner-Controlled mode — the workbook is fixed at boot. "
                "POST /upload with no file to open a new session against it.",
            )
        ws = store.create_owner_session()
    else:
        if file is None:
            raise HTTPException(400, "Server is in Workspace mode — attach a .xlsx, .csv, or .zip file.")
        data = await file.read()
        try:
            ws = store.create_workspace_session(file.filename, data)
        except SessionLimitError as e:
            raise HTTPException(429, str(e))
        except Exception as e:  # WorkbookNotFoundError et al. — bad upload, not a server fault
            raise HTTPException(400, str(e))

    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        universe = ws.ake.registry_universe()
    return UploadResponse(
        session_id=ws.session_id, mode=ws.mode.value,
        workbook_name=ws.workbook_name, registry_universe=universe,
    )


# ---------------------------------------------------------------- navigation

@app.post("/query", response_model=NavState)
def query(req: QueryRequest):
    ws = _get_workspace(req.session_id)
    return _run_on_shell(ws, req.token, _include_text(req.debug))


@app.post("/action", response_model=NavState)
def action(req: ActionRequest):
    ws = _get_workspace(req.session_id)
    return _run_on_shell(ws, req.key, _include_text(req.debug))


@app.post("/back", response_model=NavState)
def back(req: SessionRequest):
    ws = _get_workspace(req.session_id)
    return _run_on_shell(ws, "back", _include_text(req.debug))


@app.post("/home", response_model=NavState)
def home(req: SessionRequest):
    ws = _get_workspace(req.session_id)
    return _run_on_shell(ws, "home", _include_text(req.debug))


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        hits = ws.ake.search(req.term)   # already a pure list of (id, name) — shell skipped
    return SearchResponse(
        session_id=ws.session_id, term=req.term,
        results=[SearchResultItem(id=str(h[0]), name=str(h[1]) if h[1] is not None else None) for h in hits],
    )


# ---------------------------------------------------------------- discovery contexts
# The "AKE>" console: the top prompt selects a discovery CONTEXT (a view onto the registries
# the loader already derived), the lower box is a query scoped to it. context + entity ->
# discovery chain; context 'relation' -> relation view. No second entity model.

@app.get("/contexts", response_model=ContextListResponse)
def contexts(session_id: str):
    ws = _get_workspace(session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        ctxs = ws.ake.contexts()
    return ContextListResponse(session_id=ws.session_id, contexts=ctxs)


@app.post("/context_query", response_model=ContextQueryResponse)
def context_query(req: ContextQueryRequest):
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        ake = ws.ake
        resolved = ake.resolve_context(req.context) if req.context else None
        term = (req.term or "").strip()

        # No context -> global resolution (unchanged behaviour), returned as candidates.
        if resolved is None:
            if not req.context:
                hits = ake.search(term) if term else []
                cands = [{"id": str(h[0]), "name": h[1], "class": None} for h in hits]
                return ContextQueryResponse(session_id=ws.session_id, context=None,
                                            context_label=None, kind="none", candidates=cands)
            raise HTTPException(404, "No such context '%s'." % req.context)

        # Relation mode: term must resolve to a single entity -> relation view.
        if resolved == ake.RELATION_CONTEXT:
            rv = None
            if term:
                r = ake.resolve(term)
                if r.get("id"):
                    rv = ake.relation_view(r["id"])
            return ContextQueryResponse(session_id=ws.session_id, context="relation",
                                        context_label="Relation", kind="relation",
                                        relation=rv, candidates=[])

        # Registry context: filter within it. A single exact hit -> discovery chain; else
        # return the filtered candidates for the user to pick.
        info = next((c for c in ake.contexts() if c.get("registry") == resolved), None)
        label = info["label"] if info else resolved
        cands = ake.query_in_context(resolved, term)
        chain = None
        if term:
            exact = [c for c in cands if c["id"].lower() == term.lower()
                     or (c.get("name") and str(c["name"]).lower() == term.lower())]
            if len(exact) == 1:
                chain = ake.discovery_chain(exact[0]["id"])
                cands = []
                _chain_sug = ake.suggest_next(exact[0]["id"])
                if chain is not None:
                    chain["suggestions"] = _chain_sug
        return ContextQueryResponse(session_id=ws.session_id, context=resolved,
                                    context_label=label, kind="registry",
                                    candidates=cands, chain=chain)


# ---------------------------------------------------------------- Phase-2 semantic engine
# Multi-hop perspective + directed intersection, both computed on the already-derived graph
# (no per-query workbook re-read). direction chooses "drives" (out) vs "driven-by" (in).

@app.post("/perspective", response_model=PerspectiveResponse)
def perspective(req: PerspectiveRequest):
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        ake = ws.ake
        r = ake.resolve(req.entity)
        if not r.get("id"):
            # ambiguous or unknown -> surface candidates rather than guessing
            if r.get("candidates"):
                raise HTTPException(409, "Ambiguous entity '%s'; specify one of %s"
                                    % (req.entity, [c["id"] for c in r["candidates"]]))
            raise HTTPException(404, "Unknown entity '%s'." % req.entity)
        view = ake.perspective(r["id"], direction=req.direction or "both",
                               max_hops=req.max_hops or 6)
        tbl = ake.derive_table(view) if (req.table and view) else None
        sug = ake.suggest_next(r["id"], direction=req.direction or "both")
    return PerspectiveResponse(session_id=ws.session_id, perspective=view, table=tbl, suggestions=sug)


@app.post("/suggest", response_model=SuggestResponse)
def suggest(req: SuggestRequest):
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        sug = ws.ake.suggest_next(req.entity, direction=req.direction or "both", limit=req.limit or 8)
    return SuggestResponse(session_id=ws.session_id, suggestions=sug)


@app.post("/discover", response_model=DiscoverResponse)
def discover(req: DiscoverRequest):
    """Universal intent-driven discovery. Context is the SOURCE node only; the query resolves
    globally across the whole graph. Routes straight to the existing AKE.discover() pipeline
    (resolve -> bidirectional path -> evidence tiering -> suggestions). No new logic here."""
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        res = ws.ake.discover(req.query, context=req.context, max_hops=req.max_hops or 6)
    return DiscoverResponse(session_id=ws.session_id, result=res)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """THE single public interface. Runs the full pipeline through one owner-method
    (AKE.ask_pipeline): Query -> Tokenizer -> Resolver(Language+Workbook) -> Canonical Intent ->
    AlgorithmDerivation -> RuntimeEngine -> Evidence. The UI calls only this; it never touches the
    planner or RuntimeEngine directly and has no alternate execution path."""
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        r = ws.ake.ask_pipeline(req.query)
        # lightweight health band only (score) — the full layer-by-layer diagnosis is lazy (/diagnose)
        health = ws.ake.diagnose(req.query)["health"]
    return AskResponse(session_id=ws.session_id, query=r["query"], intent=r["intent"],
                       operations=r["operations"], plan=r["plan"], tokens=r["tokens"],
                       result=r["result"], answer=r["answer"], health=health)


@app.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(req: DiagnoseRequest):
    """LAZY architecture diagnosis: full layer-by-layer validation for a query, produced only when
    the user drills into a health indicator. Owned by ArchitectureDiagnosis; renders nothing."""
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        dg = ws.ake.diagnose(req.query)
    return DiagnoseResponse(session_id=ws.session_id, query=dg["query"],
                            health=dg["health"], stages=dg["stages"])


@app.post("/intersect", response_model=IntersectResponse)
def intersect(req: IntersectRequest):
    ws = _get_workspace(req.session_id)
    lock = store.shared_ake_lock if ws.mode == SessionMode.OWNER else nullcontext()
    with lock:
        ake = ws.ake
        ra, rb = ake.resolve(req.a), ake.resolve(req.b)
        for token, res in ((req.a, ra), (req.b, rb)):
            if not res.get("id"):
                if res.get("candidates"):
                    raise HTTPException(409, "Ambiguous entity '%s'; specify one of %s"
                                        % (token, [c["id"] for c in res["candidates"]]))
                raise HTTPException(404, "Unknown entity '%s'." % token)
        view = ake.intersect(ra["id"], rb["id"], direction=req.direction or "out",
                             max_hops=req.max_hops or 6)
        tbl = ake.derive_table(view) if (req.table and view) else None
    return IntersectResponse(session_id=ws.session_id, intersection=view, table=tbl)


@app.get("/session/{session_id}", response_model=NavState)
def session_state(session_id: str, debug: Optional[bool] = None):
    ws = _get_workspace(session_id)
    # Read-only: no handle() call, so prev == current and derive_event reports "no_change".
    return build_nav_state(
        ws.session_id, ws.shell, "", ws.shell.context, ws.shell.mode, _include_text(debug)
    )


@app.delete("/session/{session_id}")
def end_session(session_id: str):
    _get_workspace(session_id)  # 404s cleanly if unknown, same as every other route
    store.end(session_id)
    return {"session_id": session_id, "ended": True}


# ---------------------------------------------------------------- export (separate from live path)

@app.post("/export/{session_id}")
async def export(session_id: str):
    """Batch export, kept deliberately separate from the live-query path (spec §2 critical
    finding: runner.run() must never sit behind a live request). Runs ake/runner.py::run()
    against this session's *workbook file*, not its live AKEShell/AKE instance, in a
    throwaway directory — the live session is untouched and stays open. Returns the
    resulting ake_out.zip directly (this mirrors today's Colab download button, just over
    HTTP instead of google.colab.files.download())."""
    ws = _get_workspace(session_id)
    from ake.runner import run as runner_run  # imported lazily: only this route needs it

    outdir = os.path.join(tempfile.mkdtemp(prefix="ake_export_"), "ake_out")
    summary = await run_in_threadpool(runner_run, ws.workbook_path, outdir, False)
    zip_path = summary["zip_path"]
    return FileResponse(zip_path, filename=os.path.basename(zip_path), media_type="application/zip")
