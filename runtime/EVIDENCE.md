# AKE — Evidence Report (Before / After)

Verification: `tests/verification_report.json` (20/20 checks pass). Runner: `colab_run.py`.
CLI dispatch verification: `tests/verification_report_cli.json` (15/15 checks pass).

## Finding F-18 — dangling Registry Catalog entry crashes edge derivation
| Behavior | Before | After |
|---|---|---|
| `python colab_run.py workbook.xlsx` where the catalog lists a registry with no backing sheet | uncaught `KeyError` inside `derive_edges()`, propagates through `colab_run.py`, **exit code 1, no `ake_out/`** | dangling registry is skipped for edge derivation (consistent with how `col()`/`rows()` already treat it elsewhere); pipeline completes, `ake_out/` written, exit 0 |
| Regression suite (`tests/regression.py`) | 20/20 | **22/22** (2 new F-18 checks) |

## Finding F-15 — AKE_MASTER.py batch-mode dispatch
| Behavior | Before | After |
|---|---|---|
| `python AKE_MASTER.py workbook.xlsx` under non-interactive stdin | enters REPL, hits `EOFError` immediately, exits 0, **no `ake_out/` written, no error surfaced** | dispatches to **batch mode**: runs the full pipeline via `ake/runner.py:run()`, writes all 8 `ake_out/*.json` artifacts, exits 0 |
| `python AKE_MASTER.py` (no args) | interactive REPL | unchanged — interactive REPL |
| `python AKE_MASTER.py --demo` | scripted demo | unchanged — scripted demo |
| Interactive session against an explicit workbook | only reachable form | still reachable via `--repl` |
| Batch output location when caller subprocess sets no `cwd=` | n/a | `ake_out/` anchored beside `AKE_MASTER.py` — **independent of the caller's working directory** (a caller that forgets `cwd=` no longer gets artifacts silently written to the wrong place) |
| Determinism (two independent batch runs, same workbook) | n/a (no batch mode existed) | **byte-identical** `ake_out/*.json` across runs |
| Regression suite (`tests/regression.py`) | 20/20 | 20/20 (unaffected) |
| New CLI dispatch suite (`tests/test_cli_dispatch.py`) | n/a | **15/15** |

## Finding RP-13 — RPDE
| Metric | Before (Feature-only) | After (RPDE) |
|---|---|---|
| owner classes with traversable edges | 1/13 | **13/13** |
| universal edges | 280 | **1642** |
| relation vocabulary | fixed Feature edges | **27, derived from column headers** |
| cardinality | not computed | **derived by count** |
| duplicate / self-loop / dangling edges | — | **0 / 0 / 0** |
| cross-workbook (robotics, no code change) | n/a | **8 edges, domain vocabulary derived** |

## Finding — Canonical Property-Graph IR
| Derivation from IR ALONE | Edge-only IR | Property-graph IR |
|---|---|---|
| relationship invariants | ✅ 13 | ✅ 13 |
| attribute invariants (has_PK/has_Evidence) | ❌ | **✅ 24** |
| lifecycle/execution/evidence queries | ❌ | **✅ (lifecycle 91, execution 107)** |
| node-attribute rendering | ❌ | **✅** |
| IR nodes with attributes | 0 | **1037** |

## Determinism
Two independent runs on the same workbook → identical edge count (1642) and identical invariant
count. Colab runner emits reproducible JSON artifacts.

## Finding F-021 — Command prose → IR edges
| Metric | Before | After |
|---|---|---|
| Command edges (total / avg) | 9 / 0.08 | 260 / 2.43 |
| CMD-002 typed edges | 0 | 5 (handler:HND-026, pipeline:PIPE-001, module×3) |
| wrong-class / spurious-evidence edges | — | 0 / 0 |
| LIFECYCLE_RECONSTRUCT on CMD-002 | not applicable | executes (runtime unchanged) |
| universal edges | 1642 | 1909 |

## Finding F-022 — prose canonicalization
| Metric | Value |
|---|---|
| Command edges (F-021 → F-022) | 260 → 276 (+16 handler→Component) |
| canonicalization report: resolved_registry / resolved_component | 46 / 16 |
| not_found (legitimate) | 395 |
| **ABSENT (author must register)** | **181** |
| wrong-class edges | 0 |
Conclusion: compiler has extracted all resolvable references; full command coverage now depends on SOURCE metadata (register the 181 absent entities). Compiler cannot fabricate entities.

## Finding F-023 — cross-registry re-verification (corrects F-022)
| Classification (exact, all registries) | Count | Phase |
|---|---|---|
| compiler/matcher format ('/'-compound) — FIXED | 5 (+13 edges) | Phase 1 |
| resolution / primitive / algorithm | 0 | Phase 2/4/5 (clean) |
| registered under another entity type | 7 | Phase 3 |
| genuine metadata gap (in NO registry) | ~169–174 | Phase 6 |
Command edges 276 → 289. 0 wrong-class. Verdict: "resolve fail ≠ absent" — 12 of 181 were not gaps.


## UX-1.3 — Action-dispatch fixes (real HTTP stack, workbook v17, owner mode)

| Reported issue | Before | After | Evidence |
|---|---|---|---|
| Relation/Reference button opens wrong set | key namespace collision opened 1 entity | advertised == result_count for every direct relation on MOD-002 | 22/22 harness |
| Analyze renders a list | `mode="results"` (mislabel) | `mode="analysis"`, branch renderAnalysis | harness |
| Compare renders a list / count split | badge 176 vs results 80 | 176 == result_count == analysis.targets (and 106) | harness |
| Back skips the results list | crumb-only history → home | back → parent entity menu → home | harness + test_semantic_fidelity 25/25 |
| Back/Home fire multiple dispatches | per-repaint listeners accumulate | one delegated listener bound once | dashboard JS validated |
| Search misses canonical IDs | unranked, 50-cap truncation | ranked exact-first; MOD-002 surfaces | harness |
| Owner/Family/Feature/Category/Module relations | — | all resolve to correct counts | harness (FEAT-001) |
| Source-row semantic promotion / promoted search | — | promoted entity round-trips API, drills to 315 results | test_capability_synthesis 31/31 |
| HTTP errors | — | no 4xx/5xx across full workflow | harness |

Regression after fixes: **272/272** across 8 suites (capability_synthesis 31, cli_dispatch 35,
explorer_ux 23, reachability_engine 13, reachability_universality 32, semantic_fidelity 25,
stabilization 12, regression 101). availability/menu key alignment: 0 mismatches.
