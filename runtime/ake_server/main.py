"""Standalone entrypoint: `python -m ake_server.main`.

Kept as its own launcher rather than a fourth branch added to AKE_MASTER.py's
`if __name__` dispatch — that branch is open decision §7.1 in the architecture spec and
needs your sign-off (Launcher-territory vs. Runtime, by your own DO-NOT rule) before
AKE_MASTER.py itself is touched. Nothing here modifies AKE_MASTER.py; it only imports
`locate_workbook` from it (via ake_server/adapter.py), same as every other module in this
package. Wiring `--server` into AKE_MASTER.py later is a one-line additive branch calling
`ake_server.main.main()` if you decide that's in scope.
"""
import os
import uvicorn


def main():
    host = os.environ.get("AKE_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("AKE_SERVER_PORT", "8000"))
    uvicorn.run("ake_server.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
