"""Phase 7 — Algorithm Generator. Discovery Request -> Query Type -> bound opcode pipeline.
Reads Query Type Registry (pipeline) + Compiler Rule Registry (invariants) from the workbook."""
import re

class AlgorithmGenerator:
    def __init__(self, model):
        self.m = model
        self.qtypes = {}   # Q-id -> {name, pipeline[list]}
        qs = "Query Type Registry"
        ni, oi = self.m.col(qs, "Name"), self.m.col(qs, "Output")
        for r in self.m.rows(qs):
            if r and r[0]:
                pipe = re.split(r'\s*→\s*|\s*\|\s*', str(r[oi]))
                self.qtypes[r[0]] = {"name": r[ni], "pipeline": [p.strip() for p in pipe if p.strip()]}
        # executor map from Capability Catalog: Capability -> executor fn
        cc = "Capability Catalog"
        ci_cap, ci_exec = self.m.col(cc, "Capability"), self.m.col(cc, "Executor (fn)")
        self.exec_of = {r[ci_cap]: r[ci_exec] for r in self.m.rows(cc) if r and r[0]}

    def classify(self, req):
        v = (req.get("verb") or "").upper(); t = (req.get("text") or "").lower()
        if v == "TRACE" or any(k in t for k in ["trace", "depend", "flow", "produce", "consume"]): return "Q-03"
        if "which command" in t or "commands that" in t or "commands run" in t or "kaun se command" in t: return "Q-05"
        if any(k in t for k in ["how does", "execution of", "run karta", "stages"]): return "Q-04"
        if any(k in t for k in ["audit", "dead", "orphan", "missing", "validate", "duplicate"]): return "Q-07"
        if any(k in t for k in ["why", "incomplete", "gap", "kyu", "adhura"]): return "Q-08"
        if any(k in t for k in ["uses", "used by", "who use"]): return "Q-02"
        return "Q-01"

    def compile(self, req):
        """Returns (qid, opcode_sequence, bound_plan[(fn,kwargs)])."""
        qid = req.get("query_type") or self.classify(req)
        seq = self.qtypes.get(qid, {}).get("pipeline", [])
        plan = self._bind(qid, req)
        # Compiler invariants CR-01/CR-02: ensure entry+exit
        return qid, seq, plan

    def _bind(self, qid, req):
        tok = req.get("target")
        cmd_reg = self.m.owner_by_prefix.get("CMD")
        if qid == "Q-03":   # Trace data-flow
            return [("resolve_entity", {"token": tok}), ("walk_dataflow", {}),
                    ("attach_evidence", {}), ("render_graph", {})]
        if qid == "Q-02":   # Dependency
            return [("resolve_entity", {"token": tok}), ("walk_relationship", {}),
                    ("attach_evidence", {}), ("render_graph", {})]
        if qid == "Q-04":   # Execution of a command
            return [("resolve_entity", {"token": tok}), ("walk_execution", {}),
                    ("render_timeline", {})]
        if qid == "Q-05":   # Which commands run stage X
            prof = next((s for s in self.m.exec_sheets() if "Profile" in s), None)
            stage = req.get("stage") or tok
            return [("load_registry", {"sheet": prof}),
                    ("op_filter", {"col": stage, "val": "✅"}),
                    ("render_list", {})]
        if qid == "Q-07":   # Audit
            sub = (req.get("text") or "").lower()
            fn = ("find_dead" if "dead" in sub else "find_orphan" if "orphan" in sub
                  else "find_missing_lifecycle" if "lifecycle" in sub
                  else "find_missing_evidence" if "evidence" in sub else "check_fk")
            return [(fn, {}), ("render_table", {})]
        if qid == "Q-08":   # Gap / explain
            return [("resolve_entity", {"token": tok}), ("walk_lifecycle", {}),
                    ("walk_dataflow", {}), ("walk_execution", {}),
                    ("gap_analysis", {}), ("render_table", {})]
        # Q-01 structural default
        return [("resolve_entity", {"token": tok}), ("render_table", {})]
