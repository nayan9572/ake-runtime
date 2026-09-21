"""ReachabilityEngine — derivation-layer engine (sibling of InvariantEngine / RuleEngine /
QueryEngine in the design-phase derivation chain, see ake/__init__.py).

Not discovery: Discovery answers "what does the workbook contain" (registries, entity types,
relation types — see FeatureDiscovery / WorkbookModel). This engine answers a different
question: "for a registry class that has no DIRECT edge to some other class, is there a path
between them through other registries?" That's derived knowledge — it isn't in the workbook,
this engine computes it.

Universal by construction: this file contains zero entity type names, relation names, or
registry names. Its only inputs are:
  - model.catalog        the set of registry classes THIS workbook happens to define
  - model.universal_graph the edges THIS workbook happens to have (via UniversalEdgeGraph,
                          a generic graph primitive with no domain vocabulary of its own)
Load a Biology or Finance workbook instead of an engineering one and this engine runs
unchanged — it only ever iterates over whatever classes and edges that workbook produced.

Two-tier, deliberately: an earlier version of this engine materialized one record per
(entity, missing target class) — O(entities x classes). Correct, but wrong shape for a
registry: on a graph with many entities it produces a Derived Registry dominated by
one-off entries nobody will ever query, defeating the point of a registry (a compact set of
reusable, high-value facts). This version instead:

  derive()               Materializes CLASS-LEVEL patterns only — one canonical relation
                          sequence per (source_class, target_class) pair, O(classes^2), not
                          O(entities x classes). Each is real evidence (not a guess): every
                          instance of source_class lacking a direct edge is actually probed,
                          the first hit becomes the example, and how many of them confirmed
                          the same pattern is recorded. This is what belongs in a registry:
                          stable, reusable, deterministic, evidenced.

  path_for(entity, cls)  The "limited runtime search" a query planner may do for one specific
                          entity, on demand — gated behind derive()'s output already knowing
                          the (source_class, target_class) pair is reachable at all, so a
                          planner never blind-searches a pair already known to go nowhere.

Output is additive: both methods return plain data. Nothing here reads model.catalog /
model.universal_graph mutably, and nothing here writes back to either — the Canonical
Registry stays exactly as Discovery built it. Callers decide what to do with the output
(e.g. AKE.derived["reachability"]); this engine has no opinion on storage.

INCREMENTAL REBUILD (documented, not implemented — derive() always does a full rebuild today):
A full rebuild is the only thing implemented, and it's genuinely cheap measured, not assumed
cheap (~0.1s on EBIS's 23 classes, ~4s at a 5000-entity/40-class stress test) — full rebuild on
every workbook load is a reasonable default as-is, not just a placeholder.
The naive incremental rule — "only recompute pairs where source_class or target_class changed"
— is UNSOUND, not just imprecise: a new entity/edge on an INTERMEDIATE class (neither the source
nor target of a given pair) can open a new, or shorter, path between two OTHER classes that
never touched the changed class directly. That rule would silently miss it and serve a stale
record — exactly the "invent/miss a relationship silently" failure mode that must never happen.
Two approaches that are actually sound:
  (a) Dependency tracking — record, per derived pair, every entity/edge its BFS actually visited
      (not just the winning path; the full search frontier, since "no shorter path exists" is
      also a fact those nodes participate in). Recompute a pair iff a changed entity/edge is in
      its dependency set. Correct; costs extra bookkeeping proportional to max_depth's frontier.
  (b) Radius-based invalidation — for each changed entity, do a bounded (max_depth) reverse
      search to find every class it's newly reachable from, and recompute exactly those pairs.
      Correct; the extra pass reuses the same BFS machinery already here, no new primitive.
Recommendation: don't build either until a real workbook's size and reload frequency actually
make full rebuild a measured cost — building incremental correctness speculatively, for a case
that hasn't been shown to need it, is the more likely place to introduce a real bug.
"""

VERSION = "2.0"   # bump on any change to derive()'s algorithm/output shape; stored in every
                  # record (algorithm_version) so an old Derived Registry is diffable against a
                  # new one and never silently mistaken for output of a different algorithm.
                  # 1.0 was the per-entity design (one record per entity, not per class pair);
                  # 2.0 is the class-level design (this file).
TRAVERSAL_STRATEGY = ("forward-edge BFS via UniversalEdgeGraph.shortest_path(); ties (multiple "
                      "equal-length paths, or multiple candidate source entities) broken by "
                      "first-found, where 'first' follows sorted(entity_id) for entity choice "
                      "and workbook edge-insertion order for path choice -- not hashed, not "
                      "randomized, not dependent on PYTHONHASHSEED")


