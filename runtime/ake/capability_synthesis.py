"""Capability Synthesis — the ONLY producer of Canonical Actions (Canonical Capability
Synthesis Contract v2).

Reads nothing but Canonical Runtime Knowledge Discovery already produced on `model`
(universal_graph, universal_edges, _relation_target_map) plus whatever an entity's own
already-derived menu items carry (AKE.entity_actions()'s physical-entity derivation, or
SemanticPromotion.actions() for a promoted one -- ake/semantic_promotion.py). It never
re-reads the workbook and never builds a second graph: `canonicalize()` is a pure
post-processing pass over an already-built list of plain-dict actions.

Every action gets an immutable canonical_identity = (canonical_source, canonical_key,
target). Collision detection is by that identity alone, never by label (§6): two
actions that resolve to the same identity are merged (their availability/count union);
two actions with different identities both survive even if their labels happen to
match. discovery_stage and provenance are attached per action and are never inferred
from display text.
"""

_PROVENANCE = {
    "attribute": "scalar_attribute",
    "relation_direct": "foreign_key",
    "relation_discovered": "reachability",
    "neighbors": "derived_relation",
    "meta": "scalar_attribute",
    "analysis": "analysis",
    "promoted": "promoted_entity",
}

_STAGE = {
    "attribute": "SchemaDiscovery",
    "relation_direct": "RelationshipDiscovery",
    "relation_discovered": "ReachabilityDiscovery",
    "neighbors": "RelationshipDiscovery",
    "meta": "SchemaDiscovery",
    "analysis": "AnalysisDiscovery",
    "promoted": "SemanticPromotion",
}

_CAPABILITY = {
    "attribute": "Identity",
    "relation_direct": "Relationships",
    "relation_discovered": "Relationships",
    "neighbors": "Relationships",
    "meta": "Evidence",
    "analysis": "Analysis",
    "promoted": "Identity",
}

_EVIDENCE_LABEL = {
    "attribute": "owner registry row",
    "relation_direct": "Relationship (Universal Property Graph)",
    "neighbors": "Universal Property Graph",
    "meta": "owner registry row",
    "analysis": "graph + registry (derived)",
}

# Fixed (non-relation) query codes get a stable canonical_key -- "*" for GET_NEIGHBORS
# matches capability_matrix.py's own convention for the same aggregate concept.
_FIXED_KEY = {"WHAT_IS": "class", "GET_NAME": "name", "GET_EVIDENCE": "evidence",
              "GET_SOURCE_ROW": "source_row", "GET_NEIGHBORS": "*"}


def _bucket(act):
    if act.get("_promoted"):
        return "promoted"
    if act["type"] == "attr":
        return "attribute"
    if act["type"] == "meta":
        return "neighbors" if act["query"] == "GET_NEIGHBORS" else "meta"
    if act["type"] == "analysis":
        return "analysis"
    if act["type"] == "relation":
        return "relation_discovered" if act.get("mode") == "discovered" else "relation_direct"
    return "meta"


def _target(act, bucket, target_map):
    if "_target" in act:
        return act["_target"]
    if act.get("discovery"):
        return act["discovery"].get("target_class")
    if act.get("relation"):
        tcs = sorted(target_map.get(act["relation"], []) or [])
        if len(tcs) == 1:
            return tcs[0]
        if tcs:
            return ",".join(tcs)
    return None


def _confidence(act, bucket):
    if "_confidence" in act:
        return act["_confidence"]
    if bucket == "relation_discovered" and act.get("discovery"):
        conf = act["discovery"].get("confirmed", "")
        if isinstance(conf, str) and "/" in conf:
            try:
                num, den = conf.split("/")
                num, den = float(num), float(den)
                if den > 0:
                    return round(num / den, 3)
            except ValueError:
                pass
        return 0.5
    return 1.0 if act.get("available", True) else 0.0


def _evidence(act, bucket):
    if "_evidence" in act:
        return act["_evidence"]
    if bucket == "relation_discovered" and act.get("discovery"):
        return act["discovery"]
    if not act.get("available", True) and act.get("reason"):
        return act["reason"]
    return _EVIDENCE_LABEL.get(bucket, act.get("relation") or act.get("query"))


def canonicalize(actions, model):
    """Attach canonical_identity/provenance/discovery_stage/confidence/target/capability
    to every already-derived action, then dedupe by canonical_identity (§6). Renumbers
    `key` 1..N afterward so shell/dashboard/API numbering stays contiguous.

    `actions` is mutated in place and returned as a new, deduped, renumbered list --
    the caller's derivation logic (which entities/relations/counts exist) is untouched;
    this only adds the contract's required fields and performs collision detection."""
    target_map = getattr(model, "_relation_target_map", {})
    merged = {}
    out = []
    for act in actions:
        bucket = _bucket(act)
        key = act.get("relation") or _FIXED_KEY.get(act["query"], act["query"])
        identity = "%s::%s::%s" % (bucket, key, _target(act, bucket, target_map) or "")
        act["id"] = identity
        act["canonical_identity"] = identity
        act["canonical_source"] = bucket
        act["canonical_key"] = key
        act["provenance"] = act.get("_provenance") or _PROVENANCE[bucket]
        act["discovery_stage"] = act.get("_stage") or _STAGE[bucket]
        act["capability"] = act.get("_capability") or _CAPABILITY[bucket]
        act["confidence"] = _confidence(act, bucket)
        act["target"] = _target(act, bucket, target_map)
        act["evidence"] = _evidence(act, bucket)
        act["kind"] = act["type"]  # contract field name; "type" kept for existing renderers

        if identity in merged:
            prior = merged[identity]
            prior["available"] = prior.get("available") or act.get("available")
            prior["count"] = max(prior.get("count") or 0, act.get("count") or 0)
            prior["confidence"] = max(prior.get("confidence") or 0, act["confidence"] or 0)
            continue
        merged[identity] = act
        out.append(act)

    for i, act in enumerate(out, 1):
        act["key"] = str(i)
    return out
