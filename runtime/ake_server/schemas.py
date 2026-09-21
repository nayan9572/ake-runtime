"""Transport protocol v1 — frozen request/response shapes for ake_server.

Mirrors AKE_Server_Transport_Protocol_v1.md, which is the document of record; this file is
its executable form. Every field is a re-shaping of data AKE/AKEShell already expose (see
architecture spec §3, the hardcode audit) — this file adds wire-format structure, never new
domain vocabulary. If a frontend needs a new fact about an entity, that fact must already
exist on `AKE`/`AKEShell` before it can be added here — it does not get invented here.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class MenuItem(BaseModel):
    key: str
    label: str
    # Derived from AKEShell's own fixed action codes (WHAT_IS/GET_NAME/REL/GET_NEIGHBORS/
    # GET_EVIDENCE/GET_SOURCE_ROW — ake/shell.py's _IDENT/_TAIL/"REL" constants), not a
    # hardcoded business vocabulary. `label` and `relation` still come straight from
    # shell.menu; `type` only buckets AKE's own fixed kinds for icon/styling hints.
    type: Literal["attr", "relation", "neighbors", "meta", "analysis"]
    relation: Optional[str] = None


class EntityView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    class_: Optional[str] = Field(default=None, alias="class")
    name: Optional[str] = None


class SearchResultItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    key: Optional[str] = None   # set when sourced from shell.results (numbered); None for /search
    id: str
    name: Optional[str] = None
    class_: Optional[str] = Field(default=None, alias="class")


class UIHints(BaseModel):
    can_go_back: bool
    can_go_home: bool
    search_enabled: bool = True
    # First relation-type item in the CURRENT menu, in the order AKE itself returns
    # relations for this object (ake/shell.py::_relations) — a re-shaping of existing
    # ordering, not a per-entity-type table.
    primary_relation: Optional[str] = None
    result_count: Optional[int] = None


class EventPayload(BaseModel):
    type: Literal[
        "object_changed", "menu_changed", "results_changed", "home",
        "no_change", "shell_exit_signal",
    ]
    entity_id: Optional[str] = None


class NavState(BaseModel):
    """Frozen shape returned by /query, /action, /back, /home, and GET /session/{id}."""
    session_id: str
    mode: Literal["home", "menu", "results", "analysis"]
    breadcrumb: List[str]
    history: List[str]
    entity: Optional[EntityView] = None
    menu: List[MenuItem] = Field(default_factory=list)
    results: List[SearchResultItem] = Field(default_factory=list)
    ui_hints: UIHints
    event: Optional[EventPayload] = None
    text: Optional[str] = None   # shell.handle()'s raw render; omit by sending debug=false
    ended: bool = False          # True only when the shell read the input as exit/quit
    analysis: Optional[dict] = None  # canonical analyze()/compare() object, pass-through
                                     # (same idiom as UploadResponse.registry_universe)


class SearchResponse(BaseModel):
    session_id: str
    term: str
    results: List[SearchResultItem]


class UploadResponse(BaseModel):
    session_id: str
    mode: Literal["owner", "workspace"]
    workbook_name: str
    registry_universe: dict   # ake.registry_universe() — pass-through, already JSON


class HealthResponse(BaseModel):
    status: str
    mode: str
    active_sessions: int
    workbook_name: Optional[str] = None


class ExportResponse(BaseModel):
    session_id: str
    zip_filename: str
    summary: dict


# ---- requests ----

class QueryRequest(BaseModel):
    session_id: str
    token: str
    debug: Optional[bool] = None   # override AKE_INCLUDE_DEBUG_TEXT for this call only


class ActionRequest(BaseModel):
    session_id: str
    key: str
    debug: Optional[bool] = None


class SessionRequest(BaseModel):
    session_id: str
    debug: Optional[bool] = None


class SearchRequest(BaseModel):
    session_id: str
    term: str


class ContextListResponse(BaseModel):
    session_id: str
    contexts: list


class ContextQueryRequest(BaseModel):
    session_id: str
    context: str                 # a context word (handler / module / relation / ...) or ""
    term: Optional[str] = None   # entity id/name or filter term within the context


class ContextQueryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    session_id: str
    context: Optional[str] = None       # resolved registry name, or "relation", or None
    context_label: Optional[str] = None
    kind: str                           # "registry" | "relation" | "none"
    candidates: list = []               # filtered entities when term isn't a single exact hit
    chain: Optional[dict] = None        # discovery chain when a single entity resolved
    relation_view: Optional[dict] = Field(default=None, alias="relation")


class PerspectiveRequest(BaseModel):
    session_id: str
    entity: str
    direction: Optional[str] = "both"   # out | in | both
    max_hops: Optional[int] = 6
    table: Optional[bool] = True        # also return the derived result table


class PerspectiveResponse(BaseModel):
    session_id: str
    perspective: Optional[dict] = None
    table: Optional[dict] = None
    suggestions: Optional[dict] = None   # guided-discovery: ranked next entities to explore


class SuggestRequest(BaseModel):
    session_id: str
    entity: str
    direction: Optional[str] = "both"
    limit: Optional[int] = 8


class SuggestResponse(BaseModel):
    session_id: str
    suggestions: Optional[dict] = None


class DiscoverRequest(BaseModel):
    session_id: str
    query: str                          # the global query (entity/registry/typo) — resolved everywhere
    context: Optional[str] = None       # SOURCE node only, never a search boundary
    max_hops: Optional[int] = 6


class DiscoverResponse(BaseModel):
    session_id: str
    result: Optional[dict] = None


class AskRequest(BaseModel):
    session_id: str
    query: str                    # the single natural-language prompt


class AskResponse(BaseModel):
    session_id: str
    query: str
    intent: Optional[dict] = None
    operations: Optional[list] = None
    plan: Optional[list] = None
    tokens: Optional[list] = None
    result: Optional[dict] = None
    answer: Optional[dict] = None
    health: Optional[dict] = None        # architecture health {score, band} — lazy detail via /diagnose


class DiagnoseRequest(BaseModel):
    session_id: str
    query: str


class DiagnoseResponse(BaseModel):
    session_id: str
    query: str
    health: Optional[dict] = None
    stages: Optional[list] = None        # layer-by-layer validation (lazy, on demand)       # {status, target/source, path[hops+evidence+tier], confidence, suggestions}


class IntersectRequest(BaseModel):
    session_id: str
    a: str
    b: str
    direction: Optional[str] = "out"    # out | in | both  (direction defines the question)
    max_hops: Optional[int] = 6
    table: Optional[bool] = True


class IntersectResponse(BaseModel):
    session_id: str
    intersection: Optional[dict] = None
    table: Optional[dict] = None
