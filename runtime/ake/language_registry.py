"""Universal Language Registry — CONCEPTS ONLY (Stage 3, refactored).

This registry owns the canonical SEMANTIC CONCEPTS and their grammar TYPES — nothing else.
Every human surface word (show, display, buy, highest, …) lives in the Living Vocabulary
Registry as an alias pointing at a canonical concept here. Concepts ↔ Vocabulary are separate
owners (maintenance + auditability), joined at construction.

Versioned Grammar (correcting the earlier "grammar stable" overstatement):
  * The TYPE set and the canonical concept set CAN grow (e.g. adding CAUSE / GOAL / PROBABILITY
    later). They are not frozen forever — they are VERSIONED. GRAMMAR_VERSION bumps whenever the
    concept/type set changes, so evolution is explicit and auditable.
  * Within a version the concepts are stable: the parser depends only on canonical concepts, and
    a given version's meaning does not shift.

Concept set = the semantic roles a query can carry (ACTION/QUESTION/QUALIFIER/CONSTRAINT/
  TIME/LOGIC/VALUE_MOD). The registry assigns roles only. It stores NO execution knowledge:
  the mapping from a concept (TOP, AVERAGE, COUNT) to an opcode sequence is AlgorithmDerivation's
  exclusive responsibility (Stage 7). This preserves one-capability-one-owner: grammar names the
  role; the planner turns the role into primitives later.

This registry NEVER resolves workbook entities (Resolver owns that) and NEVER stores raw surface
words (Vocabulary owns those).
"""
from .vocabulary_registry import VocabularyRegistry

GRAMMAR_VERSION = 3

# TYPE constants (versioned grammar; may grow in future versions)
ACTION = "ACTION"
QUESTION = "QUESTION"
QUALIFIER = "QUALIFIER"
CONSTRAINT = "CONSTRAINT"
TIME = "TIME"
LOGIC = "LOGIC"
VALUE_MOD = "VALUE_MOD"

TYPES = (ACTION, QUESTION, QUALIFIER, CONSTRAINT, TIME, LOGIC, VALUE_MOD)


class Concept:
    """A canonical SEMANTIC concept: its canonical name and grammar TYPE. Nothing else.

    The Language Registry owns semantics only. It deliberately does NOT store opcodes, kwargs,
    plan fragments, or any execution knowledge — the transformation from a canonical concept to a
    primitive opcode sequence belongs exclusively to AlgorithmDerivation (Stage 7). Keeping
    planning out of here preserves 'one capability, one owner': grammar assigns roles; the planner
    plans."""
    __slots__ = ("canonical", "type")

    def __init__(self, canonical, ctype):
        self.canonical = canonical
        self.type = ctype

    def as_dict(self):
        return {"canonical": self.canonical, "type": self.type}


# Canonical concept set (concept -> (type, seed surface words)). Seed words load into the
# Vocabulary Registry at construction with source 'core'; they are NOT stored on the concept.
# NO opcodes here by design — see Concept docstring.
_CORE = [
    # (canonical, type, seed surface words) — SEMANTICS ONLY. No opcodes: concept→opcode mapping
    # is AlgorithmDerivation's job (Stage 7). Seed words load into the Vocabulary Registry.
    ("SHOW",    ACTION,    ("show", "display", "list", "give", "get", "return")),
    ("COUNT",   ACTION,    ("count", "number", "tally", "kitne", "kitna", "how many", "howmany")),
    ("COMPARE", ACTION,    ("compare", "versus", "vs", "difference", "diff")),
    ("EXPLAIN", ACTION,    ("explain", "why", "reason", "justify")),
    ("ANALYZE", ACTION,    ("analyze", "analyse", "analysis", "inspect", "examine")),
    ("FIND",    ACTION,    ("find", "search", "locate", "lookup")),
    ("TRACE",   ACTION,    ("trace", "path", "route", "connect", "reach", "reaches")),
    ("DEPEND",  ACTION,    ("depends", "depend", "dependency", "dependencies", "requires", "needs", "upstream")),
    ("IMPACT",  ACTION,    ("impacts", "impact", "affects", "affect", "downstream")),
    ("REVERSE", ACTION,    ("uses", "used-by", "usedby", "used by", "consumed-by", "consumedby",
                           "consumed by", "consumers", "referenced-by", "referencedby",
                           "referenced by", "points-to", "points to", "depended-on-by",
                           "depended on by")),
    ("EVIDENCE",ACTION,    ("evidence", "source", "provenance", "cell", "sheet", "row-of", "backing")),
    ("WHAT",    QUESTION,  ("what",)),
    ("WHICH",   QUESTION,  ("which",)),
    ("WHO",     QUESTION,  ("who", "whom")),
    ("WHERE",   QUESTION,  ("where",)),
    ("HOWMANY", QUESTION,  ("how-many", "howmany")),
    ("TOP",     QUALIFIER, ("top", "most", "highest", "best")),
    ("BOTTOM",  QUALIFIER, ("bottom", "least", "lowest", "worst", "fewest")),
    ("FIRST",   QUALIFIER, ("first", "earliest")),
    ("LAST",    QUALIFIER, ("last", "latest")),
    ("UNIQUE",  QUALIFIER, ("unique", "distinct", "different")),
    ("EQUALS",  CONSTRAINT,("equals", "equal", "is", "of")),
    ("GREATER", CONSTRAINT,("greater", "more", "above", "over")),
    ("LESS",    CONSTRAINT,("less", "fewer", "below", "under")),
    ("CONTAINS",CONSTRAINT,("contains", "has", "having", "with", "includes")),
    ("BETWEEN", CONSTRAINT,("between", "range")),
    ("AFTER",   TIME,      ("after", "since", "from")),
    ("BEFORE",  TIME,      ("before", "until", "till")),
    ("DURING",  TIME,      ("during", "within")),
    ("AND",     LOGIC,     ("and", "plus", "also")),
    ("OR",      LOGIC,     ("or", "either")),
    ("NOT",     LOGIC,     ("not", "without", "except", "excluding")),
    ("TOTAL",   VALUE_MOD, ("total", "sum", "summed")),
    ("AVERAGE", VALUE_MOD, ("average", "avg", "mean")),
    ("MIN",     VALUE_MOD, ("minimum", "min", "smallest")),
    ("MAX",     VALUE_MOD, ("maximum", "max", "largest", "biggest")),
]


