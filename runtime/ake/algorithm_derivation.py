"""M10 — Algorithm Derivation (deterministic planner).

Execution sequence is NOT hardcoded per query and NOT produced by LLM reasoning. It is DERIVED from:
  (1) Query Definition  — objective + target relation + direction + render
  (2) Registry Schema   — where the target relation lives (via the model)
  (3) Primitive Library — the frozen 45 runtime primitives
Planning rules combine these into a primitive sequence. Adding a new relation + a canonical query row
makes the runtime support it with zero code change.
"""
import re

# Canonical Query Definitions loaded from the registry (DATA) — ake/defaults/query_definitions.json.
# Adding a row (e.g. GET_MONITORS) is a DATA edit; the planner code is never touched.
import os as _os, json as _json
def _load_query_definitions():
    _p = _os.path.join(_os.path.dirname(__file__), "defaults", "query_definitions.json")
    if _os.path.exists(_p):
        return _json.load(open(_p))
    return _BUILTIN_QUERY_DEFINITIONS

# Universal query definitions that work on ANY workbook. These do not reference specific
# relation names — they use wildcards or structural queries. Relation-specific queries
# (GET_HABITAT, GET_HANDLER, etc.) are derived at workbook load time by
# derive_workbook_queries() below.
_BUILTIN_QUERY_DEFINITIONS = {
    "GET_UPSTREAM":    {"objective": "traverse", "relation": "*",         "direction": "in",  "render": "graph"},
    "GET_DOWNSTREAM":  {"objective": "traverse", "relation": "*",         "direction": "out", "render": "graph"},
    "GET_EVIDENCE":    {"objective": "attribute", "attribute": "evidence", "render": "table"},
    "GET_NEIGHBORS":   {"objective": "traverse", "relation": "*",         "direction": "both","render": "graph"},
    "VALIDATE_REFERENCES": {"objective": "validate", "render": "table"},
}
QUERY_DEFINITIONS = _load_query_definitions()


def derive_workbook_queries(model):
    """Auto-derive one GET_<REL> query per relation type found in the workbook's edges.
    A biology workbook gets GET_HABITAT, GET_PREDATOR, GET_DIET, GET_ECOSYSTEM.
    An EBIS workbook gets GET_HANDLER, GET_GATE, GET_PIPELINE, etc.
    No code change needed when the workbook changes. Merged with any explicit definitions
    from query_definitions.json (explicit wins on conflict)."""
    derived = dict(QUERY_DEFINITIONS)  # start with explicit + universal
    rels = set()
    for s, rel, t, sc, tc, ev in model.universal_edges:
        rels.add(rel)
    for rel in sorted(rels):
        qname = "GET_%s" % rel.upper().replace(" ", "_")
        if qname not in derived:
            derived[qname] = {"objective": "traverse", "relation": rel,
                              "direction": "out", "render": "tree"}
    return derived

# abstract relation groups (for the Relation Inventory) — derived from relation semantics
def relation_group(rel, model=None):
    """Assign a relation to a semantic group. If a model is available, groups are derived from
    graph topology (self-referencing relations = Classification, relations that cross registry
    boundaries = Control/DataFlow). Without a model, falls back to a generic heuristic that
    uses no domain-specific terms — only structural indicators like 'name' suffix."""
    r = rel.lower()
    if model is not None:
        return _topology_group(r, model)
    # Minimal structural heuristic — no domain terms, just naming conventions
    if r.endswith("_name") or r.endswith("_path"):
        return "Reference"
    return "Other"


def _topology_group(rel, model):
    """Derive a relation's semantic group from graph structure, not its name.
    - A relation whose source and target entities share the same registry class = Classification
    - A relation whose target entities are in a single target class = Ownership (if 1:1 ratio)
    - Everything else = Association
    No domain terms are referenced."""
    src_classes = set()
    tgt_classes = set()
    for s, r, t, sc, tc, ev in model.universal_edges:
        if r == rel:
            src_classes.add(sc)
            tgt_classes.add(tc)
    if not src_classes:
        return "Other"
    if src_classes & tgt_classes:
        return "Structural"          # self-referencing or same-class
    if len(tgt_classes) == 1:
        return "Classification"      # all targets in one class = taxonomy-like
    return "Association"             # cross-class, multi-target


