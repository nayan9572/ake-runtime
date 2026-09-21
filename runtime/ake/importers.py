"""Structural importers. AKE never recognizes a business DOMAIN and contains no domain-specific logic. It
recognizes STRUCTURE only and picks a structural strategy (Registry / Tabular / ...). A flat table is
mapped into the SAME canonical entity+relation model the registry path produces, so the one universal
explorer runs on any workbook, whatever its subject matter.

Column roles are decided purely structurally:
  - measure/attribute : mostly numeric, or dates, or a single constant value
  - dimension (entity): categorical (repeated values, not near-unique)     -> becomes an entity type
  - near-unique text  : treated as an attribute (a label), not an entity
Each row becomes a Record entity linked to the dimension-value entity of every dimension column.
"""
import re
import datetime


def _isnum(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(v); return True
    except (TypeError, ValueError):
        return False


def _prefix(name, used):
    base = re.sub(r'[^A-Za-z]', '', str(name)).upper()[:4] or "COL"
    p, i = base, 2
    while p in used:
        p = base[:3] + str(i); i += 1
    used.add(p)
    return p


class TabularImporter:
    ID = re.compile(r"^[A-Z]{2,6}-[A-Za-z0-9]+$")

    @classmethod
    def looks_tabular(cls, sheets):
        has_registry = has_flat = False
        for t, rows in sheets.items():
            if t == "Registry Catalog":
                continue
            data = [r for r in rows[1:] if r and any(c is not None for c in r)]
            if not data:
                continue
            col0 = [r[0] for r in data if r and r[0] is not None]
            if col0 and sum(1 for v in col0 if isinstance(v, str) and cls.ID.match(str(v))) / len(col0) >= 0.7:
                has_registry = True
            if len(data) >= 20 and len([h for h in rows[0] if h is not None]) >= 3:
                has_flat = True
        return has_flat and not has_registry

    @classmethod
    def transform(cls, sheets, max_records=4000):
        # choose the largest flat sheet as the record source
        best, bestn = None, 0
        for t, rows in sheets.items():
            if t == "Registry Catalog":
                continue
            data = [r for r in rows[1:] if r and any(c is not None for c in r)]
            if len(data) > bestn:
                best, bestn = (t, rows[0], data), len(data)
        if not best:
            return sheets
        sheet_name, header, data = best
        if len(data) > max_records:
            data = data[:max_records]
        n = len(data)

        used, dims, measures = set(), [], []
        for ci, h in enumerate(header):
            if h is None:
                continue
            vals = [r[ci] for r in data if ci < len(r) and r[ci] is not None]
            if not vals:
                continue
            distinct = len(set(map(str, vals)))
            uniq = distinct / len(vals)
            numr = sum(1 for v in vals if _isnum(v)) / len(vals)
            isdate = sum(1 for v in vals if isinstance(v, datetime.date)) / len(vals) > 0.5
            if numr >= 0.7 or isdate or distinct == 1:
                measures.append((ci, str(h)))
            elif distinct >= 2 and uniq < 0.98:
                dims.append((ci, str(h), _prefix(h, used)))
            else:
                measures.append((ci, str(h)))

        syn = {}
        val2id = {}
        for ci, h, pref in dims:
            seen, drows = {}, [[pref + " ID", "Name", "Evidence"]]
            for ri, r in enumerate(data):
                v = r[ci] if ci < len(r) else None
                if v is None:
                    continue
                key = str(v)
                if key not in seen:
                    eid = "%s-%d" % (pref, len(seen) + 1)
                    seen[key] = eid
                    drows.append([eid, v, "%s:row%d" % (sheet_name, ri + 2)])
            syn[h + " Registry"] = drows
            val2id[ci] = seen

        rec_pref = "REC"
        rhdr = [rec_pref + " ID"] + [h + " (FK)" for _, h, _ in dims] + [h for _, h in measures] + ["Evidence"]
        rrows = [rhdr]
        for ri, r in enumerate(data):
            rid = "%s-%d" % (rec_pref, ri + 1)
            fk = [val2id[ci].get(str(r[ci])) if ci < len(r) and r[ci] is not None else None for ci, _, _ in dims]
            mv = [r[ci] if ci < len(r) else None for ci, _ in measures]
            rrows.append([rid] + fk + mv + ["%s:row%d" % (sheet_name, ri + 2)])
        syn[sheet_name + " Records"] = rrows

        cat = [["Registry (self)", "Role in Model", "PK Column", "PK Prefix", "Rows",
                "FK Edges (\u2192 owner registry)", "Evidence Col", "Rel-Provider", "Exec-Provider"]]
        for ci, h, pref in dims:
            cat.append([h + " Registry", "Owner (entity: %s)" % h, pref + " ID", pref,
                        str(len(val2id[ci])), "\u2014", "Evidence", "no", "no"])
        cat.append([sheet_name + " Records", "Owner (entity: Record)", rec_pref + " ID", rec_pref,
                    str(n), "; ".join(h + " (FK)" for _, h, _ in dims), "Evidence", "no", "no"])
        syn["Registry Catalog"] = cat
        return syn

    @classmethod
    def strategy(cls, sheets):
        """Name the STRUCTURAL strategy (never a domain)."""
        for t, rows in sheets.items():
            if t == "Registry Catalog" and len(rows) > 1:
                return "Registry"
        pk_sheets = 0
        for t, rows in sheets.items():
            data = [r for r in rows[1:] if r and any(c is not None for c in r)]
            col0 = [r[0] for r in data if r and r[0] is not None] if data else []
            if col0 and sum(1 for v in col0 if isinstance(v, str) and cls.ID.match(str(v))) / len(col0) >= 0.7:
                pk_sheets += 1
        if pk_sheets >= 1:
            return "Registry"
        if cls.looks_tabular(sheets):
            return "Tabular"
        return "Unknown"
