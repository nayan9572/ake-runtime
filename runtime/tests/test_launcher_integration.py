import importlib.util
import io
import os
import sys
import time
import zipfile
from pathlib import Path
from urllib import request, error

import pytest


RUNTIME_DIR = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = RUNTIME_DIR / "AKE_Master_Launcher.py"


def _load_launcher():
    spec = importlib.util.spec_from_file_location("ake_master_launcher_test", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _zip_tree(source: Path, output: Path, members):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in members:
            path = source / rel
            if path.is_file():
                z.write(path, rel.as_posix())


def _json(url, method="GET", body=None, headers=None):
    data = None if body is None else __import__("json").dumps(body).encode()
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    with request.urlopen(req, timeout=10) as resp:
        import json
        return resp.status, json.loads(resp.read().decode())


def _multipart_upload(url, field, filename, payload):
    boundary = "----ake-test-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as resp:
        import json
        return resp.status, json.loads(resp.read().decode())


@pytest.fixture
def running_launcher(tmp_path, monkeypatch):
    launcher = _load_launcher()

    # Build the two Colab-style artifacts from this checkout in an isolated temp area.
    runtime_zip = tmp_path / "AKE_Runtime.zip"
    server_zip = tmp_path / "ake_server.zip"

    runtime_members = [
        Path("AKE_MASTER.py"),
        Path("requirements.txt"),
        Path("engine_bundle.json"),
        Path("ake_ebis_adapter.py"),
        Path("EBIS_Architecture_Registry_Workbook_v17.xlsx"),
    ]
    runtime_members += [
        p.relative_to(RUNTIME_DIR)
        for p in (RUNTIME_DIR / "ake").rglob("*")
        if p.is_file()
    ]
    _zip_tree(RUNTIME_DIR, runtime_zip, runtime_members)

    server_members = [
        p.relative_to(RUNTIME_DIR)
        for p in (RUNTIME_DIR / "ake_server").rglob("*")
        if p.is_file()
    ]
    # The server zip is expected to expose adapter.py at its root.
    with zipfile.ZipFile(server_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in server_members:
            z.write(RUNTIME_DIR / rel, rel.relative_to("ake_server").as_posix())

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher, "WORKING_DIR", str(tmp_path / "live"))
    monkeypatch.setattr(launcher, "SERVER_MODE", "owner")
    monkeypatch.setattr(launcher, "SERVER_PORT", 0)

    # Pick an available TCP port without changing launcher behavior.
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    monkeypatch.setattr(launcher, "SERVER_PORT", port)

    monkeypatch.setattr(launcher, "_pip_install_quiet", lambda root: None)
    monkeypatch.setattr(launcher, "_ensure_cloudflared", lambda root: None)

    root, _ = launcher.launch()
    try:
        yield launcher, Path(root), port
    finally:
        launcher._kill_stale(root)
        time.sleep(0.5)


def test_launcher_assembly_and_generated_assets(running_launcher):
    _, root, _ = running_launcher
    assert (root / "AKE_MASTER.py").is_file()
    assert (root / "ake").is_dir()
    assert (root / "ake_server").is_dir()
    assert (root / "ake_server_gateway.py").is_file()
    assert (root / "ake_dashboard" / "index.html").is_file()

    import py_compile
    py_compile.compile(str(root / "ake_server_gateway.py"), doraise=True)


def test_launcher_server_control_plane_and_workbook(running_launcher):
    launcher, root, port = running_launcher
    base = f"http://127.0.0.1:{port}"
    token = launcher._CONTROL["token"]
    headers = {"x-ake-control-token": token}

    status, health = _json(base + "/health")
    assert status == 200
    assert health["mode"] == "owner"
    assert health["workbook_name"] == "EBIS_Architecture_Registry_Workbook_v17.xlsx"

    status, public_state = _json(base + "/_ake/public_state")
    assert status == 200
    assert public_state["mode"] == "owner"

    with pytest.raises(error.HTTPError) as exc:
        request.urlopen(request.Request(base + "/_ake/control/state"), timeout=5)
    assert exc.value.code == 403

    status, state = _json(base + "/_ake/control/state", headers=headers)
    assert status == 200
    assert state["generation"] == 0

    status, mode = _json(
        base + "/_ake/control/mode",
        method="POST",
        body={"mode": "workspace"},
        headers=headers,
    )
    assert status == 200
    assert mode["mode"] == "workspace"

    status, state = _json(base + "/_ake/control/state", headers=headers)
    assert status == 200
    assert state["mode"] == "workspace"

    status, feed = _json(
        base + "/_ake/control/feed?since=0&limit=10",
        headers=headers,
    )
    assert status == 200
    assert "entries" in feed

    # Restore owner mode for workbook-switch coverage.
    _json(
        base + "/_ake/control/mode",
        method="POST",
        body={"mode": "owner"},
        headers=headers,
    )

    wb = root / "EBIS_Architecture_Registry_Workbook_v17.xlsx"
    status, switched = _json(
        base + "/_ake/control/workbook",
        method="POST",
        body={"path": str(wb)},
        headers=headers,
    )
    assert status == 200
    assert switched["workbook_name"] == wb.name
    assert switched["generation"] >= 1


def test_launcher_real_upload_query_and_observer_feed(running_launcher):
    launcher, root, port = running_launcher
    base = f"http://127.0.0.1:{port}"
    token = launcher._CONTROL["token"]
    headers = {"x-ake-control-token": token}

    wb = (root / "EBIS_Architecture_Registry_Workbook_v17.xlsx").read_bytes()
    status, uploaded = _multipart_upload(base + "/upload", "file", "copy.xlsx", wb)
    assert status == 200
    session_id = uploaded["session_id"]

    status, result = _json(
        base + "/query",
        method="POST",
        body={"session_id": session_id, "question": "overview"},
    )
    assert status == 200
    assert result["session_id"] == session_id

    # Observer middleware records both upload and query traffic.
    deadline = time.time() + 5
    feed = None
    while time.time() < deadline:
        _, feed = _json(base + "/_ake/control/feed?since=0&limit=20", headers=headers)
        paths = [entry.get("path") for entry in feed.get("entries", [])]
        if "/upload" in paths and "/query" in paths:
            break
        time.sleep(0.2)

    paths = [entry.get("path") for entry in feed.get("entries", [])]
    assert "/upload" in paths
    assert "/query" in paths
