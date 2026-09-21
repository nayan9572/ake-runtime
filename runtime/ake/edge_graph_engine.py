"""Universal Edge Graph Engine. Nodes + typed edges + reverse edges + reachability.
Consumes RPDE relational primitives (+ any dedicated relationship edges)."""
from collections import defaultdict, deque
class UniversalEdgeGraph:
    def __init__(self, edges, node_attrs=None, identity=None):
        self.edges = edges; self.fwd = defaultdict(list); self.rev = defaultdict(list)
        self.node_attrs = node_attrs or {}          # id -> {attribute: value}  (property graph)
        self.identity = identity                    # CanonicalIdentity (for routed lookups)
        for s, rel, t, sc, tc, ev in edges:
            self.fwd[s].append((rel, t, ev)); self.rev[t].append((rel, s, ev))
    def _key(self, node):
        """Route any token (display id, canonical key, int pk) to its canonical node key.
        This is the ONE place raw tokens become graph keys — callers never index directly."""
        if self.identity is not None:
            return self.identity.node_key(node)
        return str(node)
    def attrs(self, node): return self.node_attrs.get(self._key(node), {})
    def neighbors(self, node):
        node = self._key(node)
        out = [{"dir": "out", "relation": rel, "node": t, "flow": None, "evidence": ev} for rel, t, ev in self.fwd.get(node, [])]
        out += [{"dir": "in", "relation": rel, "node": s, "flow": None, "evidence": ev} for rel, s, ev in self.rev.get(node, [])]
        return out
    def reachable(self, node, depth=None):
        node = self._key(node)
        seen = {node}; q = deque([(node, 0)])
        while q:
            n, d = q.popleft()
            if depth is not None and d >= depth: continue
            for rel, t, ev in self.fwd.get(n, []):
                if t not in seen: seen.add(t); q.append((t, d + 1))
        return seen

    def shortest_path(self, source, is_target, max_depth=None):
        """BFS from source along forward edges only (matches reachable()'s semantics) for the
        first node satisfying is_target(node_id). Returns (node_path, relation_path) — the
        relation actually used at each hop, for evidence — or None if nothing within max_depth
        satisfies is_target. is_target is a plain predicate: this method has no notion of
        'class', 'registry', or any domain vocabulary — callers decide what counts as a hit.
        Deterministic: self.fwd preserves the order edges were built in (workbook read order),
        so the same source/predicate/depth always returns the same path on the same workbook."""
        if is_target(source):
            return None
        parent = {source: (None, None)}
        q = deque([(source, 0)])
        while q:
            node, d = q.popleft()
            if max_depth is not None and d >= max_depth: continue
            for rel, t, ev in self.fwd.get(node, []):
                if t in parent: continue
                parent[t] = (node, rel)
                if is_target(t):
                    nodes, rels, cur = [t], [], t
                    while parent[cur][0] is not None:
                        p, r = parent[cur]; rels.append(r); nodes.append(p); cur = p
                    nodes.reverse(); rels.reverse()
                    return nodes, rels
                q.append((t, d + 1))
        return None

    def path_between(self, source, target, max_depth=6):
        """Shortest path between TWO specific nodes, traversing edges in BOTH directions
        (forward and reverse). This is what makes context a source node rather than a search
        boundary: a target in another registry is reachable across the graph even when the
        only connection runs backward along an FK (e.g. Brand <- Product <- OrderItem <-
        Order). Reuses the already-stored fwd/rev maps -- no new structure, no domain
        vocabulary. Returns a list of hop dicts [{from, to, relation, direction, evidence}],
        or None if unreachable within max_depth. Deterministic (fwd then rev, build order)."""
        src, tgt = self._key(source), self._key(target)
        if src == tgt:
            return []
        # parent[node] = (prev_node, relation, direction, evidence)
        parent = {src: (None, None, None, None)}
        q = deque([(src, 0)])
        while q:
            node, d = q.popleft()
            if d >= max_depth:
                continue
            # step forward (node -> t) and backward (node <- s), recording which way we went
            steps = [("out", rel, t, ev) for rel, t, ev in self.fwd.get(node, [])]
            steps += [("in", rel, s, ev) for rel, s, ev in self.rev.get(node, [])]
            for direction, rel, nb, ev in steps:
                if nb in parent:
                    continue
                parent[nb] = (node, rel, direction, ev)
                if nb == tgt:
                    # reconstruct hop chain from tgt back to src
                    hops = []
                    cur = nb
                    while parent[cur][0] is not None:
                        p, r, dirn, e = parent[cur]
                        hops.append({"from": p, "to": cur, "relation": r,
                                     "direction": dirn, "evidence": e})
                        cur = p
                    hops.reverse()
                    return hops
                q.append((nb, d + 1))
        return None
