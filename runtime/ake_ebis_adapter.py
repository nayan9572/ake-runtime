"""AKE → EBIS engine bundle adapter.

Thin bridge (no AKE redesign) that makes AKE discoverable by the EBIS
Universal Engine Host contract (engine_bundle.json).

The adapter does exactly ONE thing:
  1. Takes a workbook path (from the bundle contract)
  2. Constructs the AKE instance (existing code, unchanged)
  3. Returns it as the engine handle

The AKE instance already has every method declared in engine_bundle.json's
capabilities — no wrapper, no proxy, no method forwarding needed.
"""
import sys
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ake import AKE                     # noqa: E402 — unchanged AKE class


def start(workbook_path):
    """EBIS engine launcher callable.

    Called by launch_engine() with the workbook path resolved from the
    bundle contract's 'workbook' field. Returns the live AKE handle —
    the same AKE instance that AKE_MASTER.boot() returns."""
    return AKE(workbook_path)
