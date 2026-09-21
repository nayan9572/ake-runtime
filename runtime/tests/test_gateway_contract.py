"""Contract tests for the canonical launcher gateway behavior.

These tests exercise the same gateway source that AKE_Master_Launcher.py embeds.
The AKE transport API remains owned by ake_server.api.
"""

import importlib
import os
import sys

from fastapi.testclient import TestClient

TOKEN = "phase1c-test-token"


def gateway():
    os.environ["AKE_CONTROL_TOKEN"] = TOKEN
    if "ake_server_gateway" not in sys.modules:
        return importlib.import_module("ake_server_gateway")
    return sys.modules["ake_server_gateway"]


def client():
    mod = gateway()
    return TestClient(mod.app), mod


def headers():
    return {"x-ake-control-token": TOKEN}


def test_control_state_requires_token():
    c, _ = client()
    assert c.get("/_ake/control/state").status_code == 403


def test_control_state_shape():
    c, _ = client()
    r = c.get("/_ake/control/state", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "mode", "workbook_name", "workbook_path", "generation",
        "generation_reason", "active_sessions", "feed_len",
    }


def test_public_state_is_unauthenticated_and_safe():
    c, _ = client()
    r = c.get("/_ake/public_state")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"mode", "workbook_name", "generation", "active_sessions"}
    assert "workbook_path" not in body


def test_feed_requires_token_and_uses_latest_cursor():
    c, mod = client()
    assert c.get("/_ake/control/feed").status_code == 403
    mod._feed.clear()
    mod._feed_seq["n"] = 0
    mod._record("/query", b'{"session_id":"s1","token":"FEAT-016"}',
                b'{"session_id":"s1","workbook_name":"runtime.xlsx"}', 200)
    r = c.get("/_ake/control/feed?since=0&limit=100", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] == 1
    assert body["entries"][0]["asked"] == "FEAT-016"
    assert body["entries"][0]["path"] == "/query"
    assert body["entries"][0]["status"] == 200


def test_feed_since_cursor():
    c, mod = client()
    mod._feed.clear()
    mod._feed_seq["n"] = 0
    for i in range(3):
        mod._record("/query", ('{"token":"q%d"}' % i).encode(), b"{}", 200)
    r = c.get("/_ake/control/feed?since=2&limit=100", headers=headers())
    assert [e["seq"] for e in r.json()["entries"]] == [3]


def test_mode_alias_and_validation():
    c, _ = client()
    r = c.post("/_ake/control/mode", json={"mode": "user"}, headers=headers())
    assert r.status_code == 200
    assert r.json()["mode"] == "workspace"
    r = c.post("/_ake/control/mode", json={"mode": "invalid"}, headers=headers())
    assert r.status_code == 400


def test_workbook_missing_path_rejected():
    c, _ = client()
    r = c.post(
        "/_ake/control/workbook",
        json={"path": "/definitely/not/a/workbook.xlsx"},
        headers=headers(),
    )
    assert r.status_code == 400


def test_launcher_observed_routes_are_exact():
    _, mod = client()
    assert mod._TAPPED == ("/query", "/action", "/back", "/home", "/search", "/upload")


def test_dashboard_and_server_helpers_exist():
    mod = gateway()
    assert callable(mod._pick_dashboard_dir)
    assert callable(mod.main)


def test_api_module_remains_separate():
    import ake_server.api as api
    assert api.app is not None
    assert hasattr(api, "store")
