"""Architecture Diagnosis Layer.

Produces a canonical DIAGNOSIS MODEL for a query: a layer-by-layer validation of the pipeline
(Tokenizer → Vocabulary → Grammar → Canonical Intent → Planner → Runtime) with a derived HEALTH
SCORE. This is the single owner of architecture validation/diagnosis.

Design principles (from the accepted architecture):
  * Blame is sequential: a downstream layer is only judged if the upstream layer delivered valid
    input. A word that never entered the vocabulary does NOT mean Grammar failed.
  * Correct refusal is SUCCESS: when the workbook lacks the required entities and the system does
    not fabricate, that layer is NOT_APPLICABLE, not FAIL.
  * Health Score is an ARCHITECTURE VALIDATION score (how cleanly the query flowed through owned
    layers), NOT an AI confidence.
  * This layer is LAZY: nothing here runs unless diagnosis is explicitly requested. It reuses
    existing owners (tokenizer, vocabulary, resolver, intent builder, planner); it plans/executes
    nothing new.
  * It renders nothing. It returns a model; the Analyzer/Renderer display it.

Verdicts: PASS, PARTIAL, FAIL, NOT_APPLICABLE, NOT_REACHED.
"""

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_REACHED = "NOT_REACHED"

# Weight each layer contributes to the health score. NOT_REACHED / NOT_APPLICABLE are excluded
# from the denominator (you can't score a layer that correctly had nothing to do).
_WEIGHT = {PASS: 1.0, PARTIAL: 0.5, FAIL: 0.0}