class RelationInventory:
    """Reports which relation GROUPS an entity has (does NOT create queries)."""
    def __init__(self, model): self.m = model
    def inventory(self, eid):
        groups = {}
        for e in self.m.universal_graph.neighbors(eid):
            groups.setdefault(relation_group(e["relation"]), set()).add(e["relation"])
        inv = {"Identity": ["id"], "Evidence": ["evidence"]}   # universal core
        for g, rels in groups.items(): inv[g] = sorted(rels)
        return inv


class AlgorithmDerivation:
    """M10 planner: Query Definition + Registry Schema + Primitive Library -> primitive sequence."""
    def __init__(self, model):
        self.m = model
        # The compiler is a SEPARATE transformation owner (Execution Tree -> opcode plan). The
        # planner holds an instance but does not itself emit opcodes.
        self._compiler = ExecutionCompiler(_OPS)

    # ---- Stage 7: intent -> semantic operations -> opcode plan (this class is the owner) ----
    # Internal data assets: the operation inventory (_OPS) and the concept→operation map
    # (_CONCEPT_TO_OPS) are private to this planner. The architecture exposes only
    # AlgorithmDerivation as the planning authority.
    def _derive_operations(self, intent):
        """LEVEL 1 (semantic planning): intent roles -> ordered semantic operations, using the
        internal operation vocabulary. Order: filters -> actions -> qualifiers. De-duplicated."""
        d = _intent_dict(intent)
        ops = []
        def add(seq):
            for op in seq:
                if _OPS.is_operation(op) and op not in ops:
                    ops.append(op)
        if d.get("constraints") or d.get("time"):
            add([_OPS.FILTER])
        for a in d.get("actions", []):
            add(_CONCEPT_TO_OPS.get(a["canonical"], []))
        for q in d.get("qualifiers", []):
            add(_CONCEPT_TO_OPS.get(q["canonical"], []))
        return ops

    def _scope_operations(self, scope_dict):
        """Semantic operations for ONE scope (a node of the intent tree): its actions + qualifiers,
        via the concept->operation map, ordered filters -> actions -> qualifiers."""
        ops = []
        def add(seq):
            for op in seq:
                if _OPS.is_operation(op) and op not in ops:
                    ops.append(op)
        if scope_dict.get("constraints") or scope_dict.get("time"):
            add([_OPS.FILTER])
        for a in scope_dict.get("actions", []):
            add(_CONCEPT_TO_OPS.get(a["canonical"], []))
        for q in scope_dict.get("qualifiers", []):
            add(_CONCEPT_TO_OPS.get(q["canonical"], []))
        return ops

    def _exec_node_from_scope(self, node_dict):
        """Recursively turn an intent-tree scope into an ExecutionNode carrying execution SEMANTICS
        ONLY (target, operations, values, children). No opcodes here — that's the compiler's job.
        A scope with a target but NO operation is an OPEN/DISCOVER intent: default to DISCOVER so
        the Discovery Engine runs as the planner's consumer (rich card + suggestions + path)."""
        tgt = None
        t = node_dict.get("target")
        if t:
            tgt = t.get("id") or t.get("token")
        en = ExecutionNode(scope=node_dict.get("label"), target=tgt)
        en.operations = self._scope_operations(node_dict)
        if tgt and not en.operations and not node_dict.get("children"):
            en.operations = [_OPS.OPEN]
        en.values = list(node_dict.get("values", []))
        for child in node_dict.get("children", []):
            en.add_child(self._exec_node_from_scope(child))
        return en

    def derive_execution_tree(self, intent):
        """PLANNER OWNS execution structure: Intent Tree -> Execution Tree (execution SEMANTICS).
        Consumes the intent tree (roles/hierarchy) and produces an ExecutionNode tree (operations +
        values per scope, nested). NO opcodes — hierarchy preserved, compilation deferred."""
        d = _intent_dict(intent)
        tree = d.get("tree")
        if not tree:
            return None
        root = self._exec_node_from_scope(tree)
        self._resolve_relationship_count(root)
        self._resolve_relationship_path(root, intent)
        self._resolve_scoped_filter(root, intent)
        return root

    def _resolve_scoped_filter(self, root, intent):
        """SMART FILTER capability: 'features in CAT-02' = members of the class 'features' whose
        edge lands on the entity CAT-02. Works off the RESOLVED execution tree: the root target is
        the class (already resolved to its registry, e.g. 'Feature Registry' -> prefix FEAT) and the
        filtering entity appears either in the intent references or as a child scope. Rewrite to a
        REVERSE seeded on that entity, filtered to the class prefix — answering with exactly the
        class members related to it. Reuses reverse_lookup; prefix + id come from resolved state,
        never hardcoded. Only fires for a bare class + entity with no explicit graph/aggregate op."""
        ops_now = _collect_ops(root)
        blocking = {_OPS.COUNT, _OPS.COUNT_RELATED, _OPS.PATH, _OPS.DEPENDENCY, _OPS.REACHABILITY,
                    _OPS.REVERSE, _OPS.EVIDENCE, _OPS.COMPARE, _OPS.SORT_DESC, _OPS.SORT_ASC,
                    _OPS.AVG, _OPS.SUM, _OPS.MIN, _OPS.MAX}
        if any(op in blocking for op in ops_now):
            return
        cat = getattr(self.m, "catalog", {}) or {}
        # class prefix from the RESOLVED root target (registry canonical -> prefix)
        base = str(root.target).split(".")[0] if root.target else None
        class_meta = cat.get(root.target) or cat.get(base) or {}
        class_prefix = class_meta.get("prefix")
        # filtering entity: a child scope target that is an id, or an intent reference id
        ref_id = None
        for child in root.children:
            if _looks_like_id(child.target):
                ref_id = child.target; break
        if not ref_id:
            d = _intent_dict(intent)
            for r in d.get("references", []):
                if r.get("id") or _looks_like_id(r.get("token")):
                    ref_id = r.get("id") or r.get("token"); break
        if not (class_prefix and ref_id):
            return
        root.target = ref_id
        root.operations = [_OPS.REVERSE]
        root.params = dict(root.params, source_prefix=class_prefix)
        root.children = []

    def _resolve_relationship_path(self, root, intent):
        """RELATIONSHIP PATH capability: a query naming TWO entities with a TRACE/PATH action means
        'shortest path from A to B'. The intent builder puts the first entity in targets and the
        second in references; here the planner binds them as source+target params on the PATH op so
        the compiler can hand both to graph_shortest_path. Reuses the existing shortest-path opcode;
        no new traversal. Entity ids come from the resolved intent, never hardcoded."""
        d = _intent_dict(intent)
        if not any(op == _OPS.PATH for op in _collect_ops(root)):
            return
        src = None
        for t in d.get("targets", []):
            if t.get("id") or _looks_like_id(t.get("token")):
                src = t.get("id") or t.get("token"); break
        tgt = None
        for r in d.get("references", []):
            if r.get("id") or _looks_like_id(r.get("token")):
                tgt = r.get("id") or r.get("token"); break
        if not (src and tgt):
            return
        # bind params onto the node(s) carrying PATH
        for node in _iter_nodes(root):
            if _OPS.PATH in node.operations:
                node.params = dict(node.params, source=src, target=tgt)
                # PATH here is a two-anchor shortest path; drop any trailing OPEN so we don't
                # re-open the source entity after showing the path.
                node.operations = [op for op in node.operations if op != _OPS.OPEN]

    def _resolve_relationship_count(self, root):
        """Nested-count semantic completion: when the root scope has a COUNT/aggregate and a CHILD
        scope names a class, the count is over the child class RELATED to the parent — not an
        independent OPEN of the child. Rewrite to a single COUNT_RELATED on the root, carrying the
        relation name and the child's class prefix as params. Owner: AlgorithmDerivation (semantics);
        the count_related opcode (RuntimePrimitives) executes walk+count. Relation + prefix come from
        the existing model relation map — not hardcoded.
        """
        counting = {_OPS.COUNT, _OPS.SUM, _OPS.AVG, _OPS.MIN, _OPS.MAX, _OPS.GROUP}
        if not any(op in counting for op in root.operations):
            return
        # find a child scope that names a class (target resolves to a registry/class)
        cat = getattr(self.m, "catalog", {}) or {}
        for child in list(root.children):
            child_target = child.target
            if not child_target:
                continue
            reg_meta = cat.get(child_target)
            prefix = reg_meta.get("prefix") if reg_meta else None
            if not prefix:
                continue
            # parent class prefix (e.g. Family Registry -> FAM) for both the relation lookup and a
            # class-level count when no specific parent instance is named.
            parent_meta = cat.get(root.target) or cat.get(str(root.target).split(".")[0]) or {}
            parent_prefix = parent_meta.get("prefix")
            if not parent_prefix and root.target:
                # target may itself be a class canonical like "Family Registry.Family"
                base = str(root.target).split(".")[0]
                parent_prefix = (cat.get(base) or {}).get("prefix")
            relation = self._relation_between(root.target, prefix, parent_prefix)
            # rewrite: root becomes a COUNT_RELATED; child scope folded into the relation count.
            root.operations = [_OPS.COUNT_RELATED]
            root.params = {"relation": relation, "target_prefix": prefix, "direction": "out",
                           "parent_prefix": parent_prefix}
            root.children = [c for c in root.children if c is not child]
            return

    def _relation_between(self, parent_target, child_prefix, parent_prefix=None):
        """Find the named relation from the parent CLASS to the child class, from the model's
        existing universal edges — not hardcoded. Filters edges whose source matches the parent
        class prefix and whose target matches the child class prefix. Returns the relation name or
        None (None => count all reached of the child prefix)."""
        edges = getattr(self.m, "universal_edges", []) or []
        cp = str(child_prefix).upper().rstrip("-")
        pp = str(parent_prefix).upper().rstrip("-") if parent_prefix else None
        for e in edges:
            if len(e) < 3:
                continue
            s, rel, t = e[0], e[1], e[2]
            if str(t).split("-")[0].upper() != cp:
                continue
            if pp and str(s).split("-")[0].upper() != pp:
                continue
            return rel
        return None

    def derive_from_intent(self, intent):
        """LEVEL 2 (execution planning): intent -> {operations, plan, target, execution_tree}.
        Four-transformation ownership:
          - THIS PLANNER: Intent Tree -> Execution Tree (semantics; derive_execution_tree).
          - COMPILER (ExecutionCompiler): Execution Tree -> opcode plan (self._compiler.compile).
          - RuntimeEngine: opcode plan -> result.
        The execution_tree is returned so hierarchy is never lost; `plan` is the compiler's output.
        A simple query with no tree falls back to a single-scope derivation (still compiled)."""
        d = _intent_dict(intent)
        etree = self.derive_execution_tree(intent)
        if etree is not None and (etree.children or etree.operations or etree.target):
            operations = list(etree.operations)
            for c in etree.children:
                for op in c.operations:
                    if op not in operations:
                        operations.append(op)
            plan = self._compiler.compile(etree)          # compiler owns opcode emission
            target = etree.target or next((c.target for c in etree.children if c.target), None)
            return {"operations": operations, "plan": plan, "target": target,
                    "execution_tree": etree.as_dict()}
        # fallback: build a single-scope execution node, then compile it (still via the compiler)
        operations = self._derive_operations(intent)
        target = None
        tg = d.get("targets") or []
        if tg:
            t0 = tg[0]
            target = t0.get("id") or (t0.get("best") or {}).get("canonical") or t0.get("token")
        node = ExecutionNode(scope="root", target=target)
        node.operations = operations
        node.values = list(d.get("values", []))
        plan = self._compiler.compile(node)
        return {"operations": operations, "plan": plan, "target": target,
                "execution_tree": node.as_dict()}

    @property
    def _qdefs(self):
        """Workbook-derived query definitions (merged with explicit). Falls back to the
        static QUERY_DEFINITIONS if the model hasn't been bootstrapped with derived ones."""
        return getattr(self.m, '_query_definitions', QUERY_DEFINITIONS)

    def applicable_queries(self, eid):
        """Canonical queries whose target relation is present in the entity's relation inventory,
        INCLUDING relations reachable via multi-hop (class-level check, not entity-specific BFS).
        Reads from self._qdefs (workbook-derived queries), not the static QUERY_DEFINITIONS."""
        present = set()
        for e in self.m.universal_graph.neighbors(eid): present.add(e["relation"])
        # Extend with multi-hop reachable relations (class-level, last-hop derivation)
        if hasattr(self.m, '_reachability_registry'):
            src_class = self.m.universal_graph.node_attrs.get(eid, {}).get("class")
            if src_class:
                for d in self.m._reachability_registry:
                    if d["source_class"] == src_class and d["relation_pattern"]:
                        present.add(d["relation_pattern"][-1])
        out = []
        for name, d in self._qdefs.items():
            if d["objective"] != "traverse": out.append(name); continue
            rel = d["relation"]
            if rel == "*" or any(rel in str(p) for p in present): out.append(name)
        return out

    def derive(self, query_name):
        """Deterministic planning rules -> primitive sequence (library primitives only).
        Entity-unaware: produces the same plan regardless of which entity will run it.
        For entity-aware planning (including multi-hop paths), use derive_for_entity."""
        d = self._qdefs.get(query_name) or QUERY_DEFINITIONS.get(query_name)
        if not d:
            return [("resolve_entity", {})]
        obj = d["objective"]
        seq = [("resolve_entity", {})]
        if obj == "traverse":
            seq.append(("walk_relationship", {"direction": d.get("direction", "out"),
                                              "relation": None if d.get("relation", "*") == "*" else d["relation"]}))
            seq.append(("attach_evidence", {}))
            seq.append(("render_" + d.get("render", "graph"), {}))
        elif obj == "attribute":
            seq += [("attach_evidence", {}), ("render_table", {})]
        elif obj == "validate":
            seq += [("check_fk", {}), ("render_table", {})]
        return seq

    def derive_for_entity(self, query_name, eid):
        """Entity-aware planner: produces a path-explicit plan from the reachability registry.

        When an entity has direct edges for the query's relation → same plan as derive().
        When it doesn't, but the reachability registry shows a class-level path exists →
        produces a walk_discovery plan with the derived path, target class, and hop count.
        The plan encodes HOW the answer will be found, not just WHAT to find. This makes
        the execution sequence self-documenting: any consumer that reads derived_sequence
        can see whether the answer came from a direct edge or a 3-hop discovery path.

        Falls back to derive() for non-traverse queries, wildcards, or when no path exists.
        No hardcoded entity types, relation names, or registry names anywhere."""
        d = self._qdefs.get(query_name)
        if not d or d["objective"] != "traverse":
            return self.derive(query_name)
        rel = d.get("relation")
        if not rel or rel == "*":
            return self.derive(query_name)
        # Does this entity have the relation directly?
        if any(e["relation"] == rel for e in self.m.universal_graph.neighbors(eid)):
            return self.derive(query_name)
        # Check reachability registry for a derived path
        if not hasattr(self.m, '_reachability_registry'):
            return self.derive(query_name)
        src_class = self.m.universal_graph.node_attrs.get(eid, {}).get("class")
        if not src_class:
            return self.derive(query_name)
        for rec in self.m._reachability_registry:
            if (rec["source_class"] == src_class
                    and rec["relation_pattern"]
                    and rec["relation_pattern"][-1] == rel):
                return [
                    ("resolve_entity", {}),
                    ("walk_discovery", {
                        "target_class": rec["target_class"],
                        "relation_pattern": list(rec["relation_pattern"]),
                        "hops": rec["hops"],
                        "confirmed_ratio": "%d/%d" % (rec["confirmed_instances"],
                                                      rec["sampled_instances"]),
                    }),
                    ("attach_evidence", {}),
                    ("render_" + d.get("render", "graph"), {}),
                ]
        return self.derive(query_name)


