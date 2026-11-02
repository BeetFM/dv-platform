# SKY130 block sign-off

The v2 workflow supports block-level ASIC characterization, including pinned external AES and matrix benchmarks. The local CPU preparation targets the electronic `cpu_top` block and excludes the JTAG wrapper, pads, package, and board interfaces. The upstream GitHub CPU currently has a different design; preparation records the local Git revision and hashes the actual working files, including uncommitted changes. The original checkout is left untouched.

OpenROAD implements the block, OpenRCX extracts parasitics, and embedded OpenSTA plus standalone OpenSTA independently measure timing. Yosys proves sequential equivalence. Magic, KLayout, and Netgen verify the final layout. The approved technology is `sky130A` / `sky130_fd_sc_hd`, pinned to open_pdks `0fe599b2afb6708d281543108caf8310912f54af`. [The packaged pin](../src/dv_platform/sky130-pin.json) records download and consumed-asset hashes. Each project also locks the actual executable hashes and versions.

## Provision and prepare

Use Ubuntu 24.04 with OpenROAD `26Q2-1164-g08f67ee5ec`, OpenSTA `3.1.0 2996e37a3a`, Yosys `0.33`, a C/C++ build toolchain, Tcl development files, Qt 5 development files, Ruby, and curl. The setup script downloads hash-checked PDK archives and builds the pinned Magic, Netgen, and KLayout sources under the ignored workspace directory. It downloads local Tcl/Tk/Ruby dependency packages without installing system packages or using sudo. Builds can take several minutes. Re-running setup verifies and reuses the local installation.

```bash
rtk proxy uv sync --all-groups --extra ai --frozen
rtk proxy uv run python -m scripts.qualification.sky130_setup
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.sky130 prepare-cpu --cpu-root ../cpu --output .dv-platform/sky130/cpu --memory-mb 8192
```

Output directories must be fresh. `prepare-cpu --resume` verifies the saved snapshot and successful synthesis receipts before reusing checkpoints. The memory limit and host memory reserve stop oversized jobs with an incomplete record; they never turn resource failure into a pass. This CPU has resettable and asynchronous memories, so preparation retains their semantics rather than silently replacing them with SRAM macros. Large standard-cell mappings may require a host with substantially more RAM.

Technology mapping runs coarse synthesis, memory lowering, gate expansion, and library mapping in separate
processes. `mapped-coarse.il`, `mapped-memory.il`, and `mapped-generic.il` are reusable checkpoints. Each mapping
receipt binds its exact input checkpoint, generated script, library, and Yosys executable;
changed inputs invalidate reuse and altered output checkpoints fail verification. Coarse
synthesis omits the optional SAT resource-sharing pass after that pass exhausted the native
8 GiB qualification budget. Functional equivalence remains a required sign-off check.
Gate expansion uses `techmap -extern` to share generated implementations as hierarchical
modules after both inline traversal modes exhausted 10 GiB. A second `techmap` pass finishes
logic inside those modules, and a strict guard rejects unresolved coarse cells.
Generated helper definitions are flattened and optimized before library mapping, preserving
the CPU source-module boundaries while removing unused logic hidden behind helper ports.
The mapping receipt also binds native cell-count and library-area statistics. Final mapping uses Yosys's
`check -mapped -assert`, which accepts defined parameterized modules while rejecting
remaining generic logic. Hierarchy does not relax functional or physical verification.
Source signal and instance names are retained for state correspondence in sequential induction.
The native counter regression verifies that the coarse synthesis recipe preserves useful
correspondence; full CPU equivalence remains mandatory.

The project declares its reference and mapped netlists, every source input, fixed implementation Tcl, SDC, three Liberty corners, three RC extraction rules, technology lock, requirements policy, and final GDS/netlist/DEF/ODB outputs. [Published schemas](../schemas/signoff/physical-project-v2.schema.json) describe the closed document formats.

## Characterize, then approve requirements

### External RTL benchmarks

Two external designs provide smaller starting points than the CPU:

| Design | Source and scope | Functional baseline |
| --- | --- | --- |
| AES | Pinned OpenROAD-flow-scripts / OpenCores AES encryption block, `aes_cipher_top` | Three known-answer vectors |
| Matrix | Pinned LogikBench `tpu`, full 8×8 array, signed INT8 operands and INT32 accumulators | Four matrix tiles, 256 scalar results |

The matrix fixture is an open systolic-array benchmark; it is not Google's TPU or a complete CNN accelerator. Both fixtures retain upstream RTL and provenance hashes. Their design documents are included in the generated RTL projects so optimization can use the existing code and interface contract.

```bash
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.aes --output .dv-platform/aes-new
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.tpu --output .dv-platform/matrix-new
```

Each command requires a fresh output directory and the provisioned PDK. It runs source simulation and technology mapping with a 4096 MiB synthesis address-space limit, then creates `rtl-project.json` and `physical/project.json`. This limit is a ceiling, not an allocation or a bound on every later concurrent verification process. Benchmark preparation uses 35% utilization and a 0.3 routing-capacity adjustment; these settings do not establish timing closure.

