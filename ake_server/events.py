"""Event derivation (review suggestion #1 — an event model, not just a bare response).

Every navigation response carries an `event` describing what just changed, so the
frontend never has to diff state itself to decide whether to re-render the object pane,
the results list, both, or nothing. It's a before/after diff of fields AKEShell already
exposes (`context`, `mode`) — no new domain knowledge, no polling required.

This is a same-request diff, not a push channel: the event rides on the HTTP response for
the call that caused it. Multi-client "someone else moved this session" push notifications
would need a WebSocket/SSE layer on top of SessionStore — out of scope for v1, but this
module is the natural place to add a `publish()` hook later without touching callers.
"""
from typing import Optional


def derive_event(prev_context: Optional[str], prev_mode: str, shell, ended: bool) -> dict:
    if ended:
        return {"type": "shell_exit_signal", "entity_id": None}
    new_context = shell.context
    new_mode = shell.mode
    if new_context != prev_context:
        if new_context:
            return {"type": "object_changed", "entity_id": new_context}
        return {"type": "home", "entity_id": None}
    if new_mode != prev_mode:
        # analysis and results are both "a result set is now on screen" from the client's
        # standpoint — it re-renders the stage either way.
        kind = "results_changed" if new_mode in ("results", "analysis") else "menu_changed"
        return {"type": kind, "entity_id": new_context}
    return {"type": "no_change", "entity_id": new_context}
