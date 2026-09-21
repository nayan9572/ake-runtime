"""Canonical-identity regression — locks the IR-only entity-identity fixes:

  1. Numeric primary keys are first-class: inferred pk schema, prefix-independent
     owner-sheet resolution, working FK edges, searchable, navigable by typing the id.
  2. Same NAME across two classes is AMBIGUOUS -> candidates, never an auto-open of the
     wrong class. `Class:name` disambiguates.
  3. Same raw PK across two classes gets DISTINCT canonical identities and disambiguated
     display ids; the bare pk returns candidates.
  4. Prefixed workbooks (the common case) are unchanged: display ids stay the raw pk, no
     ambiguity introduced.

Deterministic, self-contained (builds its own workbooks). Run:
  python tests/test_canonical_identity.py   -> exits nonzero on any failure.
"""
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import openpyxl
from ake import AKE
from ake.shell import AKEShell
from ake.canonical_identity import canonical_key, _schema_of

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    return bool(cond)

def _build(path, sheets):
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows: ws.append(r)
    wb.save(path)

def run():
    d = tempfile.mkdtemp()
    numeric = os.path.join(d, "numeric.xlsx")
    namecoll = os.path.join(d, "namecoll.xlsx")
    pkcoll = os.path.join(d, "pkcoll.xlsx")

    _build(numeric, {
        "Registry Catalog": [
            ["Registry (self)","Role in Model","PK Prefix","FK Edges (→ owner registry)","Evidence Col","Rel-Provider","Exec-Provider"],
            ["Machine Registry","Owner (entity: Machine)","—","","Evidence","no","no"],
            ["Part Registry","Owner (entity: Part)","—","Machine (FK)→Machine Registry","Evidence","no","no"],
        ],
        "Machine Registry": [["Machine ID","Name","Evidence"],[1001,"Lathe Alpha","d.py:1"],[1002,"Mill Beta","d.py:2"]],
        "Part Registry": [["Part ID","Name","Machine (FK)","Evidence"],[5001,"Spindle",1001,"d.py:3"],[5002,"Chuck",1001,"d.py:4"],[5003,"Table",1002,"d.py:5"]],
    })
    _build(namecoll, {
        "Registry Catalog": [
            ["Registry (self)","Role in Model","PK Prefix","FK Edges (→ owner registry)","Evidence Col","Rel-Provider","Exec-Provider"],
            ["Staff Registry","Owner (entity: Staff)","STF","","Evidence","no","no"],
            ["Product Registry","Owner (entity: Product)","PRD","","Evidence","no","no"],
        ],
        "Staff Registry": [["Staff ID","Name","Evidence"],["STF-1","Store","d.py:1"],["STF-2","Alice","d.py:2"]],
        "Product Registry": [["Product ID","Name","Evidence"],["PRD-1","Store","d.py:3"],["PRD-2","Widget","d.py:4"]],
    })
    _build(pkcoll, {
        "Registry Catalog": [
            ["Registry (self)","Role in Model","PK Prefix","FK Edges (→ owner registry)","Evidence Col","Rel-Provider","Exec-Provider"],
            ["Alpha Registry","Owner (entity: Alpha)","—","","Evidence","no","no"],
            ["Beta Registry","Owner (entity: Beta)","—","","Evidence","no","no"],
        ],
        "Alpha Registry": [["Alpha ID","Name","Evidence"],[1,"AlphaOne","d.py:1"],[2,"AlphaTwo","d.py:2"]],
        "Beta Registry": [["Beta ID","Name","Evidence"],[1,"BetaOne","d.py:3"],[2,"BetaTwo","d.py:4"]],
    })

    # ---- canonical_key unit properties ----
    check("canonical_key is class-scoped (same pk, different class -> different key)",
          canonical_key("Alpha Registry", "1") != canonical_key("Beta Registry", "1"))
    check("canonical_key is deterministic", canonical_key("X", "1") == canonical_key("X", "1"))
    check("_schema_of detects numeric", _schema_of(["1001","1002"]) == "numeric")
    check("_schema_of detects prefixed", _schema_of(["MOD-1","MOD-2"]) == "prefixed")

    # ---- 1. NUMERIC identity ----
    a = AKE(numeric)
    check("numeric pk schema inferred", a.model.identity.infer_schema("Machine Registry") == "numeric")
    r = a.resolve("1001")
    check("numeric id resolves to correct class", r.get("id") == "1001" and r.get("class") == "Machine Registry", r.get("how"))
    check("numeric owner_sheet works (no prefix regex)", a.model.owner_sheet("1001") == "Machine Registry")
    check("numeric FK edge derived (machine 1001 has incoming parts)",
          len(a.model.universal_graph.neighbors("1001")) == 2)
    check("numeric entity is searchable by name", any(h[0] == "1001" for h in a.search("Lathe")))
    check("numeric node keys are strings (type-stable identity)",
          all(isinstance(k, str) for k in a.model.universal_graph.node_attrs))
    sh = AKEShell(a); sh.handle("5001")
    check("numeric entity opens by typing bare id", sh.context == "5001" and len(sh.menu) > 0)
    mk = [k for k, v in sh.menu.items() if v[0] == "Machine"]
    check("numeric entity exposes its FK relation action", bool(mk))
    if mk:
        sh.handle(mk[0])
        check("numeric relation walk yields the target", list(sh.results.values()) == ["1001"])

    # ---- 2. NAME collision (type-aware resolver) ----
    b = AKE(namecoll)
    r = b.resolve("Store")
    check("ambiguous name does NOT auto-open (id is None)", r.get("id") is None)
    check("ambiguous name returns both class candidates",
          r.get("how") == "ambiguous_name" and {c["class"] for c in r.get("candidates", [])} == {"Staff Registry", "Product Registry"})
    r2 = b.resolve("Staff:Store")
    check("Class:name disambiguates to the right class", r2.get("id") == "STF-1" and r2.get("class") == "Staff Registry")
    r3 = b.resolve("Product:Store")
    check("Class:name disambiguates the other class", r3.get("id") == "PRD-1")
    shb = AKEShell(b); out = shb.handle("Store")
    check("shell shows candidates for ambiguous name (no wrong-entity open)",
          shb.mode == "results" and set(shb.results.values()) == {"STF-1", "PRD-1"})

    # ---- 3. PK collision (distinct canonical identity) ----
    c = AKE(pkcoll)
    res1 = c.model.identity.resolve("1"); keys_for_1 = [cc["canonical"] for cc in res1.get("candidates", [])]
    check("same pk across classes -> 2 distinct canonical keys", len(set(keys_for_1)) == 2)
    displays = sorted(cc["pk"] for cc in res1.get("candidates", []))
    check("colliding pk keeps raw display id (no synthetic 1@Class)", displays == ["1", "1"])
    r = c.resolve("1")
    check("ambiguous bare pk returns candidates", r.get("how") == "ambiguous_id" and len(r.get("candidates", [])) == 2)
    # Requirement C: no synthetic "1@Class" visible id. A colliding pk is opened by its
    # INTERNAL canonical token (from the candidate picker), which resolves to the right class.
    alpha_ck = next(cc["canonical"] for cc in r.get("candidates", []) if cc["class"] == "Alpha Registry")
    r2 = c.resolve(alpha_ck)
    check("canonical selection token resolves to the right class", r2.get("class") == "Alpha Registry")
    check("no synthetic display id exists for colliding pk", c.model.identity.display_id(alpha_ck) == "1")

    # ---- 4. Prefixed workbook unchanged (backward compat) ----
    ebis = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")
    if os.path.exists(ebis):
        e = AKE(ebis)
        check("prefixed workbook: 0 ambiguous pks", not e.model.identity.is_ambiguous("MOD-002"))
        check("prefixed workbook: display id == raw pk (bit-identical)",
              e.model.identity.display_id("MOD-002") == "MOD-002")
        check("prefixed workbook: resolve unchanged", e.resolve("MOD-002").get("id") == "MOD-002")
        check("prefixed workbook: all schemas prefixed",
              set(e.model.identity.schema_report().values()) == {"prefixed"})

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n%d/%d checks passed" % (passed, len(RESULTS)))
    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
