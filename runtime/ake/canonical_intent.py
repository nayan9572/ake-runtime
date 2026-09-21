"""Canonical Intent Builder (Stage 6).

Assembles classified tokens (from EntityResolver.classify) into a Canonical Intent — the SEMANTIC
ROLE representation of a query. It records WHAT was said (Targets/References/Actions/Questions/
Qualifiers/Constraints/Time/Values) and nothing about HOW to execute it.

Boundary (accepted architecture, refined):
  * The builder ONLY assembles semantic roles. It does NOT derive operation sequences and does NOT
    emit opcodes. The mapping from a concept (TOP, COUNT, NEAREST, SIMILAR, …) to an operation
    sequence is ALGORITHMIC KNOWLEDGE and belongs to the single planning authority,
    AlgorithmDerivation (Stage 7) — so that derivation rules grow in ONE owner, not two.
  * AlgorithmDerivation reads the roles here and produces both the semantic operation sequence and
    the executable opcode plan. Keeping derivation out of the builder prevents it from gradually
    absorbing planning knowledge.

The builder is workbook-independent and names no operations or opcodes.
"""


class IntentNode:
    """A node in the Canonical Intent TREE. Preserves hierarchy that a flat role list loses.

    A node groups ONE semantic scope: an (optional) target plus the qualifiers/values/actions that
    apply to it. Children are nested scopes (e.g. 'top product' and 'top 10 customer' as sibling
    scopes under a 'Brand 1' parent). This lets AlgorithmDerivation consume natural hierarchy
    instead of reconstructing it from a flattened list. The tree carries roles only — no operations,
    no opcodes (same boundary as the flat intent)."""
    __slots__ = ("target", "actions", "qualifiers", "values", "constraints", "time", "children", "label")

    def __init__(self, label=None, target=None):
        self.label = label          # a short human label for the scope (e.g. "top product")
        self.target = target        # resolved target/reference dict for this scope (or None)
        self.actions = []
        self.qualifiers = []
        self.values = []
        self.constraints = []
        self.time = []
        self.children = []

    def add_child(self, node):
        self.children.append(node)
        return node

    def as_dict(self):
        return {"label": self.label, "target": self.target,
                "actions": self.actions, "qualifiers": self.qualifiers,
                "values": self.values, "constraints": self.constraints, "time": self.time,
                "children": [c.as_dict() for c in self.children]}


class CanonicalIntent:
    """A complete semantic ROLE representation. Roles only — no operations, no opcodes. The
    planner (AlgorithmDerivation) derives operation sequences and opcode plans from these roles."""
    __slots__ = ("targets", "references", "actions", "questions", "qualifiers",
                 "constraints", "time", "values", "unresolved", "tree")

    def __init__(self):
        self.targets = []       # entity/workbook candidates that are the subject
        self.references = []    # other entities mentioned (filter anchors)
        self.actions = []       # ACTION concepts (SHOW, COUNT, COMPARE…)
        self.questions = []     # QUESTION concepts (WHAT, WHICH…)
        self.qualifiers = []    # QUALIFIER concepts (TOP, UNIQUE…)
        self.constraints = []   # {op, value} filter descriptors (semantic role, not a FILTER op)
        self.time = []          # TIME concepts + value
        self.values = []        # numeric/literal values (e.g. 10, 2023)
        self.unresolved = []    # tokens that resolved to nothing
        self.tree = None        # IntentNode hierarchy (additive; flat lists above stay for compat)

    def as_dict(self):
        return {"targets": self.targets, "references": self.references,
                "actions": self.actions, "questions": self.questions,
                "qualifiers": self.qualifiers, "constraints": self.constraints,
                "time": self.time, "values": self.values, "unresolved": self.unresolved,
                "tree": self.tree.as_dict() if self.tree else None}