# ============================================================================================
# Stage 7 — Canonical Intent -> Semantic Operations -> Opcode Plan.
# SINGLE PLANNING AUTHORITY: AlgorithmDerivation. The role→operation map and the operation
# inventory below are INTERNAL implementation details of this one owner — not parallel
# architectural owners. Two logical levels (semantic planning, execution planning) live inside
# AlgorithmDerivation via the methods derive_operations() / derive_plan().
# ============================================================================================
from . import operation_inventory as _OPS   # internal data asset of this planner (not a public owner)

# Level-1 knowledge: canonical concept -> semantic operation sequence. INTERNAL to
# AlgorithmDerivation. Operation names are taken from the internal inventory (single vocabulary).
# Grows here (one owner) as concepts like NEAREST/SIMILAR appear.
_CONCEPT_TO_OPS = {
    "SHOW":     [_OPS.SHOW],
    "COUNT":    [_OPS.GROUP, _OPS.COUNT],
    "HOWMANY":  [_OPS.GROUP, _OPS.COUNT],
    "COMPARE":  [_OPS.COMPARE],
    "EXPLAIN":  [_OPS.EXPLAIN],
    "ANALYZE":  [_OPS.SHOW],
    "FIND":     [_OPS.SEARCH],
    "TRACE":    [_OPS.PATH],
    "DEPEND":   [_OPS.DEPENDENCY],
    "IMPACT":   [_OPS.REACHABILITY],
    "REVERSE":  [_OPS.REVERSE],
    "EVIDENCE": [_OPS.EVIDENCE],
    "TOP":      [_OPS.SORT_DESC, _OPS.LIMIT],
    "BOTTOM":   [_OPS.SORT_ASC, _OPS.LIMIT],
    "FIRST":    [_OPS.LIMIT],
    "LAST":     [_OPS.LIMIT],
    "UNIQUE":   [_OPS.DISTINCT],
    "TOTAL":    [_OPS.SUM],
    "AVERAGE":  [_OPS.GROUP, _OPS.AVG],
    "MIN":      [_OPS.MIN],
    "MAX":      [_OPS.MAX],
    "EQUALS":   [_OPS.FILTER], "GREATER": [_OPS.FILTER], "LESS": [_OPS.FILTER],
    "CONTAINS": [_OPS.FILTER], "BETWEEN": [_OPS.FILTER],
    "AFTER":    [_OPS.FILTER], "BEFORE": [_OPS.FILTER], "DURING": [_OPS.FILTER],
}


