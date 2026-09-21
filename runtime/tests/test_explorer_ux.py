"""Tests for the explorer UX pass: permanent HOME-anchored breadcrumb and the two-tier
Engine Help / Knowledge Help split (ake/shell.py). Everything here must be pure presentation:
derived from existing state (self.crumb, self._relations(), model.rpde_cardinality, edge
evidence) with zero new per-relation dictionaries. Run: python tests/test_explorer_ux.py
"""
import sys, os, random, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
EBIS = os.path.join(ROOT, "EBIS_Architecture_Registry_Workbook_v17.xlsx")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail)); return bool(cond)


def _parse_knowledge_help(text):
    """Independent parser -- deliberately does NOT reuse any of shell.py's own code, just reads
    the rendered text back out, the way a hostile regression test (or a human) would."""
    blocks, cur = {}, None
    for line in text.splitlines():
        m = re.match(r'^  (\w+)$', line)
        if m:
            cur = m.group(1); blocks[cur] = {}
            continue
        m2 = re.match(r'^    (Target type|Cardinality|Current value|Evidence)\s*: (.*)$', line)
        if m2 and cur:
            blocks[cur][m2.group(1)] = m2.group(2)
    return blocks


def _independent_expected(ake, eid, rel):
    """Recomputed straight from the raw data structures via a separate path -- NOT by calling
    shell.py's _knowledge_help() -- so this genuinely tests the invariant instead of checking a
    function against itself."""
    g = ake.model.universal_graph
    edges = [e for e in g.neighbors(eid) if e["relation"] == rel]
    target_classes = sorted(set(g.node_attrs.get(e["node"], {}).get("class") for e in edges
                                 if g.node_attrs.get(e["node"], {}).get("class")))
    card = ake.model.rpde_cardinality.get(rel)
    has_ev = any(e.get("evidence") for e in edges)
    cur_val = (g.node_attrs.get(edges[0]["node"], {}).get("name") or edges[0]["node"]) \
        if len(edges) == 1 else "%d connected" % len(edges)
    return {"Target type": ", ".join(target_classes) if target_classes else "not documented",
            "Cardinality": card if card else "not documented", "Current value": cur_val,
            "Evidence": "available" if has_ev else "not available"}


