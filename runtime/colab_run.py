"""AKE Colab entry point. Self-bootstraps sys.path so `from colab_run import run` works after unzip."""
import os, sys

_DEBUG = "--debug" in sys.argv[1:] or os.environ.get("AKE_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
if _DEBUG:
    print("[TRACE] colab_run.py started", flush=True)
try:
    sys.stdout.reconfigure(line_buffering=True)  # non-tty stdout (piped, e.g. Colab subprocess)
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if _DEBUG:
    print("[TRACE] importing ake.runner", flush=True)
from ake.runner import run

__all__ = ["run"]

if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "--debug"]
    run(argv[0] if argv else None, debug=_DEBUG)