class CanonicalIntentBuilder:
    """Turns a natural-language query into a CanonicalIntent, using the resolver's classify() for
    every token and deriving semantic operations from the concepts found. Owns intent assembly and
    concept→semantic-operation derivation only; it never emits opcodes and never resolves entities
    itself (it delegates to the resolver)."""

    def __init__(self, resolver, tokenizer=None):
        self.resolver = resolver
        # Tokenizer is a separate owner (lexical front-end). The builder consumes ordered tokens;
        # it does not tokenize itself. If none is supplied, fall back to whitespace splitting so
        # the builder still works standalone (used only in isolated tests).
        self.tokenizer = tokenizer

    def _is_number(self, tok):
        t = tok.replace(",", "")
        return t.isdigit() or (t.count(".") == 1 and t.replace(".", "").isdigit())

    def build(self, query):
        intent = CanonicalIntent()
        tokens = self._tokenize(query)
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if self._is_number(tok):
                intent.values.append(int(tok) if tok.isdigit() else float(tok))
                i += 1
                continue
            c = self.resolver.classify(tok)
            kind = c["kind"]
            if kind == "concept":
                self._place_concept(c, intent, tokens, i)
            elif kind == "workbook":
                # first workbook noun is the target; further ones are references
                bucket = intent.targets if not intent.targets else intent.references
                bucket.append({"token": c["token"], "best": c["best"], "candidates": c["candidates"]})
            elif kind == "entity":
                bucket = intent.targets if not intent.targets else intent.references
                bucket.append({"token": c["token"], "id": c["id"], "class": c.get("class")})
            elif kind == "ambiguous":
                intent.references.append({"token": c["token"], "candidates": c["candidates"], "ambiguous": True})
            else:
                intent.unresolved.append(tok)
            i += 1
        self._build_tree(intent, tokens)
        return intent

    def _build_tree(self, intent, tokens):
        """Build the hierarchical IntentNode tree — additive to the flat roles.

        Hierarchy is derived from GRAMMAR SIGNALS, never from a connective dictionary. The rule is
        purely structural over the grammar TYPES the resolver already assigns:

          * A QUALIFIER concept (TOP/BOTTOM/UNIQUE…) opens a NEW scope — a qualifier always heads a
            ranked/limited sub-selection. Each such scope becomes a sibling under the root.
          * Non-qualifier tokens (entities, values, actions, constraints, times) attach to the
            CURRENT scope.
          * The first scope with a resolved entity target (or the pre-qualifier prelude) is the
            root; qualifier-headed scopes hang beneath it.

        No surface words (aur/ke/of/per…) are inspected — connectives are simply tokens that
        classify to no grammar role and are ignored. This keeps the parser language-independent:
        add a new connective in any language and nothing here changes, because hierarchy comes from
        the QUALIFIER grammar role, not the word."""
        root = IntentNode(label="root")
        current = root
        opened_scope = False

        for tok in tokens:
            if self._is_number(tok):
                current.values.append(int(tok) if tok.isdigit() else float(tok))
                continue
            c = self.resolver.classify(tok)
            k = c["kind"]
            if k == "concept":
                ty = c["type"]
                entry = {"canonical": c["canonical"], "type": ty}
                if ty == "QUALIFIER":
                    # grammar signal: a qualifier heads a new ranked scope
                    scope = IntentNode(label=c["canonical"].lower())
                    scope.qualifiers.append(entry)
                    root.add_child(scope)
                    current = scope
                    opened_scope = True
                elif ty in ("ACTION", "VALUE_MOD"):
                    current.actions.append(entry)
                elif ty == "CONSTRAINT":
                    current.constraints.append({"op": c["canonical"]})
                elif ty == "TIME":
                    current.time.append({"op": c["canonical"]})
                # QUESTION/LOGIC: structural only, no scope change
            elif k in ("workbook", "entity"):
                tgt = {"token": c["token"], "kind": k,
                       "id": c.get("id") or (c.get("best") or {}).get("canonical")}
                if current.target is None:
                    current.target = tgt
                else:
                    # a second entity in the same scope becomes a nested child scope
                    child = IntentNode(label=str(c["token"]), target=tgt)
                    current.add_child(child)
            # unresolved / ambiguous tokens (incl. connectives): ignored — no grammar role
        intent.tree = root

    def _tokenize(self, query):
        # Delegate to the Tokenizer owner (lexical front-end). It preserves multi-word vocabulary
        # phrases as single tokens. Use ORIGINAL text (not normalized) so downstream resolution
        # keeps case for exact-ID matching; the resolver handles case-insensitivity for names.
        if self.tokenizer is not None:
            return [t.text for t in self.tokenizer.tokenize(query)]
        return [w for w in str(query).replace("?", " ").split() if w]

    def _place_concept(self, c, intent, tokens, i):
        t = c["type"]
        entry = {"canonical": c["canonical"], "type": t}
        if t == "ACTION":
            intent.actions.append(entry)
        elif t == "QUESTION":
            intent.questions.append(entry)
        elif t == "QUALIFIER":
            intent.qualifiers.append(entry)
        elif t in ("CONSTRAINT",):
            # attach the next value if present (e.g. "= 1")
            val = tokens[i + 1] if i + 1 < len(tokens) else None
            intent.constraints.append({"op": c["canonical"], "value": val})
        elif t == "TIME":
            val = tokens[i + 1] if i + 1 < len(tokens) else None
            intent.time.append({"op": c["canonical"], "value": val})
        elif t == "VALUE_MOD":
            # value modifiers (TOTAL/AVERAGE/MIN/MAX) act like aggregation actions
            intent.actions.append(entry)
        # LOGIC concepts carry no bucket (structure only)
