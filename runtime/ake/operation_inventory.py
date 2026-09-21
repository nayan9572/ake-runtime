"""Operation Inventory — INTERNAL data asset of AlgorithmDerivation (the single planner).

Not a parallel architectural owner: this module is imported only by algorithm_derivation.py and
carries the operation vocabulary + opcode realizations that the planner uses internally.

Provenance of the 19 operations (evidence, not manual invention): they are a SEMANTIC GROUPING of
the 47 RuntimePrimitives opcodes. Aggregations COUNT/SUM/AVG/MIN/MAX all realise to the single
op_aggregate primitive (via fn); SORT_ASC/SORT_DESC to op_sort (via desc); etc. The other ~33
primitives are internals (walks, validation, render variants, resolution) not surfaced as
user-facing semantic operations. Every operation below realises to a real opcode, verified against
RuntimePrimitives in tests/test_intent_planning.py.

This is the ONE place that defines the semantic-operation vocabulary and how each semantic
operation is realised as a RuntimeEngine opcode step. It is owned by / colocated with
AlgorithmDerivation (the single planning authority); no other layer imports mapping knowledge.

Two things live here, deliberately together under one owner but kept as separate levels:

  1. SEMANTIC OPERATIONS — the vocabulary a plan is expressed in (GROUP, COUNT, SORT_DESC, LIMIT,
     AVG, COMPARE, PATH, …). This is the complete inventory, not a fixed short list.

  2. REALIZATION — how each semantic operation becomes an executable opcode step
     (SORT_DESC -> (op_sort, {"desc": True}); AVG -> (op_aggregate, {"fn": "avg"}); …).
     Opcode names here MUST exist in RuntimePrimitives.

AlgorithmDerivation uses (1) for semantic planning (roles -> operations) and (2) for execution
planning (operations -> opcode plan). Keeping both in this inventory makes the operation vocabulary
a single source of truth while preserving the two logical levels.
"""

# ---- 1. Semantic operation vocabulary (complete inventory) ----------------------------------
GROUP = "GROUP"
COUNT = "COUNT"
SUM = "SUM"
AVG = "AVG"
MIN = "MIN"
MAX = "MAX"
FILTER = "FILTER"
JOIN = "JOIN"
SORT_ASC = "SORT_ASC"
SORT_DESC = "SORT_DESC"
LIMIT = "LIMIT"
DISTINCT = "DISTINCT"
COMPARE = "COMPARE"
PATH = "PATH"
DEPENDENCY = "DEPENDENCY"
REACHABILITY = "REACHABILITY"
EXPLAIN = "EXPLAIN"
SEARCH = "SEARCH"
SHOW = "SHOW"
OPEN = "OPEN"
COUNT_RELATED = "COUNT_RELATED"
REVERSE = "REVERSE"
EVIDENCE = "EVIDENCE"

# The inventory (ordered, canonical). Membership check + iteration source of truth.
OPERATIONS = (GROUP, COUNT, SUM, AVG, MIN, MAX, FILTER, JOIN, SORT_ASC, SORT_DESC, LIMIT,
              DISTINCT, COMPARE, PATH, DEPENDENCY, REACHABILITY, EXPLAIN, SEARCH, SHOW, OPEN,
              COUNT_RELATED, REVERSE, EVIDENCE)


# ---- 2. Realization: semantic operation -> opcode step(s) -----------------------------------
# Each value is a list of (opcode_name, kwargs-template). kwargs-template values that are the
# string "<value>" are filled by the planner from the CanonicalIntent (e.g. LIMIT's n). Opcode
# names must match RuntimePrimitives.
_REALIZE = {
    GROUP:        [("op_group", {})],
    COUNT:        [("op_aggregate", {"fn": "count"})],
    SUM:          [("op_aggregate", {"fn": "sum"})],
    AVG:          [("op_aggregate", {"fn": "avg"})],
    MIN:          [("op_aggregate", {"fn": "min"})],
    MAX:          [("op_aggregate", {"fn": "max"})],
    FILTER:       [("op_filter", {})],
    JOIN:         [("op_join", {})],
    SORT_ASC:     [("op_sort", {"desc": False})],
    SORT_DESC:    [("op_sort", {"desc": True})],
    LIMIT:        [("op_limit", {"n": "<value>"})],
    DISTINCT:     [("op_distinct", {})],
    COMPARE:      [("op_compare", {})],
    PATH:         [("graph_shortest_path", {})],
    DEPENDENCY:   [("graph_dependency", {})],
    REACHABILITY: [("graph_reachability", {})],
    EXPLAIN:      [("explain", {})],
    SEARCH:       [("op_search", {})],
    SHOW:         [("render_table", {})],
    OPEN:         [("open_entity", {})],
    COUNT_RELATED: [("count_related", {})],
    REVERSE:      [("reverse_lookup", {})],
    EVIDENCE:     [("evidence_jump", {})],
}


def is_operation(op):
    return op in OPERATIONS


def realize(op, values=None):
    """Realize one semantic operation into opcode step(s): a list of (opcode_name, kwargs).
    `values` (from the intent) fills any '<value>' placeholder (used by LIMIT's n)."""
    steps = _REALIZE.get(op)
    if not steps:
        return []
    out = []
    for name, tmpl in steps:
        kw = {}
        for k, v in tmpl.items():
            if v == "<value>":
                if values:
                    kw[k] = values[0]
                # else omit -> opcode uses its own default
            else:
                kw[k] = v
        out.append((name, kw))
    return out
