"""Semantic fidelity checks against a synthetic retail-style workbook (Order/Status,
Product/Brand, Store/Phone/Email) -- reproduces and guards against 4 bugs found via real
UI testing that the EBIS-only test suite couldn't have caught, since EBIS has none of
these shapes (no repeated non-sentinel enum column, no plain-text Brand column, no
Phone/Email scalar columns). Run: python tests/test_semantic_fidelity.py.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIXTURE = os.path.join(ROOT, "tests", "retail_repro_fixture.xlsx")

from ake import AKE
from ake.shell import AKEShell

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)


def run():
    ake = AKE(FIXTURE)
    sh = AKEShell(ake)

    # ---------------------------------------------------------------- Bug 1: "Pending" status
    cands = {c["column"]: c for c in ake.promotions.candidates()}
    check("Status candidates include 'Pending' (not swallowed as a null-sentinel)",
          "Pending" in cands["Status"]["values"] and cands["Status"]["values"]["Pending"] >= 2,
          "values=%r" % cands["Status"]["values"])

    sh.handle("ORD-0001")
    status_key = next(k for k, v in sh.menu.items() if v[2] == "Status")
    out = sh.handle(status_key)
    check("ORD-0001's Status action shows ONLY its own value, not the full enumeration",
          "Status: Pending" in out and "Completed" not in out and "Rejected" not in out,
          "out=%r" % out)

    # ---------------------------------------------------------------- Bug 3: per-attribute ASK actions
    sh.handle("home")
    sh.handle("PRD-0020")
    ask_labels = {v[0] for v in sh.menu.values() if v[1] == "ASK"}
    check("A Product row exposes its OWN scalar columns as individual Canonical Actions",
          {"Price", "Brand"} <= ask_labels, "got=%r" % ask_labels)
    check("The conventional Name column (Product Name, already GET_NAME) is not duplicated",
          "Product Name" not in ask_labels, "got=%r" % ask_labels)
    price_key = next(k for k, v in sh.menu.items() if v[2] == "Price")
    price_out = sh.handle(price_key)
    real_price = ake.entity_source_row("PRD-0020")["Price"]
    check("Asking a specific attribute returns exactly THIS row's value",
          str(real_price) in price_out, "out=%r price=%r" % (price_out, real_price))

    sh.handle("home")
    sh.handle("STR-001")
    ask_labels2 = {v[0] for v in sh.menu.values() if v[1] == "ASK"}
    check("A Store row exposes Phone/Email as individual Canonical Actions",
          {"Phone", "Email"} <= ask_labels2, "got=%r" % ask_labels2)
    check("The conventional Name column (already GET_NAME) is not duplicated as an ASK action",
          "Name" not in ask_labels2, "got=%r" % ask_labels2)

    # every ASK action must carry the full CanonicalAction contract shape too
    prd_actions = ake.entity_actions("PRD-0020")
    ask_acts = [a for a in prd_actions if a["query"] == "ASK"]
    check("ASK actions carry provenance=scalar_attribute / discovery_stage=SchemaDiscovery",
          all(a["provenance"] == "scalar_attribute" and a["discovery_stage"] == "SchemaDiscovery"
              for a in ask_acts))
    check("A column already exposed as a relation (Brand's sibling FK columns, Store) "
          "is NOT duplicated as an ASK action",
          "Store" not in {a["label"] for a in ask_acts})

    # ---------------------------------------------------------------- Bug 2: Brand promoted-entity label
    sh.handle("home")
    sh.handle("Nike")
    rel_label = next(v[0] for v in sh.menu.values() if v[1] == "REL")
    check("A promoted entity's membership action is labeled with its TARGET registry "
          "(not its own column/class, which was the 'Brand (118) -> Products' confusion)",
          rel_label == "Product Registry", "got=%r" % rel_label)
    rel_key = next(k for k, v in sh.menu.items() if v[1] == "REL")
    results_text = sh.handle(rel_key)
    check("Drilling into it shows the real member count (118 Nike products)",
          "(118)" in results_text, "out=%r" % results_text[:120])

    # ---------------------------------------------------------------- Bug 4: search over ALL columns
    hits_email = ake.search("store1@example.com")
    check("search() finds a value in a non-name scalar column (email)",
          any(h[0] == "STR-001" for h in hits_email), "hits=%r" % hits_email)
    hits_phone = ake.search("555-0102")
    check("search() finds a value in another non-name scalar column (phone)",
          any(h[0] == "STR-002" for h in hits_phone), "hits=%r" % hits_phone)

    # ---------------------------------------------------------------- relation-name collision
    # Staff Registry.Store and Product Registry.Store are unrelated FK columns that happen
    # to share header text -- both derive relation name "store". Before the fix, STR-001's
    # incoming "store" edges (5 staff + 50 products) were merged into ONE action showing a
    # combined count/list mixing both entity types.
    sh.handle("home"); sh.handle("STR-001")
    rel_actions = {v[0]: v[2] for v in sh.menu.values() if v[1] == "REL"}
    check("A relation name spanning >1 source class is split, not merged",
          "Store ← Staff Registry" in rel_actions and "Store ← Product Registry" in rel_actions,
          "got=%r" % rel_actions)

    k_staff = next(k for k, v in sh.menu.items() if v[0] == "Store ← Staff Registry")
    out_staff = sh.handle(k_staff)
    check("The Staff bucket's count and actual items match (5), with no Products mixed in",
          "(5)" in out_staff.splitlines()[2] and "PRD" not in out_staff, "out=%r" % out_staff[:200])

    sh.handle("home"); sh.handle("STR-001")
    k_prod = next(k for k, v in sh.menu.items() if v[0] == "Store ← Product Registry")
    out_prod = sh.handle(k_prod)
    check("The Product bucket's count and actual items match (50), with no Staff mixed in",
          "(50)" in out_prod.splitlines()[2] and "STF" not in out_prod, "out=%r" % out_prod[:200])

    # every relation action's advertised count must equal its own explain_relation() count --
    # the actual mechanism behind the bug, checked directly rather than just eyeballing text
    acts = ake.entity_actions("STR-001")
    for a in acts:
        if a["canonical_source"] == "relation_direct":
            expl = ake.explain_relation("STR-001", a["relation"])
            check("Canonical Action count for %r matches explain_relation()'s actual count" % a["label"],
                  a["count"] == expl["count"], "advertised=%s actual=%s" % (a["count"], expl["count"]))

    # ---------------------------------------------------------------- back-navigation state hygiene
    # Corrected navigation contract (nav-frame stack): a results view is now a REAL step in
    # history, so `back` from a relation drilled from an entity returns to THAT entity's menu
    # (not straight home — that was the skip-the-list bug). A second `back` then reaches home.
    # At every step, state stays coherent: no stale results/menu leaks such that a leftover
    # digit could open the wrong entity. That anti-stale-state intent is what this guards.
    sh.handle("home"); sh.handle("STR-001")
    sh.handle(next(k for k, v in sh.menu.items() if v[0] == "Store ← Staff Registry"))
    check("Immediately after opening a relation, mode is 'results'", sh.mode == "results")
    sh.handle("back")
    check("Back from results returns to the parent entity menu (not home)",
          sh.mode == "menu" and sh.context == "STR-001", "mode=%s ctx=%s" % (sh.mode, sh.context))
    check("Back from results clears the stale results dict", sh.results == {})
    sh.handle("back")
    check("Second back reaches home", sh.mode == "menu" and sh.context is None)
    check("At home the results dict is clear", sh.results == {})
    check("At home the menu dict is clear", sh.menu == {})
    stale_digit_out = sh.handle("4")
    check("A leftover digit typed at home is rejected, not misinterpreted as an old result",
          "No option" in stale_digit_out or "unresolved" in stale_digit_out.lower()
          or "No object matches" in stale_digit_out, "out=%r" % stale_digit_out)

    return {}


if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
