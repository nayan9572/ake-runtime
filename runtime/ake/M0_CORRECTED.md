# M0 — Corrected (query-independent). Implemented in feature_discovery.py.

Old (circular): survey → query → decompose → primitives.  [queries don't exist yet]
New (root):
```
Workbook → Feature Discovery (RP-00) → Observation Discovery (RP-01)
→ Primitive Derivation (RP-02) → Closure Test (RP-03)
```
Only after closure:  Observation → Comparison → Pattern → Invariant → Rule → Query → Algorithm.

Corrected RP priority:
RP-00 Universal Workbook Feature Discovery      IMPLEMENTED+VALIDATED (v16: 11 feature-types)
RP-01 Universal Observation Discovery           IMPLEMENTED+VALIDATED (feature→observation map)
RP-02 Universal Discovery Primitive Derivation  IMPLEMENTED+VALIDATED (10 primitives)
RP-03 Primitive Closure & Completeness          CLOSED for v16 (0 gaps); cross-workbook pending
RP-04 Invariant Identification                  OPEN
RP-05 Rule Derivation                           OPEN
RP-06 Query Derivation                          OPEN
RP-07 Algorithm Synthesis                        OPEN (runtime path implemented for known query types)

Validation (v16): features=11 covered=11 gaps=0 → CLOSED. Feature Discovery is workbook-agnostic (structural scan + Registry Catalog); run closure() on any workbook.
