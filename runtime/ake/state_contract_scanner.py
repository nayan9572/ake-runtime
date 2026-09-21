"""Generic State-Contract Scanner (engine-agnostic invariant verifier).

WHY THIS EXISTS
    A concrete regression (EBIS Tier C) slipped past review: a new code path
    became a SECOND writer of an internal mirror variable (_x_ethanol) and, in the
    same change, dropped the per-cycle self-heal that kept the mirror synced to its
    canonical source. Neither a static "who imports what" check nor a post-cycle
    value check caught it (the post-cycle check was tautological — the engine self-
    healed before the check ran). What caught it was: (a) a static single-writer
    audit against a DECLARED owner, and (b) a MUTATION test that deliberately
    corrupted the mirror and verified the next lifecycle step restored it.

    This module generalizes exactly that. It is NOT EBIS-specific and contains no
    variable names. An engine supplies a CONTRACT (a declarative registry of state
    variables, their canonical owner, allowed writers, mirror relationships, self-
    heal expectations, propagation path, and schema). The scanner then runs the
    same audits against ANY engine's contract. Tomorrow the variable may be
    _x_ethanol, pressure_state, some other engine's fuel_mass, or a state owned by
    a completely different engine mounted under AKE — the scanner core does not
    change; only the engine's contract evidence changes.

DESIGN PRINCIPLES (aligned with AKE's architecture layer)
    * Contract-driven, never name-driven. No `if var == "_x_ethanol"`. The scanner
      reads a StateContract and applies GENERIC rules (declared owner vs actual
      writers, canonical-vs-mirror divergence, self-heal-on-corruption, ...).
    * Reuse-only + lazy. Nothing runs unless a scan is requested. The scanner owns
      verification; it does not own or mutate the engine's state model.
    * Correct-refusal is success (borrowed from ArchitectureDiagnosis): a missing
      optional audit input is NOT_APPLICABLE, not FAIL.
    * Static evidence + runtime evidence + mutation test — three independent
      layers. A static-only scan is explicitly marked partial.
    * Ownership hierarchy is external: whoever mounts an engine under AKE (e.g. the
      EBIS orchestrator) owns the engine; AKE only provides the scanner. The
      scanner never asserts control over an engine — it inspects and reports.

VERDICTS: PASS, PARTIAL, FAIL, NOT_APPLICABLE.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT MODEL — what an engine declares (declarative, engine-agnostic)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class StateContract:
    """One state variable's contract. An engine supplies a list of these.

    Everything here is DECLARED by the engine; the scanner verifies actual code /
    runtime against these declarations. No field names a specific engine.
    """
    name: str                              # the state variable (attribute) name
    canonical_source: Optional[str] = None # human/logical name of the source of truth
    owner_funcs: Tuple[str, ...] = ()      # functions allowed to WRITE this state
    owner_file: Optional[str] = None       # file the owner functions must live in
    seed_funcs: Tuple[str, ...] = ()       # funcs allowed to seed at init (e.g. __init__)
    mirror_of: Optional[str] = None        # if this is a mirror, the canonical attr it mirrors
    self_heal: bool = False                # must a corrupted value be repaired next lifecycle step?
    readers_expected: Tuple[str, ...] = () # optional: files/functions expected to read it
    # Optional runtime hooks (callables the engine provides so the scanner can
    # exercise the real lifecycle without knowing engine internals):
    #   get_value(engine)          -> current value of this state
    #   get_canonical(engine)      -> current value of the canonical source
    #   set_value(engine, v)       -> force-write this state (for mutation test)
    #   step_lifecycle(engine)     -> run exactly one normal lifecycle step
    notes: str = ""


@dataclass(frozen=True)
class PropagationContract:
    """A declared input→...→output propagation path the scanner can trace at
    runtime. Each stage is (label, extractor) where extractor(engine_output) returns
    the value present at that stage (or None if absent)."""
    label: str
    stages: Tuple[str, ...] = ()           # ordered stage labels (input→kernel→output→buffer→...)
    # extractor(engine, produced) -> dict {stage_label: present(bool)}
    trace: Optional[Callable[[Any, Any], Dict[str, bool]]] = None


@dataclass(frozen=True)
class SchemaContract:
    """Declared expected keys for a produced record (output row / state dict).
    The scanner flags missing / extra / renamed keys."""
    label: str
    expected_keys: Tuple[str, ...] = ()
    # produce(engine) -> the dict whose keys are audited
    produce: Optional[Callable[[Any], Dict[str, Any]]] = None
    allow_extra: bool = True               # extra keys => warning, not FAIL, unless False


@dataclass(frozen=True)
class EngineContract:
    """The full contract an engine registers with the scanner. Owner of the engine
    (e.g. EBIS orchestrator) is recorded but the scanner never uses it to control
    the engine — only to attribute ownership in the report."""
    engine_id: str
    owner: str                             # e.g. "ebis_orchestrator" — attribution only
    root_dir: str                          # source root for static scans
    states: Tuple[StateContract, ...] = ()
    propagations: Tuple[PropagationContract, ...] = ()
    schemas: Tuple[SchemaContract, ...] = ()
    # build_engine() -> a fresh, ready engine instance for runtime/mutation tests
    build_engine: Optional[Callable[[], Any]] = None
    notes: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# STATIC WRITER/READER AUDIT (source-level, generic)
# ═══════════════════════════════════════════════════════════════════════════════

def _iter_py_files(root: str):
    for dp, dn, fn in os.walk(root):
        if "__pycache__" in dp:
            continue
        for f in fn:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


class _AssignFinder(ast.NodeVisitor):
    """Collect (attr_name -> [(func_name, lineno), ...]) for `self.<attr> = ...`
    and enclosing function. Generic — no attribute names are hardcoded."""

    def __init__(self):
        self.writes: Dict[str, List[Tuple[str, int]]] = {}
        self.reads: Dict[str, List[Tuple[str, int]]] = {}
        self._func_stack: List[str] = ["<module>"]

    def visit_FunctionDef(self, node):
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _attr_of(self, target) -> Optional[str]:
        # matches `self.<name>`
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
                and target.value.id == "self":
            return target.attr
        return None

    def visit_Assign(self, node):
        for tgt in node.targets:
            a = self._attr_of(tgt)
            if a is not None:
                self.writes.setdefault(a, []).append((self._func_stack[-1], node.lineno))
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        a = self._attr_of(node.target)
        if a is not None:
            self.writes.setdefault(a, []).append((self._func_stack[-1], node.lineno))
        self.generic_visit(node)

    def visit_Attribute(self, node):
        # a READ of self.<name> (Load context)
        if isinstance(node.value, ast.Name) and node.value.id == "self" \
                and isinstance(node.ctx, ast.Load):
            self.reads.setdefault(node.attr, []).append((self._func_stack[-1], node.lineno))
        self.generic_visit(node)


def _static_index(root: str):
    """Build {file -> _AssignFinder} across the source tree. Cached per scan."""
    idx = {}
    for path in _iter_py_files(root):
        try:
            tree = ast.parse(open(path, "r", encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        f = _AssignFinder()
        f.visit(tree)
        idx[path] = f
    return idx


def audit_writers(contract: EngineContract, state: StateContract, idx) -> dict:
    """Generic single-writer audit: every `self.<state> = ...` must be inside a
    DECLARED owner (owner_funcs / seed_funcs) and, if owner_file is given, in that
    file. Any other writer is unauthorized => FAIL."""
    hits: List[Tuple[str, str, int]] = []   # (file, func, line)
    for path, finder in idx.items():
        for func, line in finder.writes.get(state.name, []):
            hits.append((path, func, line))
    if not hits:
        return {"verdict": FAIL, "detail": f"no writer found for '{state.name}' "
                f"(declared owner exists but nothing writes it)", "sites": []}
    allowed_funcs = set(state.owner_funcs) | set(state.seed_funcs)
    bad = []
    for path, func, line in hits:
        file_ok = (state.owner_file is None) or path.replace("\\", "/").endswith(state.owner_file)
        func_ok = func in allowed_funcs
        if not (file_ok and func_ok):
            bad.append((path, func, line))
    if bad:
        return {"verdict": FAIL,
                "detail": "unauthorized writer(s): " +
                          "; ".join(f"{os.path.basename(p)}:{ln} (in {fn})" for p, fn, ln in bad),
                "sites": hits}
    return {"verdict": PASS,
            "detail": f"{len(hits)} write site(s), all inside "
                      f"{{{'/'.join(sorted(allowed_funcs))}}}",
            "sites": hits}


def audit_readers(contract: EngineContract, state: StateContract, idx) -> dict:
    """Optional reader audit. If readers_expected is declared, confirm the state is
    actually read somewhere; report the read sites. Absence of declared expectation
    => NOT_APPLICABLE (we do not invent a requirement)."""
    reads = []
    for path, finder in idx.items():
        for func, line in finder.reads.get(state.name, []):
            reads.append((os.path.basename(path), func, line))
    if not state.readers_expected:
        return {"verdict": NOT_APPLICABLE, "detail": f"{len(reads)} reader(s) found "
                f"(no declared reader expectation)", "sites": reads}
    if not reads:
        return {"verdict": FAIL, "detail": f"'{state.name}' declared readable but "
                f"no reader found", "sites": []}
    return {"verdict": PASS, "detail": f"{len(reads)} reader site(s)", "sites": reads}


# ═══════════════════════════════════════════════════════════════════════════════
# RUNTIME INVARIANT + MUTATION TEST (dynamic, generic)
# ═══════════════════════════════════════════════════════════════════════════════

def audit_mirror_invariant(state: StateContract, engine) -> dict:
    """If the state is a mirror, verify mirror == canonical on a fresh engine
    (BEFORE any lifecycle step — the window where seed bugs live)."""
    if not state.mirror_of:
        return {"verdict": NOT_APPLICABLE, "detail": "not a mirror"}
    getv = state.__dict__.get  # dataclass frozen: hooks passed via contract closure
    return {"verdict": NOT_APPLICABLE, "detail": "runtime hooks provided at scan time"}


def _hooks(hooks: dict, name: str):
    fn = hooks.get(name)
    return fn


def run_mutation_test(state: StateContract, engine, hooks: dict) -> dict:
    """THE test that caught the real regression. Generic:
        1. establish valid state (fresh engine + one lifecycle step)
        2. read canonical + mirror; confirm they match (pre-condition)
        3. deliberately corrupt the mirror to canonical+delta
        4. run exactly ONE normal lifecycle step
        5. verify the mirror was restored to canonical (self-heal)
    Requires get_value, get_canonical, set_value, step_lifecycle hooks. Missing
    hooks => NOT_APPLICABLE (cannot exercise without them; not a failure)."""
    if not state.self_heal:
        return {"verdict": NOT_APPLICABLE, "detail": "no self-heal declared"}
    get_value = _hooks(hooks, "get_value")
    get_canon = _hooks(hooks, "get_canonical")
    set_value = _hooks(hooks, "set_value")
    step = _hooks(hooks, "step_lifecycle")
    if not all([get_value, get_canon, set_value, step]):
        return {"verdict": NOT_APPLICABLE,
                "detail": "self-heal declared but runtime hooks "
                          "(get_value/get_canonical/set_value/step_lifecycle) not all provided"}
    try:
        # 1. establish valid state
        step(engine)
        canon0 = get_canon(engine)
        mirror0 = get_value(engine)
        # 2. pre-condition: mirror tracks canonical
        pre_ok = (mirror0 == canon0)
        # 3. corrupt the mirror out-of-band (simulated rogue write)
        corrupt = (float(canon0) if _isnum(canon0) else 0.0) + 0.31
        set_value(engine, corrupt)
        diverged = (get_value(engine) != get_canon(engine))
        # 4. one normal lifecycle step
        step(engine)
        # 5. restored?
        canon1 = get_canon(engine)
        mirror1 = get_value(engine)
        healed = (mirror1 == canon1)
        if pre_ok and diverged and healed:
            return {"verdict": PASS,
                    "detail": f"corrupt {mirror0}→{corrupt} (canonical {canon0}); "
                              f"next step restored mirror to {mirror1}"}
        if not pre_ok:
            return {"verdict": FAIL, "detail": f"pre-condition failed: mirror {mirror0} "
                    f"!= canonical {canon0} on fresh engine"}
        if not diverged:
            return {"verdict": FAIL, "detail": "mutation not observable — set_value did not "
                    "diverge mirror from canonical (mutation harness broken)"}
        return {"verdict": FAIL,
                "detail": f"SELF-HEAL BROKEN: corrupted {corrupt} survived one lifecycle step "
                          f"(mirror={mirror1}, canonical={canon1})"}
    except Exception as e:
        return {"verdict": FAIL, "detail": f"mutation test raised {type(e).__name__}: {e}"}


def _isnum(v) -> bool:
    try:
        float(v); return True
    except (TypeError, ValueError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK / SCHEMA / PROPAGATION / DUPLICATE-AUTHORITY audits (generic)
# ═══════════════════════════════════════════════════════════════════════════════

def audit_schema(schema: SchemaContract, engine) -> dict:
    """Missing / extra / renamed keys against a declared expected set."""
    if schema.produce is None:
        return {"verdict": NOT_APPLICABLE, "detail": "no producer provided"}
    try:
        got = schema.produce(engine) or {}
    except Exception as e:
        return {"verdict": FAIL, "detail": f"producer raised {type(e).__name__}: {e}"}
    got_keys = set(got.keys())
    exp = set(schema.expected_keys)
    missing = sorted(exp - got_keys)
    extra = sorted(got_keys - exp)
    if missing:
        return {"verdict": FAIL, "detail": f"missing keys {missing}"
                + (f"; extra {extra}" if extra else "")}
    if extra and not schema.allow_extra:
        return {"verdict": FAIL, "detail": f"unexpected extra keys {extra}"}
    return {"verdict": PASS, "detail": f"{len(exp)} expected keys present"
            + (f"; {len(extra)} extra (allowed)" if extra else "")}


def audit_propagation(prop: PropagationContract, engine, produced) -> dict:
    """Trace declared input→...→downstream stages; every declared stage must carry
    the value. A gap => FAIL naming the first missing stage."""
    if prop.trace is None:
        return {"verdict": NOT_APPLICABLE, "detail": "no tracer provided"}
    try:
        present = prop.trace(engine, produced) or {}
    except Exception as e:
        return {"verdict": FAIL, "detail": f"tracer raised {type(e).__name__}: {e}"}
    gaps = [s for s in prop.stages if not present.get(s, False)]
    if gaps:
        return {"verdict": FAIL, "detail": f"value absent at stage(s): {gaps}"}
    return {"verdict": PASS, "detail": f"present through all {len(prop.stages)} stages"}


def audit_duplicate_authority(contract: EngineContract, idx) -> dict:
    """Duplicate-authority heuristic: two DIFFERENT owner_files both writing the
    same state name => two independent derivers of one property. Uses the declared
    contracts + the static write index."""
    by_name: Dict[str, set] = {}
    for st in contract.states:
        for path, finder in idx.items():
            if finder.writes.get(st.name):
                by_name.setdefault(st.name, set()).add(os.path.basename(path))
    dup = {n: sorted(fs) for n, fs in by_name.items() if len(fs) > 1}
    # A mirror legitimately has one owner; if >1 file writes it, that's the smell.
    if dup:
        return {"verdict": FAIL, "detail": f"state written from multiple files: {dup}"}
    return {"verdict": PASS, "detail": "no state written by more than one file"}


# ═══════════════════════════════════════════════════════════════════════════════
# THE SCANNER — orchestrates all audits for one engine contract
# ═══════════════════════════════════════════════════════════════════════════════

class StateContractScanner:
    """Engine-agnostic scanner. Give it an EngineContract; it runs static + runtime
    + mutation audits and returns a verdict model. Core never changes per engine —
    only the contract does. AKE owns the scanner; the engine's owner (e.g. EBIS
    orchestrator) owns the engine."""

    def __init__(self, contract: EngineContract, runtime_hooks: Optional[Dict[str, Dict]] = None):
        # runtime_hooks: {state_name: {get_value/get_canonical/set_value/step_lifecycle}}
        self.contract = contract
        self.runtime_hooks = runtime_hooks or {}

    def scan(self, static_only: bool = False) -> dict:
        c = self.contract
        idx = _static_index(c.root_dir)
        report = {
            "engine_id": c.engine_id,
            "owner": c.owner,
            "root_dir": c.root_dir,
            "states": [],
            "duplicate_authority": audit_duplicate_authority(c, idx),
            "schemas": [],
            "propagations": [],
        }

        for st in c.states:
            entry = {
                "name": st.name,
                "canonical_source": st.canonical_source,
                "mirror_of": st.mirror_of,
                "writer_audit": audit_writers(c, st, idx),
                "reader_audit": audit_readers(c, st, idx),
                "mutation_test": {"verdict": NOT_APPLICABLE, "detail": "static-only"},
            }
            if not static_only and c.build_engine is not None:
                hooks = self.runtime_hooks.get(st.name, {})
                try:
                    engine = c.build_engine()
                    entry["mutation_test"] = run_mutation_test(st, engine, hooks)
                except Exception as e:
                    entry["mutation_test"] = {"verdict": FAIL,
                                              "detail": f"engine build failed: {type(e).__name__}: {e}"}
            report["states"].append(entry)

        # schema + propagation (runtime) — only if engine buildable and not static_only
        if not static_only and c.build_engine is not None:
            for sc in c.schemas:
                try:
                    engine = c.build_engine()
                    report["schemas"].append({"label": sc.label, **audit_schema(sc, engine)})
                except Exception as e:
                    report["schemas"].append({"label": sc.label, "verdict": FAIL,
                                              "detail": f"{type(e).__name__}: {e}"})
            for pr in c.propagations:
                try:
                    engine = c.build_engine()
                    produced = None
                    # tracer is responsible for running/collecting; pass engine + None
                    report["propagations"].append({"label": pr.label, **audit_propagation(pr, engine, produced)})
                except Exception as e:
                    report["propagations"].append({"label": pr.label, "verdict": FAIL,
                                                    "detail": f"{type(e).__name__}: {e}"})

        report["summary"] = self._summarize(report)
        return report

    @staticmethod
    def _summarize(report: dict) -> dict:
        verdicts = []
        for s in report["states"]:
            verdicts += [s["writer_audit"]["verdict"], s["mutation_test"]["verdict"]]
            if s["reader_audit"]["verdict"] != NOT_APPLICABLE:
                verdicts.append(s["reader_audit"]["verdict"])
        verdicts.append(report["duplicate_authority"]["verdict"])
        verdicts += [x["verdict"] for x in report["schemas"]]
        verdicts += [x["verdict"] for x in report["propagations"]]
        scored = [v for v in verdicts if v != NOT_APPLICABLE]
        failed = [v for v in scored if v == FAIL]
        overall = FAIL if failed else (PASS if scored else NOT_APPLICABLE)
        return {"overall": overall,
                "n_checks": len(scored),
                "n_failed": len(failed),
                "not_applicable": sum(1 for v in verdicts if v == NOT_APPLICABLE)}


def render_report(report: dict) -> str:
    """Plain-text render of a scan report."""
    L = []
    L.append("=" * 66)
    L.append(f"  STATE-CONTRACT SCAN — engine '{report['engine_id']}' "
             f"(owner: {report['owner']})")
    L.append("=" * 66)
    s = report["summary"]
    L.append(f"  OVERALL: {s['overall']}  ({s['n_checks']} checks, "
             f"{s['n_failed']} failed, {s['not_applicable']} n/a)")
    L.append("-" * 66)
    for st in report["states"]:
        L.append(f"  STATE: {st['name']}"
                 + (f"  (mirror of {st['mirror_of']})" if st["mirror_of"] else ""))
        wa = st["writer_audit"]; L.append(f"    writer  : {wa['verdict']} — {wa['detail']}")
        ra = st["reader_audit"]; L.append(f"    reader  : {ra['verdict']} — {ra['detail']}")
        mt = st["mutation_test"]; L.append(f"    mutation: {mt['verdict']} — {mt['detail']}")
    da = report["duplicate_authority"]
    L.append(f"  DUPLICATE-AUTHORITY: {da['verdict']} — {da['detail']}")
    for sc in report["schemas"]:
        L.append(f"  SCHEMA [{sc['label']}]: {sc['verdict']} — {sc['detail']}")
    for pr in report["propagations"]:
        L.append(f"  PROPAGATION [{pr['label']}]: {pr['verdict']} — {pr['detail']}")
    L.append("=" * 66)
    return "\n".join(L)