def _intent_dict(intent):
    return intent.as_dict() if hasattr(intent, "as_dict") else intent


def _looks_like_id(token):
    """A PK-style token: PREFIX-NUMBER (e.g. FEAT-016, MOD-033). Prefix-agnostic — any alpha
    prefix + hyphen + digits. Not hardcoded to any workbook's prefixes."""
    import re as _re
    return bool(token and _re.match(r"^[A-Za-z]+-\d+$", str(token).strip()))


def _iter_nodes(node):
    """Depth-first walk over an ExecutionNode tree."""
    yield node
    for c in getattr(node, "children", []):
        for n in _iter_nodes(c):
            yield n


def _collect_ops(node):
    """All operations across the execution tree."""
    out = []
    for n in _iter_nodes(node):
        out.extend(n.operations)
    return out


class ExecutionNode:
    """A node in the EXECUTION TREE — the planner's execution SEMANTICS (NOT opcodes, NOT the intent
    tree, NOT a knowledge graph). Each node is one execution scope: a target + the semantic
    operations that apply to it, with child scopes nested beneath.

    Owned by AlgorithmDerivation. Deliberately holds NO opcode list — turning operations into
    opcodes is the COMPILER's job (separate owner). Keeping opcodes out of here preserves the level
    split: planner describes WHAT executes (operations, hierarchy); compiler decides HOW (opcodes).
    If ExecutionNode held opcodes, the compiler would have nothing to compile."""
    __slots__ = ("scope", "target", "operations", "values", "params", "children")

    def __init__(self, scope=None, target=None):
        self.scope = scope          # label of the intent scope this came from
        self.target = target        # resolved target for this execution scope
        self.operations = []        # semantic operations for this scope (execution semantics)
        self.values = []            # scope-local values (e.g. the N for LIMIT) — semantics, not kwargs
        self.params = {}            # per-operation semantic params (e.g. relation, target_prefix)
        self.children = []          # nested execution scopes

    def add_child(self, node):
        self.children.append(node)
        return node

    def as_dict(self):
        return {"scope": self.scope, "target": self.target,
                "operations": self.operations, "values": self.values, "params": self.params,
                "children": [c.as_dict() for c in self.children]}


