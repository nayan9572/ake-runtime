from .workbook_runtime import WorkbookModel
from .feature_discovery import FeatureDiscovery
from .discovery_primitives import DiscoveryPrimitives
from .invariant_engine import InvariantEngine
from .rule_engine import RuleEngine
from .query_engine import QueryEngine
from .runtime_primitives import RuntimePrimitives
from .algorithm_generator import AlgorithmGenerator
from .runtime_engine import RuntimeEngine
from .lifecycle import LifecyclePopulator
from .algorithm_derivation import AlgorithmDerivation, RelationInventory, QUERY_DEFINITIONS
from .capability_matrix import CapabilityMatrix, CAPABILITY_UNIVERSE
from .discovery_engine import DiscoveryEngine
from .entity_resolver import EntityResolver
from .query_discovery import QueryDiscovery
from .reachability_engine import ReachabilityEngine
from .semantic_promotion import SemanticPromotion
from .capability_synthesis import canonicalize

class AKE:
    """Engineering Spreadsheet Runtime. Full derivation chain + runtime, all workbook-driven."""
    def __init__(self, workbook_path, invariant_threshold=1.0):
        self.model = WorkbookModel(workbook_path)
        self.features = FeatureDiscovery(self.model)          # RP-00..03 (corrected M0)
        self.discovery = DiscoveryPrimitives(self.model)
        self.invariants = InvariantEngine(self.model, invariant_threshold)  # RP-04
        self.rules = RuleEngine(self.model)
        self.queries = QueryEngine(self.model)
        self.generator = AlgorithmGenerator(self.model)
        self.engine = RuntimeEngine(self.model, facade=self)
        # Promoted semantic objects (logical projections over Canonical Runtime Knowledge,
        # ake/semantic_promotion.py -- never a second graph/registry) are resolvable exactly
        # like any physical entity, so EntityResolver gets a reference too.
        self.promotions = SemanticPromotion(self.model)
        # Language layer: one Vocabulary Registry shared by the Language Registry (grammar concepts)
        # and the Workbook Knowledge Registry (workbook-derived ENTITY/ATTRIBUTE/RELATION terms).
        # Knowledge Registry harvests EXISTING owners (node_attrs, hdr, _rel_source) into the
        # vocabulary — no new discovery, no grammar mutation.
        from .vocabulary_registry import VocabularyRegistry
        from .language_registry import UniversalLanguageRegistry
        from .workbook_knowledge_registry import WorkbookKnowledgeRegistry
        self.vocabulary = VocabularyRegistry()
        self.language = UniversalLanguageRegistry(vocabulary=self.vocabulary)
        self.knowledge = WorkbookKnowledgeRegistry(self.model, self.vocabulary)
        self._knowledge_summary = self.knowledge.build()
        # Resolver combines grammar + workbook vocabulary + entity resolution (Stage 5).
        self.resolver = EntityResolver(self.model, self.promotions,
                                       language=self.language, vocabulary=self.vocabulary)
        # Canonical Intent Builder (Stage 6): natural query -> semantic intent (roles + semantic
        # operations). Carries NO opcodes; AlgorithmDerivation translates ops -> plan at Stage 7.
        from .canonical_intent import CanonicalIntentBuilder
        from .tokenizer import Tokenizer
        # Stage 8: Tokenizer (lexical front-end) — consumes the vocabulary read-only to preserve
        # multi-word phrases; resolves/classifies nothing. Feeds the builder.
        self.tokenizer = Tokenizer(vocabulary=self.vocabulary)
        self.intent_builder = CanonicalIntentBuilder(self.resolver, tokenizer=self.tokenizer)
        # Stage 7: the single planning authority. AlgorithmDerivation.derive_from_intent(intent)
        # produces the semantic operations + opcode plan. No separate planner is exposed.
        from .algorithm_derivation import AlgorithmDerivation
        self.planner = AlgorithmDerivation(self.model)
        self._diagnosis = None  # lazy: built only when diagnosis is first requested
        self.qdiscovery = QueryDiscovery(self.model)
        # Multi-hop discovery: class-level reachability + relation→target-class mapping,
        # both derived from the workbook's own edges at boot. Cost: ~0.1s on EBIS v17.
        self._reachability = ReachabilityEngine(self.model)
        self.model._reachability_registry = self._reachability.derive()
        self.model._reachability_pairs = self._reachability._class_pair_set(
            self.model._reachability_registry)
        self.model._relation_target_map = self._reachability.relation_target_map()
        # Workbook-derived query definitions: one GET_<REL> per relation in the graph.
        # Merged with explicit definitions from query_definitions.json. This makes
        # answer("GET_HABITAT", "SPE-001") work on a biology workbook without code change.
        from .algorithm_derivation import derive_workbook_queries
        self.model._query_definitions = derive_workbook_queries(self.model)

    # --- design-phase derivation chain (each stage -> canonical registry) ---
    def discover_features(self): return self.features.discover_features()
    def closure(self): return self.features.closure()
    def derive_invariants(self): return self.invariants.discover()                      # Invariant Registry
    def derive_rules(self): return self.rules.derive(self.derive_invariants())           # Rule Registry
    def derive_queries(self): return self.queries.derive(self.derive_rules())            # Universal Query Registry
    def derive_all(self):
        inv = self.derive_invariants(); rul = self.rules.derive(inv); qry = self.queries.derive(rul)
        return {"invariants": inv, "rules": rul, "queries": qry}

    # --- entity-first runtime (Entity != Query) ---
    def resolve(self, token): return self.resolver.resolve(token)
    def applicable_queries(self, entity): return self.qdiscovery.applicable(entity)
    def run_query(self, entity, query):
        req = {"target": entity["id"]}; req.update(query.get("bind", {}))
        plan = [(fn, dict(query["bind"]) if fn.startswith("walk_") else {}) for fn in query["pipeline"]]
        out = self.engine.run(plan, req); out["query_name"] = query["name"]; out["pipeline"] = query["pipeline"]
        return out
    def query_entity(self, token, prefer=None):
        ent = self.resolve(token)
        if not ent.get("id"): return {"entity": ent, "note": "unresolved"}
        aqs = self.applicable_queries(ent); sel = self.qdiscovery.select(aqs, prefer)
        return {"entity": ent, "applicable": aqs, "selected": sel,
                "result": self.run_query(ent, sel) if sel else None}

    # --- runtime ---
    def observe(self, entity_id): return self.discovery.observe(entity_id)
    def registry_universe(self):
        ru = DiscoveryEngine(self.model).registry_universe()
        # Enrich registries with entity names and prefix (for discovery hub navigation)
        g = self.model.universal_graph
        for i, reg in enumerate(ru.get("registries", [])):
            et = ru["entity_types"][i] if i < len(ru.get("entity_types", [])) else {}
            prefix = et.get("prefix", "")
            reg["prefix"] = prefix
            # Top entity names for preview (first 6 by workbook order)
            names = []
            for eid, attrs in g.node_attrs.items():
                if attrs.get("class") == reg["name"]:
                    names.append({"id": eid, "name": attrs.get("name", "")})
                    if len(names) >= 6:
                        break
            reg["preview"] = names
        # Enrich relation types with edge counts and classify by derivation source.
        # No string heuristics — classification comes from HOW the edge was derived:
        #   "declared" = from a FK column with entity IDs or from the relationship sheet
        #   "inferred" = from a prose column where text names were resolved to entities
        from collections import Counter
        rel_counts = Counter(r for _, r, _, _, _, _ in self.model.universal_edges)
        rel_source = getattr(self.model, '_rel_source', {})
        details = []
        for r in ru.get("relation_types", []):
            source = rel_source.get(r, "declared")
            details.append({
                "name": r, "edges": rel_counts.get(r, 0),
                "group": "relation" if source == "declared" else "reference",
            })
        ru["relation_details"] = details
        return ru
    def discovery_report(self): return DiscoveryEngine(self.model).report()
    def overview(self):
        ru = self.registry_universe()
        return {"registries": ru["totals"]["registries"], "total_entities": ru["totals"]["entities"],
                "entity_types": {e["prefix"]: {"prefix": e["prefix"], "count": e["count"], "examples": e["examples"]}
                                 for e in ru["entity_types"]},
                "capability_categories": [c for c, ok in ru["capabilities"].items() if ok],
                "capabilities": ru["capabilities"],
                "question_types": len(sum(CAPABILITY_UNIVERSE.values(), [])),
                "answerable": self.capability_universe()["answerable_somewhere"]}
    def list_entities(self, prefix):
        prefix = str(prefix).upper().rstrip("-")
        return [rr[0] for reg, mt in self.model.catalog.items() if mt["role"].startswith("Owner")
                for rr in self.model.rows(reg) if rr and rr[0] and str(rr[0]).split("-")[0] == prefix]

    # ---- Discovery contexts -------------------------------------------------
    # A "context" (AKE> handler / store / fuel / relation) is NOT a new object: it is a view
    # onto the registries the loader ALREADY derived into model.catalog (role + prefix).
    # These helpers read that catalog directly — no parallel context model is created.
    RELATION_CONTEXT = "relation"

    def _owner_registries(self):
        return [(reg, mt) for reg, mt in self.model.catalog.items()
                if mt.get("role", "").startswith("Owner")]

    def _entity_noun(self, role):
        import re as _r
        m = _r.search(r"entity:\s*([A-Za-z0-9 _-]+)\)", role or "")
        return m.group(1).strip() if m else None

    def contexts(self):
        """Discovery contexts for the console selector, derived from the existing catalog.
        Each maps a registry to its entity noun + prefix. The special 'relation' mode is
        always appended. Ordered by entity count."""
        out = []
        for reg, mt in self._owner_registries():
            noun = self._entity_noun(mt["role"]) or reg.split()[0]
            pfx = mt.get("prefix", "")
            pfx = "" if pfx in (None, "\u2014") else pfx
            out.append({"token": noun.lower(), "registry": reg, "label": noun,
                        "prefix": pfx, "count": sum(1 for r in self.model.rows(reg) if r and r[0]),
                        "kind": "registry"})
        out.sort(key=lambda c: -c["count"])
        out.append({"token": self.RELATION_CONTEXT, "registry": None, "label": "Relation",
                    "prefix": "", "count": 0, "kind": "relation"})
        return out

    def resolve_context(self, word):
        """Map a free word to a context, dynamically, against the existing catalog: entity
        noun, registry name, or pk prefix (singular/startswith tolerant). Returns the
        registry name, the 'relation' sentinel, or None."""
        w = str(word).strip().lower()
        if not w:
            return None
        if w in (self.RELATION_CONTEXT, "relations", "rel", "edge", "edges"):
            return self.RELATION_CONTEXT
        def _sing(s):
            return s[:-3] + "y" if s.endswith("ies") else (s[:-1] if s.endswith("s") and not s.endswith("ss") else s)
        ws = _sing(w)
        best = None
        for reg, mt in self._owner_registries():
            noun = (self._entity_noun(mt["role"]) or reg.split()[0]).lower()
            pfx = str(mt.get("prefix", "")).lower()
            name = reg.lower()
            cands = {noun, _sing(noun), name, name.replace(" registry", "").strip(),
                     _sing(reg.split()[0].lower())}
            if pfx and pfx != "\u2014":
                cands.add(pfx)
            if w in cands or ws in cands:
                return reg
            if best is None and (noun.startswith(w) or name.startswith(w)
                                 or _sing(reg.split()[0].lower()).startswith(ws)):
                best = reg
        return best

    def query_in_context(self, registry, term):
        """Scope a query to one registry (filter its entities by id/name). Exact id/name
        hits first, then partial. Returns [{id, name, class}]."""
        term_l = str(term).strip().lower()
        rows = [r for r in self.model.rows(registry) if r and r[0]]
        if not term_l:
            hits = rows
        else:
            exact = [r for r in rows if str(r[0]).lower() == term_l
                     or (len(r) > 1 and str(r[1]).lower() == term_l)]
            partial = [r for r in rows if r not in exact and
                       (term_l in str(r[0]).lower() or (len(r) > 1 and term_l in str(r[1]).lower()))]
            hits = exact + partial
        return [{"id": str(r[0]), "name": (r[1] if len(r) > 1 else None), "class": registry}
                for r in hits]

    def discovery_chain(self, entity_id, max_per_group=8):
        """The outward discovery chain for an entity: its identity, then related entities
        grouped by (direction, relation, class), ordered by group size. Built structurally
        from the universal graph, so it reflects whatever relations the workbook has. This is
        the one genuinely-new behaviour (not derivable from the old single-entity view)."""
        g = self.model.universal_graph
        attrs = g.attrs(entity_id)
        if not attrs:
            return None
        groups, counts = {}, {}
        for e in g.neighbors(entity_id):
            tclass = g.attrs(e["node"]).get("class") or "?"
            key = (e["dir"], e["relation"], tclass)
            counts[key] = counts.get(key, 0) + 1
            groups.setdefault(key, [])
            if len(groups[key]) < max_per_group:
                groups[key].append({"id": e["node"], "name": g.attrs(e["node"]).get("name"), "class": tclass})
        chain = [{"direction": k[0], "relation": k[1], "target_class": k[2],
                  "count": counts[k], "items": groups[k]}
                 for k in sorted(groups, key=lambda k: (-counts[k], k[0], k[1]))]
        return {"entity": str(entity_id),
                "identity": {"id": str(entity_id), "name": attrs.get("name"), "class": attrs.get("class")},
                "chain": chain}

    def relation_view(self, entity_id):
        """Relation-mode discovery for an entity: incoming / outgoing / evidence buckets."""
        g = self.model.universal_graph
        attrs = g.attrs(entity_id)
        if not attrs:
            return None
        incoming, outgoing = [], []
        for e in g.neighbors(entity_id):
            row = {"id": e["node"], "name": g.attrs(e["node"]).get("name"),
                   "relation": e["relation"], "class": g.attrs(e["node"]).get("class")}
            (outgoing if e["dir"] == "out" else incoming).append(row)
        return {"entity": str(entity_id),
                "identity": {"id": str(entity_id), "name": attrs.get("name"), "class": attrs.get("class")},
                "incoming": incoming, "outgoing": outgoing,
                "evidence": attrs.get("evidence"), "has_evidence": bool(attrs.get("has_Evidence"))}

    # ---- Phase-2 semantic engine (multi-hop, all on the already-derived graph) ----
    def _perspective_engine(self):
        eng = getattr(self, "_persp_eng", None)
        if eng is None:
            from .semantic_perspective import SemanticPerspectiveEngine
            eng = SemanticPerspectiveEngine(self.model)
            self._persp_eng = eng
        return eng

    def perspective(self, entity, direction="both", max_hops=6):
        """Multi-hop semantic perspective of one entity (transitive traversal on the derived
        graph, layered by hop + class). Never re-reads the workbook."""
        e = self.resolve(entity)
        eid = e.get("id") or entity
        return self._perspective_engine().perspective(eid, direction=direction, max_hops=max_hops)

    def intersect(self, a, b, direction="out", max_hops=6):
        """Directed two-perspective intersection (A→…, B→… ; direction chooses drives vs
        driven-by). Fuel→CA50 and CA50→Fuel are different questions."""
        ra, rb = self.resolve(a), self.resolve(b)
        return self._perspective_engine().intersect(ra.get("id") or a, rb.get("id") or b,
                                                     direction=direction, max_hops=max_hops)

    def derive_table(self, view):
        """Derive a result table (columns chosen from what the traversal found) from a
        perspective or intersection result."""
        return self._perspective_engine().derive_table(view)

    # ---- Evidence tiering (classify existing evidence, not a new engine) ----
    # Tiers, strongest first. Derived from graph facts (edge source, canonical identity,
    # value/name/lexical match) — never hardcoded relation or registry names.
    EVIDENCE_TIERS = {
        "L1_structural": 1.00,   # FK / PK / composite-FK (declared structural edge)
        "L2_declared":   0.90,   # declared relationship registry / catalog relation
        "L3_canonical":  0.80,   # same canonical identity / shared reference / alias
        "L4_value":      0.62,   # exact value match or exact name match (no structural link)
        "L5_lexical":    0.34,   # lexical similarity / typo-corrected / synonym (LOWEST; not "semantic")
    }

    def _tier_for_relation(self, relation):
        """Classify one edge's evidence tier from the relation's derivation source, which the
        loader already recorded in model._rel_source ('declared' = FK/relationship sheet ->
        structural; 'inferred' = prose name resolution -> value/lexical). Graph-derived."""
        src = getattr(self.model, "_rel_source", {}).get(relation)
        if src == "declared":
            return "L1_structural"
        if src == "inferred":
            return "L4_value"
        return "L4_value"

    def _hop_evidence(self, hop):
        """Evidence record for a single path hop: its tier, the human reason (FK/relation +
        the workbook evidence locus), and the tier's base confidence."""
        tier = self._tier_for_relation(hop["relation"])
        conf = self.EVIDENCE_TIERS.get(tier, 0.3)
        # human-readable reason, derived — names come from the data, never hardcoded
        arrow = "→" if hop["direction"] == "out" else "←"
        reason = "%s %s %s %s (%s)" % (hop["from"], arrow, hop["relation"], hop["to"],
                                       "structural/FK" if tier == "L1_structural" else "reference")
        return {"tier": tier, "confidence": conf, "reason": reason,
                "relation": hop["relation"], "direction": hop["direction"],
                "evidence": hop["evidence"]}

    def scan_state_contract(self, engine_contract, runtime_hooks=None, static_only=False):
        """Run the generic engine-agnostic State-Contract Scanner against ANY
        engine's declared contract (state ownership, writers, mirror self-heal,
        schema, propagation, duplicate-authority). AKE owns the scanner; the
        engine's own owner (e.g. the EBIS orchestrator) owns the engine. The
        scanner core is contract-driven — no engine-specific names — so the same
        AKE can verify a future engine mounted on top of it by supplying only that
        engine's contract evidence. See ake/state_contract_scanner.py."""
        from .state_contract_scanner import StateContractScanner
        return StateContractScanner(engine_contract, runtime_hooks=runtime_hooks).scan(static_only=static_only)

    def diagnose(self, query):
        """Lazy architecture diagnosis: layer-by-layer validation + health score for a query.
        Owned by ArchitectureDiagnosis (single validation owner); built on first use so the normal
        Ask path stays fast and clean. Returns a diagnosis model; renders nothing."""
        if self._diagnosis is None:
            from .architecture_diagnosis import ArchitectureDiagnosis
            self._diagnosis = ArchitectureDiagnosis(self)
        return self._diagnosis.diagnose(query)

    def ask_pipeline(self, query):
        """THE single end-to-end pipeline (Stages 1-8), one entry point for the dashboard's single
        prompt. Every stage is an existing owner; this method only chains them, adding no grammar,
        planning, or execution logic of its own:

          query -> Tokenizer -> (Language + Workbook vocab via Resolver.classify inside the
          builder) -> CanonicalIntent (roles) -> AlgorithmDerivation.derive_from_intent
          (semantic operations + opcode plan) -> RuntimeEngine.run -> result + evidence.

        Returns a transparent record of every stage for explainability. No direct RuntimeEngine
        call lives in the UI — the UI calls this one method."""
        toks = [t.as_dict() for t in self.tokenizer.tokenize(query)]
        intent = self.intent_builder.build(query)
        derived = self.planner.derive_from_intent(intent)          # {operations, plan, target}
        target = derived.get("target")
        out = None
        if derived["plan"]:
            req = {"target": target} if target else {}
            out = self.engine.run(derived["plan"], req)
        # answer: prefer the discovery output produced BY THE PLANNED PLAN (DISCOVER op ran the
        # Discovery Engine as a downstream consumer). Only fall back to a direct discover() if the
        # plan produced none — this keeps Discovery inside the one pipeline, not a parallel call.
        answer = None
        if out and out.get("discovery"):
            answer = out["discovery"]
        elif target:
            answer = self.discover(target)
        return {"query": query, "tokens": toks, "intent": intent.as_dict(),
                "operations": derived["operations"], "plan": [[n, kw] for n, kw in derived["plan"]],
                "result": out, "answer": answer}

    def discover(self, query, context=None, max_hops=6, limit_suggest=6):
        """Universal intent-driven discovery — the single pipeline. Context is only the SOURCE
        node, never a search boundary; the query is resolved GLOBALLY across the whole graph.

        Pipeline (all existing owners, rewired):
          resolve(query) [+ typo/synonym in resolver]  -> global target
            -> if ambiguous: ranked candidates (disambiguation), no guess
            -> graph.path_between(context, target) [bidirectional]  -> multi-hop path
            -> per-hop evidence tiering (L1..L5) + path confidence  (from explain sources)
            -> suggest_next(target)                                  -> next exploration
        Returns a structured result every surface renders. No registry/entity/prefix literals.
        """
        # 1) GLOBAL resolution of the query (never scoped to a registry).
        r = self.resolve(query)
        if not r.get("id"):
            if r.get("candidates"):
                # 2) Disambiguation: ranked candidates with a confidence hint, never a guess.
                cands = [{"id": c["id"], "name": c.get("name"), "class": c.get("class"),
                          "confidence": round(0.9 - 0.05 * i, 2)}
                         for i, c in enumerate(r["candidates"][:8])]
                return {"status": "ambiguous", "query": query, "context": context,
                        "candidates": cands}
            # unknown -> closest entities (never a bare "no matches")
            hits = self.search(query)
            closest = [{"id": h[0], "name": h[1]} for h in hits[:limit_suggest]] if hits else \
                      [{"id": s["id"], "name": s["name"]} for s in
                       self.suggest_next(query, limit=limit_suggest).get("suggestions", [])]
            return {"status": "unknown", "query": query, "context": context, "closest": closest}

        target = r["id"]
        result = {"status": "resolved", "query": query,
                  "target": {"id": target, "name": self.model.universal_graph.attrs(target).get("name"),
                             "class": self.model.universal_graph.attrs(target).get("class")}}

        # 3) If a context (source) is given, find the bidirectional path source -> target.
        if context:
            cr = self.resolve(context)
            if cr.get("id"):
                src = cr["id"]
                result["source"] = {"id": src,
                                    "name": self.model.universal_graph.attrs(src).get("name"),
                                    "class": self.model.universal_graph.attrs(src).get("class")}
                hops = self.model.universal_graph.path_between(src, target, max_depth=max_hops)
                if hops is None:
                    result["path"] = None
                    result["reachable"] = False
                elif hops == []:
                    result["path"] = []
                    result["reachable"] = True
                    result["distance"] = 0
                else:
                    ev_hops = [self._hop_evidence(h) for h in hops]
                    # 4) Path confidence = product of hop confidences (weakest link dominates),
                    #    so a single L5 hop can't masquerade as an all-structural path.
                    conf = 1.0
                    for e in ev_hops:
                        conf *= e["confidence"]
                    result["path"] = [{"from": h["from"], "to": h["to"],
                                       "relation": h["relation"], "direction": h["direction"],
                                       "tier": e["tier"], "confidence": e["confidence"],
                                       "reason": e["reason"], "evidence": e["evidence"]}
                                      for h, e in zip(hops, ev_hops)]
                    result["reachable"] = True
                    result["distance"] = len(hops)
                    result["confidence"] = round(conf, 3)
                    result["weakest_tier"] = min((e["tier"] for e in ev_hops),
                                                 key=lambda t: self.EVIDENCE_TIERS.get(t, 0))
            else:
                result["source"] = None

        # 5) Next-exploration suggestions from the target (existing engine).
        sug = self.suggest_next(target, limit=limit_suggest)
        result["suggestions"] = sug.get("suggestions", []) if sug else []
        return result

    def suggest_next(self, entity, direction="both", limit=8):
        """Guided-discovery suggestions: after an entity resolves, the ranked next entities
        worth exploring, derived from the graph neighbourhood (hop + importance + relation
        multiplicity). Never a fixed list. If the token is ambiguous, returns candidates; if
        unknown, returns the closest workbook entities so the user is never dead-ended."""
        r = self.resolve(entity)
        if r.get("id"):
            sug = self._perspective_engine().suggest_next(r["id"], direction=direction, limit=limit)
            if sug is not None:
                sug["resolved"] = True
                return sug
        if r.get("candidates"):
            return {"resolved": False, "reason": "ambiguous", "anchor": None,
                    "suggestions": [{"id": c["id"], "name": c.get("name"), "class": c.get("class"),
                                     "relation": None, "hop": None, "score": None}
                                    for c in r["candidates"][:limit]]}
        hits = self.search(entity)
        if not hits:
            # no name overlap at all — still never dead-end: offer the most connected
            # (important) entities in the workbook as discovery entry points.
            eng = self._perspective_engine()
            g = self.model.universal_graph
            ranked = sorted(g.node_attrs.keys(), key=lambda k: -eng._importance(k))[:limit]
            hits = [(k, g.attrs(k).get("name")) for k in ranked]
        return {"resolved": False, "reason": "unknown", "anchor": None,
                "suggestions": [{"id": h[0], "name": h[1], "class": None,
                                 "relation": None, "hop": None, "score": None} for h in hits[:limit]]}

    def _name_search_index(self):
        """Lazily-built, cached search index for O(1) exact-name and fast prefix lookup.
        Built once from owner rows (like the canonical identity index); IDs were already
        indexed, names were not — at 100k entities a name scan was ~800ms (audit F-C). Maps
        lowercased name -> list of (id, name) and lowercased id -> (id, name)."""
        idx = getattr(self, "_nsi", None)
        if idx is not None:
            return idx
        by_name = {}
        by_id = {}
        ordered = []   # (id, name) in workbook order, for substring fallback without re-walking catalog
        for reg, mt in self.model.catalog.items():
            if not mt["role"].startswith("Owner"):
                continue
            for rr in self.model.rows(reg):
                if not (rr and rr[0]):
                    continue
                eid = str(rr[0]); name = rr[1] if len(rr) > 1 else ""
                pair = (eid, name)
                by_id[eid.lower()] = pair
                if name not in (None, ""):
                    by_name.setdefault(str(name).lower(), []).append(pair)
                ordered.append((pair, [str(v).lower() for v in rr if v not in (None, "")]))
        idx = {"by_name": by_name, "by_id": by_id, "ordered": ordered}
        self._nsi = idx
        return idx

    def search(self, term):
        """Owner-row text search, RANKED so an exact canonical-ID or exact-name match is
        never buried below substring matches (previously the 50-row cap could drop the
        exact entity a user typed). Rank order: exact id/name > id/name prefix > word-start
        in any field > substring anywhere. Ties keep workbook order (stable).

        Backed by a name/id index (built once): exact id/name and prefix hits are served from
        the index; only genuine substring queries fall back to a single ordered scan."""
        raw = str(term).strip()
        term = raw.lower()
        if not term:
            return []
        nsi = self._name_search_index()
        # Fast path: exact id or exact name — served entirely from the index, no scan at all.
        # This is the common interactive case and now costs O(1) instead of an owner-row walk.
        exact = []
        if term in nsi["by_id"]:
            exact.append(nsi["by_id"][term])
        for pair in nsi["by_name"].get(term, []):
            if pair not in exact:
                exact.append(pair)
        if exact:
            return exact[:50]
        # Otherwise a ranked scan over the prebuilt ordered list (values pre-lowercased once at
        # index build, no catalog re-walk). Only substring/word-start queries reach here.
        scored = []
        order = 0
        for pair, low in nsi["ordered"]:
            eid, name = pair
            if not any(term in f for f in low):
                continue
            eid_l = eid.lower(); name_l = str(name).lower()
            if eid_l == term or name_l == term:
                rank = 0
            elif eid_l.startswith(term) or name_l.startswith(term):
                rank = 1
            elif any(f.startswith(term) or (" " + term) in f for f in low):
                rank = 2
            else:
                rank = 3
            scored.append((rank, order, (eid, name)))
            order += 1
        scored.sort(key=lambda x: (x[0], x[1]))
        return [p for _, _, p in scored[:50]]

    def _search_legacy(self, term):
        raw = str(term).strip()
        term = raw.lower()
        scored = []  # (rank, order, (id, name))
        order = 0
        for reg, mt in self.model.catalog.items():
            if not mt["role"].startswith("Owner"):
                continue
            for rr in self.model.rows(reg):
                if not (rr and rr[0]):
                    continue
                fields = [str(v) for v in rr if v not in (None, "")]
                low = [f.lower() for f in fields]
                if not any(term in f for f in low):
                    continue
                eid = str(rr[0])
                name = rr[1] if len(rr) > 1 else ""
                eid_l = eid.lower()
                name_l = str(name).lower()
                if eid_l == term or name_l == term:
                    rank = 0                       # exact id/name
                elif eid_l.startswith(term) or name_l.startswith(term):
                    rank = 1                       # id/name prefix
                elif any(f.startswith(term) or (" " + term) in f for f in low):
                    rank = 2                       # word-start in some field
                else:
                    rank = 3                       # substring anywhere
                scored.append((rank, order, (eid, name)))
                order += 1
        scored.sort(key=lambda t: (t[0], t[1]))
        return [pair for _, _, pair in scored[:50]]

    def list_by_relation(self, rel):
        """Return all edges of a given relation type. Used by the dashboard when a
        relation chip is clicked — this is graph traversal, not text search."""
        g = self.model.universal_graph
        edges = []
        seen = set()
        for src, relation, tgt, src_cls, tgt_cls, ev in self.model.universal_edges:
            if relation == rel and (src, tgt) not in seen:
                seen.add((src, tgt))
                src_name = g.attrs(src).get("name")
                tgt_name = g.attrs(tgt).get("name")
                edges.append({
                    "source": src, "source_name": src_name,
                    "target": tgt, "target_name": tgt_name,
                    "relation": rel, "evidence": ev,
                })
        return edges
    def describe(self, token):
        e = self.resolve(token)
        if not e.get("id"): return {"note": "unresolved", "candidates": e.get("candidates", [])}
        cm = self.capabilities(token)["capabilities"]
        avail = [i["question"] for cat in cm.values() for i in cat if i["supported"]]
        unavail = [i["question"] for cat in cm.values() for i in cat if not i["supported"]]
        a = self.entity_attrs(e["id"])
        return {"id": e["id"], "class": e["class"], "name": a.get("name"),
                "available_queries": avail, "unavailable_queries": unavail}
    def capabilities(self, token):
        e = self.resolve(token); return CapabilityMatrix(self.model).for_entity(e["id"]) if e.get("id") else {}
    def capability_universe(self): return CapabilityMatrix(self.model).workbook_universe()
    def relation_inventory(self, token):
        e = self.resolve(token); return RelationInventory(self.model).inventory(e["id"]) if e.get("id") else {}
    def answer(self, query_name, token):
        e = self.resolve(token)
        if not e.get("id"): return {"entity": token, "note": "unresolved"}
        if query_name not in getattr(self.model, '_query_definitions', QUERY_DEFINITIONS):
            return {"entity": e["id"], "query": query_name, "result": None,
                    "note": "'%s' is not a defined query (see QUERY_DEFINITIONS)" % query_name}
        ad = AlgorithmDerivation(self.model)
        plan = ad.derive_for_entity(query_name, e["id"])     # path-aware planning
        out = self.engine.run(plan, {"target": e["id"]})
        out["query"] = query_name
        out["derived_sequence"] = [fn for fn, _ in plan]
        # Expose the plan's kwargs so consumers see the discovery path, not just the opcode name
        out["plan"] = [{"opcode": fn, **kw} for fn, kw in plan]
        return out
    def applicable_canonical_queries(self, token):
        e = self.resolve(token); return AlgorithmDerivation(self.model).applicable_queries(e["id"]) if e.get("id") else []
    def lifecycle(self, token):
        ent = self.resolve(token)
        return LifecyclePopulator(self.model).populate(ent["id"]) if ent.get("id") else {"entity": token, "note": "unresolved"}
    def ask(self, request):
        qid, seq, plan = self.generator.compile(request)
        out = self.engine.run(plan, request); out["query_type"] = qid; out["opcode_pipeline"] = seq
        return out

    # --- multi-hop discovery (wired to ReachabilityEngine, universal) ---
    def reachable_relations(self, eid):
        """Relations reachable via multi-hop from this entity's class, excluding those already
        available as direct edges. Uses the LAST HOP of each class-level reachability path as
        the semantically meaningful relation — "handler" from Feature→...→Handler, not every
        relation that Handler entities happen to have. No hardcoded relation names."""
        direct = {e["relation"] for e in self.model.universal_graph.neighbors(eid)}
        src_class = self.model.universal_graph.attrs(eid).get("class")
        if not src_class:
            return []
        extra = set()
        for d in self.model._reachability_registry:
            if d["source_class"] == src_class and d["relation_pattern"]:
                last_rel = d["relation_pattern"][-1]
                if last_rel not in direct:
                    extra.add(last_rel)
        return sorted(extra)

    def discover_relation(self, eid, rel):
        """Multi-hop discovery for a specific relation from a specific entity. Returns results
        in the same format as universal_graph.neighbors() entries, so every consumer (shell,
        dashboard, API) can treat them identically to direct edges. Evidence carries the full
        discovery path for transparency. Target classes are identified by matching the last hop
        of known reachability paths — the same derivation reachable_relations uses."""
        src_class = self.model.universal_graph.attrs(eid).get("class")
        if not src_class:
            return []
        # Find which target classes this relation is the last hop for (from this source class)
        target_classes = set()
        for d in self.model._reachability_registry:
            if d["source_class"] == src_class and d["relation_pattern"]:
                if d["relation_pattern"][-1] == rel:
                    target_classes.add(d["target_class"])
        # Also check direct edge targets (relation may exist as both direct and multi-hop)
        target_classes |= self.model._relation_target_map.get(rel, set())
        if not target_classes:
            return []
        results = []
        for tc in target_classes:
            hits = self._reachability.all_reachable(
                eid, tc, self.model._reachability_pairs)
            for hit in hits:
                pn, pr = hit["path_nodes"], hit["path_rels"]
                trail = " → ".join("%s -%s→" % (pn[i], pr[i]) for i in range(len(pr)))
                results.append({
                    "dir": "discovered", "relation": rel, "node": hit["node"],
                    "flow": None,
                    "evidence": "path: %s %s" % (trail, hit["node"]),
                })
        return results

    def entity_attrs(self, eid):
        """Single source of truth for an entity's attribute view — physical (read straight
        off the Universal Property Graph) or promoted (a logical projection, never a second
        graph — ake/semantic_promotion.py). Rendering reads this instead of reaching into
        model.universal_graph directly, so a promoted semantic object gets the identical
        treatment as a physical one (Capability Synthesis Contract v2 §7/§9)."""
        if self.promotions.is_promoted(eid):
            return self.promotions.entity_view(eid) or {}
        return self.model.universal_graph.attrs(eid)

    def entity_source_row(self, eid):
        """Same dispatch as entity_attrs(), for the source-row view."""
        if self.promotions.is_promoted(eid):
            return self.promotions.source_row(eid) or {}
        cls = self.model.owner_sheet(eid)
        row = self.model.owner_row(eid)[1]
        return self.model.row_dict(cls, row) if row else {}

    def entity_actions(self, eid):
        """Canonical menu for an entity: every action with its count, availability, and mode.
        This is the SINGLE source of truth for what a user can do with an entity. Shell
        renders it as numbered text, dashboard renders it as buttons with badges, API returns
        it as JSON — same data, different presentation. No surface should re-derive this.

        This is the Capability Synthesis entry point (Contract v2 §3/§9): a promoted
        semantic object is synthesized through the identical pipeline as a physical one —
        canonicalize() is the single place that attaches immutable provenance/discovery_stage
        and resolves collisions by canonical identity, never by label."""
        if self.promotions.is_promoted(eid):
            return canonicalize(self.promotions.actions(eid), self.model)
        g = self.model.universal_graph
        attrs = g.attrs(eid)
        neighbors = g.neighbors(eid)
        per_rel = {}
        for e in neighbors:
            per_rel[e["relation"]] = per_rel.get(e["relation"], 0) + 1
        discovered_rels = set(self.reachable_relations(eid))
        # Source row
        rowdict = {}
        cls = self.model.owner_sheet(eid)
        row = self.model.owner_row(eid)[1]
        if row:
            rowdict = self.model.row_dict(cls, row)
        actions = []
        # Identity
        actions.append({"label": "What is", "type": "attr", "query": "WHAT_IS",
                        "relation": None, "count": 1 if attrs.get("class") else 0,
                        "available": bool(attrs.get("class")), "mode": "fixed", "reason": None})
        actions.append({"label": "Name", "type": "attr", "query": "GET_NAME",
                        "relation": None, "count": 1 if attrs.get("name") else 0,
                        "available": bool(attrs.get("name")), "mode": "fixed",
                        "reason": None if attrs.get("name") else "No name recorded."})
        # Direct relations (stable workbook order via neighbors iteration)
        #
        # A relation NAME alone is not always a stable canonical identity: two unrelated
        # FK columns in different registries can share header text (e.g. both "Staff
        # Registry.Store" and "Product Registry.Store" derive the relation name "store"),
        # and since reverse edges are indexed purely by that name, the target entity's
        # incoming edges would otherwise silently merge staff and products into one
        # bucket -- the count would still add up, but the label would misrepresent what
        # you actually get when you open it. Split by the OTHER side's class whenever an
        # incoming relation name spans more than one source class (Contract §6: canonical
        # identity, not a matching label, drives collision/merge decisions).
        incoming_classes = {}
        for e in neighbors:
            if e["dir"] == "in":
                incoming_classes.setdefault(e["relation"], set()).add(
                    g.attrs(e["node"]).get("class"))
        ambiguous = {rel for rel, classes in incoming_classes.items() if len(classes) > 1}

        def _group_key(e):
            if e["dir"] == "in" and e["relation"] in ambiguous:
                return (e["relation"], g.attrs(e["node"]).get("class"))
            return (e["relation"], None)

        buckets = {}
        for e in neighbors:
            buckets.setdefault(_group_key(e), []).append(e)

        seen = set()
        seen_keys = set()
        for e in neighbors:
            rel = e["relation"]
            key = _group_key(e)
            if key in seen_keys:
                continue
            seen_keys.add(key); seen.add(rel)
            edges_here = buckets[key]
            cnt = len(edges_here)
            label = rel.replace("_", " ").title()
            if key[1]:
                label = "%s ← %s" % (label, key[1])
                rel_id = "%s::%s" % (rel, key[1])
            else:
                rel_id = rel
            act_dict = {"label": label, "type": "relation",
                       "query": "REL", "relation": rel_id, "count": cnt,
                       "available": cnt > 0, "mode": "direct", "reason": None}
            if key[1]:
                act_dict["_target"] = key[1]
            actions.append(act_dict)
        # Discovered relations — with path metadata for explainability
        src_class = attrs.get("class")
        for rel in sorted(discovered_rels):
            if rel in seen:
                continue
            seen.add(rel)
            # Find the reachability record that connects this class to the target via this relation
            path_info = None
            if src_class:
                for d in self.model._reachability_registry:
                    if (d["source_class"] == src_class and d["relation_pattern"]
                            and d["relation_pattern"][-1] == rel):
                        path_info = {
                            "target_class": d["target_class"],
                            "via": d["relation_pattern"],
                            "hops": d["hops"],
                            "confirmed": "%d/%d" % (d["confirmed_instances"], d["sampled_instances"]),
                        }
                        break
            actions.append({"label": rel.replace("_", " ").title(), "type": "relation",
                            "query": "REL", "relation": rel, "count": -1,
                            "available": True, "mode": "discovered", "reason": None,
                            "discovery": path_info})
        # Scalar attributes — every other column this row holds becomes its own Canonical
        # Action (Contract §3 "every UI element is a Canonical Action" / §4 scalar_attribute),
        # instead of being visible only inside the single Source-row dump. A column already
        # exposed as a relation (direct or discovered, tracked in `seen`) is skipped here,
        # never duplicated -- collision avoidance by canonical identity, not by re-deriving.
        header0 = self.model.hdr.get(cls, [None])[0] if cls else None
        hdr_full = self.model.hdr.get(cls, []) if cls else []
        header1 = hdr_full[1] if len(hdr_full) > 1 else None
        for col, val in rowdict.items():
            if col in (header0, header1) or col.lower() in seen or val in (None, ""):
                continue
            if any(x in col.lower() for x in ("evidence", "source", "reference", "citation")):
                continue
            actions.append({"label": col, "type": "attr", "query": "ASK", "relation": col,
                            "count": 1, "available": True, "mode": "fixed", "reason": None,
                            "_capability": "Attributes"})
        # Tail
        actions.append({"label": "Neighbors", "type": "meta", "query": "GET_NEIGHBORS",
                        "relation": None, "count": len(neighbors),
                        "available": len(neighbors) > 0, "mode": "fixed",
                        "reason": None if neighbors else "No relationships documented."})
        actions.append({"label": "Evidence", "type": "meta", "query": "GET_EVIDENCE",
                        "relation": None, "count": 1 if attrs.get("evidence") else 0,
                        "available": bool(attrs.get("evidence")), "mode": "fixed",
                        "reason": None if attrs.get("evidence") else "No evidence documented."})
        actions.append({"label": "Source row", "type": "meta", "query": "GET_SOURCE_ROW",
                        "relation": None, "count": len(rowdict),
                        "available": len(rowdict) > 0, "mode": "fixed",
                        "reason": None if rowdict else "No source row found."})
        # Analysis operations — reachable from every entity via the same menu contract.
        # Each maps to a token the shell resolves through _dispatch.
        actions.append({"label": "Analyze this entity", "type": "analysis",
                        "query": "ANALYZE_ENTITY", "relation": None,
                        "count": 1, "available": True, "mode": "analysis", "reason": None})
        siblings_count = len(self._resolve_scope(eid, "siblings"))
        actions.append({"label": "Compare with siblings", "type": "analysis",
                        "query": "COMPARE_SIBLINGS", "relation": None,
                        "count": siblings_count, "available": siblings_count > 0, "mode": "analysis",
                        "reason": None if siblings_count else "No siblings share a direct parent."})
        layer_count = sum(1 for a in g.node_attrs.values() if a.get("class") == attrs.get("class")) - 1
        actions.append({"label": "Compare with layer", "type": "analysis",
                        "query": "COMPARE_LAYER", "relation": None,
                        "count": layer_count, "available": layer_count > 0, "mode": "analysis",
                        "reason": None if layer_count else "No other entities in this registry."})
        return canonicalize(actions, self.model)

    def explain_relation(self, eid, rel):
        """Canonical explained result for exploring a relation from an entity.

        Returns a structured dict that every surface renders — shell as text, dashboard as
        cards, API as JSON. The explanation is derived automatically from:
        - Whether the edges are direct or discovered
        - The traversal path (for multi-hop)
        - Evidence on each edge (from the workbook)
        - The reachability record (class-level confidence)

        No surface should build its own explanation. This is the single source."""
        if self.promotions.is_promoted(eid):
            return self.promotions.explain(eid, rel)
        g = self.model.universal_graph
        # A disambiguated bucket (see entity_actions()) is passed as "relname::SourceClass"
        # -- split it back out so the filter matches EXACTLY the entities that action's
        # advertised count was built from, not the full (mixed) set under that raw name.
        real_rel, sep, disambig_class = rel.partition("::")
        if sep:
            direct = [e for e in g.neighbors(eid) if e["relation"] == real_rel
                     and e["dir"] == "in"
                     and g.attrs(e["node"]).get("class") == disambig_class]
        else:
            direct = [e for e in g.neighbors(eid) if e["relation"] == real_rel]
        discovered = []
        discovery_meta = None

        if not direct:
            discovered = self.discover_relation(eid, real_rel)
            # Find the class-level reachability record for explainability
            src_class = g.attrs(eid).get("class")
            if src_class:
                for d in self.model._reachability_registry:
                    if (d["source_class"] == src_class and d["relation_pattern"]
                            and d["relation_pattern"][-1] == real_rel):
                        discovery_meta = {
                            "target_class": d["target_class"],
                            "via": d["relation_pattern"],
                            "hops": d["hops"],
                            "confirmed": d["confirmed_instances"],
                            "sampled": d["sampled_instances"],
                        }
                        break

        edges = direct or discovered
        mode = "direct" if direct else ("discovered" if discovered else "empty")

        # Build result items with evidence
        items = []
        for e in edges:
            node_attrs = g.attrs(e["node"])
            item = {
                "node": e["node"],
                "name": node_attrs.get("name"),
                "class": node_attrs.get("class"),
                "relation": e["relation"],
                "evidence": e.get("evidence"),
            }
            items.append(item)

        explanation = {"entity": eid, "relation": rel, "mode": mode, "count": len(items),
                       "items": items}

        if mode == "discovered" and discovery_meta:
            explanation["discovery"] = {
                "path": " → ".join(discovery_meta["via"]),
                "target_class": discovery_meta["target_class"],
                "hops": discovery_meta["hops"],
                "class_confidence": "%d/%d entities of this class have this path" % (
                    discovery_meta["confirmed"], discovery_meta["sampled"]),
            }
        elif mode == "empty":
            # Explain WHY it's empty
            if discovery_meta:
                explanation["reason"] = (
                    "%s can reach %s via %s (%d/%d class instances), "
                    "but %s specifically has no path." % (
                        g.attrs(eid).get("class", "this class"),
                        discovery_meta["target_class"],
                        " → ".join(discovery_meta["via"]),
                        discovery_meta["confirmed"], discovery_meta["sampled"],
                        eid))
            else:
                explanation["reason"] = "No %s relationship exists for %s, directly or via discovery." % (
                    real_rel.replace("_", " "), eid)

        return explanation

    def dimensions(self, eid):
        """Discover comparable dimensions for an entity — every outgoing relation is a
        dimension. Returns {relation: [{"id":..., "name":..., "class":...}, ...]}.

        No hardcoded dimension list. Whatever the graph contains for this entity is what
        can be compared. Extracted from what entity_actions() already computes inline so
        Compare and future analysis operations can reuse it."""
        g = self.model.universal_graph
        dims = {}
        for e in g.neighbors(eid):
            if e["dir"] != "out":
                continue
            attrs = g.attrs(e["node"])
            dims.setdefault(e["relation"], []).append({
                "id": e["node"],
                "name": attrs.get("name", ""),
                "class": attrs.get("class", ""),
            })
        return dims

    def _resolve_scope(self, target, scope):
        """Resolve a scope keyword to the set of entities to compare against.
        target: the anchor entity ID.
        scope:  either an entity ID or "siblings" | "layer" | "upstream" | "downstream".
        Returns a list of entity IDs (excluding the target itself)."""
        g = self.model.universal_graph
        if scope in g.node_attrs:
            return [scope]  # scope is itself an entity ID
        if scope == "layer":
            cls = g.attrs(target).get("class")
            if not cls:
                return []
            return [eid for eid, a in g.node_attrs.items()
                    if a.get("class") == cls and eid != target]
        if scope == "downstream":
            return [e["node"] for e in g.neighbors(target) if e["dir"] == "out"]
        if scope == "upstream":
            return [e["node"] for e in g.neighbors(target) if e["dir"] == "in"]
        if scope == "siblings":
            # Siblings = entities sharing at least one direct parent (same target on
            # at least one outgoing edge from us). Universal: does not know what a
            # "parent" is, just uses the graph.
            parents = {(e["relation"], e["node"]) for e in g.neighbors(target) if e["dir"] == "out"}
            if not parents:
                return []
            siblings = set()
            for rel, parent in parents:
                for rev in g.neighbors(parent):
                    if rev["dir"] == "in" and rev["relation"] == rel and rev["node"] != target:
                        siblings.add(rev["node"])
            return sorted(siblings)
        return []

    def compare(self, target, scope):
        """Canonical analysis operation: compare an anchor entity against a scope.

        target: entity ID (the anchor).
        scope:  entity ID (direct pairwise) OR one of:
                "siblings", "layer", "upstream", "downstream".

        Returns the canonical analysis object — same schema style as explain_relation.
        Every dimension comes from the graph; nothing is hardcoded."""
        g = self.model.universal_graph
        if target not in g.node_attrs:
            return {"operation": "compare", "targets": [target],
                    "error": "Unknown entity: %s" % target}

        others = self._resolve_scope(target, scope)
        if not others:
            return {"operation": "compare", "targets": [target], "scope": scope,
                    "dimensions": [], "error": "No entities found for scope '%s'." % scope}

        # Discover dimensions across target + all others; a dimension is any relation
        # that appears on any of them.
        left_dims = self.dimensions(target)
        right_entities = others
        # Union of all right-side dimensions
        right_union = {}
        for r_eid in right_entities:
            for rel, targets in self.dimensions(r_eid).items():
                right_union.setdefault(rel, {}).setdefault(r_eid, targets)

        all_rels = set(left_dims) | set(right_union)

        dimensions_out = []
        for rel in sorted(all_rels):
            left_ids = {t["id"] for t in left_dims.get(rel, [])}
            # For scope=single entity, use that one's dimension; for group scope,
            # a dimension is "common" if the target and ALL others have overlap.
            if len(right_entities) == 1:
                right_ids = {t["id"] for t in right_union.get(rel, {}).get(right_entities[0], [])}
                common = left_ids & right_ids
                only_l = left_ids - right_ids
                only_r = right_ids - left_ids
                target_class = ""
                if left_dims.get(rel): target_class = left_dims[rel][0]["class"]
                elif right_union.get(rel):
                    first_r = next(iter(right_union[rel].values()))
                    if first_r: target_class = first_r[0]["class"]
                status = ("common" if common and not (only_l or only_r) else
                          ("different" if (only_l or only_r) else "missing"))
                dimensions_out.append({
                    "relation": rel,
                    "target_class": target_class,
                    "status": status,
                    "common": [{"id": eid, "name": g.attrs(eid).get("name", "")}
                               for eid in sorted(common)],
                    "only_left": [{"id": eid, "name": g.attrs(eid).get("name", "")}
                                  for eid in sorted(only_l)],
                    "only_right": [{"id": eid, "name": g.attrs(eid).get("name", "")}
                                   for eid in sorted(only_r)],
                })
            else:
                # Group scope: for each dimension, count how many others share targets with left
                right_by_entity = right_union.get(rel, {})
                shared_across = set(left_ids)
                for r_eid in right_entities:
                    r_targets = {t["id"] for t in right_by_entity.get(r_eid, [])}
                    shared_across &= r_targets
                target_class = ""
                if left_dims.get(rel): target_class = left_dims[rel][0]["class"]
                dimensions_out.append({
                    "relation": rel,
                    "target_class": target_class,
                    "status": "common" if shared_across else "different",
                    "shared_by_all": [{"id": eid, "name": g.attrs(eid).get("name", "")}
                                      for eid in sorted(shared_across)],
                    "left_targets": [{"id": eid, "name": g.attrs(eid).get("name", "")}
                                     for eid in sorted(left_ids)],
                    "right_entity_count": len(right_entities),
                })

        return {
            "operation": "compare",
            "targets": [target] + list(others),
            "scope": scope,
            "anchor": target,
            "dimensions": dimensions_out,
        }

    def analyze(self, eid):
        """Canonical analysis of one entity — observations derived entirely from the
        existing runtime knowledge: graph, registry, relationships, evidence, siblings.

        This is not an AI engine. It has no hardcoded observation text. Every observation
        is a structured fact about what the graph and registry already know about eid.
        The renderer converts these facts into natural sentences at display time."""
        g = self.model.universal_graph
        attrs = g.attrs(eid)
        if not attrs:
            return {"operation": "analyze", "entity": eid,
                    "error": "Unknown entity: %s" % eid}

        cls = attrs.get("class", "")
        observations = []

        # 1. Registry membership — which registry this entity belongs to
        peers = [x for x, a in g.node_attrs.items() if a.get("class") == cls and x != eid]
        observations.append({
            "kind": "registry_membership",
            "title": "Registry membership",
            "summary": "%s is one of %d entities in %s." % (eid, len(peers) + 1, cls or "?"),
            "items": [{"text": "Part of %s alongside %d other entities." % (cls or "?", len(peers))}],
        })

        # 2. Direct relationships — what this entity is directly connected to
        outgoing = [e for e in g.neighbors(eid) if e["dir"] == "out"]
        incoming = [e for e in g.neighbors(eid) if e["dir"] == "in"]
        rel_out = {}
        for e in outgoing:
            rel_out.setdefault(e["relation"], []).append(e["node"])
        observations.append({
            "kind": "direct_relationships",
            "title": "Direct relationships (%d outgoing, %d incoming)" % (
                len(outgoing), len(incoming)),
            "summary": ("%s references %d entities and is referenced by %d." % (
                eid, len(outgoing), len(incoming))) if (outgoing or incoming) else
                "%s has no documented relationships." % eid,
            "items": [{"text": "%s → %d %s" % (r, len(ts), r)}
                      for r, ts in sorted(rel_out.items(), key=lambda x: -len(x[1]))[:8]],
        })

        # 3. Strongest connection — which relation has the most targets
        if rel_out:
            top_rel, top_targets = max(rel_out.items(), key=lambda x: len(x[1]))
            observations.append({
                "kind": "strongest_connection",
                "title": "Strongest connection",
                "summary": "Its widest relation is '%s' with %d targets." % (top_rel, len(top_targets)),
                "backed_by": sorted({str(e.get("evidence")) for e in outgoing
                                     if e["relation"] == top_rel and e.get("evidence")})[:3],
                "items": [{"id": t, "name": g.attrs(t).get("name", "")}
                          for t in top_targets[:5]],
                "note": "Via relation '%s' (%d targets)" % (top_rel, len(top_targets)),
            })

        # 4. Dependencies — downstream entities this one relies on
        downstream_ids = set(e["node"] for e in outgoing)
        if downstream_ids:
            observations.append({
                "kind": "dependencies",
                "title": "Direct dependencies (%d)" % len(downstream_ids),
                "summary": "%s depends on %d entities directly." % (eid, len(downstream_ids)),
                "backed_by": sorted({str(e.get("evidence")) for e in outgoing if e.get("evidence")})[:3],
                "items": [{"id": d, "name": g.attrs(d).get("name", "")}
                          for d in sorted(downstream_ids)[:5]],
            })

        # 5. Dependents — who depends on this entity
        upstream_ids = set(e["node"] for e in incoming)
        if upstream_ids:
            observations.append({
                "kind": "dependents",
                "title": "Depended on by (%d)" % len(upstream_ids),
                "summary": "%d entities rely on %s." % (len(upstream_ids), eid),
                "backed_by": sorted({str(e.get("evidence")) for e in incoming if e.get("evidence")})[:3],
                "items": [{"id": u, "name": g.attrs(u).get("name", "")}
                          for u in sorted(upstream_ids)[:5]],
            })

        # 6. Reachable relations — what can be discovered from here via multi-hop
        reachable = self.reachable_relations(eid)
        if reachable:
            observations.append({
                "kind": "reachable_relations",
                "title": "Reachable via discovery (%d relation types)" % len(reachable),
                "items": [{"text": r} for r in sorted(reachable)[:8]],
                "note": "Multi-hop paths through intermediate registries",
            })

        # 7. Siblings — entities sharing a direct parent with this one
        siblings = self._resolve_scope(eid, "siblings")
        if siblings:
            observations.append({
                "kind": "siblings",
                "title": "Siblings sharing a direct parent (%d)" % len(siblings),
                "items": [{"id": s, "name": g.attrs(s).get("name", "")}
                          for s in siblings[:5]],
            })

        # 8. How this differs from siblings — dimension-level diff
        if siblings:
            cmp_res = self.compare(eid, "siblings")
            unique_dims = [d["relation"] for d in cmp_res.get("dimensions", [])
                           if d.get("status") != "common" and d.get("left_targets")]
            observations.append({
                "kind": "sibling_differences",
                "title": "How this entity differs from siblings",
                "summary": ("Unique on %d of its dimensions." % len(unique_dims)) if unique_dims
                           else "Overlaps its siblings on every dimension.",
                "items": [{"text": "Unique on dimension: %s" % r} for r in unique_dims[:5]] or
                         [{"text": "Fully overlaps with siblings on all dimensions."}],
            })

        # 9. Evidence — provenance from the source workbook
        evidence = attrs.get("evidence")
        if evidence:
            observations.append({
                "kind": "evidence",
                "title": "Evidence",
                "items": [{"text": str(evidence)[:120]}],
            })

        # 10. Suggested next steps — most-connected neighbors to explore next
        if rel_out:
            neighbors_ranked = []
            for r, ts in rel_out.items():
                for t in ts:
                    t_degree = len(g.fwd.get(t, [])) + len(g.rev.get(t, []))
                    neighbors_ranked.append((t_degree, t, r))
            neighbors_ranked.sort(reverse=True)
            top_next = []
            seen_ids = set()
            for _, t, _ in neighbors_ranked:
                if t not in seen_ids:
                    seen_ids.add(t); top_next.append(t)
                if len(top_next) >= 5: break
            observations.append({
                "kind": "next_steps",
                "title": "Next entities to explore",
                "items": [{"id": t, "name": g.attrs(t).get("name", "")}
                          for t in top_next],
                "note": "Ranked by connectivity in the graph",
            })

        return {
            "operation": "analyze",
            "entity": eid,
            "identity": {"id": eid, "name": attrs.get("name", ""), "class": cls},
            "observations": observations,
        }

def run(*a, **k):
    from .runner import run as _r
    return _r(*a, **k)