Preparation and simulation do not prove equivalence or sign-off. Run physical characterization and all release checks against the generated physical project. Keep the complete 8×8 configuration and every output/state proof obligation when comparing matrix implementations. Current local execution records are `.dv-platform/aes-execution-status.json` and `.dv-platform/tpu-execution-status.json`; hash-bound retained experiments are under `qualification/evidence/PHYS-01/`. A timed-out proof remains unproven, even when every simulation vector passes.

Configure the real Enterprise entitlement and its trust policy before running `dv-enterprise`. The independent engineering/manufacturing trust policy is a separate configuration field. Repository settings require production approval for `status --policy ci` and expect that policy at `/etc/dv-platform/signoff-trust.json`; an absent policy keeps approval false.

```bash
rtk proxy .dv-platform/sky130/tools/run uv run dv-enterprise --config dv-platform.toml --json signoff characterize --project .dv-platform/sky130/cpu/project/project.json
```

Initial constraints are explicitly provisional: a 100 ns clock, 0.1 ns uncertainty, zero input/output delay, 0.1 ns input transition, 0.010 output load, and 50% core utilization. Characterization reports measurements and every missing requirement. For a common primary clock it also derives a period proposal with 10% headroom and replays all nine views against that proposal in separate reports. This does not change the project constraints or establish an approved operating frequency.

An engineering owner must specify and sign the real contract: clock and boundary constraints, operating modes, setup/hold margins, maximum area and power, IR-drop and current-density limits, representative VCD workload and minimum annotation coverage, supply-source locations, and conductor thickness. Supply files use PDNSim's [four-column format](https://github.com/The-OpenROAD-Project/OpenROAD/blob/08f67ee5ecd14db5a42be8c610bbfd1ccf079299/src/psm/doc/Vsrc_description.md): x, y, bump-edge length in micrometres, then nominal voltage. All source and workload files must be declared project inputs. Analysis preserves their positions and derives the correct source voltage for each PVT corner.

The [requirements schema](../schemas/signoff/requirements-v1.schema.json) permits null limits only for drafts. Marking boundary assumptions complete does not supply missing budgets. Engineering signatures bind the exact technology lock and constraint hashes. Add the signing certificate to the declared inputs, then freeze a new project and execute a new run. Use `canonical_signed_document` from `dv_platform.signing` with an externally managed P-256 key; no production signing keys are generated by the workflow.

## Iterative timing closure and native checks

```bash
rtk proxy .dv-platform/sky130/tools/run uv run --env-file .env dv-enterprise --config dv-platform.toml --allow-network --json physical-optimize --project /path/to/frozen/project.json --ai --max-iterations 3
rtk proxy .dv-platform/sky130/tools/run uv run dv-enterprise --config dv-platform.toml --json signoff check --project /path/to/frozen/project.json --run /path/to/run.json
```

For a larger design, `signoff check --equivalence-memory-mb N` sets the address-space budget for
both sequential-equivalence proofs. The default is 4096 MiB; valid budgets are 256–262144 MiB.
Choose a budget the host can sustain. Native receipts retain the exact resource limit, and
resource failures remain failed or unknown analyses. This execution setting does not change
timing constraints, acceptance limits, or approval requirements.
Equivalence first attempts complete state-transition comparison for uninitialized
registers on one identical rising-edge primary clock. Native Yosys normalization
uses standard synthesis don't-care semantics, followed by a checked bijection of
every retained state bit. ABC and SAT prove every primary output and every register
D cone for all shared input/state assignments. Clock connections and polarity are
checked before exposing state; no unmatched retained register is omitted.

For at least 1,024 output and next-state comparisons, the checker lowers the cut
models to scalar gates and audits every connected bit for defined Boolean values,
single drivers and acyclic driven logic. Eligible models use native ASCII AIGs
with checked port symbols. An exact reachable XOR miter is retained for every
comparison; only byte-identical miters within that run share a proof. Every unique
miter must pass pinned ABC normalization and native SAT. The complete comparison
map, scripts, native receipts and nested proof artifacts are hash-bound. Models
with unknown values retain the existing undef-aware aggregate proof.

The cone backend requires at least 1,536 MiB of inherited address-space budget.
It uses at most six workers, with 256 MiB limits on each Yosys process and its
inheriting ABC child. Worker count reserves 1 GiB of budget for coordination.
These are process limits, not an aggregate RAM reservation or host memory limit.
All workers share the proof deadline; a failed proof cancels pending work and
waits for already started bounded native calls before returning failure.

Unsupported state correspondence, initialized registers, or other clock structures
retain the clock-event method: source and candidate models compile in separate
native processes, retaining RTLIL checkpoints before the final proof. Each model
is structurally validated in a fresh process so compiler allocations do not consume
the checker's memory budget. A failed transition proof never invokes the fallback.
Preparation, validation, fallback, and proof share one timeout and the same memory
cap. Input or prepared-model changes invalidate a proof, and every obligation must
be proven. Implementation-only hierarchy hints are removed from derived models.

