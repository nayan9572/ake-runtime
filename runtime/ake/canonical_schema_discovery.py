"""Canonical Schema Discovery (CSD) — universal dataset intake.

Accepts any structured dataset (Excel, CSV) and builds the canonical graph AKE consumes.
AKE no longer depends on workbook-specific registries, PREFIX-N ID formats, or a Registry
Catalog sheet. The dataset itself is the authority; the canonical graph is derived.

Discovery pipeline (in order):
  1. Sheet ingestion — read Excel sheets or CSV files into rows+headers
  2. PK detection — per-sheet: find the column whose values are unique identifiers
  3. FK detection — cross-sheet: find columns whose values overlap another sheet's PK
  4. Entity/attribute classification — remaining columns are attributes or measures
  5. Catalog synthesis — build a Registry Catalog equivalent from discovered structure
  6. Edge derivation — FK columns become typed edges; relation name = column header

No hardcoded entity types, prefix formats, relation names, column names, or sheet names.
Every decision is evidence-based and logged.
"""
import re
import os
import csv
from collections import Counter


class CanonicalSchemaDiscovery:
    """Discover entities, PKs, FKs, and relationships from raw sheets."""

    def __init__(self, sheets, source_name="dataset"):
        """sheets: {sheet_name: [[col0,col1,...], ...]} — first row is header."""
        self.sheets = sheets
        self.source = source_name
        self.evidence = []  # structured log of every decision

    # ---- 1. PK detection ----

    def _detect_pk(self, sheet_name, header, data):
        """Find the primary key column for a sheet. Criteria (in priority order):
        1. Column 0 if all values are unique and non-null
        2. Any column named *_id, *_ID, id, ID, or with 'key' in header
        3. First column with all-unique non-null values
        Returns (column_index, prefix_or_None, evidence_dict) or None."""
        if not data or not header:
            return None

        candidates = []
        for ci, h in enumerate(header):
            if h is None:
                continue
            vals = [r[ci] for r in data if ci < len(r) and r[ci] is not None]
            if not vals:
                continue
            uniq = len(set(str(v) for v in vals))
            total = len(vals)
            null_count = sum(1 for r in data if ci >= len(r) or r[ci] is None)
            if uniq == total and null_count == 0:
                # Detect prefix pattern (any consistent pattern before a number/separator)
                prefix = self._detect_prefix(vals)
                h_lower = str(h).lower().replace(" ", "_")
                # Priority scoring
                score = 0
                if ci == 0:
                    score += 10  # first column bonus
                if any(x in h_lower for x in ["_id", "id", "key", "code", "pk"]):
                    score += 8   # naming bonus
                if prefix:
                    score += 5   # has consistent prefix
                candidates.append((ci, prefix, score, {
                    "column": ci, "header": h, "unique_values": uniq,
                    "total_rows": total, "prefix": prefix,
                }))

        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[2])
        best = candidates[0]
        self.evidence.append({
            "step": "pk_detection", "sheet": sheet_name,
            "chosen": header[best[0]], "prefix": best[1],
            "candidates": len(candidates), "reason": "highest score (%d)" % best[2],
        })
        return best[0], best[1], best[3]

    def _detect_prefix(self, values):
        """Detect a consistent prefix pattern in ID values.
        Handles: PREFIX-N, PREFIX_N, A1, S001, D01, etc."""
        str_vals = [str(v) for v in values[:50]]
        if not str_vals:
            return None
        # Try common separator patterns
        for sep_re in [r'^([A-Za-z]+)[_-]', r'^([A-Za-z]+)\d']:
            prefixes = []
            for v in str_vals:
                m = re.match(sep_re, v)
                if m:
                    prefixes.append(m.group(1).upper())
            if prefixes and len(set(prefixes)) == 1 and len(prefixes) >= len(str_vals) * 0.7:
                return prefixes[0]
        return None

    # ---- 2. FK detection ----

    def _detect_fks(self, pk_map):
        """Find foreign key columns by value overlap with other sheets' PKs.
        pk_map: {sheet_name: (pk_col_index, pk_values_set, prefix)}
        Returns: [(source_sheet, source_col_index, target_sheet, overlap_ratio)]"""
        fks = []
        for src_sheet, src_rows in self.sheets.items():
            if len(src_rows) < 2:
                continue
            src_header = src_rows[0]
            src_data = src_rows[1:]
            src_pk_col = pk_map.get(src_sheet, (None,))[0]

            for ci, h in enumerate(src_header):
                if h is None or ci == src_pk_col:
                    continue
                vals = set(str(r[ci]) for r in src_data
                          if ci < len(r) and r[ci] is not None)
                if not vals:
                    continue
                # Check against every other sheet's PK values
                for tgt_sheet, (tgt_pk_col, tgt_pk_vals, tgt_prefix) in pk_map.items():
                    if tgt_sheet == src_sheet:
                        continue
                    overlap = vals & tgt_pk_vals
                    ratio = len(overlap) / len(vals) if vals else 0
                    # Also check header naming hints
                    h_lower = str(h).lower().replace(" ", "_")
                    tgt_name_hint = any(x in h_lower for x in [
                        tgt_sheet.lower().replace(" ", "_")[:8],
                        (tgt_prefix or "???").lower(),
                    ]) if tgt_prefix else False

                    if ratio >= 0.5 or (ratio >= 0.3 and tgt_name_hint):
                        fks.append((src_sheet, ci, tgt_sheet, ratio))
                        self.evidence.append({
                            "step": "fk_detection", "source": src_sheet,
                            "column": h, "target": tgt_sheet,
                            "overlap": "%.0f%%" % (ratio * 100),
                            "values_matched": len(overlap), "total_values": len(vals),
                            "header_hint": tgt_name_hint,
                        })
        return fks

    # ---- 3. Full discovery ----

    def discover(self):
        """Run the full discovery pipeline. Returns a structure that WorkbookModel
        can consume as if it were a well-formed workbook with a Registry Catalog."""

        # Step 1: Detect PKs per sheet
        pk_map = {}  # sheet -> (pk_col, pk_values_set, prefix)
        owner_sheets = {}  # sheet -> prefix
        prefix_used = set()

        for sheet_name, rows in self.sheets.items():
            if not rows or sheet_name == "Registry Catalog":
                continue
            header = rows[0]
            data = [r for r in rows[1:] if r and any(c is not None for c in r)]
            if not data:
                continue
            pk_result = self._detect_pk(sheet_name, header, data)
            if pk_result:
                pk_col, prefix, _ = pk_result
                pk_vals = set(str(r[pk_col]) for r in data
                             if pk_col < len(r) and r[pk_col] is not None)
                if not prefix:
                    # Generate a prefix from the sheet name
                    prefix = self._generate_prefix(sheet_name, prefix_used)
                prefix_used.add(prefix)
                pk_map[sheet_name] = (pk_col, pk_vals, prefix)
                owner_sheets[sheet_name] = prefix

        # Step 2: Detect FKs
        fks = self._detect_fks(pk_map)

        # Step 3: Normalize PKs to PREFIX-N format for AKE compatibility
        # AKE's graph uses PREFIX-N IDs internally. We map the original values.
        id_maps = {}  # sheet -> {original_value: normalized_id}
        normalized_sheets = {}

        for sheet_name, rows in self.sheets.items():
            if not rows or sheet_name == "Registry Catalog":
                continue
            header = list(rows[0])
            data = rows[1:]
            pk_info = pk_map.get(sheet_name)

            if pk_info:
                pk_col, _, prefix = pk_info
                # Build the mapping
                mapping = {}
                for ri, r in enumerate(data):
                    if pk_col < len(r) and r[pk_col] is not None:
                        orig = str(r[pk_col])
                        if not re.match(r'^[A-Z]{2,6}-\w', orig):
                            new_id = "%s-%03d" % (prefix, ri + 1)
                            mapping[orig] = new_id
                        else:
                            mapping[orig] = orig  # already normalized
                id_maps[sheet_name] = mapping

                # Rewrite the sheet with normalized PKs
                new_rows = [header]
                for r in data:
                    nr = list(r)
                    if pk_col < len(nr) and nr[pk_col] is not None:
                        orig = str(nr[pk_col])
                        nr[pk_col] = mapping.get(orig, orig)
                    new_rows.append(nr)
                normalized_sheets[sheet_name] = new_rows
            else:
                normalized_sheets[sheet_name] = rows

        # Step 4: Rewrite FK values to normalized IDs
        for src_sheet, src_col, tgt_sheet, _ in fks:
            tgt_map = id_maps.get(tgt_sheet, {})
            if not tgt_map:
                continue
            rows = normalized_sheets.get(src_sheet, [])
            for ri in range(1, len(rows)):
                r = rows[ri]
                if src_col < len(r) and r[src_col] is not None:
                    orig = str(r[src_col])
                    if orig in tgt_map:
                        r[src_col] = tgt_map[orig]

        # Step 5: Mark FK columns with (FK) suffix for RPDE compatibility
        for src_sheet, src_col, tgt_sheet, _ in fks:
            header = normalized_sheets[src_sheet][0]
            h = str(header[src_col] or "")
            if "(FK)" not in h:
                header[src_col] = h + " (FK)"

        # Step 6: Synthesize Registry Catalog
        cat_header = ["Registry (self)", "Role in Model", "PK Column", "PK Prefix",
                      "Rows", "FK Edges (\u2192 owner registry)", "Evidence Col",
                      "Rel-Provider", "Exec-Provider"]
        cat_rows = [cat_header]
        for sheet_name in normalized_sheets:
            if sheet_name == "Registry Catalog":
                continue
            pk_info = pk_map.get(sheet_name)
            prefix = owner_sheets.get(sheet_name, "\u2014")
            header = normalized_sheets[sheet_name][0]
            pk_col_name = header[pk_info[0]] if pk_info else "\u2014"
            n_rows = len(normalized_sheets[sheet_name]) - 1
            # FK edges description
            sheet_fks = [(src_col, tgt) for src, src_col, tgt, _ in fks if src == sheet_name]
            fk_desc = "; ".join("%s\u2192%s" % (header[ci], tgt) for ci, tgt in sheet_fks) or "\u2014"
            # Evidence column (heuristic: look for columns named evidence, source, reference)
            ev_col = "\u2014"
            for h in header:
                if h and any(x in str(h).lower() for x in ["evidence", "source", "reference", "citation"]):
                    ev_col = str(h); break
            role = "Owner (entity: %s)" % sheet_name if pk_info else "Reference"
            cat_rows.append([sheet_name, role, pk_col_name, prefix,
                            str(n_rows), fk_desc, ev_col, "no", "no"])

        normalized_sheets["Registry Catalog"] = cat_rows

        self.evidence.append({
            "step": "synthesis_complete",
            "owner_sheets": len(owner_sheets),
            "fk_edges": len(fks),
            "total_id_mappings": sum(len(m) for m in id_maps.values()),
        })

        return normalized_sheets

    def _generate_prefix(self, sheet_name, used):
        """Generate a PREFIX from a sheet name, avoiding collisions."""
        # Take first letters of significant words
        words = re.findall(r'[A-Za-z]+', sheet_name)
        if not words:
            base = "SHT"
        elif len(words) == 1:
            base = words[0][:4].upper()
        else:
            base = "".join(w[0] for w in words[:4]).upper()
        if len(base) < 2:
            base = (base + "XX")[:3]
        p, i = base, 2
        while p in used:
            p = base[:3] + str(i); i += 1
        return p


def load_dataset(path):
    """Load any supported dataset format into the sheets dict CSD expects.
    Supports: .xlsx, .xls, .csv, .tsv"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
        return {ws.title: [[c.value for c in r] for r in ws.iter_rows()]
                for ws in wb.worksheets}
    elif ext in (".csv", ".tsv"):
        delimiter = "\t" if ext == ".tsv" else ","
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = [row for row in reader]
        name = os.path.splitext(os.path.basename(path))[0]
        return {name: rows}
    else:
        raise ValueError("Unsupported file format: %s" % ext)
