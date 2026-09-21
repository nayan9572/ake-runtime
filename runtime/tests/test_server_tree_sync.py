from pathlib import Path


def test_root_and_runtime_server_source_trees_are_identical():
    repo_root = Path(__file__).resolve().parents[2]
    runtime_server = repo_root / "runtime" / "ake_server"
    root_server = repo_root / "ake_server"

    assert runtime_server.is_dir()
    assert root_server.is_dir()

    def source_files(base):
        return sorted(
            p.relative_to(base)
            for p in base.rglob("*.py")
            if "tests" not in p.parts and "__pycache__" not in p.parts
        )

    runtime_files = source_files(runtime_server)
    root_files = source_files(root_server)
    assert root_files == runtime_files

    for rel in runtime_files:
        assert (root_server / rel).read_bytes() == (runtime_server / rel).read_bytes(), rel
