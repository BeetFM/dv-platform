# Capability Matrix

Snapshot date: 2026-07-21.

States have strict meanings:

- `supported`: implemented and accepted only with measured per-check evidence.
- `partial`: useful executable behavior exists, but the production profile is not complete.
- `scaffold`: collateral can be emitted, but it is not a qualified self-checking path.
- `unsupported`: no executable claim is made; strict workflows must report or block the gap.

## Generation and execution targets

| Target | Generation | Compile/elaboration | Per-check execution | Current state |
| --- | --- | --- | --- | --- |
| cocotb/Icarus | Self-checking generic/ready-valid checks plus typed bounded APB4 and AXI4-Lite drivers, monitors, register reference models, scoreboards, channel coverage, and timeouts | Python syntax is mandatory; both qualified protocol profiles compile and execute with Icarus/cocotb | JUnit scenario identities map to stable checks; zero or unmatched tests remain `unexecuted` | `supported`, including the qualified APB4 and bounded AXI4-Lite profiles |
| formal/SymbiYosys | Harnesses, property-specific assumptions, safety/induction/liveness properties, covers, CDC/reset/memory tiers, and typed APB4/AXI4-Lite protocol/register properties | Generated structure is checked; qualified profiles run SBY/Yosys/Z3 prove and cover tasks | Scenario traces and prove/cover tasks map to stable checks; assumption-witness covers and unmatched-result gates prevent vacuous closure | `supported` for the qualified bounded subsets |
| SystemVerilog | Conservative bench plus assertions/covers, including APB setup/access/wait stability and all five AXI4-Lite channel payload-stability properties; normalized reset-to-constant checks emit native result records | Verilator lint plus an Icarus compile/run wrapper for the qualified reset slice | Exact generated trace IDs are mandatory; missing, duplicate, unknown, partial, malformed, or failed native results do not close | `partial`; reset-to-constant native closure is qualified, while protocol native execution remains scaffolded |
| Verilog | Conservative stimulus plus normalized reset-to-constant checks | Verilator lint plus an Icarus compile/run wrapper for the qualified reset slice | Uses the same exact native result decoder as SystemVerilog | `partial` for the reset vertical slice; broader behavior remains `scaffold` |
| VHDL | VHDL-only entity/generic/architecture facts drive typed observable reset checks and conservative stimulus | The bounded source normalizer is qualified; GHDL 4.1.0 VHDL-2008 syntax/elaboration/run passes the generated reset slice | Generated result records use exact trace reconciliation; a zero process exit is insufficient | `supported` for bounded normalization and the observable reset vertical slice; broader generation/execution remains `partial` |
| UVM | Paired ready/valid package, sequence, sequencer, driver, monitor, scoreboard, environment, test, interface, and top; conservative fallback scaffold elsewhere | AMD Vivado Simulator 2025.2 compiles/elaborates the generated UVM 1.2 environment and runs 16 non-vacuous scoreboard transactions | Imported `vendor_verified` evidence requires exact `QUAL-SIM-001` and `QUAL-UVM-001` checks, named UVM completion, and zero UVM errors/fatals; exit code alone never closes | `partial`: the paired ready/valid generator is vendor-qualified; multi-agent, RAL, broader transactions, and project-level UVM run/coverage integration remain scaffolded or unsupported |

## Protocol and register depth

