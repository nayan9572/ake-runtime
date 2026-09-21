from pathlib import Path


def test_root_and_runtime_server_trees_are_identical():
    repo_root = Path(__file__).resolve().parents[2]
    runtime_server = repo_root / "runtime" / "ake_server"
    root_server = repo_root / "ake_server"

    assert runtime_server.is_dir()
    assert root_server.is_dir()

    runtime_files = sorted(
        p.relative_to(runtime_server)
        for p in runtime_server.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    root_files = sorted(
        p.relative_to(root_server)
        for p in root_server.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    assert root_files == runtime_files

    for rel in runtime_files:
        assert (root_server / rel).read_bytes() == (runtime_server / rel).read_bytes(), rel
