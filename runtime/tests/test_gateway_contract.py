"""Phase-1 contract tests for the launcher control plane."""

from fastapi.testclient import TestClient

from ake_server_gateway import ControlPlane, create_gateway_app

TOKEN = "phase1-test-token"


def client():
    control = ControlPlane(token=TOKEN, mode="owner", workbook_name="initial.xlsx")
    app = create_gateway_app(control)
    return TestClient(app), control


def headers():
    return {"x-ake-control-token": TOKEN}


def test_state_requires_control_token():
    c, _ = client()
    assert c.get("/_ake/control/state").status_code == 403


def test_state_contract():
    c, _ = client()
    r = c.get("/_ake/control/state", headers=headers())
    assert r.status_code == 200
    assert r.json() == {
        "mode": "owner",
        "workbook_name": "initial.xlsx",
        "active_sessions": 0,
    }


def test_feed_contract_and_sequence():
    c, control = client()
    control.record(session_id="s1", asked="GET_NAME", entity="FEAT-016",
                   workbook="initial.xlsx", at=100.0)
    control.record(session_id="s2", asked="search", entity="LHV",
                   workbook="initial.xlsx", at=101.0)
    r = c.get("/_ake/control/feed?since=0&limit=5", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert body["next_seq"] == 2
    assert [e["seq"] for e in body["entries"]] == [1, 2]
    assert body["entries"][0]["session_id"] == "s1"
    assert body["entries"][1]["asked"] == "search"


def test_feed_since_cursor():
    c, control = client()
    for i in range(3):
        control.record(session_id=f"s{i}", asked="query", at=100 + i)
    r = c.get("/_ake/control/feed?since=2&limit=5", headers=headers())
    assert r.status_code == 200
    assert [e["seq"] for e in r.json()["entries"]] == [3]


def test_mode_accepts_launcher_user_alias():
    c, control = client()
    r = c.post("/_ake/control/mode", json={"mode": "user"}, headers=headers())
    assert r.status_code == 200
    assert r.json() == {"mode": "workspace"}
    assert control.mode == "workspace"


def test_mode_accepts_owner():
    c, control = client()
    c.post("/_ake/control/mode", json={"mode": "user"}, headers=headers())
    r = c.post("/_ake/control/mode", json={"mode": "owner"}, headers=headers())
    assert r.status_code == 200
    assert r.json() == {"mode": "owner"}


def test_workbook_contract(tmp_path):
    c, control = client()
    wb = tmp_path / "registry.xlsx"
    wb.write_bytes(b"placeholder")
    r = c.post(
        "/_ake/control/workbook",
        json={"path": str(wb)},
        headers=headers(),
    )
    assert r.status_code == 200
    assert r.json() == {"workbook_name": "registry.xlsx"}
    assert control.workbook_name == "registry.xlsx"


def test_workbook_missing_path_rejected():
    c, _ = client()
    r = c.post(
        "/_ake/control/workbook",
        json={"path": "/definitely/not/a/workbook.xlsx"},
        headers=headers(),
    )
    assert r.status_code == 400


def test_control_routes_are_isolated_from_ake_api():
    c, _ = client()
    assert c.get("/health").status_code == 404
