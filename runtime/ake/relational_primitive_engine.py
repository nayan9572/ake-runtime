"""RPDE — Relational Primitive Derivation Engine (missing compiler pass).
FK observation -> typed relational primitive (edge). Relation vocabulary is DERIVED from column
headers (workbook semantics), NOT hardcoded. Resolves both ID-valued and NAME-valued references."""
import re
from collections import defaultdict, Counter
ID = re.compile(r'^[A-Z]+-\w')

class RelationalPrimitiveEngine:
    def __init__(self, model):
        self.m = model
        self.name_index = self._name_index()

    def _name_index(self):
        idx = {}
        for reg, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            for r in self.m.rows(reg):
                if r and len(r) > 1 and isinstance(r[1], str):
                    idx.setdefault(r[1].strip().lower(), (reg, r[0]))
        return idx

    def _relation_from_column(self, col):                       # derived relation type
        c = re.sub(r'\(FK\)|\(s\)', '', str(col)).strip()
        return re.sub(r'[^A-Za-z0-9]+', '_', c).strip('_').lower() or "references"

    def _resolve_targets(self, val):
        """Resolve an FK cell to (target_id, target_class) pairs. Works for:
          * alpha-prefixed ID tokens (MOD-002) — original behaviour, unchanged;
          * NUMERIC / opaque pks (1001) — matched against the canonical pk index so a
            numeric FK actually produces an edge (previously invisible);
          * NAME-valued references — matched against the owner name index.
        Identity is class-scoped via owner_sheet, so numeric collisions resolve per class."""
        sval = str(val)
        ident = getattr(self.m, "identity", None)
        # 1) alpha-prefixed ID tokens
        toks = re.findall(r'[A-Za-z]+-\w+', sval)
        if toks:
            return [(t, self.m.owner_sheet(t)) for t in toks if self.m.owner_sheet(t)]
        # 2) whole-value pk match (numeric or opaque): the cell IS a pk held by some owner
        if ident is not None:
            key = sval.strip()
            regs = ident.classes_for_pk(key)
            if regs:
                return [(key, reg) for reg in regs]
        # 3) name-valued references (may be a delimited list)
        out = []
        for p in re.split(r'[;,/|]', sval):
            key = p.strip().lower()
            if key in self.name_index:
                reg, tid = self.name_index[key]
                out.append((tid, reg))
        return out

    def _is_fk_column(self, sheet, ci, header):
        if "(FK)" in str(header): return True
        vals = [r[ci] for r in self.m.rows(sheet) if ci < len(r) and r[ci] is not None][:20]
        if not vals: return False
        ident = getattr(self.m, "identity", None)
        def _hit(v):
            if isinstance(v, str) and ID.match(str(v)):
                return True
            if str(v).strip().lower() in self.name_index:
                return True
            # numeric/opaque pk that belongs to some OTHER owner registry -> FK-like
            if ident is not None:
                regs = ident.classes_for_pk(str(v).strip())
                if regs and sheet not in regs:
                    return True
            return False
        hit = sum(1 for v in vals if _hit(v))
        return hit >= max(1, len(vals) // 2)

    def derive_edges(self):
        edges = []
        for reg, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            hdr = self.m.hdr.get(reg)
            if not hdr: continue          # catalog lists this registry but no sheet backs it (F-18)
            evi = self.m.evidence_col(reg); eci = self.m.col(reg, evi) if evi else None
            for ci, h in enumerate(hdr):
                if ci == 0 or not h: continue
                if not self._is_fk_column(reg, ci, h): continue
                rel = self._relation_from_column(h)
                for r in self.m.rows(reg):
                    if not r or not r[0] or ci >= len(r) or r[ci] is None: continue
                    ev = r[eci] if eci is not None and eci < len(r) else None
                    for tid, tclass in self._resolve_targets(r[ci]):
                        if tclass and tid != r[0]:
                            edges.append((r[0], rel, tid, reg, tclass, ev))
        return edges


    # ---- F-021: resolve prose reference columns (values are descriptions, not IDs) ----
    def _reg_name_index(self, reg):
        idx = {}
        for r in self.m.rows(reg):
            if r and len(r) > 1 and isinstance(r[1], str):
                idx.setdefault(r[1].strip().lower(), r[0])
        return idx

    def _target_registry_for_column(self, header):
        # generic: pick the owner registry whose title shares a significant word with the column
        words = [w for w in re.split(r'[^a-z]+', str(header).lower()) if len(w) > 3]
        for reg, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            rt = reg.lower()
            if any(w in rt or w.rstrip('s') in rt for w in words):
                return reg
        return None

    def _match_prose(self, prose, idx):
        core = re.sub(r'\(.*?\)', '', str(prose)).strip().lower()
        if not core or core in ("not found", "none", "n/a", "-"): return None
        if core in idx: return idx[core]                         # exact (annotation-stripped)
        toks = [t for t in re.split(r'[^a-z0-9_.]+', core) if t]
        for name, eid in idx.items():                           # substring overlap (>=5 chars)
            n = name.strip()
            if len(n) >= 5 and (n in core or core in n):
                return eid
        for t in toks:                                          # function-token exact
            if len(t) >= 5 and t in idx: return idx[t]
        cset = set(w for w in toks if len(w) > 3)                # significant-token overlap (>=2 shared)
        if len(cset) >= 2:
            for name, eid in idx.items():
                nset = set(w for w in re.split(r'[^a-z0-9]+', name) if len(w) > 3)
                if len(cset & nset) >= 2: return eid
        return None

    def derive_prose_edges(self):
        edges = []; ID = re.compile(r'^[A-Z]+-\w')
        idx_cache = {}
        for reg, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            if reg not in self.m.hdr: continue                   # F-18: skip dangling catalog registry
            hdr = self.m.hdr[reg]; evi = self.m.evidence_col(reg); eci = self.m.col(reg, evi) if evi else None
            for ci, h in enumerate(hdr):
                if ci == 0 or not h: continue
                if eci is not None and ci == eci: continue       # F-021 fix B: never treat evidence as a reference
                if "evidence" in str(h).lower(): continue
                vals = [r[ci] for r in self.m.rows(reg) if ci < len(r) and r[ci] is not None][:20]
                if not vals: continue
                idlike = sum(1 for v in vals if isinstance(v, str) and ID.match(str(v)))
                if idlike >= max(1, len(vals) // 2): continue    # already handled as FK
                tgt_reg = self._target_registry_for_column(h)
                if not tgt_reg or tgt_reg == reg: continue
                if tgt_reg not in idx_cache: idx_cache[tgt_reg] = self._reg_name_index(tgt_reg)
                idx = idx_cache[tgt_reg]
                rel = self._relation_from_column(h)
                # Secondary targets are DERIVED from the catalog, not hardcoded. Previously
                # this special-cased the literals "handler"/"Component"; instead we collect
                # every owner registry the column/relation plausibly references (by name-word
                # overlap) OTHER than the primary target, and try each as a conservative
                # exact-match fallback. On the reference workbook this reproduces the old
                # handler→Component behaviour without naming either; on any other workbook it
                # generalises to whatever registries that workbook actually declares.
                secondary_idxs = self._secondary_target_indexes(h, primary=tgt_reg)
                for r in self.m.rows(reg):
                    if not r or not r[0] or ci >= len(r) or r[ci] is None: continue
                    ev = r[eci] if eci is not None and eci < len(r) else None
                    for part in re.split(r'[;,/]', str(r[ci])):
                        tid = self._match_prose(part, idx)               # primary: name-matched registry
                        if not tid:
                            for sidx in secondary_idxs:                  # derived secondary registries
                                tid = self._match_exact(part, sidx)
                                if tid: break
                        if tid and tid != r[0]:
                            tclass = self.m.owner_sheet(tid)
                            if tclass: edges.append((r[0], rel, tid, reg, tclass, ev))
        return edges

    def _secondary_target_indexes(self, header, primary=None):
        """Owner registries (other than `primary`) that a column's prose values actually
        resolve into — derived from the DATA, not from names and not hardcoded. For the
        column's values that don't match the primary target, we look up where they exact-match
        across all owner registries; any registry that absorbs a meaningful share of them is a
        derived secondary target. This reproduces workbook-specific facts (e.g. that handler
        names are implemented as Components) without ever naming "handler" or "Component", and
        generalises to whatever secondary registry any other workbook actually uses."""
        cache = getattr(self, "_sec_idx_cache", None)
        if cache is None:
            cache = {}; self._sec_idx_cache = cache
        key = (str(header), primary)
        if key in cache:
            return cache[key]
        # Build/reuse a global exact-name index: name -> registry, across all owner registries.
        gni = getattr(self, "_global_name_reg", None)
        if gni is None:
            gni = {}
            for regname, meta in self.m.catalog.items():
                if not meta["role"].startswith("Owner"):
                    continue
                for nm, _eid in self._reg_name_index(regname).items():
                    gni.setdefault(nm, regname)   # first owner wins; deterministic by catalog order
            self._global_name_reg = gni
        # Sample this column's values; see which OTHER registries their names land in.
        
        from collections import Counter
        landed = Counter()
        for regname, meta in self.m.catalog.items():
            if not meta["role"].startswith("Owner"):
                continue
            hi = self.m.col(regname, header)
            if hi is None:
                continue
            pidx = self._reg_name_index(primary) if primary else {}
            for r in self.m.rows(regname):
                if hi >= len(r) or r[hi] is None:
                    continue
                for part in re.split(r'[;,/]', str(r[hi])):
                    core = re.sub(r'\(.*?\)', '', part).strip().lower()
                    if not core or core in pidx:
                        continue
                    tgt = gni.get(core)
                    if tgt and tgt != primary:
                        landed[tgt] += 1
        # Any registry that absorbs at least a few of the unmatched values is a real secondary.
        # Restrict to the DOMINANT secondary target(s): the relation's unmatched values should
        # concentrate in one registry (as handler-names concentrate in Components), not scatter.
        # Requiring dominance keeps this as precise as the original hardcoded pair while staying
        # fully derived — a lone stray value landing in some unrelated registry is not promoted.
        if not landed:
            targets = []
        else:
            top = landed.most_common()
            best = top[0][1]
            # keep only targets that hold a dominant share (>= 50% of the best, and >= 3 hits),
            # so a single accidental name collision never creates a spurious secondary target.
            targets = [self._reg_name_index(reg) for reg, n in top if n >= max(3, best * 0.5)]
        cache[key] = targets
        return targets

    def _match_exact(self, prose, idx):
        core = re.sub(r'\(.*?\)', '', str(prose)).strip().lower()
        if not core or core in ("not found", "none", "n/a"): return None
        if core in idx: return idx[core]
        for t in [x for x in re.split(r'[^a-z0-9_.]+', core) if len(x) >= 5]:
            if t in idx: return idx[t]
        return None

    def canonicalization_report(self):
        cmd = self.m.owner_by_prefix.get("CMD")
        if not cmd: return {"applicable": False}
        # Diagnostic coverage report (NOT edge-derivation decision logic): for the Command
        # registry's reference columns, count which prose refs resolve vs are genuinely absent,
        # for the workbook author. The reference columns are the owner-registry-referencing
        # columns of the Command sheet, discovered from the catalog via _target_registry_for_column
        # (any column whose header maps to an owner registry other than Command). The
        # secondary-target fallback is DERIVED via _secondary_target_indexes — the previous
        # hardcoded "handler"->Component literal and _comp_index() are gone.
        cols = {}
        for h in self.m.hdr.get(cmd, []):
            if not h or "evidence" in str(h).lower():
                continue
            tgt = self._target_registry_for_column(h)
            if tgt and tgt != cmd and self.m.col(cmd, h) is not None:
                cols[str(h)] = tgt
        rep = {"resolved_registry": 0, "resolved_component": 0, "not_found": 0, "absent": 0, "absent_refs": []}
        for r in self.m.rows(cmd):
            rd = self.m.row_dict(cmd, r)
            for col, treg in cols.items():
                idx = self._reg_name_index(treg) if treg in self.m.sheets else {}
                secondary = self._secondary_target_indexes(col, primary=treg)
                for part in re.split(r'[;,/]', str(rd.get(col, ""))):
                    p = part.strip()
                    if not p: continue
                    if p.lower() in ("not found", "none", "n/a"): rep["not_found"] += 1; continue
                    if self._match_prose(p, idx): rep["resolved_registry"] += 1
                    elif any(self._match_exact(p, sidx) for sidx in secondary): rep["resolved_component"] += 1
                    else:
                        loc = self._exact_anywhere(p)
                        if loc and loc[0] == treg: rep["resolved_registry"] += 1     # matcher-format recovered
                        elif loc:
                            rep.setdefault("registered_other_type", 0); rep["registered_other_type"] += 1
                            rep.setdefault("other_type_refs", [])
                            if len(rep["other_type_refs"]) < 100: rep["other_type_refs"].append({"command": r[0], "column": col, "ref": p, "found_in": loc[0], "id": loc[1]})
                        else:
                            rep["absent"] += 1
                            if len(rep["absent_refs"]) < 200: rep["absent_refs"].append({"command": r[0], "column": col, "ref": p})
        return rep

    def _exact_anywhere(self, ref):
        import re as _re
        def nm(x): return _re.sub(r'[^a-z0-9]+', ' ', _re.sub(r'\(.*?\)', '', str(x).lower())).strip()
        if not hasattr(self, "_exidx"):
            self._exidx = {}
            for reg, meta in self.m.catalog.items():
                if not meta["role"].startswith("Owner"): continue
                for r in self.m.rows(reg):
                    if r and len(r) > 1 and isinstance(r[1], str): self._exidx.setdefault(nm(r[1]), (reg, r[0]))
        if nm(ref) in self._exidx: return self._exidx[nm(ref)]
        for part in _re.split(r'/', str(ref)):
            if nm(part) and nm(part) in self._exidx: return self._exidx[nm(part)]
        return None

    def name_index_flat(self):
        if not hasattr(self, "_nif"):
            self._nif = {k: v[1] for k, v in self.name_index.items()}
        return self._nif

    def cardinality(self, edges):
        by = defaultdict(lambda: {"s": Counter(), "t": Counter()})
        for s, rel, t, sc, tc, ev in edges:
            by[rel]["s"][s] += 1; by[rel]["t"][t] += 1
        return {rel: ("N" if max(d["s"].values()) > 1 else "1") + "→" + ("N" if max(d["t"].values()) > 1 else "1")
                for rel, d in by.items()}
