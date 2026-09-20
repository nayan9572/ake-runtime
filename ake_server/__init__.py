"""ake_server — Server Adapter for AKE Runtime.

Sibling package to `ake/`, physically outside it, per the DO-NOT-touch boundary in
AKE_Server_Architecture_Specification_v1.md. Nothing in here imports `ake/*` for
anything but its already-public methods (AKE, AKEShell) and the one reused helper
(AKE_MASTER.locate_workbook). No file under `ake/` is modified, and `ake/runner.py::run()`
is never called on the live-request path (see spec §2 — critical finding).
"""
