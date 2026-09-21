"""Living Vocabulary Registry — append-only, ambiguity-aware, evidence-backed.

Owns every human SURFACE WORD (alias). A word may map to MULTIPLE candidates; resolution chooses
the best later. Nothing is ever overwritten — the registry is append-only with a full lifecycle,
so history is always auditable.

Corrections applied (accepted architecture):
  2. Ambiguity: a word holds a LIST of candidates, each with its own confidence/evidence/source.
  3. Evidence-backed confidence: every candidate carries confidence + reason + evidence +
     matched_signals (e.g. 3/3) + source. Confidence never stands alone.
  4. Append-only lifecycle: ACTIVE / DEPRECATED / REJECTED / SUPERSEDED. Adding a new mapping for a
     word supersedes the prior ACTIVE candidate (marked SUPERSEDED) but keeps it in history.

This registry never resolves workbook entities (Resolver owns that) and never parses grammar
(parser owns that). It stores surface-word → candidate(s), with provenance and lifecycle.
"""

ACTIVE = "active"
DEPRECATED = "deprecated"
REJECTED = "rejected"
SUPERSEDED = "superseded"


class Candidate:
    """One (word → canonical) mapping with full evidence, owner authority, and lifecycle."""
    __slots__ = ("word", "canonical", "type", "source", "owner", "reason", "evidence",
                 "matched_signals", "total_signals", "confidence", "version", "status")

    def __init__(self, word, canonical, ctype, source, confidence,
                 owner=None, reason=None, evidence=None, matched_signals=None,
                 total_signals=None, version=1, status=ACTIVE):
        self.word = word.lower()
        self.canonical = canonical
        self.type = ctype
        self.source = source
        self.owner = owner            # owning registry/object that produced this candidate
        self.reason = reason
        self.evidence = evidence
        self.matched_signals = matched_signals
        self.total_signals = total_signals
        self.confidence = float(confidence)
        self.version = int(version)
        self.status = status

    def signals_str(self):
        if self.matched_signals is None or self.total_signals is None:
            return None
        return "%d/%d" % (self.matched_signals, self.total_signals)

    def as_dict(self):
        return {"word": self.word, "canonical": self.canonical, "type": self.type,
                "source": self.source, "owner": self.owner, "reason": self.reason,
                "evidence": self.evidence, "matched_signals": self.matched_signals,
                "total_signals": self.total_signals, "signals": self.signals_str(),
                "confidence": self.confidence, "version": self.version, "status": self.status}


class VocabularyRegistry:
    """Append-only, ambiguity-aware. word -> list[Candidate] (all versions, all statuses)."""

    def __init__(self):
        self._words = {}   # word -> list[Candidate]  (append-only; never truncated)
        self._audit = []   # append-only op log

    # ---- registration (append-only) -----------------------------------------------------
    def add(self, word, canonical, ctype, source, confidence=1.0, owner=None, reason=None,
            evidence=None, matched_signals=None, total_signals=None, supersede=True):
        """Append a candidate mapping for `word`. Requires a source (provenance). `owner` records
        the owning registry/object that produced the candidate (so resolution always knows which
        canonical authority stands behind each one). If `supersede` and an ACTIVE candidate for
        the SAME canonical exists, that prior one is marked SUPERSEDED (kept in history) and the
        new one becomes ACTIVE. Different canonicals coexist as ambiguous candidates. Never
        overwrites; always appends."""
        w = str(word).strip().lower()
        if not w or not canonical or not source:
            return False
        lst = self._words.setdefault(w, [])
        version = 1 + max([c.version for c in lst if c.canonical == canonical], default=0)
        if supersede:
            for c in lst:
                if c.canonical == canonical and c.status == ACTIVE:
                    c.status = SUPERSEDED
                    self._audit.append({"op": "supersede", **c.as_dict()})
        cand = Candidate(w, canonical, ctype, source, confidence, owner, reason, evidence,
                         matched_signals, total_signals, version, ACTIVE)
        lst.append(cand)
        self._audit.append({"op": "add", **cand.as_dict()})
        return True

    def _set_status(self, word, canonical, status):
        w = str(word).strip().lower()
        changed = False
        for c in self._words.get(w, []):
            if c.status == ACTIVE and (canonical is None or c.canonical == canonical):
                c.status = status
                c.version += 1
                self._audit.append({"op": status, **c.as_dict()})
                changed = True
        return changed

    def deprecate(self, word, canonical=None):
        return self._set_status(word, canonical, DEPRECATED)

    def reject(self, word, canonical=None):
        return self._set_status(word, canonical, REJECTED)

    # ---- lookup / ambiguity -------------------------------------------------------------
    def candidates(self, word):
        """All ACTIVE candidates for a word, best-confidence first (ambiguity preserved)."""
        w = str(word).strip().lower() if word is not None else ""
        act = [c for c in self._words.get(w, []) if c.status == ACTIVE]
        return sorted(act, key=lambda c: -c.confidence)

    def resolve(self, word):
        """Best single ACTIVE candidate (highest confidence), or None. Ambiguity is available via
        candidates(); resolve() is the convenience 'best guess' used where one is needed."""
        cs = self.candidates(word)
        return cs[0] if cs else None

    def history(self, word):
        """Complete append-only history for a word — every candidate, every status."""
        w = str(word).strip().lower() if word is not None else ""
        return [c.as_dict() for c in self._words.get(w, [])]

    def entries(self, status=ACTIVE, canonical=None, ctype=None):
        out = []
        for lst in self._words.values():
            for c in lst:
                if (status is None or c.status == status) and \
                   (canonical is None or c.canonical == canonical) and \
                   (ctype is None or c.type == ctype):
                    out.append(c.as_dict())
        return out

    def audit(self):
        return list(self._audit)

    def phrase_exists(self, phrase):
        """Single, meaning-free API for the Tokenizer: does this surface phrase exist as a known
        vocabulary word (any active candidate)? Returns bool only — no candidate, no canonical, no
        type. The caller never learns which underlying vocabulary (universal grammar vs workbook)
        backs it; that stays hidden behind this registry. Read-only."""
        if phrase is None:
            return False
        w = str(phrase).strip().lower()
        if not w:
            return False
        return any(c.status == ACTIVE for c in self._words.get(w, []))

    # ---- explainability -----------------------------------------------------------------
    def explain(self, word):
        """Explainability: the best candidate with full evidence, plus any competing candidates.
        Returns a miss record (not None) when unknown, so callers always have something to show."""
        cs = self.candidates(word)
        if not cs:
            return {"word": str(word).strip().lower() if word else "", "match": False,
                    "reason": "no vocabulary entry", "canonical": None, "type": None,
                    "candidate": None, "confidence": 0.0, "source": None,
                    "signals": None, "alternatives": []}
        best = cs[0]
        reason = best.reason or ("exact match" if best.word == best.canonical.lower() else "alias match")
        return {"word": best.word, "match": True, "reason": reason,
                "canonical": best.canonical, "type": best.type, "owner": best.owner,
                "candidate": best.evidence or best.canonical,
                "confidence": best.confidence, "source": best.source,
                "signals": best.signals_str(),
                "alternatives": [{"canonical": c.canonical, "candidate": c.evidence or c.canonical,
                                  "owner": c.owner, "confidence": c.confidence, "source": c.source,
                                  "reason": c.reason} for c in cs[1:]]}
