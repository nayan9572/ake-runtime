"""Phase 6 — Runtime Primitive Engine. 45 opcode executors (names = Capability Catalog.Executor)."""
import re
from collections import defaultdict, deque

class RuntimePrimitives:
    def __init__(self, model, facade=None): self.m = model; self._facade = facade
    def _ctx_eid(self, ctx):
        """Extract a single entity id from ctx (target may be a list of (sheet,row) tuples)."""
        v = ctx.get("target")
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, tuple) and len(first) > 1:
                return first[1][0]
            return first
        return v if isinstance(v, str) else None

    # ---- Resolution ----
    def resolve_entity(self, ctx, token=None):
        token = token or ctx.get("token")
        t, row = self.m.owner_row(token)
        if row: ctx["target"] = [(t, row)]; ctx["rows"] = [(t, row)]; return ctx
        # registry/class token -> load its member rows (so ranking/aggregating a CLASS has rows).
        cat = getattr(self.m, "catalog", {}) or {}
        base = str(token).split(".")[0]
        reg = token if token in cat else (base if base in cat else None)
        if reg is not None:
            rows = [(reg, rr) for rr in self.m.rows(reg) if rr and rr[0]]
            if rows:
                ctx["target"] = rows; ctx["rows"] = rows; return ctx
        # name search across owner name columns
        hits = self.op_search(ctx, token=token).get("candidates", [])
        ctx["target"] = hits[:1]; ctx["rows"] = hits[:1]; return ctx
    def reverse_lookup(self, ctx, relation=None, source_prefix=None):
        """REVERSE capability: find every entity that POINTS AT the seeded target (incoming edges).
        Reuses the model's universal_edges (single graph substrate) — no new traversal engine.
        Groups the incoming edges by relation so 'what uses MOD-001' answers with the COMP/VAL
        entities and the relation they use.
          - relation: filter to one relation name (e.g. 'category').
          - source_prefix: filter incoming SOURCES to one class prefix (e.g. 'FEAT') — this powers the
            scoped smart-filter 'features in CAT-02' = FEAT entities whose edge lands on CAT-02."""
        seed_rows = ctx.get("target") or ctx.get("rows") or []
        seed = {r[0] for _, r in seed_rows} if seed_rows else set()
        if not seed and ctx.get("token"):
            seed = {ctx["token"]}
        sp = str(source_prefix).upper().rstrip("-") if source_prefix else None
        edges = getattr(self.m, "universal_edges", []) or []
        incoming = []
        for e in edges:
            if len(e) < 3:
                continue
            s, rel, t = e[0], e[1], e[2]
            if t in seed and (relation is None or rel == relation):
                if sp and str(s).split("-")[0].upper() != sp:
                    continue
                incoming.append({"id": s, "relation": rel})
        ctx["rows"] = [(self.m.owner_sheet(x["id"]) or "", (x["id"],)) for x in incoming]
        ctx["reverse"] = {"target": sorted(seed), "incoming": incoming,
                          "count": len(incoming),
                          "by_relation": _group_by_relation(incoming)}
        ctx["result"] = len(incoming)
        return ctx

    def evidence_jump(self, ctx, eid=None):
        """EVIDENCE capability: open the workbook provenance for the seeded entity — which sheet /
        registry it lives in, its full source row (every column = a cell), and any evidence column.
        Reuses the model's owner_sheet + row_dict (the workbook is the substrate); no new store."""
        eid = eid or (ctx["target"][0][1][0] if ctx.get("target") else ctx.get("token"))
        if not eid:
            ctx["evidence"] = None
            return ctx
        sheet = self.m.owner_sheet(eid)
        _, row = self.m.owner_row(eid)
        row_dict = self.m.row_dict(sheet, row) if (sheet and row) else {}
        # evidence-bearing columns (name contains 'evidence' / 'source' / 'cell' / 'ref')
        ev_cols = {k: v for k, v in row_dict.items()
                   if any(tok in str(k).lower() for tok in ("evidence", "source", "cell", "ref", "sheet", "row"))}
        ctx["evidence"] = {"id": eid, "sheet": sheet, "row": row_dict,
                           "evidence_cells": ev_cols,
                           "cell_count": len(row_dict)}
        ctx["rows"] = [(sheet or "", (eid,))]
        return ctx

    def count_related(self, ctx, relation=None, target_prefix=None, direction="out",
                      parent_prefix=None):
        """Count entities of a child class RELATED to the parent. Execution path for nested counting
        ("Family me kitne Feature hain" = count Features related to Family). REUSES the model's
        universal edges (the single graph substrate); composes walk+count, does not re-traverse.

          - relation: named relation (e.g. 'features'); None counts via any relation.
          - target_prefix: child class PK prefix to count (e.g. 'FEAT').
          - parent_prefix: when set (and no specific parent instance is seeded), do a CLASS-LEVEL
            count — distinct child-class entities related to ANY parent-class instance. This is the
            semantics of "how many Features does Family have" with no specific family named.
          - direction: 'out'/'in'/'both'.
        """
        cp = str(target_prefix).upper().rstrip("-") if target_prefix else None
        seed_rows = ctx.get("target") or ctx.get("rows") or []
        seed = {r[0] for _, r in seed_rows} if seed_rows else set()
        edges = getattr(self.m, "universal_edges", []) or []

        # class-level count: no specific parent instance -> count distinct child entities related to
        # any parent-class instance (via the relation, if named).
        if parent_prefix and not seed:
            pp = str(parent_prefix).upper().rstrip("-")
            found = set()
            for e in edges:
                if len(e) < 3:
                    continue
                s, rel, t = e[0], e[1], e[2]
                if relation and rel != relation:
                    continue
                if str(s).split("-")[0].upper() != pp:
                    continue
                if cp and str(t).split("-")[0].upper() != cp:
                    continue
                found.add(t)
            ctx["result"] = len(found)
            ctx["count_members"] = sorted(found)
            return ctx

        # instance-level count: walk from the seeded parent and count reached child-class entities.
        self.walk_relationship(ctx, direction=direction, relation=relation)
        nodes = ctx.get("nodes", set())
        reached = [n for n in nodes if n not in seed]
        if cp:
            reached = [n for n in reached if str(n).split("-")[0].upper() == cp]
        ctx["result"] = len(reached)
        ctx["count_members"] = reached
        return ctx

    def open_entity(self, ctx, token=None):
        """OPEN operation's opcode. OPEN is the semantic operation (open/inspect an entity or
        registry); the Discovery Engine is the EXECUTION SUBSTRATE it runs on — the layer that
        reaches the graph, members, neighbours, suggestions, and evidence. Discovery is NOT an
        operation; it is the substrate that OPEN (and PATH/COUNT/COMPARE via their opcodes) execute
        against.

        Two OPEN cases, both via the discovery substrate:
          - a graph ENTITY -> facade.discover(token) gives the rich card + suggestions + path.
          - a REGISTRY container (a catalog name like 'Category Registry') -> list its members via
            the substrate (list_entities on the registry's prefix), so opening a registry shows its
            contents exactly like the old panel's Family->Feature list."""
        token = token or ctx.get("token")
        if self._facade is None or not token:
            return ctx
        # registry container? (a catalog registry name) -> list members via the substrate
        cat = getattr(self.m, "catalog", {}) or {}
        reg_meta = cat.get(token)
        if reg_meta is not None and hasattr(self._facade, "list_entities"):
            prefix = reg_meta.get("prefix") or reg_meta.get("pk_prefix")
            members = self._facade.list_entities(prefix) if prefix else []
            ctx["discovery"] = {"status": "registry", "registry": token, "prefix": prefix,
                                "members": members, "count": len(members)}
            return ctx
        # otherwise a graph entity -> the discovery substrate's rich output
        ctx["discovery"] = self._facade.discover(token)
        return ctx
    def load_registry(self, ctx, sheet=None):
        sheet = sheet or ctx.get("sheet")
        ctx["rows"] = [(sheet, r) for r in self.m.rows(sheet) if r and r[0]]; ctx["sheet"] = sheet; return ctx
    def resolve_pk(self, ctx, eid=None):
        t, row = self.m.owner_row(eid or ctx.get("token")); ctx["rows"] = [(t, row)] if row else []; return ctx
    def resolve_fk(self, ctx, fk=None):
        t, row = self.m.owner_row(fk); ctx["rows"] = [(t, row)] if row else []; return ctx
    def owner_lookup(self, ctx, prefix=None): ctx["owner"] = self.m.owner_by_prefix.get(prefix); return ctx
    def reference_lookup(self, ctx, eid=None):
        eid = eid or (ctx["target"][0][1][0] if ctx.get("target") else None)
        refs = [(s, r) for s in self.m.FIND_SHEETS(eid) if s != self.m.owner_sheet(eid)
                for r in self.m.rows(s) if r and eid in r] if hasattr(self.m,'FIND_SHEETS') else []
        # FIND_SHEETS lives on discovery; recompute from cell_index
        sheets = {h[0] for h in self.m.cell_index.get(eid, [])} - {self.m.owner_sheet(eid)}
        ctx["rows"] = [(s, r) for s in sheets for r in self.m.rows(s) if r and eid in r]; return ctx

    # ---- Spreadsheet ----
    def op_filter(self, ctx, col=None, val=None, pred=None):
        out = []
        for s, r in ctx["rows"]:
            ci = self.m.col(s, col) if col else None
            if pred: 
                if pred(s, r): out.append((s, r))
            elif ci is not None and r[ci] == val: out.append((s, r))
        ctx["rows"] = out; return ctx
    def op_sort(self, ctx, col=None, desc=False):
        # sort rows by a column (or by group metrics if present and no col given)
        if col:
            ctx["rows"] = sorted(ctx["rows"], key=lambda sr: str(r_get(self.m, sr, col)), reverse=bool(desc))
        elif ctx.get("metrics"):
            ctx["metrics"] = dict(sorted(ctx["metrics"].items(),
                                         key=lambda kv: (kv[1] is None, kv[1]), reverse=bool(desc)))
        return ctx
    def op_group(self, ctx, col=None):
        g = defaultdict(list)
        for s, r in ctx.get("rows", []): g[r_get(self.m, (s, r), col)].append((s, r))
        ctx["groups"] = dict(g); return ctx
    def op_aggregate(self, ctx, fn="count", col=None):
        g = ctx.get("groups")
        if g is not None and col is None:
            # grouped count (existing behaviour)
            ctx["metrics"] = {k: len(v) for k, v in g.items()}
            return ctx
        # numeric aggregation over a column, per group if grouped else over all rows
        def _nums(rows):
            out = []
            for s, r in rows:
                v = r_get(self.m, (s, r), col) if col else None
                try:
                    out.append(float(v))
                except (TypeError, ValueError):
                    continue
            return out
        def _agg(nums):
            if fn == "count":
                return len(nums)
            if not nums:
                return None
            if fn == "sum":
                return sum(nums)
            if fn == "avg":
                return sum(nums) / len(nums)
            if fn == "min":
                return min(nums)
            if fn == "max":
                return max(nums)
            return len(nums)
        if g is not None:
            ctx["metrics"] = {k: _agg(_nums(v)) for k, v in g.items()}
        else:
            ctx["metrics"] = {"_all": _agg(_nums(ctx.get("rows", [])))}
        return ctx
    def op_join(self, ctx, sheet=None, on=None):
        joined = []
        for s, r in ctx["rows"]:
            key = r[0]
            for r2 in self.m.rows(sheet):
                if r2 and r2[0] == key: joined.append((sheet, r2))
        ctx["rows"] = joined or ctx["rows"]; return ctx
    def op_expand(self, ctx, fkcol=None):
        out = []
        for s, r in ctx["rows"]:
            ci = self.m.col(s, fkcol)
            if ci is not None and r[ci]:
                for tok in re.findall(r'[A-Z]+-\w+', str(r[ci])):
                    t2, r2 = self.m.owner_row(tok)
                    if r2: out.append((t2, r2))
        ctx["rows"] = out; return ctx
    def op_pivot(self, ctx, **k): return ctx
    def op_project(self, ctx, cols=None): ctx["project"] = cols; return ctx
    def op_limit(self, ctx, n=10):
        # LIMIT opcode: keep the first n rows (after any sort). Universal, workbook-independent.
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 10
        if "rows" in ctx:
            ctx["rows"] = ctx["rows"][:max(0, n)]
        ctx["limit"] = n
        return ctx
    def op_distinct(self, ctx):
        seen = set(); out = []
        for s, r in ctx["rows"]:
            if (s, r[0]) not in seen: seen.add((s, r[0])); out.append((s, r))
        ctx["rows"] = out; return ctx
    def op_search(self, ctx, token=None):
        token = (token or ctx.get("token") or "").lower(); cands = []
        for reg, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            nmc = 1  # name usually col 1
            for r in self.m.rows(reg):
                if r and len(r) > 1 and isinstance(r[1], str) and token in r[1].lower():
                    cands.append((reg, r))
        ctx["candidates"] = cands; return {"candidates": cands}

    # ---- Traversal ----
    def walk_parent(self, ctx, **k):
        out = []
        for s, r in ctx["rows"]:
            for i, hh in enumerate(self.m.hdr[s]):
                if hh and "(FK)" in str(hh) and isinstance(r[i], str):
                    for tok in re.findall(r'[A-Z]+-\w+', str(r[i])):
                        t2, r2 = self.m.owner_row(tok)
                        if r2: out.append((t2, r2))
        ctx["rows"] = out; return ctx
    def walk_child(self, ctx, **k): return self.reference_lookup(ctx)
    def walk_relationship(self, ctx, flow=None, direction="both", relation=None):
        seed = {r[0] for _, r in ctx.get("target", ctx["rows"])}
        src = self.m.universal_edges if flow is None else self.m.edges  # universal graph unless data-flow filter
        nodes, edges = set(seed), []
        for tup in src:
            s, rel, t = tup[0], tup[1], tup[2]; fl = tup[3] if len(tup) > 4 else None; ev = tup[-1]
            if flow and fl != flow: continue
            if relation and relation not in str(rel): continue          # M10: filter by relation type (from query def)
            if s in seed and direction in ("out", "both"): edges.append((s, rel, t, fl, ev)); nodes |= {s, t}
            if t in seed and direction in ("in", "both"): edges.append((s, rel, t, fl, ev)); nodes |= {s, t}
        # Multi-hop fallback: when 1-hop found nothing for a specific relation, use
        # ReachabilityEngine to find paths through intermediate registries. Only fires
        # for outgoing traversal with a named relation — wildcard and incoming stay 1-hop.
        if not edges and relation and direction in ("out", "both") and flow is None:
            mh = self._multi_hop(seed, relation)
            if mh:
                edges, nodes = mh[0], mh[1] | seed
        ctx["nodes"], ctx["edges"] = nodes, edges; return ctx

    def _multi_hop(self, seed, relation):
        if not hasattr(self.m, '_reachability_pairs') or not hasattr(self.m, '_relation_target_map'):
            return None
        target_classes = self.m._relation_target_map.get(relation, set())
        if not target_classes:
            return None
        from .reachability_engine import ReachabilityEngine
        re = ReachabilityEngine(self.m)
        # Build edge-evidence index once per call (not per entity)
        edge_ev = {}
        for tup in self.m.universal_edges:
            edge_ev[(tup[0], tup[1], tup[2])] = tup[-1]
        all_edges, all_nodes = [], set()
        for eid in seed:
            for tc in target_classes:
                for hit in re.all_reachable(eid, tc, self.m._reachability_pairs):
                    pn, pr = hit["path_nodes"], hit["path_rels"]
                    all_nodes.update(pn)
                    for i in range(len(pr)):
                        ev = edge_ev.get((pn[i], pr[i], pn[i + 1]))
                        all_edges.append((pn[i], pr[i], pn[i + 1], None, ev))
        return (all_edges, all_nodes) if all_edges else None
    def walk_dataflow(self, ctx, direction="both"): return self.walk_relationship(ctx, flow="Data", direction=direction)

    def walk_discovery(self, ctx, target_class=None, relation_pattern=None, hops=None,
                       confirmed_ratio=None):
        """Multi-hop traversal along a planner-derived path. Unlike walk_relationship's
        implicit fallback, this opcode is EXPLICITLY placed in the plan by
        derive_for_entity — the plan itself documents that a multi-hop path was chosen,
        what target class is being reached, and via which relation sequence. This makes
        the execution pipeline self-explaining: derived_sequence shows walk_discovery
        instead of walk_relationship, and the kwargs carry the discovery metadata."""
        seed = {r[0] for _, r in ctx.get("target", ctx["rows"])}
        from .reachability_engine import ReachabilityEngine
        re = ReachabilityEngine(self.m)
        pairs = getattr(self.m, '_reachability_pairs', None)
        edge_ev = {}
        for tup in self.m.universal_edges:
            edge_ev[(tup[0], tup[1], tup[2])] = tup[-1]
        all_edges, all_nodes = [], set()
        for eid in seed:
            for hit in re.all_reachable(eid, target_class, pairs):
                pn, pr = hit["path_nodes"], hit["path_rels"]
                all_nodes.update(pn)
                for i in range(len(pr)):
                    ev = edge_ev.get((pn[i], pr[i], pn[i + 1]))
                    all_edges.append((pn[i], pr[i], pn[i + 1], None, ev))
        ctx["nodes"] = all_nodes | seed
        ctx["edges"] = all_edges
        # Attach discovery metadata so renderers/consumers can show the path explanation
        ctx["discovery"] = {
            "target_class": target_class,
            "relation_pattern": relation_pattern,
            "hops": hops,
            "confirmed_ratio": confirmed_ratio,
        }
        return ctx
    def walk_upstream(self, ctx): return self.walk_relationship(ctx, direction="in")
    def walk_downstream(self, ctx): return self.walk_relationship(ctx, direction="out")
    def walk_execution(self, ctx, eid=None):
        eid = eid or (ctx["target"][0][1][0] if ctx.get("target") else None)
        prof = next((s for s in self.m.exec_sheets() if "Profile" in s), None)
        prof_hdr = self.m.hdr.get(prof) if prof else None
        stages = [h for h in prof_hdr[2:]] if prof_hdr else []
        fired = []
        for r in self.m.rows(prof):
            if r and r[0] == eid:
                for i, st in enumerate(stages, start=2):
                    fired.append((st, r[i]))
        ctx["stages"] = fired; return ctx
    def walk_lifecycle(self, ctx, eid=None):
        eid = eid or (ctx["target"][0][1][0] if ctx.get("target") else None)
        lc = next((s for s in self.m.sheets if "Lifecycle Status" in s), None)
        grid = {}
        if lc:
            for r in self.m.rows(lc):
                if r and r[0] == eid: grid = {self.m.hdr[lc][i]: r[i] for i in range(4, min(10, len(r)))}
        ctx["lifecycle"] = grid; return ctx

    # ---- Graph ----
    def graph_bfs(self, ctx, **k):
        adj = defaultdict(list)
        for s, rel, t, fl, ev in ctx.get("edges", []): adj[s].append(t); adj[t].append(s)
        return ctx
    def graph_dfs(self, ctx, **k): return ctx
    def graph_dependency(self, ctx, **k):
        # DEPENDENCY opcode: what this entity depends on = incoming relations. Delegates to the
        # existing traversal owner (walk_relationship, direction=in). Single authority.
        return self.walk_relationship(ctx, direction="in")
    def graph_reachability(self, ctx, remove=None, **k):
        # IMPACT opcode: what this entity reaches/affects = outgoing relations. Delegates to the
        # same traversal owner (direction=out). No separate reachability logic.
        return self.walk_relationship(ctx, direction="out")
    def graph_cycles(self, ctx, **k): return ctx
    def graph_shortest_path(self, ctx, source=None, target=None, max_depth=6):
        # PATH opcode: delegate to the graph's bidirectional path_between (single owner).
        g = self.m.universal_graph
        def _eid(v):
            # ctx target may be a list of (sheet,row) tuples, a plain id, or None
            if isinstance(v, list) and v:
                first = v[0]
                if isinstance(first, tuple) and len(first) > 1:
                    return first[1][0]
                return first
            return v
        src = source or _eid(ctx.get("target")) or ctx.get("token")
        tgt = target or ctx.get("path_target")
        if not src or not tgt:
            return ctx
        hops = g.path_between(src, tgt, max_depth=max_depth)
        ctx["path"] = hops
        if hops:
            ctx["edges"] = [(h["from"], h["relation"], h["to"], None, h["evidence"]) for h in hops]
            ctx.setdefault("evidence", {})
            for h in hops:
                ctx["evidence"]["%s->%s" % (h["from"], h["to"])] = h["evidence"]
            ctx["result"] = {"path": hops, "distance": len(hops)}
        return ctx

    # ---- Validation ----
    def check_fk(self, ctx, **k):
        bad = []
        pk_all = set(self.m.cell_index.keys())
        for reg, meta in self.m.catalog.items():
            for r in self.m.rows(reg):
                for i, hh in enumerate(self.m.hdr[reg]):
                    if hh and "(FK)" in str(hh) and isinstance(r[i], str):
                        for tok in re.findall(r'[A-Z]+-\w+', r[i]):
                            if not self.m.owner_row(tok)[1]: bad.append((reg, r[0], tok))
        ctx["result"] = {"invalid_fk": bad}; return ctx
    def find_orphan(self, ctx, **k):
        """Find entities with no outgoing edges. Universal — scans all owner registries."""
        g = self.m.universal_graph
        orphans = [eid for eid, attrs in g.node_attrs.items()
                   if not g.fwd.get(eid)]
        ctx["result"] = {"orphans": orphans[:200]}; return ctx
    def find_dead(self, ctx, **k):
        """Find entities marked as dead/deprecated/inactive in any status-like column. Universal."""
        dead = []
        for reg, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            hdr = self.m.hdr.get(reg, [])
            # Find any column with "status", "classification", or "state" in its header
            for ci, h in enumerate(hdr):
                if h and any(x in str(h).lower() for x in ["status", "classif", "state"]):
                    for r in self.m.rows(reg):
                        if r and ci < len(r) and str(r[ci]).lower().startswith("dead"):
                            dead.append(r[0])
        ctx["result"] = {"dead": dead}; return ctx
    def find_missing_lifecycle(self, ctx, **k):
        """Find entities with no outgoing edges to any other registry. Universal."""
        g = self.m.universal_graph
        miss = []
        for eid, attrs in g.node_attrs.items():
            fwd = g.fwd.get(eid, [])
            if not fwd:
                miss.append(eid)
        ctx["result"] = {"missing_lifecycle": miss[:200]}; return ctx
    def find_missing_evidence(self, ctx, **k):
        miss = []
        for reg, meta in self.m.catalog.items():
            ec = self.m.evidence_col(reg)
            if not ec: continue
            ci = self.m.col(reg, ec)
            for r in self.m.rows(reg):
                if r and (ci is None or not re.search(r'\.py:\d+|:\d+', str(r[ci]))): miss.append((reg, r[0]))
        ctx["result"] = {"missing_evidence": miss[:50]}; return ctx
    def find_duplicate(self, ctx, **k): return ctx

    # ---- Analysis ----
    def op_compare(self, ctx, target=None, scope="siblings", **k):
        # COMPARE opcode: delegate to the single owner AKE.compare (siblings/layer/pairwise).
        if self._facade is None:
            return ctx
        anchor = target or self._ctx_eid(ctx) or ctx.get("token")
        if not anchor:
            return ctx
        res = self._facade.compare(anchor, scope)
        ctx["result"] = res
        if isinstance(res, dict) and res.get("dimensions"):
            ctx.setdefault("evidence", {})["compare:%s" % anchor] = res.get("scope", scope)
        return ctx
    def gap_analysis(self, ctx, **k):
        grid = ctx.get("lifecycle", {})
        missing = [k2 for k2, v in grid.items() if v not in ("✅",)]
        ctx["result"] = {"lifecycle": grid, "missing_stages": missing,
                         "dataflow_edges": len(ctx.get("edges", [])), "fired_stages": ctx.get("stages", [])}
        return ctx
    def explain(self, ctx, relation=None, **k):
        # EXPLAIN opcode: delegate to the single owner AKE.explain_relation.
        if self._facade is None or not relation:
            return ctx
        eid = self._ctx_eid(ctx) or ctx.get("token")
        if not eid:
            return ctx
        res = self._facade.explain_relation(eid, relation)
        ctx["result"] = res
        if isinstance(res, dict):
            ctx.setdefault("evidence", {})
            for it in res.get("items", []):
                if it.get("evidence"):
                    ctx["evidence"]["%s->%s" % (eid, it.get("node"))] = it["evidence"]
        return ctx

    # ---- Rendering (terminals) ----
    def attach_evidence(self, ctx, **k):
        ev = {}
        for s, r in ctx.get("rows", []):
            ec = self.m.evidence_col(s); ci = self.m.col(s, ec) if ec else None
            ev[r[0]] = r[ci] if ci is not None else None
        for (s, rel, t, fl, e) in ctx.get("edges", []): ev[f"{s}->{t}"] = e
        ctx["evidence"] = ev; return ctx
    def render_list(self, ctx, **k):
        ctx["result"] = [(r[0], r[1] if len(r) > 1 else None) for s, r in ctx.get("rows", [])]; return ctx
    def render_table(self, ctx, **k):
        if "result" not in ctx:
            ctx["result"] = [self.m.row_dict(s, r) for s, r in ctx.get("rows", [])]
        return ctx
    def render_tree(self, ctx, **k):
        seed = sorted({r[0] for _, r in ctx.get("target", ctx.get("rows", []))})
        ctx["result"] = {"root": seed, "edges": ["%s -%s-> %s" % (s, rel, t) for s, rel, t, fl, ev in ctx.get("edges", [])]}
        return ctx
    def render_graph(self, ctx, **k):
        ctx["result"] = {"nodes": sorted(ctx.get("nodes", [])),
                         "edges": [f"{s} -{rel}-> {t}" for s, rel, t, fl, ev in ctx.get("edges", [])]}
        return ctx
    def render_timeline(self, ctx, **k):
        ctx["result"] = ctx.get("stages", []); return ctx

def _group_by_relation(incoming):
    """Group reverse-lookup hits by relation name (for a readable 'used by' breakdown)."""
    g = {}
    for x in incoming:
        g.setdefault(x["relation"], []).append(x["id"])
    return g

def r_get(m, sr, col):
    s, r = sr; ci = m.col(s, col)
    return r[ci] if ci is not None else None