Each iteration measures TT 25°C/1.8 V, SS 100°C/1.6 V, and FF −40°C/1.95 V against minimum, nominal, and maximum RC extraction. Both timing engines must agree on metrics, clocks, and resolved exceptions. The AI receives measured arrival/required-arrival gaps, evidence IDs, immutable acceptance rules, and previous hypotheses and results. Repeated recipes and regressions in any view are rejected. Bounded prompt factoring preserves all scenario gates and measurements while reducing repeated context. Receipts distinguish actual model calls from test doubles or unavailable providers.

Release checks include clock-checked source-to-mapped and mapped-to-final sequential equivalence; full-layout Magic and KLayout DRC; transistor LVS including fillers; antenna; density; power/body-pin connectivity; static grid analysis for both rails and every view; conservative conductor/via current-density bounds; and VCD annotation coverage. Static grid analysis uses the pinned technology resistance model and the declared workload. Foundry acceptance of that model and of the current-density limits remains part of manufacturing review.

A missing tool, timed-out process, resource failure, unsupported density window, missing workload, or absent budget remains failed or unknown. The pinned whole-chip density helper requires a layout at least 700 × 700 µm; it cannot approve the tiny native fixture. The GDS layer map and pin labels are explicit. Signal timing exports omit supply ports while the physical database, GDS, and CDL retain them.

## Review and approval

The default characterization flow uses standard clock routing rules and requires an explicit
engineering-approved density/fill strategy for final closure. Automatic floating metal fill
would violate the enabled floating-metal checks. Density analysis remains mandatory and an
unsupported or failing result blocks readiness. GDS export preserves declared DEF fill shapes;
it never drops them to hide findings. Routed vias are flattened geometrically during export
so extraction resolves their physical connectivity before assigning unique node names.

The release bundle copies and hashes project inputs, selected implementation, raw reports, native receipts, workflow sources, and AI receipts. Changes after measurement invalidate the release. Engineering readiness, engineering approval, manufacturing acceptance, and `signoff_approved` are separate states.

The external [trust policy](../schemas/signoff/trust-v1.schema.json) lists authorized certificate fingerprints for the two roles and revocations. Engineering and manufacturing must use distinct signing keys. An [approval](../schemas/signoff/approval-v1.schema.json) binds the exact release, technology, policy, reviewer, and validity interval. Engineering may accept counted findings from a completed DRC, antenna, or density report using a signed waiver tied to its exact digest and count. Missing analyses, timing failures, equivalence, and power failures cannot be waived. Manufacturing acceptance also binds the exact engineering approval and waiver decision.

```bash
rtk proxy uv run dv-enterprise --config dv-platform.toml --json signoff import-approval --release /path/to/release.json --approval /path/to/engineering.json
rtk proxy uv run dv-enterprise --config dv-platform.toml --json signoff import-approval --release /path/to/release.json --approval /path/to/manufacturing.json
rtk proxy uv run dv-enterprise --config dv-platform.toml --json signoff status --release /path/to/release.json --policy ci
rtk proxy uv run dv-platform --json status --policy ci
```

Use `--signoff-trust-policy` on a `signoff` command to override the sign-off trust policy. The bootstrap `--trust-policy` option belongs to Enterprise licensing. Status rechecks hashes, signatures, expiry, revocations, and waiver validity each time. Timing closure alone never grants production approval.

## Native tool smoke and full qualification

```bash
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.sky130 prepare-smoke --output .dv-platform/sky130/fixture
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.sky130 qualify --tool-smoke --project .dv-platform/sky130/fixture/project/project.json --output .dv-platform/sky130/check
rtk proxy .dv-platform/sky130/tools/run uv run --env-file .env python -m scripts.qualification.sky130 qualify --tool-smoke --project .dv-platform/sky130/fixture/project/project.json --output .dv-platform/sky130/live --live-ai
```

The tiny accumulator is an installation/protocol smoke fixture. `--tool-smoke`
reports timing and density without requiring closure and labels the result
`tool_smoke`; it still requires complete equivalence and native layout check execution.
It is never full native qualification or production signoff. For a real prepared
benchmark, omit `--tool-smoke`: all nine native gates, including timing and density,
must pass. Both modes retain raw check statuses and require independent owner approval.

The accumulator fixture supplies deterministic stimulus, fixture supply locations, and explicitly synthetic conductor dimensions to exercise native power protocols. They are not CPU requirements. Tool smoke and full qualification both require real native checker execution and memory mutation controls; live mode also requires an actual model call. Test entitlements and test signing authorities are never production authority. The manual [native CI workflow](../.github/workflows/sky130-native.yml) runs on a provisioned `sky130` self-hosted runner behind the protected `sky130-native` environment and retains evidence. Configure that environment and its API_KEY before enabling live calls; pull requests do not run jobs with that credential.