class ArchitectureDiagnosis:
    """Single owner of pipeline validation. Given a query, walks the owned layers in sequence and
    reports each layer's verdict + owner + root cause, then a health score. Reuse-only."""

    def __init__(self, ake):
        self.ake = ake

    def diagnose(self, query):
        a = self.ake
        stages = []

        # ---- 1. Tokenizer (lexical) ----
        toks = a.tokenizer.tokenize(query)
        tok_ok = len(toks) > 0
        stages.append(self._stage(
            "Tokenizer", "Universal Tokenizer",
            PASS if tok_ok else FAIL,
            expected="ordered tokens", actual="%d tokens" % len(toks),
            root_cause=None if tok_ok else "empty tokenization",
            evidence=[t.norm for t in toks]))

        # ---- 2. Vocabulary (which tokens are known words) ----
        unknown = [t.text for t in toks if not (a.vocabulary.phrase_exists(t.norm)
                                                or a.vocabulary.candidates(t.text))]
        # content words only (ignore obvious glue) for the verdict, but report all
        vocab_status = PASS if not unknown else PARTIAL
        stages.append(self._stage(
            "Vocabulary", "Vocabulary / Workbook Knowledge Registry",
            vocab_status,
            expected="query words resolvable to concepts/entities",
            actual="%d unknown" % len(unknown),
            root_cause=None if not unknown else ("no approved alias for: " + ", ".join(unknown[:6])),
            evidence=unknown))

        # ---- 3. classify -> concepts vs entities (Grammar + Resolver) ----
        kinds = {}
        for t in toks:
            kinds[t.text] = a.resolver.classify(t.text)["kind"]
        got_concept = any(k == "concept" for k in kinds.values())
        got_entity = any(k in ("workbook", "entity") for k in kinds.values())
        # Grammar is only judged on words that WERE known; if nothing was known, Grammar is NOT_REACHED
        known_any = len(unknown) < len(toks)
        grammar_status = (PASS if got_concept else (PARTIAL if known_any else NOT_REACHED))
        stages.append(self._stage(
            "Grammar", "Universal Language Registry",
            grammar_status,
            expected="known words classified into grammar/entity roles",
            actual="concepts=%s entities=%s" % (got_concept, got_entity),
            root_cause=(None if got_concept else
                        ("no input reached grammar" if not known_any else "no grammar concept matched")),
            evidence=kinds))

        # ---- 4. Canonical Intent (roles) ----
        intent = a.intent_builder.build(query)
        d = intent.as_dict()
        has_target = bool(d["targets"])
        has_roles = bool(d["actions"] or d["qualifiers"] or d["constraints"] or d["time"] or d["targets"])
        intent_status = PASS if has_roles else (NOT_APPLICABLE if not got_entity and not got_concept else PARTIAL)
        stages.append(self._stage(
            "Canonical Intent", "Canonical Intent Builder",
            intent_status,
            expected="semantic roles assembled",
            actual="targets=%d actions=%d qualifiers=%d" % (
                len(d["targets"]), len(d["actions"]), len(d["qualifiers"])),
            root_cause=(None if has_roles else "no resolvable roles (upstream unresolved)"),
            evidence={"targets": [t.get("token") for t in d["targets"]],
                      "actions": [x["canonical"] for x in d["actions"]],
                      "qualifiers": [x["canonical"] for x in d["qualifiers"]],
                      "unresolved": d["unresolved"]}))

        # ---- 5. Planner: validate EACH transformation (intent tree -> exec tree -> compiled plan) ----
        plan = a.planner.derive_from_intent(intent)
        ops = plan["operations"]
        rank_quals = [q for q in d["qualifiers"] if q["canonical"] in ("TOP", "BOTTOM")]
        # transformation A: intent tree ranking scopes
        itree = d.get("tree")
        def _intent_rank(node):
            if not node:
                return 0
            n = 1 if any(q["canonical"] in ("TOP", "BOTTOM") for q in node.get("qualifiers", [])) else 0
            for c in node.get("children", []):
                n += _intent_rank(c)
            return n
        intent_scopes = _intent_rank(itree)
        # transformation B: execution tree ranking scopes
        etree = plan.get("execution_tree")
        def _exec_rank(node):
            if not node:
                return 0
            n = 1 if any(op in ("SORT_DESC", "SORT_ASC") for op in node.get("operations", [])) else 0
            for c in node.get("children", []):
                n += _exec_rank(c)
            return n
        exec_scopes = _exec_rank(etree)
        # transformation C: compiled plan sort opcodes
        compiled_sorts = sum(1 for op, _ in plan["plan"] if op == "op_sort")
        # hierarchy is lost if it degrades at ANY transformation
        hierarchy_lost = (len(rank_quals) >= 2 and
                          (intent_scopes < len(rank_quals) or exec_scopes < intent_scopes
                           or compiled_sorts < exec_scopes))
        if not has_roles:
            planner_status = NOT_REACHED
            pcause = "no intent roles to plan"
        elif hierarchy_lost:
            planner_status = FAIL
            pcause = "hierarchy lost across transforms: intent=%d scopes, exec=%d, compiled sorts=%d (qualifiers=%d)" % (
                intent_scopes, exec_scopes, compiled_sorts, len(rank_quals))
        elif ops:
            planner_status = PASS
            pcause = None
        else:
            planner_status = PARTIAL
            pcause = "target resolved but no operation derived (missing concept/op)"
        stages.append(self._stage(
            "Planner", "AlgorithmDerivation",
            planner_status,
            expected="operations (hierarchy preserved) + opcode plan",
            actual="operations=%s target=%s" % (ops, plan["target"]),
            root_cause=pcause,
            evidence={"operations": ops, "plan": [[p[0], p[1]] for p in plan["plan"]],
                      "target": plan["target"], "ranking_qualifiers": len(rank_quals),
                      "intent_scopes": intent_scopes, "exec_scopes": exec_scopes,
                      "compiled_sorts": compiled_sorts,
                      "ranking_scopes_in_tree": exec_scopes}))

        # ---- 6. Runtime (execution + evidence), only if there is a plan ----
        if plan["plan"]:
            out = a.engine.run(plan["plan"], {"target": plan["target"]} if plan["target"] else {})
            ran = out.get("executed") == [p[0] for p in plan["plan"]]
            runtime_status = PASS if ran else FAIL
            stages.append(self._stage(
                "Runtime", "RuntimeEngine",
                runtime_status,
                expected="plan executed with evidence",
                actual="executed=%s" % out.get("executed"),
                root_cause=None if ran else "execution diverged from plan",
                evidence={"executed": out.get("executed"), "has_evidence": bool(out.get("evidence"))}))
        else:
            stages.append(self._stage(
                "Runtime", "RuntimeEngine", NOT_REACHED,
                expected="plan execution",
                actual="no plan to execute",
                root_cause="planner produced no opcode plan", evidence={}))

        health = self._health(stages)
        return {"query": query, "health": health, "stages": stages}

    def _stage(self, name, owner, status, expected, actual, root_cause, evidence):
        return {"stage": name, "owner": owner, "status": status,
                "expected": expected, "actual": actual,
                "root_cause": root_cause, "evidence": evidence}

    def _health(self, stages):
        """Architecture validation score: mean of scored layers (PASS=1, PARTIAL=.5, FAIL=0),
        excluding NOT_REACHED and NOT_APPLICABLE (a layer that correctly had nothing to do neither
        helps nor hurts). Returns {score, band, scored, total_layers}."""
        scored = [s for s in stages if s["status"] in _WEIGHT]
        if not scored:
            return {"score": None, "band": "n/a", "scored": 0, "total_layers": len(stages)}
        val = sum(_WEIGHT[s["status"]] for s in scored) / len(scored)
        pct = int(round(val * 100))
        band = "green" if pct >= 85 else ("yellow" if pct >= 55 else "red")
        return {"score": pct, "band": band, "scored": len(scored), "total_layers": len(stages)}
