"""Phase 8 — Runtime Engine. Execute bound plan; return evidence-backed result."""
from .runtime_primitives import RuntimePrimitives

class RuntimeEngine:
    def __init__(self, model, facade=None):
        self.m = model; self.rp = RuntimePrimitives(model, facade=facade)

    def run(self, plan, req):
        ctx = {"token": req.get("target"), "rows": []}
        trace = []
        for fn, kwargs in plan:
            getattr(self.rp, fn)(ctx, **kwargs)
            trace.append(fn)
        # Surface whatever the executed opcodes produced — result, evidence, and the structured
        # outputs of graph/aggregate/list operations (edges/nodes/groups/metrics/rows). The
        # Analyzer decides what to render; Runtime just returns the execution outputs.
        out = {"result": ctx.get("result"), "evidence": ctx.get("evidence"),
               "executed": trace, "target": ctx.get("target")}
        for key in ("edges", "nodes", "groups", "metrics", "rows", "candidates", "discovery",
                    "reverse"):
            if ctx.get(key):
                out[key] = ctx[key]
        return out