class UniversalLanguageRegistry:
    """Owner of canonical concepts (versioned grammar). Aliases are delegated to a Living
    Vocabulary Registry so the two concerns are separate. All prior APIs preserved:
    lookup / is_concept / concepts / register_alias / audit."""

    def __init__(self, vocabulary=None):
        self.version = GRAMMAR_VERSION
        self._concepts = {}                       # canonical -> Concept
        self.vocab = vocabulary or VocabularyRegistry()
        self._build_core()

    def _build_core(self):
        for canonical, ctype, seeds in _CORE:
            self._concepts[canonical] = Concept(canonical, ctype)
            # the canonical word itself + its seed surface words become 'core' vocabulary aliases
            self.vocab.add(canonical, canonical, ctype, source="core", owner="grammar", confidence=1.0)
            for w in seeds:
                self.vocab.add(w, canonical, ctype, source="core", owner="grammar", confidence=1.0)

    # ---- concept access ------------------------------------------------------------------
    def concept(self, canonical):
        return self._concepts.get(canonical)

    def concepts(self, ctype=None):
        cs = self._concepts.values()
        if ctype:
            cs = [c for c in cs if c.type == ctype]
        return [c.as_dict() for c in cs]

    # ---- lookup (preserved API): surface word -> Concept ---------------------------------
    def lookup(self, word):
        """Surface word -> canonical Concept (via the Vocabulary Registry), or None. A miss means
        'not a language concept' — the Resolver then tries it as an entity."""
        e = self.vocab.resolve(word)
        if e is None:
            # tolerance: hyphen/space variants
            for variant in (str(word).strip().lower().replace(" ", "-"),
                            str(word).strip().lower().replace("-", "")):
                e = self.vocab.resolve(variant)
                if e:
                    break
        return self._concepts.get(e.canonical) if e else None

    def is_concept(self, word):
        return self.lookup(word) is not None

    # ---- preserved API: register_alias / audit ------------------------------------------
    def register_alias(self, alias, canonical, source, evidence=None, confidence=1.0):
        """Add a surface-word alias to an EXISTING canonical concept, with provenance. Cannot
        create new canonical concepts (grammar is versioned, changed only by GRAMMAR_VERSION
        bumps). Delegates storage to the Vocabulary Registry."""
        a = str(alias).strip().lower()
        if not a or canonical not in self._concepts or not source:
            return False
        return self.vocab.add(a, canonical, self._concepts[canonical].type,
                              source=source, evidence=evidence, confidence=confidence)

    def audit(self):
        """Alias audit comes from the Vocabulary Registry (single source of alias provenance)."""
        return [{"alias": e["word"], "canonical": e["canonical"], "type": e["type"],
                 "source": e["source"], "confidence": e["confidence"],
                 "version": e["version"], "status": e["status"]}
                for e in self.vocab.entries(status=None)]
