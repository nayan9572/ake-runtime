# AKE Capability Universe

For any entity, AKE answers questions across **10 categories / 31 canonical question types**. A question
is *supported* for an entity when the backing relation/attribute exists in that entity's compiled record;
otherwise AKE reports it as not-referenced (legitimate) or a metadata gap — it never guesses. Every
supported answer carries evidence (registry + file:line).

Validated on `EBIS_Architecture_Registry_Workbook_v17.xlsx`: **1037 entities, all 31 question types
answerable somewhere in the workbook.** Universal questions answer for every entity; control/data-flow/
classification are family-specific (a Feature has no Handler; a Command has no Category).

## Categories & questions
| Category | Questions |
|---|---|
| Identity | WHAT_IS · GET_NAME · GET_PURPOSE |
| Ownership | GET_OWNER |
| Relationships | GET_NEIGHBORS · GET_INCOMING · GET_OUTGOING |
| Control | GET_HANDLER · GET_GATE · GET_PIPELINE · GET_BRIDGE · GET_VALIDATOR |
| Data Flow | GET_PRODUCERS · GET_CONSUMERS · GET_READS · GET_PUBLISHES · GET_OBSERVES |
| Dependency | GET_UPSTREAM · GET_DOWNSTREAM · IS_ROOT · IS_LEAF |
| Classification | GET_CATEGORY · GET_FAMILY · GET_ROLE |
| Integrity | CHECK_FK · IS_ORPHAN · IS_DUPLICATE |
| Coverage | MISSING_EVIDENCE · EMPTY_FIELDS |
| Evidence | GET_EVIDENCE · GET_SOURCE_ROW |

## Per-question coverage on EBIS (entities answerable / 1037)
| Question | Answerable | Backing |
|---|---|---|
| WHAT_IS / GET_NAME / GET_PURPOSE | 1037 | owner registry row (universal) |
| CHECK_FK / IS_ORPHAN / IS_DUPLICATE | 1037 | integrity primitives (universal) |
| MISSING_EVIDENCE / EMPTY_FIELDS | 1037 | coverage analysis (universal) |
| GET_EVIDENCE / GET_SOURCE_ROW | 1017 | evidence attribute |
| GET_NEIGHBORS/INCOMING/OUTGOING, GET_UPSTREAM/DOWNSTREAM, IS_ROOT/LEAF | 1011 | Universal Property Graph |
| GET_OWNER | 991 | module relation |
| GET_FAMILY | 114 | family relation |
| GET_HANDLER | 110 | handler relation |
| GET_CATEGORY | 104 | category relation |
| GET_ROLE | 99 | role relation |
| GET_GATE | 26 | gate relation |
| GET_PRODUCERS | 26 | produces relation |
| GET_OBSERVES | 23 | observes relation |
| GET_VALIDATOR | 21 | validator relation |
| GET_PIPELINE | 16 | pipeline relation |
| GET_CONSUMERS | 12 | consumes relation |
| GET_PUBLISHES | 11 | publishes relation |
| GET_BRIDGE | 10 | bridge relation |
| GET_READS | 4 | reads relation |

## Reading this
- **Universal capabilities** (Identity, Integrity, Coverage, Evidence, Graph) hold for essentially every
  entity — these are the guaranteed floor on any conforming workbook.
- **Family-specific capabilities** (Control, Data Flow, Classification) reflect what each family actually
  models; low counts are correct, not gaps.
- Adding a **new relation** to the workbook + a **new question** to the query-definition registry extends
  this universe with **zero engine code change** (proven: GET_MONITORS).

## API
```python
AKE(wb).capability_universe()      # workbook-wide matrix (counts above)
AKE(wb).capabilities("FEAT-016")   # per-entity matrix (which questions supported + evidence)
```
