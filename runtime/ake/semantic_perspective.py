"""Semantic Perspective Engine — Phase 2 of the AKE Knowledge Runtime.

Phase 1 (done once, elsewhere): workbook -> registries/owners/relations discovered ->
universal property graph built. That graph is the derived knowledge; it is NOT rebuilt per
query. This module is Phase 2: every capability here runs purely on the already-derived
in-memory graph (`model.universal_graph`) and never re-reads the workbook.

Three capabilities, all graph-only:

1. perspective(entity, direction, max_hops)
   A multi-hop semantic traversal from one entity. Instead of one hop (immediate
   neighbours), it walks transitively and layers the reachable entities by hop distance and
   class: e.g. CA50 -> Variable -> Feature -> Module -> Command -> Handler -> ... Each
   reached entity records the shortest relation path back to the source (its evidence trail).

2. intersect(a, b, direction)
   Two directed perspectives, intersected. Direction matters: Fuel -> CA50 is not the same
   as CA50 -> Fuel, because the context entity defines the traversal origin and the arrow
   defines whether we follow "what this drives" (out) or "what drives this" (in). The
   intersection is the set of entities reachable from BOTH origins, plus the join entities
   where the two influence cones meet — the derived "how A relates to B" answer.

3. derive_table(perspective_or_intersection)
   A result table whose COLUMNS are derived from what the traversal actually found, not
   hardcoded. Columns are included only when the underlying graph supplies them (Owner only
   if owner entities exist on the paths; Evidence only if evidence is present; Runtime-impact
   only if execution/lifecycle flags exist; Strength always, from path length + multiplicity).

No domain vocabulary: "Variable", "Fuel", "CA50" never appear as literals. Everything is
derived from node `class`, edge `relation`, and the property-graph attributes.
"""


def _norm_dir(direction):
    d = (direction or "both").lower()
    if d in ("out", "outgoing", "downstream", "drives", "forward"):
        return "out"
    if d in ("in", "incoming", "upstream", "driven_by", "backward", "reverse"):
        return "in"
    return "both"


