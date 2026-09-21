"""Entity Resolution — any input token (ID | name | file | file:line | class:name)
-> Entity (owner row).

An Entity is NOT a query. Queries are derived from the entity separately.

TYPE-AWARE, GLOBALLY-UNIQUE (canonical-identity backed)
    Resolution no longer returns the first cross-registry label match. Identity is the
    class-scoped canonical key, so:
      * an exact ID resolves through the prefix-independent canonical index (numeric pks
        included), not a `[A-Z]+-` regex;
      * an exact NAME that is unique across classes resolves directly; if the same name
        exists in more than one class it is AMBIGUOUS and returns candidates — never an
        arbitrary auto-open (this is the "same name, different class -> wrong entity" fix);
      * `Class:name` (or `Class::name`) lets a caller disambiguate explicitly;
      * an ambiguous raw pk (same pk reused across registries) also returns candidates.
"""
import re

_CLASS_SCOPED = re.compile(r'^\s*(.+?)\s*::?\s*(.+?)\s*$')  # "Class:name" / "Class::name"


class EntityResolver:
    def __init__(self, model, promotions=None, language=None, vocabulary=None):
        self.m = model
        self.promotions = promotions
        # Stage 5: the resolver COMBINES two registries but owns neither's logic.
        #   language   — grammar concepts (asked, never parsed here)
        #   vocabulary — workbook-derived candidates (owner-tagged); entity resolution below
        # stays the resolver's own authority. Strict separation: language never resolves
        # entities; vocabulary never parses grammar; resolver arbitrates.
        self.language = language
        self.vocabulary = vocabulary

    def _ident(self):
        return getattr(self.m, "identity", None)

    def _owner_regs(self):
        return [(reg, meta) for reg, meta in self.m.catalog.items()
                if meta["role"].startswith("Owner")]

    def _row_in(self, reg, pk):
        for r in self.m.rows(reg):
            if r and str(r[0]) == str(pk):
                return r
        return None

    def resolve(self, token):
        token = str(token).strip()
        ident = self._ident()

        # 1) Direct ID (display id, raw pk, or canonical key) via the identity registry API.
        if ident is not None:
            res = ident.resolve(token)
            if res["status"] == "ambiguous":
                cands = [{"id": c["pk"], "class": c["registry"], "name": c["name"],
                          "canonical": c["canonical"]} for c in res["candidates"]]
                return {"id": None, "candidates": cands, "how": "ambiguous_id"}
            if res["status"] == "unique":
                row = self._row_in(res["registry"], res["pk"])
                if row:
                    return {"id": str(row[0]), "class": res["registry"], "row": row,
                            "canonical": res["canonical"], "how": "id"}

        # Legacy direct-ID path (only reached if identity index missed).
        t, row = self.m.owner_row(token)
        if row:
            return {"id": str(row[0]), "class": t, "row": row, "how": "id"}

        # 2) Explicit class-scoped name: "Class:name" — type-aware, unambiguous by construction.
        mcs = _CLASS_SCOPED.match(token)
        if mcs:
            cls_hint, name_hint = mcs.group(1), mcs.group(2)
            for reg, meta in self._owner_regs():
                if reg.lower() != cls_hint.lower() and cls_hint.lower() not in reg.lower():
                    continue
                for r in self.m.rows(reg):
                    if r and len(r) > 1 and isinstance(r[1], str) and r[1].lower() == name_hint.lower():
                        return {"id": str(r[0]), "class": reg, "row": r, "how": "class_name"}

        # 3) Exact NAME across all owner classes. Only auto-resolve when globally unique.
        exact = []
        for reg, meta in self._owner_regs():
            for r in self.m.rows(reg):
                if r and len(r) > 1 and isinstance(r[1], str) and r[1].lower() == token.lower():
                    exact.append({"id": str(r[0]), "class": reg, "row": r, "name": r[1]})
        if len(exact) == 1:
            e = exact[0]
            return {"id": e["id"], "class": e["class"], "row": e["row"], "how": "name"}
        if len(exact) > 1:
            return {"id": None,
                    "candidates": [{"id": e["id"], "class": e["class"], "name": e["name"]} for e in exact[:8]],
                    "how": "ambiguous_name"}

        # 4) Promoted semantic object (email/phone/serial/etc.).
        if self.promotions is not None:
            promo = self.promotions.resolve(token)
            if promo:
                return {"id": promo["id"], "class": promo["class"], "row": None, "how": promo["how"]}

        # 5) Fuzzy name (substring) -> candidates only.
        cands = []
        for reg, meta in self._owner_regs():
            for r in self.m.rows(reg):
                if r and len(r) > 1 and isinstance(r[1], str) and token.lower() in r[1].lower():
                    cands.append({"id": str(r[0]), "class": reg, "name": r[1]})
        if cands:
            return {"id": None, "candidates": cands[:8], "how": "fuzzy"}

        # 6) Typo / near-miss tolerance -> candidates only. Edit-distance (difflib ratio)
        # against owner entity names AND registry-derived vocabulary. This is what lets
        # 'ordr'/'prdct'/'custmer' resolve. No hardcoded vocabulary: the candidate pool is the
        # workbook's own discovered names. Never auto-opens; always returns ranked candidates.
        import difflib
        tl = token.lower()
        near = []
        for reg, meta in self._owner_regs():
            for r in self.m.rows(reg):
                if not (r and len(r) > 1 and isinstance(r[1], str)):
                    continue
                nm = r[1]
                ratio = difflib.SequenceMatcher(None, tl, nm.lower()).ratio()
                # also compare against each significant word of the name (so a typo of one
                # word in a multi-word name still scores), taking the best.
                for w in nm.lower().split():
                    if len(w) >= 3:
                        ratio = max(ratio, difflib.SequenceMatcher(None, tl, w).ratio())
                if ratio >= 0.8:
                    near.append((ratio, {"id": str(r[0]), "class": reg, "name": nm}))
        if near:
            near.sort(key=lambda x: -x[0])
            seen = set(); out = []
            for _, c in near:
                if c["id"] in seen:
                    continue
                seen.add(c["id"]); out.append(c)
            return {"id": None, "candidates": out[:8], "how": "typo"}
        return {"id": None, "how": "unresolved"}

    # ---- Stage 5: combining layer (grammar concept | workbook term | entity) -------------
    def classify(self, token):
        """Classify a single token by consulting, in order and with strict separation:
          1) Language Registry — is it a grammar CONCEPT? (the registry decides; we only ask)
          2) Vocabulary Registry — workbook-derived candidates (ENTITY/ATTRIBUTE/RELATION),
             owner-tagged, ambiguity preserved
          3) Entity resolution — this resolver's own authority (resolve())
        Returns {kind, token, ...}. kind ∈ {concept, workbook, entity, ambiguous, unresolved}.
        The layer never parses grammar itself and never lets a registry resolve an entity; it
        only arbitrates between the owners' answers."""
        tok = str(token).strip()

        # 1) grammar concept — ask the Language Registry (it owns grammar)
        if self.language is not None:
            concept = self.language.lookup(tok)
            if concept is not None:
                return {"kind": "concept", "token": tok,
                        "canonical": concept.canonical, "type": concept.type}

        # 2) workbook vocabulary candidates (owner-tagged, ambiguity preserved)
        if self.vocabulary is not None:
            cands = self.vocabulary.candidates(tok)
            if cands:
                out = [{"canonical": c.canonical, "type": c.type, "owner": c.owner,
                        "confidence": c.confidence, "source": c.source,
                        "reason": c.reason, "evidence": c.evidence,
                        "signals": c.signals_str()} for c in cands]
                # single unambiguous ENTITY candidate -> resolve it to an entity for convenience,
                # but keep the vocabulary provenance.
                if len(out) == 1 and out[0]["type"] == "ENTITY":
                    r = self.resolve(out[0]["canonical"])
                    return {"kind": "workbook", "token": tok, "best": out[0],
                            "candidates": out, "entity": r if r.get("id") else None}
                return {"kind": "workbook", "token": tok, "best": out[0], "candidates": out}

        # 3) entity resolution — the resolver's own authority
        r = self.resolve(tok)
        if r.get("id"):
            return {"kind": "entity", "token": tok, "id": r["id"],
                    "class": r.get("class"), "how": r.get("how")}
        if r.get("candidates"):
            return {"kind": "ambiguous", "token": tok, "candidates": r["candidates"],
                    "how": r.get("how")}
        return {"kind": "unresolved", "token": tok}

    def _name_of(self, reg, pk):
        r = self._row_in(reg, pk)
        return r[1] if r and len(r) > 1 and isinstance(r[1], str) else None
