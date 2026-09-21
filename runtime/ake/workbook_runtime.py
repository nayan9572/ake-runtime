"""Phase 1 — Workbook Runtime. Canonical Workbook Model, metadata-driven via Registry Catalog."""
import re
import zipfile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

class WorkbookModel:
    def __init__(self, path):
        self.path = path
        # CSV/TSV: use CSD's loader (openpyxl can't open these)
        ext = str(path).lower().rsplit(".", 1)[-1] if "." in str(path) else ""
        if ext in ("csv", "tsv"):
            from .canonical_schema_discovery import load_dataset, CanonicalSchemaDiscovery
            raw_sheets = load_dataset(str(path))
            csd = CanonicalSchemaDiscovery(raw_sheets, source_name=str(path))
            self.sheets = csd.discover()
            self.import_strategy = "Discovered"
            self._csd_evidence = csd.evidence
        else:
            try:
                wb = load_workbook(path, data_only=True)
            except FileNotFoundError:
                raise FileNotFoundError(f"Workbook not found: '{path}'") from None
            except InvalidFileException:
                hint = " — this looks like a .zip, not a workbook; pass the .xlsx inside it, " \
                       "or hand the .zip to colab_run.py / AKE_MASTER.py, which auto-extract it." \
                       if str(path).lower().endswith(".zip") else ""
                raise InvalidFileException(f"'{path}' is not a readable .xlsx workbook{hint}") from None
            except zipfile.BadZipFile:
                raise InvalidFileException(f"'{path}' is not a valid .xlsx file (corrupt or not an Excel file)") from None
            self.sheets = {ws.title: [[c.value for c in r] for r in ws.iter_rows()] for ws in wb.worksheets}
            from .importers import TabularImporter
            self.import_strategy = TabularImporter.strategy(self.sheets)
            if self.import_strategy == "Tabular":
                self.sheets = TabularImporter.transform(self.sheets)
            elif self.import_strategy == "Unknown":
                from .canonical_schema_discovery import CanonicalSchemaDiscovery
                csd = CanonicalSchemaDiscovery(self.sheets, source_name=str(path))
                discovered = csd.discover()
                if any(m.get("step") == "synthesis_complete" and m.get("owner_sheets", 0) > 0
                       for m in csd.evidence):
                    self.sheets = discovered
                    self.import_strategy = "Discovered"
                    self._csd_evidence = csd.evidence
        self.hdr = {t: (rows[0] if rows else []) for t, rows in self.sheets.items()}
        self._load_catalog()
        self._build_canonical_identity()
        self._index_pk()
        self._build_relationship_graph()
        self._build_universal_graph()

    # ---- Registry Catalog = self-description (no hardcoded names) ----
    def _load_catalog(self):
        self.catalog = {}          # registry -> meta
        self.owner_by_prefix = {}  # PK prefix -> owner registry
        cat = self.sheets.get("Registry Catalog", [])
        if len(cat) < 2:                     # F-04 fallback: no catalog sheet -> infer from structure
            self._infer_catalog(); return
        h = self.hdr.get("Registry Catalog", [])
        ci = {name: h.index(name) for name in h if name}
        try:
            for row in cat[1:]:
                reg = row[ci["Registry (self)"]]
                role = str(row[ci["Role in Model"]])
                prefix = row[ci["PK Prefix"]]
                fks = str(row[ci.get("FK Edges (→ owner registry)", -1)] or "")
                ev = row[ci.get("Evidence Col", -1)]
                self.catalog[reg] = {"role": role, "prefix": prefix, "fks": fks, "evidence": ev,
                                     "rel": row[ci.get("Rel-Provider", -1)] == "yes",
                                     "exec": row[ci.get("Exec-Provider", -1)] == "yes"}
                if role.startswith("Owner") and prefix and prefix != "—":
                    self.owner_by_prefix[prefix] = reg
        except KeyError as e:                 # malformed catalog sheet (required column missing):
            self.catalog = {}                 # same fallback as "no catalog sheet at all" (F-04)
            self.owner_by_prefix = {}
            import sys
            print(f"[AKE] warning: 'Registry Catalog' sheet is missing required column {e} — "
                  f"inferring registries from structure instead", file=sys.stderr)
            self._infer_catalog()

    def _infer_catalog(self):
        """Infer a minimal Registry Catalog from structure (owner sheets by ID-pattern PK)."""
        import re as _re
        ID = _re.compile(r'^[A-Z]+-\w')
        owners = {}
        for t, rows in self.sheets.items():
            body = rows[1:] if len(rows) > 1 else []
            col0 = [r[0] for r in body if r and r[0] is not None]
            if col0 and all(isinstance(v, str) and ID.match(str(v)) for v in col0[:20]) and len(set(col0)) == len(col0):
                pref = _re.match(r'([A-Z]+)-', col0[0]).group(1)
                owners[t] = pref; self.owner_by_prefix[pref] = t
        for t, rows in self.sheets.items():
            hdr = self.hdr.get(t, []); body = rows[1:] if len(rows) > 1 else []
            fks = []
            for ci, hh in enumerate(hdr):
                if ci == 0 or not hh: continue
                vals = [r[ci] for r in body if ci < len(r) and r[ci] is not None][:20]
                if not vals: continue
                is_fk = "(FK)" in str(hh) or any(isinstance(v, str) and ID.match(str(v)) and
                        _re.match(r'([A-Z]+)-', str(v)).group(1) in self.owner_by_prefix for v in vals)
                if is_fk:
                    tgt = "?"
                    for v in vals:
                        mm = _re.match(r'([A-Z]+)-', str(v)) if isinstance(v, str) else None
                        if mm and mm.group(1) in self.owner_by_prefix: tgt = self.owner_by_prefix[mm.group(1)]; break
                    fks.append(f"{str(hh).replace(' (FK)','')}→{tgt}")
            evi = next((hh for hh in hdr if hh and "Evidence" in str(hh)), "—")
            self.catalog[t] = {"role": (f"Owner (entity: {t})" if t in owners else "Reference"),
                               "prefix": owners.get(t, "—"), "fks": "; ".join(fks) or "—",
                               "evidence": evi, "rel": False, "exec": False}

    def col(self, sheet, name):
        h = self.hdr.get(sheet, [])
        return h.index(name) if name in h else None

    def rows(self, sheet):
        return self.sheets.get(sheet, [])[1:]

    def _build_canonical_identity(self):
        """Build the class-scoped identity index (composite (class,pk) -> canonical hash),
        making owner-sheet resolution prefix-INDEPENDENT so numeric/composite pks work and
        cross-class pk collisions are separated. Interface ids stay the raw pk."""
        from .canonical_identity import CanonicalIdentity
        self.identity = CanonicalIdentity(self)

    def owner_sheet(self, entity_id):
        # Prefix-independent lookup via the canonical identity registry (API only).
        ident = getattr(self, "identity", None)
        if ident is not None:
            reg = ident.owner(entity_id)
            if reg is not None:
                return reg
        # Fallback used only during identity build itself (before self.identity exists).
        m = re.match(r'([A-Z]+)-', str(entity_id))
        return self.owner_by_prefix.get(m.group(1)) if m else None

    def node_key(self, entity_id):
        """Canonical graph node key for an entity. All graph lookups must route through this
        (display id -> canonical -> node key), never index the graph with a raw string."""
        ident = getattr(self, "identity", None)
        return ident.node_key(entity_id) if ident is not None else str(entity_id)

    def owner_row(self, entity_id):
        t = self.owner_sheet(entity_id)
        if not t: return None, None
        for r in self.rows(t):
            if r and r[0] == entity_id: return t, r
        return t, None

    def row_dict(self, sheet, row):
        return {self.hdr[sheet][i]: row[i] for i in range(len(self.hdr[sheet])) if self.hdr[sheet][i]}

    # ---- PK index across all sheets ----
    def _index_pk(self):
        self.cell_index = {}  # id -> list of (sheet, rownum, column)
        # Index every owner pk value (prefixed, numeric, composite, opaque) plus any cell
        # that textually matches a known pk. Previously only `[A-Z]+-\w` cells were indexed,
        # so numeric pks were invisible to cell-level lookups.
        owner_pks = set()
        for reg, meta in getattr(self, "catalog", {}).items():
            if not meta.get("role", "").startswith("Owner"):
                continue
            for r in self.rows(reg):
                if r and r[0] not in (None, ""):
                    owner_pks.add(str(r[0]))
        for t, rows in self.sheets.items():
            for ri, row in enumerate(rows[1:], 2):
                for ci, v in enumerate(row):
                    if v in (None, ""):
                        continue
                    sv = str(v)
                    if sv in owner_pks or re.match(r'[A-Za-z]+-\w', sv):
                        self.cell_index.setdefault(sv, []).append((t, ri, self.hdr[t][ci]))

    # ---- Relationship graph (Rel-Provider registry) ----
    def _build_relationship_graph(self):
        self.rel_sheet = next((r for r, m in self.catalog.items() if m["rel"]), None)
        self.edges = []  # (src, relation, tgt, flow, evidence)
        if not self.rel_sheet: return
        s = self.rel_sheet
        si, ri, ti = self.col(s, "Source (FK)"), self.col(s, "Relation"), self.col(s, "Target (FK)")
        fi, ei = self.col(s, "Flow Type"), self.col(s, "Evidence (file:line)")
        for row in self.rows(s):
            if row and row[si]:
                self.edges.append((row[si], row[ri], row[ti],
                                   row[fi] if fi is not None else None,
                                   row[ei] if ei is not None else None))

    def _build_universal_graph(self):
        from .relational_primitive_engine import RelationalPrimitiveEngine
        from .edge_graph_engine import UniversalEdgeGraph
        rpde = RelationalPrimitiveEngine(self); self._rpde = rpde
        fk_edges = rpde.derive_edges()
        prose_edges = rpde.derive_prose_edges()  # F-021
        # merge: dedicated relationship edges (typed, with flow) + RPDE FK-derived edges (all classes)
        rel_edges = [(s, rel, t, self.owner_sheet(s), self.owner_sheet(t), ev) for s, rel, t, fl, ev in self.edges]
        self.universal_edges = rel_edges + fk_edges + prose_edges
        # IDENTITY NORMALIZATION: every edge endpoint becomes its canonical NODE KEY. For a
        # unique pk that is the raw pk string (so prefixed/numeric workbooks are stable); for
        # a COLLIDING pk it is the class-scoped canonical key, so the two entities are
        # distinct nodes and edges attach to the right one. Routing uses each endpoint's own
        # class (sc/tc), which the edge already carries.
        ident = getattr(self, "identity", None)
        def _nk(pk, cls):
            if ident is not None and cls:
                return ident.node_key_for(cls, str(pk))
            return str(pk)
        self.universal_edges = [
            (_nk(s, sc), rel, _nk(t, tc), sc, tc, ev)
            for (s, rel, t, sc, tc, ev) in self.universal_edges
        ]
        self.rpde_cardinality = rpde.cardinality(fk_edges) if fk_edges else {}
        # Tag relations by derivation source — used for structural/reference classification.
        # This is graph-based: the SOURCE of each edge (explicit relationship sheet,
        # FK column with entity IDs, or prose column with resolved names) determines
        # whether it's a declared structural link or an inferred reference.
        self._rel_source = {}  # relation_name → "declared" | "inferred"
        for _, rel, _, _, _, _ in rel_edges:
            self._rel_source.setdefault(rel, "declared")   # from relationship sheet
        for _, rel, _, _, _, _ in fk_edges:
            self._rel_source.setdefault(rel, "declared")   # from FK column (entity IDs)
        for _, rel, _, _, _, _ in prose_edges:
            self._rel_source.setdefault(rel, "inferred")   # from text (name resolution)
        node_attrs = self._build_node_attributes()
        self.universal_graph = UniversalEdgeGraph(self.universal_edges, node_attrs,
                                                  identity=getattr(self, "identity", None))

    def _build_node_attributes(self):
        import re as _re
        attrs = {}
        prof = next((s for s in self.exec_sheets() if "Profile" in s), None)
        lc = next((s for s in self.sheets if "Lifecycle Status" in s), None)
        for reg, meta in self.catalog.items():
            if not meta["role"].startswith("Owner"): continue
            evi = self.evidence_col(reg); eci = self.col(reg, evi) if evi else None
            for r in self.rows(reg):
                if not r or not r[0]: continue
                # has_PK is now TRUE for any non-empty pk (numeric, composite, opaque, or
                # prefixed) — a pk existing is what matters, not whether it is alpha-prefixed.
                pk = str(r[0])
                a = {"class": reg, "has_PK": bool(pk),
                     "name": str(r[1]) if len(r) > 1 and r[1] is not None else None}
                # Carry the class-scoped canonical identity on every node. Nodes stay keyed
                # by display id (keeps the 200+ existing call-sites and v17 output stable),
                # but each node now KNOWS its collision-free identity.
                a["canonical"] = self.identity.canonical_id(pk) if getattr(self, "identity", None) else None
                a["has_Evidence"] = bool(eci is not None and eci < len(r) and _re.search(r'\.py:\d+|:\d+', str(r[eci])))
                a["evidence"] = r[eci] if eci is not None and eci < len(r) else None
                a["metadata"] = self.row_dict(reg, r)
                a["in_execution"] = bool(prof and any(rr and rr[0] == r[0] for rr in self.rows(prof)))
                a["has_lifecycle"] = bool(lc and any(rr and rr[0] == r[0] for rr in self.rows(lc)))
                if getattr(self, "identity", None):
                    a["canonical"] = self.identity.canonical_for(reg, str(r[0]))
                    nk = self.identity.node_key_for(reg, str(r[0]))
                else:
                    nk = str(r[0])
                attrs[nk] = a
        return attrs

    def exec_sheets(self):
        return [r for r, m in self.catalog.items() if m["exec"]]

    def evidence_col(self, sheet):
        c = self.catalog.get(sheet, {}).get("evidence")
        return c if c and c != "—" else None
