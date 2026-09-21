# AKE Compatibility

| Workbook shape | Supported | Path |
|---|---|---|
| Registry-convention (Registry Catalog + ID PKs + FK cols) | ✅ full | native |
| Catalog-less, ID-pattern PKs (single/multi sheet) | ✅ compiles (observation + IR + invariants) | F-04 inference + bundled defaults |
| Multi-registry with FK IDs | ✅ typed edges via RPDE | RPDE |
| FK stored as entity NAMES | ✅ resolved by name | RPDE name resolution |
| Non-engineering domains (robotics/customer with ID PKs) | ✅ graph builds, derived vocabulary | verified (robotics) |

## Not yet supported (see KNOWN_LIMITATIONS.md)
- Genuine composite primary keys (F-06)
- Composite primary keys (F-06)
- Relationship sheets with non-standard column names, when a Registry Catalog IS present (F-07)
- Duplicate primary-key values within the same registry (F-08b)
- FK stored as free-text prose that matches no entity name (Command residual)

IR schema: see SCHEMA_VERSION.json (v1.1). Canonical metrics: BASELINE.json.
