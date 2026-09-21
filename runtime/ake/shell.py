"""AKE — one Universal Knowledge Explorer for every workbook.

The classifier only selects a STRUCTURAL importer (Registry/Tabular/...). After mapping into the canonical
graph, the SAME stateful explorer runs regardless of domain. The only difference is graph richness:
EBIS exposes owner/handler/gate; a tabular workbook exposes customer/product/region — same explorer, same
navigation. Each object is a page; its menu is DERIVED from the relations that object actually has.
"""
import re
from collections import defaultdict
from .validation import WorkbookValidation

_ID = re.compile(r'^(?:[A-Za-z]{2,10}-[A-Za-z0-9]+|\d+|.+?@.+)$')  # prefixed | numeric | class-scoped
_IDENT = [("What is", "WHAT_IS"), ("Name", "GET_NAME")]
_TAIL = [("Neighbors", "GET_NEIGHBORS"), ("Evidence", "GET_EVIDENCE"), ("Source row", "GET_SOURCE_ROW")]


class AKEShell:
    def __init__(self, ake, dev=False):
        self.ake = ake
        self.dev = dev
        self.strategy = getattr(ake.model, "import_strategy", "Registry")
        self.context = None
        self.crumb = []
        self.hist = []
        self.menu = {}
        self.results = {}
        self.result_total = 0      # true size of the current result set BEFORE the render
                                   # cap; badge/result_count read this so advertised ==
                                   # returned even when the printed list is truncated.
        self.mode = "menu"
        self.last_analysis = None  # canonical analysis object from the most recent
                                   # analyze()/compare(); cleared on any other navigation
                                   # so build_nav_state can pass it through unflattened.
        # Nav-frame stack. A "frame" is one restorable VIEW (menu / results / analysis).
        # `back` pops a frame and replays it verbatim, so a results or analysis page is a
        # real step in history — not skipped. Opening an entity still pushes to `crumb`
        # (the entity trail shown in the rail); `stack` is the finer view-level history the
        # crumb never captured, which is why `back` used to jump straight home from a
        # results list. The two are kept in sync: every frame records the crumb depth it
        # was created at, so replaying a frame also restores the correct crumb.
        self.stack = []
        self._suppress_next_frame = False  # one-shot: set by _action_page so a compare/
                                           # analyze reached via self.handle() doesn't push
                                           # a second frame on top of the menu frame.
        # Discovery-console context (the "AKE>" mode selector). None = no context (a bare
        # query resolves globally, as before). A registry name scopes queries to that
        # registry and shows discovery chains; "relation" is the entity relation view. This
        # is a view/selector on the EXISTING catalog, not a second entity space.
        self.console_context = None

    # ---------- banner ----------
    def banner(self):
        ru = self.ake.registry_universe()
        ex = ru["entity_types"][0]["examples"][0] if ru["entity_types"] else "<ID>"
        head = "Structural strategy : %s  (the same explorer works on any workbook)" % self.strategy
        return (self.ake.discovery_report() + "\n\n" + WorkbookValidation(self.ake.model).dashboard()
                + "\n\n" + head + "\n\nEnter an object (e.g. %s) to open it, or: help | search(<text>) | exit" % ex)

    # ---------- helpers ----------
    def _crumbline(self):
        return "HOME" + "".join(" → " + self._disp(c) for c in self.crumb)

    def _disp(self, token):
        """Translate an internal context/crumb token (which may be a canonical CID- key for a
        colliding entity) to its user-facing display id (the raw pk). Internal identity never
        leaks into what the user sees."""
        ident = getattr(self.ake.model, "identity", None)
        return ident.display_id(token) if ident is not None else token

    def _attrs(self, eid):
        return self.ake.entity_attrs(eid)

    def _rowdict(self, eid):
        return self.ake.entity_source_row(eid)

    def _neighbors(self, eid):
        return self.ake.model.universal_graph.neighbors(eid)

    def _relations(self, eid):
        rels, seen = [], set()
        for e in self._neighbors(eid):
            if e["relation"] not in seen:
                seen.add(e["relation"]); rels.append(e["relation"])
        return rels

    def _menu_lookup(self, text):
        """Case/spacing-insensitive match of typed text against the CURRENT menu's own relation
        names and friendly labels -- the same dict _menu_page() already built this page, nothing
        new. Lets 'handler', 'Handler', and '6' invoke the identical action when Handler happens
        to be menu item 6 right now. No per-relation-name table anywhere."""
        norm = text.strip().lower().replace("_", " ")
        for key, (friendly, q, rel) in self.menu.items():
            if norm == friendly.lower() or (rel and norm == rel.lower().replace("_", " ")):
                return key
        return None

    # ---------- pages ----------
    def _snapshot(self):
        """Capture the currently rendered view as a restorable frame. Called just BEFORE a
        navigation replaces the view, so `back` can return to exactly what was on screen."""
        return {
            "context": self.context,
            "mode": self.mode,
            "results": dict(self.results),
            "result_total": self.result_total,
            "last_analysis": self.last_analysis,
            "menu": dict(self.menu),
            "crumb_depth": len(self.crumb),
        }

    def _push_frame(self):
        self.stack.append(self._snapshot())

    def _maybe_push(self):
        """Push a restorable frame UNLESS _action_page already pushed one for this action
        (compare/analyze reached via self.handle). Consumes the one-shot suppress flag."""
        if getattr(self, "_suppress_next_frame", False):
            self._suppress_next_frame = False
            return
        if self.mode in ("results", "analysis"):
            self._push_frame()

    def _restore(self, fr):
        """Replay a frame verbatim: state is restored, then the matching page text is
        re-rendered through the SAME code path that first produced it — never a second,
        divergent renderer."""
        self.context = fr["context"]
        self.results = dict(fr["results"])
        self.result_total = fr["result_total"]
        self.last_analysis = fr["last_analysis"]
        self.menu = dict(fr["menu"])
        self.mode = fr["mode"]
        # Trim the crumb back to the depth this frame was created at (an entity opened
        # AFTER this frame must not linger in the rail once we step back past it).
        del self.crumb[fr["crumb_depth"]:]
        if fr["mode"] == "analysis" and fr["last_analysis"]:
            return self._render_analysis(fr["last_analysis"])
        if fr["mode"] == "results":
            return self._render_results_frame(fr)
        if fr["context"] is None:
            self.mode = "menu"; self.menu = {}
            return "Enter an object to open it, or search(<text>)."
        return self._menu_page()

    _RESULT_CAP = 80  # printed-row cap; result_total still reports the true size

    def _render_analysis(self, result):
        """Single renderer for BOTH analyze() and compare() output, used on first run and
        on back-replay. Sets mode='analysis' (NOT 'results') so the payload's own mode is
        truthful — the dashboard's analysis view no longer relies on a mislabelled
        'results' mode. Navigable items still populate self.results (keyed r-selectable),
        and self.result_total carries the TRUE count so the advertised badge matches."""
        op = result.get("operation", "analyze")
        self.results = {}; self.mode = "analysis"
        if op == "compare":
            scope = result.get("scope", "")
            group_targets = [t for t in result["targets"] if t != result["anchor"]]
            self.result_total = len(group_targets)
            L = ["Compare: %s vs %s" % (result["anchor"], scope), ""]
            if len(group_targets) > 1:
                L.append("Comparing against %d entities:" % len(group_targets))
                L.append("")
                for i, eid in enumerate(group_targets[:self._RESULT_CAP], 1):
                    self.results[str(i)] = eid
                    attrs = self.ake.model.universal_graph.node_attrs.get(eid, {})
                    nm = attrs.get("name", "")
                    L.append("  %2d. %s%s" % (i, eid, "  (%s)" % nm if nm else ""))
                if len(group_targets) > self._RESULT_CAP:
                    L.append("  ... and %d more" % (len(group_targets) - self._RESULT_CAP))
                L.append("")
                L.append("Dimensions shared across all:")
                any_shared = False
                for d in result["dimensions"]:
                    shared = d.get("shared_by_all", [])
                    if shared:
                        any_shared = True
                        names = ", ".join(x.get("name") or x["id"] for x in shared[:3])
                        L.append("  %s: %d shared → %s" % (d["relation"], len(shared), names))
                if not any_shared:
                    L.append("  (no dimension is shared by every entity in this scope)")
                L.append("")
                L.append("Open any result by number or ID.  Type 'analyze' for %s.  back to return." % result["anchor"])
            else:
                L.append("(%d dimensions)" % len(result["dimensions"]))
                L.append("")
                idx = 1
                for d in result["dimensions"]:
                    L.append("  [%s] %s %s" % (d["status"], d["relation"],
                             "→ " + d.get("target_class", "") if d.get("target_class") else ""))
                    for item in d.get("common", [])[:3]:
                        self.results[str(idx)] = item["id"]
                        L.append("      %d. common: %s (%s)" % (idx, item["id"], item.get("name", "")))
                        idx += 1
                    for item in d.get("only_left", [])[:3]:
                        self.results[str(idx)] = item["id"]
                        L.append("      %d. only %s: %s (%s)" % (
                            idx, result["anchor"], item["id"], item.get("name", "")))
                        idx += 1
                    for item in d.get("only_right", [])[:3]:
                        self.results[str(idx)] = item["id"]
                        L.append("      %d. only right: %s (%s)" % (
                            idx, item["id"], item.get("name", "")))
                        idx += 1
                    L.append("")
                self.result_total = len(self.results)
                L.append("Open any result by number or ID.  Type 'analyze' for %s.  back to return." % result["anchor"])
            return "\n".join(L)
        # analyze
        L = ["Analysis: %s" % result["entity"], ""]
        ident = result.get("identity", {})
        L.append("  Identity")
        L.append("    name : %s" % (ident.get("name") or "—"))
        L.append("    class: %s" % (ident.get("class") or "—"))
        L.append("")
        idx = 1
        for obs in result.get("observations", []):
            L.append("  %s" % obs["title"])
            for item in obs.get("items", [])[:5]:
                if item.get("id"):
                    self.results[str(idx)] = item["id"]
                    L.append("    %d. %s%s" % (idx, item["id"],
                             "  (%s)" % item["name"] if item.get("name") else ""))
                    idx += 1
                else:
                    L.append("    - %s" % item.get("text", ""))
            if obs.get("note"):
                L.append("    (%s)" % obs["note"])
            L.append("")
        self.result_total = len(self.results)
        L.append("Open any result by number or ID.  back to return.")
        return "\n".join(L)

    def _render_results_frame(self, fr):
        """Reprint a restored results view. The canonical result map is already in
        self.results (restored by _restore); this only re-renders the text so the console
        pane matches. The structured payload the dashboard actually draws from is the
        results map + result_total, both already restored, so the reprint is cosmetic."""
        rows = list(fr["results"].items())
        L = ["Results  (%d)" % fr["result_total"], ""]
        for k, node in rows:
            nm = self._attrs(node).get("name")
            L.append("  %s. %s%s" % (k, node, "  (%s)" % nm if nm else ""))
        L += ["", "Open a result by number or ID.  back to return."]
        return "\n".join(L)

    def open_object(self, eid):
        # Normalize the incoming token. For a UNIQUE entity, context is the stable display
        # id (raw pk). For a COLLIDING pk, we must keep the canonical CID- token as context
        # so the class is preserved (two entities share the raw pk) — the display layer still
        # shows the raw pk, but internal identity stays unambiguous.
        ident = getattr(self.ake.model, "identity", None)
        if ident is not None:
            res = ident.resolve(eid)
            if res.get("status") == "unique":
                # unique: context is the node key (raw pk for unique, canonical if the pk
                # collides — resolve() on a canonical token returns unique and node_key maps
                # it correctly). Keep the token that indexes the graph.
                eid = ident.node_key(res["canonical"]) if res.get("canonical") else res["display"]
        # Opening an entity from a results/analysis view is a forward step: snapshot the
        # view we are leaving so `back` returns to it, not to the entity two levels up.
        if self.mode in ("results", "analysis"):
            self._push_frame()
        self.context = eid
        if not self.crumb or self.crumb[-1] != eid:
            self.crumb.append(eid)
        if eid not in self.hist:
            self.hist.append(eid)
        self.mode = "menu"; self.results = {}; self.result_total = 0
        self.last_analysis = None
        return self._menu_page()

    def _menu_page(self):
        eid = self.context
        a = self._attrs(eid)
        self.menu = {}; self.mode = "menu"; n = 1
        # Header shows the DISPLAY id (raw pk); the internal context may be a canonical token
        # for a colliding entity, but that never appears to the user.
        L = ["", "%s  [%s]" % (self._disp(eid), a.get("class") or "?"), "  name: %s" % (a.get("name") or "-"),
             "", "You can explore"]
        # Menu is built from AKE.entity_actions — the canonical source of what actions exist
        # with their counts, availability, and mode. Same data the dashboard reads. The shell
        # only decides HOW to render each item, never WHICH items exist or WHAT counts are.
        for act in self.ake.entity_actions(eid):
            key = act["key"]
            q = act["query"]
            rel = act.get("relation")
            self.menu[key] = (act["label"], q, rel)
            count_str = ""
            if act["mode"] == "discovered":
                count_str = "  \u21dd"
            elif act["type"] == "relation" and act["count"] >= 0:
                count_str = "  (%d)" % act["count"]
            elif act["query"] == "GET_NEIGHBORS" and act["count"] > 0:
                count_str = "  (%d)" % act["count"]
            L.append("  %2d. %s%s" % (n, act["label"], count_str))
            n += 1
        L += ["", "Enter a number, an ID, or: back | home | tree | history | help | exit"]
        return "\n".join(L)

    def _run_attr(self, q, eid, rel=None):
        a = self._attrs(eid); rd = self._rowdict(eid)
        if q == "WHAT_IS":
            return "%s is a %s." % (eid, a.get("class"))
        if q == "GET_NAME":
            return a.get("name") or "(no name)"
        if q == "GET_SOURCE_ROW":
            return "%s :: %s" % (a.get("class"), "; ".join("%s=%s" % (k, rd[k]) for k in list(rd)[:8]))
        if q == "GET_EVIDENCE":
            return a.get("evidence") or "(no evidence)"
        if q == "ASK":
            return "%s: %s" % (rel, rd.get(rel, "(no value)"))
        return None

    def _action_page(self, friendly, q, rel):
        eid = self.context
        if q in ("WHAT_IS", "GET_NAME", "GET_EVIDENCE", "GET_SOURCE_ROW", "ASK"):
            self.mode = "menu"
            return "%s\n  %s" % (friendly, self._run_attr(q, eid, rel))
        # Every branch below leaves the menu for a results/analysis view. Snapshot the menu
        # so `back` returns to it. compare()/analyze() are reached via self.handle() below
        # and must NOT snapshot again — this flag suppresses their own push exactly once.
        self._push_frame()
        self._suppress_next_frame = True
        if q in ("COMPARE_SIBLINGS", "COMPARE_LAYER"):
            scope = "siblings" if q == "COMPARE_SIBLINGS" else "layer"
            return self.handle("compare(%s, %s)" % (eid, scope))
        if q == "ANALYZE_ENTITY":
            return self.handle("analyze(%s)" % eid)
        # Relation walk — ALL relation actions (REL and GET_NEIGHBORS) consume the same
        # canonical explained result from AKE. The shell never builds its own edge list
        # or invents its own explanations.
        if q == "GET_NEIGHBORS":
            edges = self._neighbors(eid)
            if not edges:
                self.mode = "menu"
                return "%s\n  (none — this entity has no relationships)" % friendly
            self.results = {}; self.mode = "results"
            self.result_total = len(edges)
            L = ["%s of %s  (%d)" % (friendly, eid, len(edges)), ""]
            for i, e in enumerate(edges, 1):
                nm = self._attrs(e["node"]).get("name")
                self.results[str(i)] = e["node"]
                L.append("  %2d. %s -%s-> %s%s" % (i, eid, e["relation"], e["node"],
                         "  (%s)" % nm if nm else ""))
            L += ["", "Open a result by number or ID.  back to return."]
            return "\n".join(L)
        # Specific relation: use AKE.explain_relation for full explainability
        expl = self.ake.explain_relation(eid, rel)
        if expl["count"] == 0:
            self.mode = "menu"
            reason = expl.get("reason", "")
            return "%s\n  (none)%s" % (friendly, "\n  %s" % reason if reason else "")
        self.results = {}; self.mode = "results"
        self.result_total = expl["count"]
        mode_tag = ""
        if expl["mode"] == "discovered" and expl.get("discovery"):
            d = expl["discovery"]
            mode_tag = "  [discovered via %s, %d hops]" % (d["path"], d["hops"])
        L = ["%s of %s  (%d)%s" % (friendly, eid, expl["count"], mode_tag), ""]
        for i, item in enumerate(expl["items"], 1):
            self.results[str(i)] = item["node"]
            nm = item.get("name") or ""
            ev = ""
            if item.get("evidence"):
                ev_str = str(item["evidence"])
                if ev_str.startswith("path:"):
                    ev_str = ev_str[:47] + "..." if len(ev_str) > 50 else ev_str
                elif len(ev_str) > 50:
                    ev_str = ev_str[:47] + "..."
                ev = "  [%s]" % ev_str
            L.append("  %2d. %s -%s-> %s%s%s" % (i, eid, item["relation"], item["node"],
                     "  (%s)" % nm if nm else "", ev))
        if expl.get("discovery"):
            d = expl["discovery"]
            L += ["", "  Discovery: %s → %s" % (d["path"], d["target_class"]),
                  "  Confidence: %s" % d["class_confidence"]]
        L += ["", "Open a result by number or ID.  back to return."]
        return "\n".join(L)

    def _tree(self):
        eid = self.context
        groups = defaultdict(list)
        for e in self._neighbors(eid):
            groups[e["relation"]].append(e["node"])
        L = [eid]
        items = list(groups.items())
        for i, (rel, tgts) in enumerate(items):
            branch = "└──" if i == len(items) - 1 else "├──"
            L.append("%s %s" % (branch, rel))
            for t in tgts[:5]:
                nm = self._attrs(t).get("name")
                L.append("      %s%s" % (t, "  (%s)" % nm if nm else ""))
        return "\n".join(L) if items else "%s has no relationships." % eid

    # ---------- interpreter ----------
    def handle(self, line):
        result = self._dispatch(line)
        if not result:            # None (exit) or "" (blank input) -- pass through unchanged
            return result
        return self._crumbline() + "\n\n" + result

    def _dispatch(self, line):
        line = (line or "").strip()
        self.last_analysis = None  # any navigation invalidates the previous analysis view
        if not line:
            return ""
        low = line.lower()
        if low in ("exit", "quit", ":quit"):
            return None
        if low in ("help", "help()"):
            return self._help()
        if low == "help engine":
            return self._engine_help_block()
        if low == "home":
            self.context, self.crumb, self.mode = None, [], "menu"
            self.menu = {}; self.results = {}; self.result_total = 0
            self.last_analysis = None; self.stack = []
            self.console_context = None
            return "Enter an object to open it, or search(<text>)."
        # Discovery-console context selector: "context handler" / "context relation" /
        # "context" (clear). Reads the existing catalog via ake.resolve_context.
        if low == "context" or low.startswith("context "):
            arg = line[7:].strip() if len(line) > 7 else ""
            if not arg:
                self.console_context = None
                return "Context cleared. Queries now resolve across the whole workbook."
            ctx = self.ake.resolve_context(arg)
            if ctx is None:
                avail = ", ".join(c["token"] for c in self.ake.contexts())
                return "No such context '%s'. Available: %s" % (arg, avail)
            self.console_context = ctx
            if ctx == self.ake.RELATION_CONTEXT:
                return "Context: relation. Enter an entity ID/name to see its relations."
            info = next((c for c in self.ake.contexts() if c["registry"] == ctx), None)
            n = info["count"] if info else "?"
            return ("Context: %s (%s entities). Enter an ID/name to open its discovery "
                    "chain, or a term to filter within this context." % (ctx, n))
        if low == "back":
            # A results/analysis view is a real frame on the stack — pop and replay it so
            # `back` from a list returns to that list's parent VIEW, never skipping it.
            if self.stack:
                return self._restore(self.stack.pop())
            # No pending view frame: fall back to the entity crumb trail.
            if self.crumb:
                self.crumb.pop()
            if self.crumb:
                self.context = self.crumb[-1]
                self.mode = "menu"; self.results = {}; self.result_total = 0
                self.last_analysis = None
                return self._menu_page()
            self.context, self.mode = None, "menu"
            self.menu = {}; self.results = {}; self.result_total = 0
            self.last_analysis = None
            return "Enter an object to open it, or search(<text>)."
        if low == "history":
            return "History\n" + "\n".join("  %d. %s" % (i + 1, h) for i, h in enumerate(self.hist)) if self.hist else "History empty."
        if low == "tree":
            return self._tree() if self.context else "Open an object first."
        if low in ("summary", "summary()"):
            return self.ake.discovery_report()
        if low in ("verify", "verify()"):
            return WorkbookValidation(self.ake.model).dashboard()
        if low == "analyze" and self.context:
            return self._dispatch("analyze(%s)" % self.context)
        if low == "dev":
            self.dev = not self.dev; return "developer mode: %s" % ("ON" if self.dev else "OFF")
        if low.startswith("dev "):
            return self._developer(low[4:].strip())

        # Explicit result selector: the dashboard sends "r<N>" for a ledger row, so a
        # results-row click can NEVER be mis-resolved against a menu key of the same
        # number. This is the collision fix — a menu action and a results row shared the
        # "1".."N" namespace, so clicking result 9 while the shell had reverted to menu
        # mode opened menu action 9 (a single entity) instead of result row 9.
        rmatch = re.match(r"^r(\d+)$", low)
        if rmatch:
            k = rmatch.group(1)
            if k in self.results:
                return self.open_object(self.results[k])
            return "No result %s here." % k

        if line.isdigit():
            # Mode decides the selector namespace first: a results view resolves digits as
            # rows, a menu view as actions. But a digit that is NOT a valid selector in the
            # current mode is not an error — it may be a NUMERIC ENTITY ID. Fall through to
            # resolution instead of rejecting it, so numeric-pk workbooks are navigable by
            # typing the id directly. (Prefixed workbooks are unaffected: their selectors are
            # small integers and their ids are alpha-prefixed, so nothing changes for them.)
            if self.mode == "results" and line in self.results:
                return self.open_object(self.results[line])
            if self.mode == "menu" and line in self.menu:
                return self._action_page(*self.menu[line])
            # Fall through to entity resolution ONLY if the digit is a genuine owner pk in a
            # numeric-identity workbook. In a prefixed workbook a bare digit is never an
            # entity id (it could at most coincide with a promoted VALUE), so it stays a
            # rejected stale-selector — preserving the anti-stale-state guarantee.
            ident = getattr(self.ake.model, "identity", None)
            if ident is not None and ident.classes_for_pk(line):
                e = self.ake.resolve(line)
                if e.get("id"):
                    return self.open_object(e["id"])
                if e.get("candidates"):
                    return self._candidate_list(line, e["candidates"])
            return "No option %s here." % line

        if self.mode == "menu" and self.menu:
            match = self._menu_lookup(line)
            if match:
                return self._action_page(*self.menu[match])

        _KNOWN_VERBS = ("search", "list", "rel", "compare", "analyze")
        mm = re.match(r'([\w ]+?)\s*\(\s*(.*?)\s*\)\s*$', line)
        verb, arg = (mm.group(1).strip().lower(), mm.group(2).strip()) \
            if mm and mm.group(1).strip().lower() in _KNOWN_VERBS else (None, line)
        if verb == "search":
            hits = self.ake.search(arg)
            if not hits:
                return "No matches for '%s'." % arg
            self._maybe_push()
            self.results = {}; self.mode = "results"
            self.result_total = len(hits)
            L = ["Search: %s  (%d)" % (arg, len(hits)), ""]
            for i, (eid, name) in enumerate(hits, 1):
                self.results[str(i)] = eid
                L.append("  %2d. %s%s" % (i, eid, "  (%s)" % name if name else ""))
            L += ["", "Open a result by number or ID.  back to return."]
            return "\n".join(L)
        if verb == "list":
            ids = self.ake.list_entities(arg)
            if not ids:
                return "No entities with prefix '%s'." % arg.upper()
            self._maybe_push()
            self.results = {}; self.mode = "results"
            self.result_total = len(ids)
            L = ["%s entities  (%d)" % (arg.upper(), len(ids)), ""]
            for i, eid in enumerate(ids[:80], 1):
                nm = self._attrs(eid).get("name")
                self.results[str(i)] = eid
                L.append("  %2d. %s%s" % (i, eid, "  (%s)" % nm if nm else ""))
            if len(ids) > 80:
                L.append("  ... and %d more" % (len(ids) - 80))
            L += ["", "Open a result by number or ID.  back to return."]
            return "\n".join(L)
        if verb == "rel":
            edges = self.ake.list_by_relation(arg)
            if not edges:
                return "No edges of type '%s'." % arg
            self._maybe_push()
            self.results = {}; self.mode = "results"
            self.result_total = len(edges)
            L = ["Relation: %s  (%d edges)" % (arg, len(edges)), ""]
            for i, e in enumerate(edges[:80], 1):
                self.results[str(i)] = e["source"]
                nm = e.get("source_name") or ""
                tgt = e.get("target_name") or e["target"]
                L.append("  %2d. %s -%s-> %s%s" % (i, e["source"], arg, e["target"],
                         "  (%s → %s)" % (nm, tgt) if nm else "  (→ %s)" % tgt))
            if len(edges) > 80:
                L.append("  ... and %d more" % (len(edges) - 80))
            L += ["", "Open a result by number or ID.  back to return."]
            return "\n".join(L)
        if verb == "compare":
            # Parse "A, B" or "A, siblings" or single arg (uses current context)
            parts = [p.strip() for p in arg.split(",")]
            if len(parts) == 1:
                target = self.context or parts[0]
                scope = parts[0]
            else:
                target, scope = parts[0], parts[1]
            # A results/analysis view we are leaving must be snapshotted so `back` returns
            # to it. (Opening from a menu leaves nothing to preserve.)
            self._maybe_push()
            result = self.ake.compare(target, scope)
            if result.get("error"):
                return "Compare error: %s" % result["error"]
            result.setdefault("scope", scope)
            result.setdefault("operation", "compare")
            self.last_analysis = result  # keep the canonical object for the API layer
            return self._render_analysis(result)

        if verb == "analyze":
            eid = arg or self.context
            if not eid:
                return "analyze needs an entity, e.g. analyze(FEAT-032)"
            self._maybe_push()
            result = self.ake.analyze(eid)
            if result.get("error"):
                return "Analyze error: %s" % result["error"]
            result.setdefault("operation", "analyze")
            self.last_analysis = result  # keep the canonical object for the API layer
            return self._render_analysis(result)

        if _ID.match(line):
            e = self.ake.resolve(line)
            if e.get("id"):
                return self.open_object(e["id"])
            if e.get("candidates"):
                return self._candidate_list(line, e["candidates"])
            return "Unknown ID '%s'." % line
        target = arg if verb else line
        e = self.ake.resolve(target)
        if e.get("id"):
            return self.open_object(e["id"])
        # Ambiguous name/id (same label or pk across classes): show the candidates as a
        # navigable results list — never auto-open one, so the WRONG class is never guessed.
        if e.get("candidates"):
            return self._candidate_list(target, e["candidates"])
        hits = self.ake.search(target)
        return ("Did you mean:\n" + "\n".join("  %s  %s" % (h[0], h[1]) for h in hits[:8])) if hits \
            else "No object matches '%s'. Try search(<text>) or list(<PREFIX>)." % target

    def _candidate_list(self, token, candidates):
        """Render an ambiguous resolution as a picker. The visible id stays the raw pk — no
        synthetic '1@Class' is ever shown. Selection is carried by an INTERNAL canonical
        token (opaque CID-...), so opening a candidate is unambiguous without polluting the
        user-facing id space."""
        self.results = {}; self.mode = "results"; self.result_total = len(candidates)
        L = ["Multiple entities found for '%s' — pick one:" % token, ""]
        for i, cnd in enumerate(candidates, 1):
            sel = cnd.get("canonical") or cnd["id"]   # canonical token when colliding pk
            self.results[str(i)] = sel
            nm = ("  %s" % cnd["name"]) if cnd.get("name") else ""
            L.append("  %2d. %s%s" % (i, cnd["id"], nm))
            L.append("      Registry : %s" % cnd.get("class", "?"))
        L += ["", "Open a result by number.  back to return."]
        return "\n".join(L)

    def _help(self):
        if self.context is None:
            return self._engine_help_block() + "\n\n" + self._knowledge_help()
        # an object is open: Engine Help doesn't change per-object -- printing it in full again
        # on every 'help' call is pure repetition. The signal used is self.context, already
        # existing state (it already gates _menu_page()/_tree()/etc.), not a new flag.
        return "Type 'help engine' to see navigation commands again.\n\n" + self._knowledge_help()

    def _engine_help_block(self):
        L = ["Engine Help  (fixed -- how this explorer works, not derived from any workbook)", "",
             "  <ID>            open an object", "  <number>        run an action / open a result",
             "  <relation name> same as its number -- e.g. 'handler' works whenever Handler is on the menu",
             "  search(<text>)  find objects by name or id", "  list(<PREFIX>)  list all ids of a type",
             "  tree            show current object's relationships",
             "  back | home | history | summary() | verify() | exit"]
        if self.dev:
            L += ["", "Developer: dev ir | dev registry | dev capability | dev rules"]
        return "\n".join(L)

    def _knowledge_help(self):
        """Everything below is derived from the current object's actual data -- nothing here is
        a per-relation dictionary. Cardinality comes from model.rpde_cardinality (already
        computed once at workbook load, ake/relational_primitive_engine.py -- reused, not
        recomputed). Target type comes from the neighbor's own class attribute. Evidence is
        whatever's already on the edge. "Available next actions" is self.menu itself, restated
        as verb + label -- the same data _menu_page() already shows, not new knowledge. A
        relation this workbook doesn't have simply doesn't appear; nothing here would need to
        change if tomorrow's workbook has entirely different relation names."""
        if not self.context:
            return ("Knowledge Help  (derived from the current object -- there isn't one open "
                     "yet, so there's nothing to derive)")
        eid = self.context
        rels = self._relations(eid)
        if not rels:
            return "Knowledge Help  (%s)\n  This object has no relationships to explore." % eid
        L = ["Knowledge Help  (derived from %s -- changes for every object and every workbook)" % eid, ""]
        if self.menu:
            L.append("Available next actions")
            for key in sorted(self.menu, key=int):
                friendly, q, rel = self.menu[key]
                L.append("  %s %s" % ("Open" if q == "REL" else "Show", friendly))
            L.append("")
        for rel in rels:
            edges = [e for e in self._neighbors(eid) if e["relation"] == rel]
            target_classes = sorted(set(c for e in edges if (c := self._attrs(e["node"]).get("class"))))
            card = self.ake.model.rpde_cardinality.get(rel)
            has_evidence = any(e.get("evidence") for e in edges)
            L.append("  %s" % rel)
            L.append("    Target type    : %s" % (", ".join(target_classes) if target_classes else "not documented"))
            L.append("    Cardinality    : %s" % (card if card else "not documented"))
            if len(edges) == 1:
                nm = self._attrs(edges[0]["node"]).get("name")
                L.append("    Current value  : %s" % (nm or edges[0]["node"]))
            else:
                L.append("    Current value  : %d connected" % len(edges))
            L.append("    Evidence       : %s" % ("available" if has_evidence else "not available"))
        return "\n".join(L)

    def _developer(self, what):
        a = self.ake
        if what in ("", "summary"):
            return "strategy=%s IR nodes=%d edges=%d" % (self.strategy, len(a.model.universal_graph.node_attrs), len(a.model.universal_edges))
        if what == "ir":
            return "IR: %d typed nodes, %d typed edges" % (len(a.model.universal_graph.node_attrs), len(a.model.universal_edges))
        if what == "registry":
            import json; return json.dumps(a.registry_universe()["totals"], indent=1)
        if what == "capability":
            import json; return json.dumps(a.capability_universe()["per_question"], indent=1)
        if what == "rules":
            return "\n".join("  %s: %s" % (r["id"], r["purpose"]) for r in a.derive_rules()[:10])
        return "dev topics: summary | ir | registry | capability | rules"

    def run(self, input_fn=input, output_fn=print):
        output_fn(self.banner())
        while True:
            try:
                line = input_fn("\nAKE > ")
            except (EOFError, KeyboardInterrupt):
                break
            res = self.handle(line)
            if res is None:
                output_fn("bye"); break
            if res:
                output_fn(res)


def start(workbook_path, dev=False):
    from . import AKE
    AKEShell(AKE(workbook_path), dev=dev).run()