def run():
    from ake import AKE
    from ake.shell import AKEShell

    # --- no new relation-name-KEYED MAPPING was introduced (a dict-literal pattern like
    # "handler": "..." would indicate one; a one-off illustrative mention in help text, e.g.
    # "'handler' works whenever Handler is on the menu", legitimately is not the same thing) ---
    src = open(os.path.join(ROOT, "ake", "shell.py")).read()
    code_only = src.split('"""', 2)[-1]   # drop the module docstring too (also just prose)
    suspicious = re.search(r'["\'](?:handler|segment|country|product)["\']\s*:\s*["\']',
                            code_only, re.IGNORECASE)
    check("shell.py's code adds no dict-literal mapping a specific relation name to description text",
          not suspicious, "would indicate a hardcoded per-relation-name lookup table")

    ake = AKE(EBIS)
    sh = AKEShell(ake)

    # --- breadcrumb: HOME-anchored, "->" arrow matching rpde_cardinality's own existing
    # convention, derived from self.crumb, shown on every response type ---
    check("breadcrumb starts with HOME before any object is opened",
          sh._crumbline() == "HOME")
    menu = sh.handle("CMD-002")
    check("breadcrumb (HOME → CMD-002) appears on the menu page", "HOME → CMD-002" in menu)
    help_out = sh.handle("help")
    check("breadcrumb also appears on the help page (not just the menu)", "HOME → CMD-002" in help_out)
    tree_out = sh.handle("tree")
    check("breadcrumb also appears on the tree page", "HOME → CMD-002" in tree_out)
    check("breadcrumb text is exactly self.crumb formatted -- no separate tracked state",
          sh._crumbline() == "HOME" + "".join(" → " + c for c in sh.crumb))

    # drill one level deeper, confirm breadcrumb grows using the SAME self.crumb list
    rel_num = next(k for k, v in sh.menu.items() if v[1] == "REL")
    sh.handle(rel_num)
    first_result = next(iter(sh.results.values()))
    deeper = sh.handle("1")
    check("breadcrumb grows to HOME → CMD-002 → <deeper> after drilling in",
          f"HOME → CMD-002 → {first_result}" in deeper)

    back_out = sh.handle("back")
    check("breadcrumb shrinks back after 'back', still from the same self.crumb list",
          "HOME → CMD-002" in back_out and first_result not in sh.crumb)

    exit_result = sh.handle("exit")
    check("exit still returns None (breadcrumb wrapper doesn't break the exit signal)",
          exit_result is None)

    # --- relation names are executable, resolving to the SAME menu action a number would ---
    sh4 = AKEShell(ake)
    sh4.handle("CMD-002")
    rel_key, (rel_friendly, rel_q, rel_name) = next((k, v) for k, v in sh4.menu.items() if v[1] == "REL")
    by_number = AKEShell(ake); by_number.handle("CMD-002")
    out_by_number = by_number.handle(rel_key)
    by_name = AKEShell(ake); by_name.handle("CMD-002")
    out_by_name = by_name.handle(rel_name)          # typed the raw relation name
    out_by_label = AKEShell(ake); out_by_label.handle("CMD-002")
    out_by_friendly = out_by_label.handle(rel_friendly.lower())   # typed the friendly label, lowercased
    check("typing a relation's raw name resolves to the identical action as its number",
          out_by_number == out_by_name)
    check("typing a relation's friendly label (any case) also resolves identically",
          out_by_number == out_by_friendly)

    # --- two-tier help: full Engine Help only with no object open; abbreviated once one is,
    # with 'help engine' as the explicit escape hatch back to the full block ---
    sh2 = AKEShell(ake)
    help_at_home = sh2.handle("help")
    check("help before opening anything shows the full Engine Help block",
          "Engine Help" in help_at_home and "back | home" in help_at_home)
    sh2.handle("CMD-002")
    help2 = sh2.handle("help")
    check("help after opening an object does NOT re-print the full Engine Help block",
          "back | home" not in help2)
    check("help after opening an object shows a reminder instead, plus Knowledge Help",
          "help engine" in help2 and "Knowledge Help" in help2)
    check("'help engine' still gives the full block back on demand",
          "back | home" in sh2.handle("help engine"))
    check("Knowledge Help lists an actual relation this object has (handler)", "handler" in help2)

    # --- honest 'not documented' fallback: EBIS's 'handler' relation has no FK-derived cardinality ---
    check("cardinality genuinely absent for 'handler' in the underlying data (precondition for this test)",
          "handler" not in ake.model.rpde_cardinality)
    check("Knowledge Help shows 'not documented' for handler's cardinality, doesn't invent one",
          "not documented" in help2)

    # --- help with NO object open doesn't invent knowledge about a nonexistent object ---
    sh3 = AKEShell(ake)
    help3 = sh3.handle("help")
    check("Knowledge Help with no object open says so plainly, invents nothing",
          "Knowledge Help" in help3 and "there isn't one open" in help3)

    # --- a workbook WITH real cardinality data shows it, not 'not documented' ---
    random.seed(1)
    lib_path = os.path.join(ROOT, "_tmp_ux_validation.xlsx")
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Sample"
    ws.append(["Segment", "Country", "Product", "Sales"])
    for i in range(30):
        ws.append([random.choice(["Enterprise", "SMB"]), random.choice(["USA", "Canada", "Mexico"]),
                   random.choice(["Widget", "Gadget"]), random.randint(100, 9999)])
    wb.save(lib_path)
    fin_ake = AKE(lib_path)
    fin_sh = AKEShell(fin_ake)
    rec_id = next(eid for eid, a in fin_ake.model.universal_graph.node_attrs.items()
                  if "Records" in (a.get("class") or ""))
    fin_sh.handle(rec_id)
    fin_help = fin_sh.handle("help engine") + "\n" + fin_sh.handle("help")
    os.remove(lib_path)
    check("cross-domain: the SAME shell.py, unmodified, derives Segment/Country/Product help "
          "from a completely different workbook",
          all(x in fin_help for x in ("segment", "country", "product")))
    check("cross-domain: real cardinality is shown (not 'not documented') when the data has it",
          "1→N" in fin_help or "N→1" in fin_help or "N→N" in fin_help or "1→1" in fin_help)
    seg_key = next((k for k, v in fin_sh.menu.items() if v[2] == "segment"), None)
    out_a = AKEShell(fin_ake); out_a.handle(rec_id); out_by_num = out_a.handle(seg_key) if seg_key else None
    out_b = AKEShell(fin_ake); out_b.handle(rec_id); out_by_txt = out_b.handle("segment") if seg_key else None
    check("cross-domain: typing a relation name also works on this unrelated workbook",
          seg_key is not None and out_by_num == out_by_txt, (seg_key, out_by_num, out_by_txt))

    # --- invariant: Displayed Knowledge Help fields subset-of Existing Registry/Graph ---
    # for every field shown on a help page, independently reconstruct what it SHOULD say from
    # raw model data (a separate code path, not _knowledge_help() calling itself) and diff.
    # any relation shown that isn't genuinely on the object, or any field that doesn't match
    # independent recomputation, is exactly the "invented knowledge" these rules forbid.
    violations = []
    sample_ids = random.sample(list(ake.model.universal_graph.node_attrs.keys()), 60)
    checked_blocks = 0
    for eid in sample_ids:
        probe = AKEShell(ake)
        probe.handle(eid)
        if not probe.context:
            continue
        blocks = _parse_knowledge_help(probe.handle("help"))
        for rel, displayed in blocks.items():
            if rel not in probe._relations(eid):
                violations.append((eid, rel, "relation shown but not actually on this object"))
                continue
            expected = _independent_expected(ake, eid, rel)
            checked_blocks += 1
            for field, exp_val in expected.items():
                if displayed.get(field) != exp_val:
                    violations.append((eid, rel, field, displayed.get(field), exp_val))
    check("invariant: every Knowledge Help field, across 60 random real objects, reconstructs "
          "exactly from raw registry/graph data (Displayed subset-of Existing)",
          not violations and checked_blocks > 0, f"{len(violations)} violations / {checked_blocks} checked")

    return {}


if __name__ == "__main__":
    run()
    passed = sum(1 for _, ok, _ in RESULTS if ok); total = len(RESULTS)
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
