# Generic State-Contract Scanner — usage

`ake/state_contract_scanner.py` is an **engine-agnostic** invariant verifier.
It contains **no engine-specific variable names**. Any engine (EBIS today, or a
different engine mounted on AKE tomorrow) registers a declarative contract; the
scanner runs the same audits against it.

## What it audits (generic rules)

| Audit | Rule |
|---|---|
| State ownership / writer | every `self.<state> = ...` must be inside a DECLARED owner func (+ file); any other writer → FAIL |
| Reader | if a reader expectation is declared, confirm the state is actually read |
| Canonical-vs-mirror | a mirror must equal its canonical source on a fresh engine |
| **Self-heal (mutation test)** | corrupt the mirror out-of-band, run ONE lifecycle step, verify it was restored |
| Fallback | (declared) invalid/missing value must not silently become a default |
| Propagation | value present through every declared input→kernel→output→buffer→downstream stage |
| Schema | missing / extra / renamed keys vs a declared expected set |
| Duplicate-authority | the same state written from >1 file → FAIL |

The **mutation test** is the part that caught the real EBIS Tier C regression:
a corrupted mirror (`_x_ethanol=0.71` while `ethanol_fraction=0.4`) that the
broken self-heal failed to repair.

## Ownership model

AKE owns the **scanner**. The engine's own owner (for EBIS, the **EBIS
orchestrator**) owns the **engine**. The scanner only inspects and reports; it
never controls the engine. `EngineContract.owner` is attribution only.

## Minimal EBIS contract (real, runnable)

```python
from ake.state_contract_scanner import (
    EngineContract, StateContract, SchemaContract, StateContractScanner, render_report)

contract = EngineContract(
    engine_id="EBIS_theta_kernel",
    owner="ebis_orchestrator",                     # EBIS orchestrator owns the engine
    root_dir="<path>/build/src",
    states=(
        StateContract(
            name="_x_ethanol",
            canonical_source="intake.ethanol_fraction",
            owner_funcs=("_sync_blend_mirror",),   # the SINGLE mirror owner
            owner_file="theta_domain_engine.py",
            seed_funcs=("__init__",),
            mirror_of="intake.ethanol_fraction",
            self_heal=True,
        ),
    ),
    schemas=(
        SchemaContract(label="FUEL_STATE",
            expected_keys=("blend_fraction","LHV","AFR_stoich","S_L_ref","latent_heat","octane_RON"),
            produce=lambda k: k.run_cycle(rpm=3000.0, cycle_num=0).get("FUEL_STATE", {}),
            allow_extra=False),
    ),
    build_engine=build_ebis_kernel,                # returns a fresh kernel
)

hooks = {"_x_ethanol": {
    "get_value":      lambda k: k.closed_cycle._x_ethanol,
    "get_canonical":  lambda k: k.intake.intake_cfg.ethanol_fraction,
    "set_value":      lambda k, v: setattr(k.closed_cycle, "_x_ethanol", v),
    "step_lifecycle": lambda k: (setattr(k,'spark_theta',335.0), k.run_cycle(rpm=3000.0, cycle_num=0)),
}}

print(render_report(StateContractScanner(contract, runtime_hooks=hooks).scan()))
```

To scan a **future engine** mounted on AKE: write that engine's `EngineContract`
+ hooks. The scanner core does not change.
