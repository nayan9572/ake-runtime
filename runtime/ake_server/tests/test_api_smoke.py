"""End-to-end smoke test for ake_server, run against the real bundled workbook — not
mocked. Matches the existing project's own convention (see tests/test_explorer_ux.py,
tests/test_cli_dispatch.py: independent checks of the frozen contract, not a reimplementation
of the code under test). Run with:

    AKE_SERVER_MODE=owner AKE_WORKBOOK=EBIS_Architecture_Registry_Workbook_v17.xlsx \
        pytest ake_server/tests/test_api_smoke.py -v

(run from the AKE_Runtime/ root, same place AKE_MASTER.py lives, so locate_workbook finds it).
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("AKE_SERVER_MODE", "owner")
os.environ.setdefault("AKE_WORKBOOK", "EBIS_Architecture_Registry_Workbook_v17.xlsx")

from ake_server.api import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "owner"


def test_upload_rejects_file_in_owner_mode(client):
    r = client.post("/upload", files={"file": ("x.xlsx", b"junk")})
    assert r.status_code == 400


def test_full_navigation_round_trip(client):
    up = client.post("/upload").json()
    sid = up["session_id"]
    assert up["mode"] == "owner"
    ru = up["registry_universe"]
    ex_id = ru["entity_types"][0]["examples"][0]

    qs = client.post("/query", json={"session_id": sid, "token": ex_id}).json()
    assert qs["mode"] == "menu"
    assert qs["entity"]["id"] == ex_id
    assert qs["event"] == {"type": "object_changed", "entity_id": ex_id}
    assert qs["breadcrumb"] == [ex_id]
    assert any(m["type"] == "attr" for m in qs["menu"])

    rel_item = next((m for m in qs["menu"] if m["type"] == "relation"), None)
    if rel_item:
        rs = client.post("/action", json={"session_id": sid, "key": rel_item["key"]}).json()
        assert rs["mode"] == "results"
        assert rs["event"]["type"] == "results_changed"
        assert rs["ui_hints"]["result_count"] == len(rs["results"])
        if rs["results"]:
            child = rs["results"][0]
            os_ = client.post("/action", json={"session_id": sid, "key": child["key"]}).json()
            assert os_["entity"]["id"] == child["id"]
            assert os_["breadcrumb"] == [ex_id, child["id"]]

    back = client.post("/back", json={"session_id": sid}).json()
    assert back["mode"] in ("menu", "home")

    home = client.post("/home", json={"session_id": sid}).json()
    assert home["mode"] == "home"
    assert home["event"] == {"type": "home", "entity_id": None}
    assert home["ui_hints"]["can_go_home"] is False


def test_search_bypasses_shell(client):
    sid = client.post("/upload").json()["session_id"]
    r = client.post("/search", json={"session_id": sid, "term": "a"}).json()
    assert r["term"] == "a"
    assert len(r["results"]) <= 50  # ake.search()'s own cap, not re-imposed here


def test_exit_token_signals_without_mutating_state(client):
    sid = client.post("/upload").json()["session_id"]
    ru = client.get(f"/session/{sid}").json()
    before = ru["breadcrumb"]
    r = client.post("/query", json={"session_id": sid, "token": "exit"}).json()
    assert r["ended"] is True
    assert r["event"]["type"] == "shell_exit_signal"
    assert r["breadcrumb"] == before  # ake/shell.py's own contract: exit changes nothing


def test_unknown_session_is_404(client):
    assert client.get("/session/does-not-exist").status_code == 404
    assert client.post("/query", json={"session_id": "nope", "token": "x"}).status_code == 404


def test_delete_session_frees_it(client):
    sid = client.post("/upload").json()["session_id"]
    assert client.delete(f"/session/{sid}").status_code == 200
    assert client.get(f"/session/{sid}").status_code == 404


def test_export_produces_a_zip_without_touching_live_session(client):
    sid = client.post("/upload").json()["session_id"]
    before = client.get(f"/session/{sid}").json()
    r = client.post(f"/export/{sid}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert len(r.content) > 0
    after = client.get(f"/session/{sid}").json()
    assert after["breadcrumb"] == before["breadcrumb"]  # export never touched the live shell