class ExecutionCompiler:
    """Owner of the third transformation: Execution Tree -> Executable Plan (opcode graph).

    Separate from the planner: the planner produces execution SEMANTICS (an ExecutionNode tree of
    operations); this compiler turns those semantics into concrete opcodes for a target runtime.
    Today it emits a FLAT opcode list (the current RuntimeEngine executes a flat list); if the
    runtime later becomes an execution DAG, ONLY this compiler changes — the planner and the
    Execution Tree do not. Runtime never recompiles; the planner never emits opcodes."""

    def __init__(self, inventory):
        self._ops = inventory     # operation inventory (realize op -> opcode steps)

    def compile(self, node):
        """Execution Tree -> flat opcode plan (depth-first: a scope's opcodes, then its children).
        Data-loading is materialised here per scope: a scope with a target and a row-consuming
        operation begins with resolve_entity so rows are seeded by the owning opcode."""
        ops = self._ops
        row_consuming = {ops.GROUP, ops.FILTER, ops.SORT_ASC, ops.SORT_DESC, ops.LIMIT,
                         ops.DISTINCT, ops.COUNT, ops.SUM, ops.AVG, ops.MIN, ops.MAX}
        # graph-traversal operations also need the target entity seeded (walk_relationship /
        # shortest_path read ctx["target"]). resolve_entity sets both target and rows.
        graph_ops = {ops.PATH, ops.DEPENDENCY, ops.REACHABILITY, ops.COUNT_RELATED,
                     ops.REVERSE, ops.EVIDENCE}
        needs_seed = row_consuming | graph_ops
        plan = []
        if node.target and any(o in needs_seed for o in node.operations):
            plan.append(("resolve_entity", {"token": node.target}))
        vals = list(node.values)
        for op in node.operations:
            steps = ops.realize(op, vals) if op == ops.LIMIT else ops.realize(op)
            # inject this scope's semantic params (e.g. relation, target_prefix) into the opcode
            if node.params:
                steps = [(name, dict(kw, **node.params)) for name, kw in steps]
            plan.extend(steps)
        for child in node.children:
            plan.extend(self.compile(child))
        return plan


# The two-level derivation is attached to AlgorithmDerivation below (see _derive_operations /
# derive_from_intent). IntentPlanner remains only as a thin INTERNAL alias for back-compat; it is
# not a separate planning authority — it delegates to AlgorithmDerivation.
class IntentPlanner:
    """Internal helper/alias. Not a public planner — delegates to AlgorithmDerivation so there is
    exactly one planning authority. Kept so existing references resolve."""
    def __init__(self, model):
        self._ad = AlgorithmDerivation(model)

    def derive_operations(self, intent):
        return self._ad._derive_operations(intent)

    def derive_plan(self, intent):
        return self._ad.derive_from_intent(intent)
