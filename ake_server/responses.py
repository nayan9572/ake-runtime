"""Builds the frozen NavState payload straight off an AKEShell instance's own attributes.

Per architecture spec §3's explicit refinement: never parse the pretty string
AKEShell.handle() returns — read the structured attributes (shell.menu, shell.crumb,
shell.context, shell.hist, shell.results, shell.mode) directly off the same instance
*after* calling handle(). shell._attrs(eid) is reused as-is (it's the same one-liner
AKEShell's own _menu_page()/_action_page() already call) rather than re-deriving node
name/class a second way.
"""
from .schemas import NavState, MenuItem, EntityView, SearchResultItem, UIHints, EventPayload
from .events import derive_event

# AKEShell's own fixed action codes (ake/shell.py: _IDENT, _TAIL, and the "REL" literal
# used by _menu_page()) — bucketed for UI typing only, see schemas.py::MenuItem.
_MENU_TYPE = {
    "WHAT_IS": "attr",
    "GET_NAME": "attr",
    "REL": "relation",
    "GET_NEIGHBORS": "neighbors",
    "GET_EVIDENCE": "meta",
    "GET_SOURCE_ROW": "meta",
    "ANALYZE_ENTITY": "analysis",
    "COMPARE_SIBLINGS": "analysis",
    "COMPARE_LAYER": "analysis",
}


def _menu_items(shell):
    return [
        MenuItem(key=key, label=friendly, type=_MENU_TYPE.get(q, "attr"), relation=rel)
        for key, (friendly, q, rel) in shell.menu.items()
    ]


def _entity(shell):
    if not shell.context:
        return None
    a = shell._attrs(shell.context)
    return EntityView.model_validate({
        "id": shell.context,
        "class": str(a["class"]) if a.get("class") is not None else None,
        "name": str(a["name"]) if a.get("name") is not None else None,
    })


def _results(shell):
    # Both a plain results list AND an analysis view carry navigable rows in
    # shell.results (analysis rows are the observation/compare targets the user can open).
    if shell.mode not in ("results", "analysis"):
        return []
    out = []
    for key, node_id in shell.results.items():
        a = shell._attrs(node_id)
        out.append(SearchResultItem.model_validate({
            "key": key, "id": node_id,
            "name": str(a["name"]) if a.get("name") is not None else None,
            "class": str(a["class"]) if a.get("class") is not None else None,
        }))
    return out


def _ui_hints(shell):
    primary_relation = None
    for _, (_, q, rel) in shell.menu.items():
        if q == "REL":
            primary_relation = rel
            break
    # result_count is the TRUE size of the current result/analysis set, not the printed
    # (capped) row count — so the "Results (N)" heading and any downstream badge match the
    # advertised action count even when the visible list is truncated. shell.result_total
    # is set by every producer alongside shell.results.
    has_set = shell.mode in ("results", "analysis")
    total = getattr(shell, "result_total", 0) or len(shell.results)
    return UIHints(
        can_go_back=bool(shell.crumb) or bool(getattr(shell, "stack", [])),
        can_go_home=shell.context is not None,
        search_enabled=True,
        primary_relation=primary_relation,
        result_count=total if has_set else None,
    )


def build_nav_state(session_id, shell, raw_text, prev_context, prev_mode, include_text=True) -> NavState:
    ended = raw_text is None
    event = EventPayload(**derive_event(prev_context, prev_mode, shell, ended))
    # 'results' and 'analysis' are pass-through view modes. Only a null-context menu is
    # reinterpreted as 'home'; a live entity menu keeps 'menu'.
    if shell.mode in ("results", "analysis"):
        mode = shell.mode
    else:
        mode = "home" if shell.context is None else shell.mode
    return NavState(
        session_id=session_id,
        mode=mode,
        breadcrumb=list(shell.crumb),
        history=list(shell.hist),
        entity=_entity(shell),
        menu=_menu_items(shell) if (shell.context and shell.mode == "menu") else [],
        results=_results(shell),
        ui_hints=_ui_hints(shell),
        event=event,
        text=(raw_text if include_text else None),
        ended=ended,
        analysis=getattr(shell, "last_analysis", None),
    )