class ReachabilityEngine:
    def __init__(self, model, max_depth=5):
        self.m = model
        self.max_depth = max_depth

    def _class_of(self, eid):
        # Memoised: this is called millions of times during derive() at scale. The node->class
        # map is fixed once the graph is built, so caching it removes the dominant hotspot.
        cache = getattr(self, "_class_cache", None)
        if cache is None:
            cache = {k: v.get("class") for k, v in self.m.universal_graph.node_attrs.items()}
            self._class_cache = cache
        return cache.get(eid)

    def _direct_classes(self, eid):
        """Classes eid already has at least one direct edge to -- nothing to derive for these."""
        g = self.m.universal_graph
        return set(c for e in g.neighbors(eid) if (c := self._class_of(e["node"])))

    def _entities_by_class(self):
        g = self.m.universal_graph
        by_class = {}
        for eid in sorted(g.node_attrs.keys()):          # sorted: stable, deterministic order
            c = self._class_of(eid)
            if c:
                by_class.setdefault(c, []).append(eid)
        return by_class

    def derive(self):
        """One deterministic pass over registry CLASSES, not entities. For each ordered pair
        of classes (source_class, target_class) in this workbook where at least one instance
        of source_class lacks a direct edge to target_class: probe every such instance (BFS,
        bounded by max_depth), keep the first hit as the representative example, and count how
        many instances confirmed the same reachability. One record per confirmed class pair --
        never one record per entity.

        Returns: list of {source_class, target_class, relation_pattern, hops, example_source,
        example_path, confirmed_instances, sampled_instances, algorithm, confidence}, sorted by
        (source_class, target_class) for a stable, diffable output.
        """
        g = self.m.universal_graph
        classes = sorted(self.m.catalog.keys())            # discovered from *this* workbook
        by_class = self._entities_by_class()
        derived = []
        for src_class in classes:
            entities = by_class.get(src_class, [])
            if not entities:
                continue
            for target_class in classes:
                if target_class == src_class:
                    continue
                candidates = [e for e in entities if target_class not in self._direct_classes(e)]
                if not candidates:
                    continue                                # every instance already has this direct
                # SCALE: probe a bounded, deterministic SAMPLE of candidates rather than every
                # one. The record already reports confirmed vs sampled; exhaustive confirmation
                # is O(entities^2) with deep chains (the audit's 741k-BFS hotspot). We sample up
                # to SAMPLE_CAP evenly across the candidate list (stable stride, deterministic),
                # keep the first hit as the representative example, and estimate confirmed_
                # instances by scaling the sample hit-rate back to the full candidate count.
                SAMPLE_CAP = 40
                n = len(candidates)
                if n <= SAMPLE_CAP:
                    sample = candidates
                else:
                    stride = n / float(SAMPLE_CAP)
                    sample = [candidates[int(i * stride)] for i in range(SAMPLE_CAP)]
                example, sample_hits = None, 0
                for e in sample:
                    hit = g.shortest_path(e, lambda nn, tc=target_class: self._class_of(nn) == tc,
                                           max_depth=self.max_depth)
                    if hit:
                        sample_hits += 1
                        if example is None:
                            example = (e, hit)
                if example is None:
                    continue                                # sampled instances don't connect
                # estimate full confirmed count from the sample hit-rate (exact when unsampled)
                confirmed = sample_hits if n <= SAMPLE_CAP else int(round(sample_hits * n / len(sample)))
                example_source, (nodes, rels) = example
                derived.append({
                    "source_class": src_class,
                    "target_class": target_class,
                    "relation_pattern": rels,
                    "hops": len(rels),
                    "example_source": example_source,
                    "example_path": nodes,
                    "confirmed_instances": confirmed,
                    "sampled_instances": len(candidates),
                    "confidence": round(1.0 / len(rels), 2),   # heuristic: farther = lower confidence
                    "algorithm": "ReachabilityEngine.class_level",
                    "algorithm_version": VERSION,
                    "traversal_strategy": TRAVERSAL_STRATEGY,
                    "max_depth": self.max_depth,
                })
        return sorted(derived, key=lambda d: (d["source_class"], d["target_class"]))

    def relation_target_map(self):
        """Derive which target class(es) each relation type points to, from edge data only.
        No hardcoded relation names — purely derived from the workbook's own edges."""
        from collections import defaultdict
        rtm = defaultdict(set)
        for s, rel, t, sc, tc, ev in self.m.universal_edges:
            rtm[rel].add(tc)
        return {k: v for k, v in rtm.items()}

    def _class_pair_set(self, registry):
        """Fast set-based lookup for (source_class, target_class) pairs in the registry."""
        return {(d["source_class"], d["target_class"]) for d in registry}

    def all_reachable(self, entity_id, target_class, class_level_registry=None):
        """Find ALL entities of target_class reachable from entity_id within max_depth.
        Returns list of {node, path_nodes, path_rels} dicts. BFS continues through target
        hits, so chains of connected target-class entities are all found."""
        src_class = self._class_of(entity_id)
        if class_level_registry is not None:
            pairs = (self._class_pair_set(class_level_registry)
                     if not isinstance(class_level_registry, set)
                     else class_level_registry)
            if (src_class, target_class) not in pairs:
                return []
        from collections import deque
        g = self.m.universal_graph
        parent = {entity_id: (None, None)}
        queue = deque([(entity_id, 0)])
        hits = []
        while queue:
            node, d = queue.popleft()
            if d >= self.max_depth:
                continue
            for rel, t, ev in g.fwd.get(node, []):
                if t in parent:
                    continue
                parent[t] = (node, rel)
                if self._class_of(t) == target_class:
                    nodes, rels, cur = [t], [], t
                    while parent[cur][0] is not None:
                        p, r = parent[cur]
                        rels.append(r)
                        nodes.append(p)
                        cur = p
                    nodes.reverse()
                    rels.reverse()
                    hits.append({"node": t, "path_nodes": nodes, "path_rels": rels})
                queue.append((t, d + 1))
        return hits

    def path_for(self, entity_id, target_class, class_level_registry=None):
        """On-demand per-entity resolution -- the bounded runtime search a planner does for one
        specific entity, only when it's actually asked for. If class_level_registry is given
        (typically derive()'s own output), skips searching entirely when that registry already
        shows this (source_class, target_class) pair never connects -- a cheap dict lookup
        instead of a wasted BFS. Returns (node_path, relation_path) or None."""
        src_class = self._class_of(entity_id)
        if class_level_registry is not None:
            known = any(d["source_class"] == src_class and d["target_class"] == target_class
                        for d in class_level_registry)
            if not known:
                return None
        return self.m.universal_graph.shortest_path(
            entity_id, lambda n, tc=target_class: self._class_of(n) == tc, max_depth=self.max_depth)