| Profile | Recognition | Scenario/generation depth | State |
| --- | --- | --- | --- |
| APB4 slave | Complete named PSEL/PENABLE/PREADY/PWRITE/PADDR/PWDATA/PSTRB/PRDATA/PSLVERR interface, directions, widths, and clock/reset facts are retained; ambiguity becomes an unsupported semantic | Typed scenarios are the sole source for generated cocotb and formal drivers/models/properties, trace symbols, covers, and timeouts. Full CLI qualification covers reset, setup/access, waits, stable controls/responses, completion, PSTRB, RW/RO/W1C, invalid addresses, and PSLVERR. Good RTL passes and nine generated-collateral mutants are killed on both backends. | `supported` for the bounded slave profile; native SystemVerilog execution and broader APB semantics remain scaffold/unsupported |
| AXI4-Lite slave | Complete AW/W/B/AR/R payload and handshake set with slave directions, byte-addressable matching data widths, WSTRB lanes, two-bit responses, matching address widths, and unambiguous clock/reset; incomplete or ambiguous signatures fail closed | Typed bounded scenarios generate independent AW/W timing, one-read/one-write outstanding handling, concurrent progress, monitor/reference scoreboard, bounded completion, five-channel coverage, response backpressure/stability, WSTRB, errors, invalid addresses, reset recovery, SVA, and formal properties. Full-CLI good-DUT and ten-mutant matrices pass on generated cocotb and formal collateral. | `supported` for the bounded slave profile; full AXI, bursts, IDs, and more than one outstanding transaction per direction are `unsupported` |
| AHB-Lite | Bounded single-beat signature | Executable probes and stability assertions exist | `partial` |
| Ready/valid | Named source/sink channel recognition | Backpressure and data-stability checks | `supported` within the qualified pilot constraints |
| Register model | Offset, fields, reset/access metadata, byte-enable and invalid-address policies from governed/normalized sources | A scenario is executable only when dependent semantics are known; the qualified APB4 and bounded AXI4-Lite register subsets are scoreboard- and mutation-tested. Unknown behavior stays open. | `supported` for the qualified APB4 and bounded AXI4-Lite subsets; `partial` elsewhere |
| CDC synchronizers | Ordered externally observable stages plus an explicit two-flop, pulse-stretch, toggle, or request/acknowledgement policy | Typed bounded scenarios generate independent cocotb transition/round-trip checks and formal stage assertions/non-vacuity covers. Good-DUT and four-mutant matrices pass on generated collateral. | `supported` for the governed single-bit profile; hidden, reconvergent, and general multi-bit schemes remain fail-closed |
| Async FIFO / Gray pointers | One normalized power-of-two memory, distinct synchronous read/write domains, explicit port/pointer mappings, and two ordered depth-sized Gray synchronizers | Generated cocotb queue scoreboards fill/drain, full/empty blocking, ordering, wraparound, unequal clocks, reset recovery, encoding, and one-bit transitions. Generated formal checks vector stages, pointer encoding/increment/hold, flag equations, reset, and non-vacuity. The good DUT and seven simulation/five formal mutants pass the declared matrix. | `supported` for the governed bounded profile; FWFT, multiple ports, non-power-of-two depth, standalone coherency, and reconvergence remain unsupported |
| Reset domains / RDC | Unique reset-to-control-domain ownership, exact clock/assertion style, observable ready output, bounded release policy, and an optional acyclic dependency through an ordered two-stage ready synchronizer | Generated cocotb checks asynchronous assertion, prerequisite hold, ordered release, recovery/removal offsets, bounded readiness, and resolvability. Generated formal checks async clear, guarded hold/release, every RDC stage, monotonic-release assumptions, and non-vacuity. Good-DUT and six-mutant matrices pass on both backends. | `supported` for the governed observable profile; physical timing, hidden stages, and architectural power sequencing remain unsupported |
| Bounded synchronous memory | One known byte-addressable synchronous memory and clock/reset domain, one read port, two write requesters with byte enables/grants, declared collision/zero-init/round-robin/parity policy, and exact observable mappings | Generated cocotb exhaustively scoreboards legal addresses, byte merging, collisions, both requesters, arbitration, reset initialization/recovery, and parity injection. Generated formal uses a bounded reference word plus grant/collision/parity properties and non-vacuity. Good-DUT and eight-mutant matrices pass on both backends. | `supported` for the governed bounded SRAM profile; SECDED, repair, init files, asynchronous/more-than-two-port storage, and macro timing remain unsupported |
| Bounded formal contract | Distinct trigger/response/invariant mappings in one normalized clock/reset domain, with pulse and causality policy plus a 1–64-cycle bound | Generated induction proves state/design invariants, response causality, and bounded liveness; assumption-witness/response/completion covers establish non-vacuity. Good DUT passes and four mutants are killed. | `supported` for the governed bounded-response profile; inferred assumptions and general/unbounded temporal synthesis remain unsupported |

## Platform services

| Capability | State | Boundary |
| --- | --- | --- |
| Plan schema v17 | `supported` | Each scenario records `executable`, `scaffold`, or `unsupported` per target with renderer identity and reason. Plans v1-v16 remain readable; v16 static mappings migrate to `unsupported` and require re-planning. |
| Immutable revisions v3 | `supported` | Revisions bind canonical-plan, RTL-manifest, and parent-snapshot hashes plus affected checks/scenarios/artifacts, selected template parameters, and rerun targets. Changed inputs require an explicit fork; legacy records remain readable. |
| Validation result v1 | `supported` | Simulation/formal summaries carry a common check-result envelope. No checks or unmatched tool output is `unexecuted`, regardless of exit code. |
| Parameter-sweep coverage v3 | `supported` | Coverage groups explicit elaboration points by design unit and canonical check semantics. Every semantic cross-point must close at every configured point; incomplete matrices fail coverage and CI status. |
| RTL facts v10 | `supported` | VHDL source evidence and normalization frontend identity round-trip independently from the narrower executable reset claim. |
| LiteLLM planning | `partial` | Explicit opt-in, bounded context/output, local cache, credential indirection, content-free audit, deterministic fallback, and proposal v1 compatibility exist. Planning now uses the common same-model repair gateway; proposal v2 adds evidence-linked scenario intent. |
| Reusable AI gateway | `supported` for bounded intent | Planning, feedback analysis, and opt-in scenario-template selection use one configured model, provider retries, at most two same-model schema repairs, content-free audit records, and deterministic fallback. Cross-provider routing and model-authored code are unsupported. |
| Feedback closure | `supported` | A typed dependency graph drives affected artifact replacement while preserving unrelated files. Generated provenance invalidates prior runs, and CI status requires fresh required-target runs followed by coverage rebuilt from those exact summaries. |
| Plugins | `supported` for built-in contracts | Versioned local document/PDF and governed OCR-sidecar loaders, local embeddings/vector storage, deterministic report manifests, regex redaction, UCIS, semantic/requirements importers, and enterprise simulator/formal/analyzer runners are connected and contract-tested. External plugin trust/signing is Stage 6 governance. |

## Production milestone

The narrow open-tool production milestone is accepted for bounded APB4 and AXI4-Lite slave profiles. Both use generated collateral through analyze, plan, generate, execute/prove, coverage, and strict status; both require exact non-vacuous per-check outcomes, kill their required mutant matrices, and reproduce generated bytes. This acceptance does not extend to full AXI, native simulator closure, UVM, or wider protocol/language targets.

Stage 4 verification depth is additionally accepted for the governed CDC,
async-FIFO, reset/RDC, SRAM, and bounded-response formal profiles, explicit
parameter-sweep cross-point aggregation, and bounded VHDL-only normalization.
Each capability retains the narrower boundary stated in its matrix row and
acceptance document. Stage 5 additionally accepts exact native result contracts,
tool-version enforcement, the GHDL 4.1.0 reset-result slice, vendor-qualified
Vivado Simulator 2025.2 UVM generation, and the built-in adapter matrix. The
bounded Stage 5 acceptance is complete; broader target depth retains the limits
stated in this matrix.
