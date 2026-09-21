"""RP-00..RP-03 — Feature Discovery Engine (corrected M0, query-independent).
Workbook → Structural Feature Discovery → Observation Discovery → Primitive Derivation → Closure Test.
Workbook-agnostic: scans any workbook via structure + Registry Catalog."""
import re
from collections import Counter

ID = re.compile(r'^[A-Z]+-\w')
FILELINE = re.compile(r'[\w./]+\.py:\d+|:\d+$')
STATUS_VOCAB = {"✅", "❌", "◐", "✓", "✗", "yes", "no", "Y", "N"}

class FeatureDiscovery:
    def __init__(self, model): self.m = model

    # ---- RP-00: Structural Feature Discovery (auto-detect feature-types present) ----
    def discover_features(self):
        feats = {}   # feature-type -> {detected_in, example}
        def add(ft, where, ex):
            feats.setdefault(ft, {"detected_in": set(), "example": ex})["detected_in"].add(where)

        # cross-sheet id presence (for FK/duplicate detection)
        idsheets = {}
        for eid, hits in self.m.cell_index.items():
            idsheets[eid] = {h[0] for h in hits}

        for sheet, rows in self.m.sheets.items():
            if len(rows) < 2: continue
            hdr = self.m.hdr[sheet]; body = rows[1:]
            ncol = len(hdr)
            fk_cols = []; status_cols = []
            for ci in range(ncol):
                col_vals = [r[ci] for r in body if ci < len(r) and r[ci] is not None]
                if not col_vals: continue
                h = str(hdr[ci]) if ci < len(hdr) else ""
                sample = col_vals[0]
                # PK: col 0 unique ID
                if ci == 0 and all(isinstance(v, str) and ID.match(v) for v in col_vals[:20]):
                    if len(set(col_vals)) == len(col_vals): add("Entity-Identity (PK)", sheet, f"{sheet}.{h}")
                # Evidence / provenance
                if any(isinstance(v, str) and FILELINE.search(str(v)) for v in col_vals[:20]):
                    add("Provenance (file:line)", sheet, f"{sheet}.{h}")
                # FK column
                is_fk = "(FK)" in h or (ci > 0 and sum(1 for v in col_vals[:20] if isinstance(v, str) and ID.match(v)) >= max(1, len(col_vals[:20])//2))
                if is_fk and ci > 0:
                    fk_cols.append(ci); add("Cross-Sheet Reference (FK)", sheet, f"{sheet}.{h}")
                    # hierarchy = FK to a different owner
                    for v in col_vals[:5]:
                        if isinstance(v, str) and ID.match(v):
                            ow = self.m.owner_sheet(v)
                            if ow and ow != sheet: add("Hierarchy (parent/child)", sheet, f"{sheet}.{h}→{ow}"); break
                # ordered sequence: sortable ordinal column
                if all(isinstance(v, (int, str)) and str(v).strip().isdigit() for v in col_vals[:20]) and ci == 0:
                    nums = [int(str(v)) for v in col_vals[:20]]
                    if nums == sorted(nums) and len(set(nums)) == len(nums): add("Ordered Sequence (ordinal)", sheet, f"{sheet}.{h}")
                # status-grid cell
                if sum(1 for v in col_vals[:20] if str(v) in STATUS_VOCAB) >= max(1, len(col_vals[:20])//2):
                    status_cols.append(ci)
                # descriptive metadata (free text, not ID/evidence)
                if isinstance(sample, str) and not ID.match(str(sample)) and not FILELINE.search(str(sample)) and len(str(sample)) > 12:
                    add("Descriptive Metadata", sheet, f"{sheet}.{h}")
            # directed edge sheet = >=2 FK cols
            if len(fk_cols) >= 2: add("Directed Edge (relationship)", sheet, sheet)
            # edge attribute = non-FK cols on an edge sheet
            if len(fk_cols) >= 2 and ncol > len(fk_cols) + 1: add("Edge Attribute", sheet, sheet)
            # cell grid = >=3 adjacent status cols
            if len(status_cols) >= 3: add("Cell-Grid Status Matrix", sheet, sheet)

        # occurrence / location are always available where ids exist
        add("Occurrence Frequency", "ALL", "cell_index")
        add("Row/Column Location", "ALL", "cell_index")
        for f in feats: feats[f]["detected_in"] = sorted(feats[f]["detected_in"])[:3]
        return feats

    # ---- RP-01/RP-02: Observation Discovery → Primitive mapping ----
    OBS_MAP = {
        "Entity-Identity (PK)": ("RESOLVE_KEYS", "primitive"),
        "Cross-Sheet Reference (FK)": ("RESOLVE_KEYS + FIND_SHEETS", "primitive"),
        "Provenance (file:line)": ("FIND_FILES", "primitive"),
        "Descriptive Metadata": ("READ_METADATA", "primitive"),
        "Directed Edge (relationship)": ("GRAPH_NEIGHBORS", "primitive"),
        "Edge Attribute": ("READ_METADATA(edge row)", "primitive (D-010)"),
        "Ordered Sequence (ordinal)": ("READ_METADATA + SORT", "composition"),
        "Cell-Grid Status Matrix": ("READ_METADATA(full row)", "primitive (D-009)"),
        "Hierarchy (parent/child)": ("FIND_HIERARCHY", "primitive"),
        "Occurrence Frequency": ("COUNT_OCCURRENCES", "primitive"),
        "Row/Column Location": ("FIND_ROWS + FIND_COLUMNS", "primitive"),
    }

    # ---- RP-03: Closure Test ----
    def closure(self):
        feats = self.discover_features()
        covered, gaps = [], []
        for ft in feats:
            if ft in self.OBS_MAP:
                prim, kind = self.OBS_MAP[ft]; covered.append((ft, prim, kind))
            else:
                gaps.append(ft)
        base10 = {"COUNT_OCCURRENCES","FIND_SHEETS","FIND_COLUMNS","FIND_ROWS","FIND_FILES",
                  "RESOLVE_KEYS","GRAPH_NEIGHBORS","FIND_HIERARCHY","FIND_DUPLICATES","READ_METADATA"}
        used = set()
        for _, prim, _ in covered:
            used |= {t for t in re.split(r'[ +()]', prim) if t.isupper() and t in base10}
        return {"features": feats, "covered": covered, "gaps": gaps,
                "closed": len(gaps) == 0, "primitives_used": sorted(used),
                "primitive_count": len(base10)}