class SemanticPerspectiveEngine:
    def __init__(self, model):
        self.m = model
        self.g = model.universal_graph

    # ------------------------------------------------------------------ helpers
    def _step(self, node, direction):
        """One hop from node in the chosen direction, as (relation, neighbor, evidence)."""
        g = self.g
        key = g._key(node)
        out = []
        if direction in ("out", "both"):
            out += [(rel, t, ev) for rel, t, ev in g.fwd.get(key, [])]
        if direction in ("in", "both"):
            out += [(rel, s, ev) for rel, s, ev in g.rev.get(key, [])]
        return out

    def _traverse(self, source, direction, max_hops):
        """BFS over the derived graph from source. Returns:
        reached: {node_key: {hop, class, name, relation_path, node_path, via_relation}}
        Deterministic (fwd/rev preserve build order). Purely in-memory."""
        g = self.g
        src = g._key(source)
        direction = _norm_dir(direction)
        reached = {}
        # parent map for shortest relation path reconstruction
        parent = {src: (None, None)}
        from collections import deque
        q = deque([(src, 0)])
        while q:
            node, hop = q.popleft()
            if max_hops is not None and hop >= max_hops:
                continue
            for rel, nb, ev in self._step(node, direction):
                if nb in parent:
                    continue
                parent[nb] = (node, rel)
                # reconstruct path
                nodes, rels, cur = [nb], [], nb
                while parent[cur][0] is not None:
                    p, r = parent[cur]; rels.append(r); nodes.append(p); cur = p
                nodes.reverse(); rels.reverse()
                a = g.attrs(nb)
                reached[nb] = {
                    "id": nb, "hop": hop + 1,
                    "class": a.get("class"), "name": a.get("name"),
                    "relation_path": rels, "node_path": nodes,
                    "via_relation": rels[-1] if rels else None,
                    "evidence": a.get("evidence"), "has_evidence": bool(a.get("has_Evidence")),
                    "in_execution": bool(a.get("in_execution")), "has_lifecycle": bool(a.get("has_lifecycle")),
                }
                q.append((nb, hop + 1))
        return src, reached

    # ------------------------------------------------------------------ 1. perspective
    def perspective(self, entity, direction="both", max_hops=6):
        """Multi-hop semantic view of one entity: reachable entities layered by hop and
        grouped by class, each with its relation path (evidence trail). Graph-only."""
        g = self.g
        if not g.attrs(entity):
            return None
        src, reached = self._traverse(entity, direction, max_hops)
        ident = g.attrs(src)
        # layer by hop
        layers = {}
        for node, info in reached.items():
            layers.setdefault(info["hop"], []).append(info)
        # group by class (a "semantic band": Variable band, Feature band, ...)
        bands = {}
        for node, info in reached.items():
            cls = info["class"] or "?"
            bands.setdefault(cls, []).append(info)
        for cls in bands:
            bands[cls].sort(key=lambda x: (x["hop"], x["id"]))
        return {
            "origin": {"id": src, "name": ident.get("name"), "class": ident.get("class")},
            "direction": _norm_dir(direction),
            "max_hops": max_hops,
            "reached_count": len(reached),
            "layers": {h: sorted(v, key=lambda x: x["id"]) for h, v in sorted(layers.items())},
            "bands": dict(sorted(bands.items(), key=lambda kv: (-len(kv[1]), kv[0]))),
        }

    # ------------------------------------------------------------------ 2. intersection
    def intersect(self, a, b, direction="out", max_hops=6):
        """Directed two-perspective intersection. `direction` is applied to BOTH origins:
        with 'out' this is "what A drives" ∩ "what B drives"; with 'in', "what drives A" ∩
        "what drives B". Because the origins differ, intersect(A,B,dir) and intersect(B,A,dir)
        share the overlap set but attribute paths to different sources — and 'out' vs 'in'
        are entirely different questions. Returns the shared entities plus each side's path to
        them (the derived 'how these two relate' answer). Graph-only."""
        g = self.g
        if not g.attrs(a) or not g.attrs(b):
            return None
        ka, ra = self._traverse(a, direction, max_hops)
        kb, rb = self._traverse(b, direction, max_hops)
        shared_keys = (set(ra) & set(rb)) - {ka, kb}
        # is B directly reachable from A (and vice versa)? that is the most direct relation
        a_to_b = rb.get  # placeholder to keep names clear
        direct_a_reaches_b = kb in ra
        direct_b_reaches_a = ka in rb
        shared = []
        for k in shared_keys:
            ia, ib = ra[k], rb[k]
            at = g.attrs(k)
            shared.append({
                "id": k, "class": at.get("class"), "name": at.get("name"),
                "from_a": {"hop": ia["hop"], "relation_path": ia["relation_path"], "node_path": ia["node_path"]},
                "from_b": {"hop": ib["hop"], "relation_path": ib["relation_path"], "node_path": ib["node_path"]},
                "combined_distance": ia["hop"] + ib["hop"],
                "has_evidence": bool(at.get("has_Evidence")), "evidence": at.get("evidence"),
                "in_execution": bool(at.get("in_execution")),
            })
        shared.sort(key=lambda x: (x["combined_distance"], x["id"]))
        return {
            "a": {"id": ka, "name": g.attrs(ka).get("name"), "class": g.attrs(ka).get("class")},
            "b": {"id": kb, "name": g.attrs(kb).get("name"), "class": g.attrs(kb).get("class")},
            "direction": _norm_dir(direction),
            "max_hops": max_hops,
            "a_reaches_b_directly": direct_a_reaches_b,
            "b_reaches_a_directly": direct_b_reaches_a,
            "a_to_b_path": rb_path if (rb_path := (ra[kb]["relation_path"] if direct_a_reaches_b else None)) else None,
            "b_to_a_path": (rb[ka]["relation_path"] if direct_b_reaches_a else None),
            "shared_count": len(shared),
            "shared": shared,
        }

    # ------------------------------------------------------------------ 3. derived table
    def derive_table(self, view):
        """Derive a result table from a perspective or an intersection. COLUMNS are chosen
        from what the data actually contains — nothing hardcoded. Returns {columns, rows}."""
        if view is None:
            return {"columns": [], "rows": []}
        is_intersection = "shared" in view
        items = view["shared"] if is_intersection else [i for band in view["bands"].values() for i in band]

        # Decide columns by evidence in the data.
        has_owner = any(it.get("class") for it in items)          # class == owning registry
        has_evidence = any(it.get("has_evidence") for it in items)
        has_runtime = any(it.get("in_execution") or it.get("has_lifecycle") for it in items)
        rel_present = any((it.get("via_relation") or it.get("from_a")) for it in items)

        columns = ["Entity"]
        if rel_present:
            columns.append("Relationship")
        columns.append("Strength")
        if has_owner:
            columns.append("Owner")
        if has_runtime:
            columns.append("Runtime Impact")
        if has_evidence:
            columns.append("Evidence")

        rows = []
        for it in items:
            # Strength: closer + on an execution path + evidence-backed => stronger. Derived,
            # normalized 0..1, never hardcoded per relation type.
            if is_intersection:
                dist = it["combined_distance"]
                rel = " ∩ ".join(filter(None, [
                    "→".join(it["from_a"]["relation_path"]) or None,
                    "→".join(it["from_b"]["relation_path"]) or None,
                ])) or "(shared)"
            else:
                dist = it["hop"]
                rel = "→".join(it.get("relation_path") or []) or (it.get("via_relation") or "")
            strength = round(1.0 / (1 + dist) * (1.25 if it.get("in_execution") else 1.0)
                             * (1.15 if it.get("has_evidence") else 1.0), 3)
            strength = min(strength, 1.0)
            row = {"Entity": "%s%s" % (it["id"], (" — %s" % it["name"]) if it.get("name") else "")}
            if rel_present:
                row["Relationship"] = rel
            row["Strength"] = strength
            if has_owner:
                row["Owner"] = it.get("class") or "—"
            if has_runtime:
                impact = []
                if it.get("in_execution"): impact.append("execution")
                if it.get("has_lifecycle"): impact.append("lifecycle")
                row["Runtime Impact"] = ", ".join(impact) or "—"
            if has_evidence:
                row["Evidence"] = it.get("evidence") or "—"
            rows.append(row)
        # strongest first
        rows.sort(key=lambda r: -r["Strength"])
        return {"columns": columns, "rows": rows,
                "derived_from": "intersection" if is_intersection else "perspective"}

    # ------------------------------------------------------------------ 4. guided discovery
    def _importance(self, node):
        """Graph importance of a node = its total degree (in + out). A cheap, workbook-derived
        centrality: entities that participate in many relations are more meaningful next steps.
        Cached per build."""
        cache = getattr(self, "_deg_cache", None)
        if cache is None:
            g = self.g
            cache = {}
            for s, rel, t, sc, tc, ev in g.edges:
                cache[s] = cache.get(s, 0) + 1
                cache[t] = cache.get(t, 0) + 1
            self._deg_cache = cache
        return cache.get(self.g._key(node), 0)

    def suggest_next(self, entity, direction="both", limit=8):
        """Guided-discovery: after an entity resolves, propose the most meaningful NEXT
        entities to explore, ranked from the graph — never a fixed list. Ranking combines:
          * hop distance  (closer = more relevant; direct neighbours first)
          * graph importance (degree centrality of the candidate)
          * relation multiplicity (how strongly the anchor connects to it)
        Returns a ranked list of {id, name, class, relation, hop, score}. Deterministic."""
        g = self.g
        if not g.attrs(entity):
            return None
        src = g._key(entity)
        # gather candidates within 2 hops (direct neighbours weighted highest), with the
        # relation used to first reach each and the minimum hop distance.
        seen = {src: (0, None)}
        from collections import deque
        q = deque([(src, 0, None)])
        cand = {}
        while q:
            node, hop, first_rel = q.popleft()
            if hop >= 2:
                continue
            for e in self._neighbors_dir(node, direction):
                nb, rel = e["node"], e["relation"]
                if nb == src:
                    continue
                r0 = first_rel or rel
                if nb not in cand or hop + 1 < cand[nb]["hop"]:
                    cand[nb] = {"hop": hop + 1, "relation": r0,
                                "mult": cand.get(nb, {}).get("mult", 0) + 1}
                else:
                    cand[nb]["mult"] += 1
                if nb not in seen:
                    seen[nb] = (hop + 1, r0)
                    q.append((nb, hop + 1, r0))
        if not cand:
            return {"anchor": {"id": src, "name": g.attrs(src).get("name"), "class": g.attrs(src).get("class")},
                    "suggestions": []}
        # score + rank
        max_imp = max((self._importance(k) for k in cand), default=1) or 1
        ranked = []
        for k, info in cand.items():
            imp = self._importance(k)
            # closer hop, higher importance, higher multiplicity -> stronger suggestion.
            score = round((1.0 / info["hop"]) * (0.5 + 0.5 * imp / max_imp) * (1.0 + 0.1 * (info["mult"] - 1)), 4)
            a = g.attrs(k)
            ranked.append({"id": k, "name": a.get("name"), "class": a.get("class"),
                           "relation": info["relation"], "hop": info["hop"],
                           "importance": imp, "score": min(score, 1.0)})
        ranked.sort(key=lambda x: (-x["score"], x["hop"], x["id"]))
        return {"anchor": {"id": src, "name": g.attrs(src).get("name"), "class": g.attrs(src).get("class")},
                "direction": _norm_dir(direction),
                "suggestions": ranked[:limit]}

    def _neighbors_dir(self, node, direction):
        d = _norm_dir(direction)
        out = []
        for e in self.g.neighbors(node):
            if d == "both" or e["dir"] == d:
                out.append(e)
        return out
