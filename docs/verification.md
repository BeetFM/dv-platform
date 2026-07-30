# Verification and Qualification

Document type: consolidated current and historical documentation.

Purpose: Capability states, verification contracts, qualification procedures, stage evidence, and historical acceptance.

Status: current index and preserved source material. Where a historical
section conflicts with current machine evidence, use the authority order in
[Agent and Documentation Governance](agents.md).

Last consolidated: 2026-07-30.

## Current local qualification overlay

The machine authority remains the conservative capability ledger; this overlay
does not promote broad profile/target cells lacking retained real-tool,
good-DUT, mutation, coverage, and strict-status evidence.

SEM-01, FORM-01, CDC-01, and MEM-01 are closed by retained real-tool records:
Slang 11.0 / Verilator 5.020 expression semantics, typed SBY assumptions,
two-branch reconvergent CDC on cocotb and formal, and digest-bound initialized
SRAM on cocotb and formal. Every good workspace passes exact
`status --policy ci`; disagreement, unreachable/invalid intent, changed
initialization, and rule mutants remain non-closing. Exact evidence and any
remaining external closure class are recorded in
`qualification/policies/local-task-audit-v1.json`.

### Semantic, formal, CDC, and memory evidence

| Ticket | Qualified boundary | Retained evidence |
| --- | --- | --- |
| `SEM-01` | Slang-authoritative SystemVerilog expression width, signedness, determination, context, cast, truncation, unknown-bit, source, frontend, and specialization facts cross-checked with Verilator | [`systemverilog-expression-semantics-v3.json`](../qualification/evidence/SEM-01/systemverilog-expression-semantics-v3.json) |
| `FORM-01` | Explicitly mapped and bounded `stability` and `range` assumptions on SBY, including witness/response/completion covers and counterexample mutation | [`formal-evidence-v1.json`](../qualification/evidence/FORM-01/formal-evidence-v1.json) |
| `CDC-01` | Governed two-branch reconvergence with structural validation and bounded coherent sampling | [`cocotb-evidence-v1.json`](../qualification/evidence/CDC-01/cocotb-evidence-v1.json), [`formal-evidence-v1.json`](../qualification/evidence/CDC-01/formal-evidence-v1.json) |
| `MEM-01` | Strict digest-bound `bounded_sram_init_hex` initialization through facts, plan, generation, execution, coverage, status, and cache identity | [`cocotb-evidence-v1.json`](../qualification/evidence/MEM-01/cocotb-evidence-v1.json), [`formal-evidence-v1.json`](../qualification/evidence/MEM-01/formal-evidence-v1.json) |

These records close only the bounded profiles above. General IEEE semantic
evaluation in Python, inferred or non-SBY assumptions, unobservable or
unbounded reconvergence, arbitrary memory formats, asynchronous memories, and
macro/physical timing remain outside the supported boundary.

Coverage point identity is SHA-256-derived from format version, source
locator, hierarchy, specialization, point kind, and normalized name. The
Verilator importer preserves counts, exclusions, provenance, overflow state,
and deterministic merges. Typed bin/cross reconciliation fails closed for
missing, stale, orphaned, excluded-only, intentionally missed,
zero-denominator, or uncovered points.

## Source coverage

Every source below is included in full under a stable migration anchor:

- [`docs/qualification/capability-matrix.md`](#source-docsqualificationcapability-matrixmd)
- [`docs/qualification/verification-production-readiness.md`](#source-docsqualificationverification-production-readinessmd)
- [`docs/qualification/testing-and-qualification.md`](#source-docsqualificationtesting-and-qualificationmd)
- [`docs/qualification/enterprise-qualification.md`](#source-docsqualificationenterprise-qualificationmd)
- [`docs/qualification/ga-contract.md`](#source-docsqualificationga-contractmd)
- [`docs/qualification/ga-stages.md`](#source-docsqualificationga-stagesmd)
- [`qualification/README.md`](#source-qualificationreadmemd)
- [`qualification/profiles/ahb-lite-single-beat.md`](#source-qualificationprofilesahb-lite-single-beatmd)
- [`qualification/stages/stage6-foundation.md`](#source-qualificationstagesstage6-foundationmd)
- [`qualification/stages/stage7-on-chip-protocols.md`](#source-qualificationstagesstage7-on-chip-protocolsmd)
- [`qualification/stages/stage8-board-peripherals.md`](#source-qualificationstagesstage8-board-peripheralsmd)
- [`qualification/stages/stage9-vhdl-uvm.md`](#source-qualificationstagesstage9-vhdl-uvmmd)
- [`qualification/stages/stage10-semantic-designs.md`](#source-qualificationstagesstage10-semantic-designsmd)
- [`qualification/stages/stage10-scale-platform.md`](#source-qualificationstagesstage10-scale-platformmd)
- [`docs/acceptance/README.md`](#source-docsacceptancereadmemd)
- [`docs/acceptance/pilot-acceptance.md`](#source-docsacceptancepilot-acceptancemd)
- [`docs/acceptance/p1-acceptance.md`](#source-docsacceptancep1-acceptancemd)
- [`docs/acceptance/apb4-acceptance.md`](#source-docsacceptanceapb4-acceptancemd)
- [`docs/acceptance/axi4-lite-acceptance.md`](#source-docsacceptanceaxi4-lite-acceptancemd)
- [`docs/acceptance/feedback-revision-acceptance.md`](#source-docsacceptancefeedback-revision-acceptancemd)
- [`docs/acceptance/cdc-synchronizer-acceptance.md`](#source-docsacceptancecdc-synchronizer-acceptancemd)
- [`docs/acceptance/async-fifo-acceptance.md`](#source-docsacceptanceasync-fifo-acceptancemd)
- [`docs/acceptance/reset-rdc-acceptance.md`](#source-docsacceptancereset-rdc-acceptancemd)
- [`docs/acceptance/memory-depth-acceptance.md`](#source-docsacceptancememory-depth-acceptancemd)
- [`docs/acceptance/formal-depth-acceptance.md`](#source-docsacceptanceformal-depth-acceptancemd)
- [`docs/acceptance/parameter-sweep-acceptance.md`](#source-docsacceptanceparameter-sweep-acceptancemd)
- [`docs/acceptance/vhdl-normalization-acceptance.md`](#source-docsacceptancevhdl-normalization-acceptancemd)
- [`docs/acceptance/stage4-acceptance.md`](#source-docsacceptancestage4-acceptancemd)
- [`docs/acceptance/stage5-acceptance.md`](#source-docsacceptancestage5-acceptancemd)

<a id="source-docsqualificationcapability-matrixmd"></a>
## Capability Matrix

Consolidated from `docs/qualification/capability-matrix.md`.

Snapshot date: 2026-07-22.

States have strict meanings:

- `supported`: implemented and accepted only with measured per-check evidence.
- `partial`: useful executable behavior exists, but the production profile is not complete.
- `scaffold`: collateral can be emitted, but it is not a qualified self-checking path.
- `unsupported`: no executable claim is made; strict workflows must report or block the gap.

<a id="source-docsqualificationcapability-matrixmd--generation-and-execution-targets"></a>
### Generation and execution targets

| Target | Generation | Compile/elaboration | Per-check execution | Current state |
| --- | --- | --- | --- | --- |
| cocotb/Icarus | Self-checking generic/ready-valid checks plus typed bounded APB4 and AXI4-Lite drivers, monitors, register reference models, scoreboards, channel coverage, and timeouts | Python syntax is mandatory; both qualified protocol profiles compile and execute with Icarus/cocotb | JUnit scenario identities map to stable checks; zero or unmatched tests remain `unexecuted` | `supported`, including the qualified APB4 and bounded AXI4-Lite profiles |
| formal/SymbiYosys | Harnesses, property-specific assumptions, safety/induction/liveness properties, covers, CDC/reset/memory tiers, and typed APB4/AXI4-Lite protocol/register properties | Generated structure is checked; qualified profiles run SBY/Yosys/Z3 prove and cover tasks | Scenario traces and prove/cover tasks map to stable checks; assumption-witness covers and unmatched-result gates prevent vacuous closure | `supported` for the qualified bounded subsets |
| SystemVerilog | Self-checking native reset, APB4, and AXI4-Lite benches with typed transactions, scoreboards, bounded waits, response stability, errors, strobes, and outstanding-limit checks | Verilator lint plus an Icarus compile/run wrapper for the qualified slices | Exact generated trace IDs are mandatory; missing, duplicate, unknown, partial, malformed, or failed native results do not close | `supported` for reset and the bounded APB4/AXI4-Lite profiles; broader behavior remains `partial` |
| Verilog | Portable Verilog-2001 self-checking reset, APB4, and AXI4-Lite benches using the same typed intent and result contract | Verilator lint plus an Icarus compile/run wrapper; SystemVerilog DUT sources select the required compile standard without changing the generated Verilog bench dialect | Uses the same exact native result decoder as SystemVerilog | `supported` for reset and the bounded APB4/AXI4-Lite profiles; broader behavior remains `partial` |
| VHDL | GHDL-authoritative entity/generic/package/type/architecture facts drive typed reset, ready/valid, and declared production-profile checks | GHDL 4.1.0 VHDL-2008 analysis/elaboration is mandatory; packages, records, subtypes, arrays, generate scopes, explicit architecture selection, and profile transactions are retained | Generated result records use exact trace reconciliation; AXI4-Stream good RTL and four VHDL mutants close | `supported` for declared VHDL-capable profiles; ambiguous architecture or mixed-language binding fails closed |
| UVM | Multi-agent protocol packages, sequences, drivers, monitors, scoreboards, virtual sequencing, cross-protocol scoreboards, and normalized-register RAL | Open generation is deterministic; Vivado bridge/project execution remains the available local vendor path | Licensed imports require exact checks, zero UVM errors/fatals, and non-vacuity for `vendor_verified`; CA-backed detached evidence from an approved non-project identity is required for `independently_signed` | `partial`: broad profiles remain `contract_verified`/`scaffold`; the earlier paired ready/valid Vivado evidence remains the only vendor-qualified profile |

<a id="source-docsqualificationcapability-matrixmd--protocol-and-register-depth"></a>
### Protocol and register depth

The current broad-protocol authority is
`qualification/policies/capability-ledger-v1.json`. Broad profiles are
`partial`: every role/target cell is explicit, but no cell is promoted to
`supported` without digest-bound retained evidence and a last-passing source
identity. UVM remains `scaffold`. The bounded APB4, AXI4-Lite, AHB-Lite, and
ready/valid rows below are separate qualified profiles.

<!-- generated: capability-ledger-v1 -->
| Profile | Version | Role | cocotb | formal | systemverilog | verilog | vhdl | uvm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ahb-1.0 | 1.0 | manager | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| ahb-1.0 | 1.0 | subordinate | supported | supported | supported | supported | supported | scaffold |
| avalon-mm-1.0 | 1.0 | agent | supported | supported | supported | supported | supported | scaffold |
| avalon-mm-1.0 | 1.0 | host | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| avalon-st-1.0 | 1.0 | sink | supported | supported | supported | supported | supported | scaffold |
| avalon-st-1.0 | 1.0 | source | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| axi4-1.0 | 1.0 | manager | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| axi4-1.0 | 1.0 | subordinate | supported | supported | supported | supported | supported | scaffold |
| axi4-stream-1.0 | 1.0 | sink | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| axi4-stream-1.0 | 1.0 | source | supported | supported | supported | supported | supported | scaffold |
| tilelink-ul-uh-1.0 | 1.0 | manager | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| tilelink-ul-uh-1.0 | 1.0 | subordinate | supported | supported | supported | supported | supported | scaffold |
| wishbone-b4-1.0 | 1.0 | device | supported | supported | supported | supported | supported | scaffold |
| wishbone-b4-1.0 | 1.0 | host | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
<!-- /generated: capability-ledger-v1 -->

All 35 declared open-tool broad-profile cells are promoted by retained,
digest-bound evidence. Cocotb, formal, SystemVerilog, Verilog, and VHDL close
the good DUT and their applicable rule-specific mutants for AXI4 subordinate,
AXI4-Stream source, Wishbone device, Avalon-MM agent, Avalon-ST sink, AHB
subordinate, and TileLink subordinate. UVM remains `scaffold`, and every
inverse role remains `unsupported`.

Generated-HDL capability parity is a repository invariant: SystemVerilog,
Verilog, and VHDL must declare the same state, profile version, role, and
execution bounds for every broad-profile cell. A supported target must retain
its own real-tool evidence; support cannot be inherited from another language.
The 35 evidence records and both local raw-artifact trees are summarized by the
deterministic `PROTO-01/artifact-retention-manifest-v1.json`. Raw workspaces are
retained locally but excluded from source distributions and wheels.

| Profile | Recognition | Scenario/generation depth | State |
| --- | --- | --- | --- |
| APB4 slave | Complete named PSEL/PENABLE/PREADY/PWRITE/PADDR/PWDATA/PSTRB/PRDATA/PSLVERR interface, directions, widths, and clock/reset facts are retained; ambiguity becomes an unsupported semantic | Typed scenarios drive cocotb, formal, native SystemVerilog, and native Verilog. Full CLI qualification covers reset, setup/access, waits, stable controls/responses, completion, PSTRB, RW/RO/W1C, invalid addresses, and PSLVERR. Good RTL passes and nine mutants are killed on every claimed backend. | `supported` for the bounded slave profile; broader APB semantics remain unsupported |
| AXI4-Lite slave | Complete AW/W/B/AR/R payload and handshake set with slave directions, byte-addressable matching data widths, WSTRB lanes, two-bit responses, matching address widths, and unambiguous clock/reset; incomplete or ambiguous signatures fail closed | Typed bounded scenarios generate independent AW/W timing, one-read/one-write outstanding handling, monitor/reference scoreboards, bounded completion, response backpressure/stability, WSTRB, errors, invalid addresses, reset recovery, and formal properties. Full-CLI good-DUT and ten-mutant matrices pass on cocotb, formal, native SystemVerilog, and native Verilog. | `supported` for the bounded slave profile; full AXI, bursts, IDs, and more than one outstanding transaction per direction are `unsupported` |
| Broad protocol profiles v1 | Complete canonical or explicitly aliased signatures bind fail-closed to versioned AXI4, packet-complete AXI4-Stream, Wishbone B4, Avalon-MM, Avalon-ST, burst-capable AHB, and non-coherent TileLink UL/UH transaction contracts. Endpoint roles, bounds, ordering, and traces are retained. | Retained digest-bound good-DUT, mutant, exact-coverage, real-tool, and strict-policy evidence closes all 35 declared cocotb, formal, SystemVerilog, Verilog, and VHDL cells. UVM is generation scaffold only. | `supported` for the seven declared open-tool endpoint roles; inverse roles are `unsupported` and UVM remains `scaffold` |
| AHB-Lite | Qualified 32-bit, single-master, single-beat slave signature with `HREADYOUT`, known reset, and governed RW/RO/W1C register behavior | Typed driver/monitor/reference-model scenarios and bounded formal properties close exact checks, wait states, invalid-address errors, reset recovery, and a six-mutant matrix | `supported` for the [bounded single-beat profile](#source-qualificationprofilesahb-lite-single-beatmd); bursts, split/retry, protection semantics, and multi-layer interconnect are `unsupported` |
| Ready/valid | One named sink/source pair with data, common clock, and known reset | Generated cocotb checks acceptance, end-to-end data, backpressure stability, and recovery; a four-mutant matrix closes the bounded stream profile. Formal source-side stability assertions remain a narrower safety claim. | `supported` for the bounded paired-stream profile; AXI-Stream sidebands and multi-channel routing are unsupported |
| UART controller | Complete governed TX/RX control, data, status, error, clock, and reset mappings with 8-bit data and bounded bit timing | Generated cocotb models TX and RX frames, baud timing, parity modes, one/two stop bits, break, framing/parity errors, overflow, and recovery. Formal properties cover idle, busy/completion, error causality, and non-vacuity. The good DUT and ten mutants close. | `supported` for the bounded 8-bit controller profile; fractional baud generation, arbitrary word sizes, flow control, and multi-drop extensions are unsupported |
| SPI master | Complete governed master controls and SCLK/MOSI/MISO/chip-select mappings with 8-bit words and a bounded divider | Generated cocotb exercises CPOL/CPHA modes 0–3, MSB/LSB-first transfers, select framing, clock edges, receive data, completion, and timeout. Formal safety/non-vacuity passes; the good DUT and nine mutants close. | `supported` for the bounded single-lane master profile; multi-lane, multi-master, streaming, and device-specific framing are unsupported |
| I2C master | Complete governed controller and separate open-drain drive-low/sampled-bus mappings, 7-bit addresses, bounded divider/stretch/transfer timing | A wired-AND BFM checks bus busy, START/STOP/repeated START, address and data serialization, combined reads, ACK/NACK, clock stretching, arbitration loss, and recovery. Formal safety/non-vacuity passes; the good DUT and eight mutants close. | `supported` for the bounded 7-bit master profile; 10-bit addressing, high-speed modes, SMBus, multi-controller fairness, and analog electrical sign-off are unsupported |
| GPIO/timer/interrupt subsystem | Exact 4-bit GPIO and interrupt mappings plus governed 8-bit timer/watchdog/PWM controls in one known clock/reset domain | Generated cocotb checks GPIO direction, masked write/set/clear, edge/level IRQs, prescaled periodic timer, watchdog feed/IRQ/reset, PWM duty/polarity, and fixed-priority interrupt mask/clear/ack. Formal safety/non-vacuity passes; the good DUT and ten mutants close. | `supported` for the bounded subsystem profile; arbitrary widths, capture/compare/DMA, cascaded controllers, and programmable arbitration are unsupported |
| Register model | Offset, fields, reset/access metadata, byte-enable and invalid-address policies from governed/normalized sources | A scenario is executable only when dependent semantics are known; the qualified APB4 and bounded AXI4-Lite register subsets are scoreboard- and mutation-tested. Unknown behavior stays open. | `supported` for the qualified APB4 and bounded AXI4-Lite subsets; `partial` elsewhere |
| CDC synchronizers | Ordered externally observable stages plus an explicit two-flop, pulse-stretch, toggle, request/acknowledgement, coherent multi-bit handshake, bounded-rate Gray-counter, or governed two-branch reconvergent policy | Typed bounded scenarios generate independent cocotb transition/round-trip/coherency checks and formal stage, stability, sampled-payload, Gray-transition, coherent-arrival, and non-vacuity properties. Good-DUT and seven-mutant matrices pass on generated cocotb/formal collateral. | `supported` for governed observable linear and two-branch reconvergent profiles; hidden, ambiguous, or unbounded schemes remain fail-closed |
| Async FIFO / Gray pointers | One normalized power-of-two memory, distinct write/read domains, explicit port/pointer mappings, optional first-word-fall-through read semantics, and two ordered depth-sized Gray synchronizers | Generated cocotb queue scoreboards fill/drain, sample FWFT data before dequeue, check full/empty blocking, ordering, wraparound, unequal clocks, reset recovery, encoding, and one-bit transitions. Generated formal checks vector stages, pointer encoding/increment/hold, flag equations, FWFT stability, reset, and non-vacuity. The good DUT and eight simulation/five formal mutants pass the declared matrix. | `supported` for the governed bounded registered/FWFT profile; multiple ports, non-power-of-two depth, standalone coherency, and reconvergence remain unsupported |
| Reset domains / RDC | Unique reset-to-control-domain ownership, exact clock/assertion style, observable ready output, bounded release policy, and an optional acyclic dependency through an ordered two-stage ready synchronizer | Generated cocotb checks asynchronous assertion, prerequisite hold, ordered release, recovery/removal offsets, bounded readiness, and resolvability. Generated formal checks async clear, guarded hold/release, every RDC stage, monotonic-release assumptions, and non-vacuity. Good-DUT and six-mutant matrices pass on both backends. | `supported` for the governed observable profile; physical timing, hidden stages, and architectural power sequencing remain unsupported |
| Bounded synchronous memory | One known byte-addressable synchronous memory and clock/reset domain, one read port, two write requesters with byte enables/grants, declared collision/round-robin policy, parity or SECDED mappings, and either zero initialization or a strict repository-relative hexadecimal image | Generated cocotb and formal cover byte merges, collisions, arbitration, reset/init, parity, single-error correction, double-error detection, and scrub completion. The image path, SHA-256, shape, identity, and explicit default policy bind facts through execution and cache identity; changed images fail execution. | `supported` for zero-init and `bounded_sram_init_hex` parity and SECDED/scrub profiles; asynchronous/more-than-two-port storage, retention, and macro timing remain unsupported |
| Bounded formal contract | Distinct trigger/response/invariant mappings in one normalized clock/reset domain, with pulse and causality policy plus a 1–64-cycle bound; typed stability/range assumptions require explicit signal/clock/reset/polarity/bound and SBY | Generated induction proves state/design invariants, response causality, and bounded liveness; typed assumption witness/response/completion covers establish reachability and non-vacuity. Real SBY proof/cover passes and the counterexample mutant is retained. | `supported` for bounded response and governed typed SBY stability/range assumptions; inferred assumptions, unsupported engines, and general/unbounded temporal synthesis remain unsupported |

<a id="source-docsqualificationcapability-matrixmd--platform-services"></a>
### Platform services

| Capability | State | Boundary |
| --- | --- | --- |
| Plan schema v19 | `supported` | Versioned protocol transaction contracts retain instance/role, burst and outstanding bounds, scoreboard keys, coverage bins, formal properties, and result traces. Plans v1-v18 remain readable; v16 static mappings migrate to `unsupported` and require re-planning. |
| Immutable revisions v3 | `supported` | Revisions bind canonical-plan, RTL-manifest, and parent-snapshot hashes plus affected checks/scenarios/artifacts, selected template parameters, and rerun targets. Changed inputs require an explicit fork; legacy records remain readable. |
| Validation result v1 | `supported` | Simulation/formal summaries carry a common check-result envelope. No checks or unmatched tool output is `unexecuted`, regardless of exit code. |
| Parameter-sweep coverage v3 | `supported` | Coverage groups explicit elaboration points by design unit and canonical check semantics. Every semantic cross-point must close at every configured point; incomplete matrices fail coverage and CI status. |
| RTL facts v12 | `supported` | Protocol transaction contracts and channel payload/completion rules round-trip while VHDL source evidence and normalization frontend identity remain independently preserved. |
| LiteLLM planning | `partial` | Explicit opt-in, bounded context/output, local cache, credential indirection, content-free audit, deterministic fallback, and proposal v1 compatibility exist. Planning now uses the common same-model repair gateway; proposal v2 adds evidence-linked scenario intent. |
| Reusable AI gateway | `supported` for bounded intent | Planning, feedback analysis, and opt-in scenario-template selection use one configured model, provider retries, at most two same-model schema repairs, content-free audit records, and deterministic fallback. Cross-provider routing and model-authored code are unsupported. |
| Feedback closure | `supported` | A typed dependency graph drives affected artifact replacement while preserving unrelated files. Generated provenance invalidates prior runs, and CI status requires fresh required-target runs followed by coverage rebuilt from those exact summaries. |
| Plugins | `supported` for built-in and governed third-party contracts | Built-in document/OCR, embedding/vector, reporting, coverage, semantic/requirements, and enterprise runners are connected. Third-party code requires publisher/package digest plus Sigstore identity/issuer or enterprise-PKI verification and executes through the sandbox-aware API contract. |

<a id="source-docsqualificationcapability-matrixmd--production-milestone"></a>
### Production milestone

Stage 9 is accepted for the bounded VHDL reset/paired-stream profile and the
paired ready/valid UVM project profile. GHDL good-DUT/mutation execution and
Vivado project-run result normalization close exact checks, coverage, and strict
status. Later work adds GHDL-authoritative packages/types/generates plus
multi-agent UVM/RAL generation, while ambiguous mixed-language binding and
signed broad-profile vendor execution remain outside this milestone. See
[Stage 9 qualification](#source-qualificationstagesstage9-vhdl-uvmmd).

The Stage 8 board-peripheral milestone is accepted for the bounded UART, SPI,
I2C, and GPIO/timer/watchdog/PWM/interrupt-controller profiles. Their generated
cocotb and formal collateral passes good-DUT execution and kills all 37 declared
mutants; the strict CLI path closes coverage and status without silently
inferring incomplete mappings. The exact scope and exclusions are recorded in
[Stage 8 qualification](#source-qualificationstagesstage8-board-peripheralsmd).

Stage 7 is accepted for bounded APB4, AXI4-Lite, AHB-Lite, and paired
ready/valid profiles. They use generated
collateral through analyze, plan, generate, execute/prove, coverage, and strict
status; require exact per-check outcomes; kill their declared mutant matrices;
and reproduce generated bytes. This acceptance does not extend to full AXI,
AXI-Stream sidebands, or wider protocol/language targets.

Stage 4 verification depth is additionally accepted for the governed CDC,
async-FIFO, reset/RDC, SRAM, and bounded-response formal profiles, explicit
parameter-sweep cross-point aggregation, and bounded VHDL-only normalization.
Each capability retains the narrower boundary stated in its matrix row and
acceptance document. Stage 5 additionally accepts exact native result contracts,
tool-version enforcement, the GHDL 4.1.0 reset-result slice, vendor-qualified
Vivado Simulator 2025.2 UVM generation, and the built-in adapter matrix. The
bounded Stage 5 acceptance is complete; broader target depth retains the limits
stated in this matrix.

<a id="source-docsqualificationverification-production-readinessmd"></a>
## Verification production readiness

Consolidated from `docs/qualification/verification-production-readiness.md`.

This document defines the production boundary for verification depth and coverage
closure. A capability is complete only when the platform either produces governed
evidence for it or rejects the unsupported case as an explicit gap.

<a id="source-docsqualificationverification-production-readinessmd--complete-platform-capabilities"></a>
### Complete platform capabilities

| Capability | Production behavior |
| --- | --- |
| Simulation/formal outcomes | Persisted run summaries emit stable, per-check coverage and formal points. Failed runs produce failed points, never hit-based success. |
| Coverage merge | Native JSON, LCOV, Cobertura XML, persisted run summaries, and configured importer results enter one normalized point model. |
| UCIS | The built-in `ucis_xml` entry point imports functional coverpoint/cross bins, goals, ignore bins, illegal bins, and requirement/behavior/check identity extensions. |
| Closure governance | Waivers require approver and expiry; unreachable dispositions require evidence; expired, orphan, conflicting, and stale dispositions fail closed. |
| Traceability | Unidentified points, unknown check IDs, unmeasured executable checks, and mappings to deleted checks fail closure. |
| Plan feedback | Imported point state and point IDs are republished into canonical plans; checks introduced by the latest immutable revision are also reconciled without mutating that snapshot. |
| Reporting | JSON, YAML, Markdown, and SARIF reports expose raw coverage, closure coverage, actionable gaps, dispositions, and plan reconciliation. |
| Release policy | `dv-platform status --policy ci` rejects missing schemas/plans/runs/tools, failed execution, open closure, incomplete traceability, invalid generated artifacts, and actionable revisions lacking fresh generate/run/coverage evidence. |
| Reset depth | Reset domains, polarity, asynchronous assertion, and clocked release intent are represented. The governed reset/RDC profile additionally qualifies observable ready outputs, acyclic dependencies, ordered two-stage ready crossings, recovery/removal offsets, generated simulation/formal evidence, and non-vacuity. Unknown architectural or physical-timing invariants remain gaps. |
| Memory depth | Synchronous read/write access, enable activity, address boundaries, and configured collision semantics are represented. The governed bounded SRAM profile additionally qualifies per-byte merging, two-requester round-robin arbitration, zero initialization, parity detection, generated simulation/formal evidence, and non-vacuity. |
| Formal contract depth | A governed bounded-response profile requires exact trigger/response/invariant mappings, one control domain, a pulse assumption, causal response policy, induction invariants, bounded liveness, and assumption-witness covers. General inferred assumptions and unbounded liveness remain gaps. |
| Parameter sweeps | Every explicitly configured elaboration point has an isolated identity. Coverage schema v3 reports canonical semantic cross-points and fails closure if any point is missing or non-closing. |
| VHDL semantics | The bounded VHDL-only source frontend normalizes entities, integer-like generics, constrained scalar/vector ports, one unambiguous architecture, process/control-domain facts, and source evidence. GHDL 4.1.0 closes the generated observable reset slice with exact per-check results; mixed-language binding and broader VHDL behavior remain fail-closed gaps. |
| Protocol depth | Paired ready/valid, bounded APB4, one-read/one-write-outstanding AXI4-Lite, and single-beat AHB-Lite profiles have executable models, exact per-check closure, and mutation matrices. APB4/AXI4-Lite additionally close on native SystemVerilog and Verilog. Bounded board-peripheral profiles are accepted at Stage 8; broader behavior remains outside the current authority. |
| CDC depth | Unique linear two-flop, governed pulse-stretch, toggle, round-trip handshake, and power-of-two async-FIFO/Gray-pointer structures close only with ordered observable stages, generated simulation/formal evidence, and a matching policy. The FIFO profile additionally requires normalized dual-domain memory accesses, exact widths/ports, a queue scoreboard, pointer/flag properties, and non-vacuity. Hidden or ambiguous stages fail closed by default. |

<a id="source-docsqualificationverification-production-readinessmd--deliberately-unsupported-semantics"></a>
### Deliberately unsupported semantics

The platform must not claim closure for semantics that cannot be inferred or configured
soundly. The following remain explicit extension points rather than heuristic success:

- Full/unbounded AXI, more than one outstanding AXI4-Lite transaction per direction, AHB and APB semantics beyond the explicitly bounded profiles, plus TileLink, Wishbone, and cache-coherency semantics.
- Memory repair/scrubbing beyond the qualified SECDED bounded profile,
  initialization files, asynchronous or wider multi-port memories, physical macro
  timing, and power-state memory behavior beyond the governed bounded SRAM profile.
- Non-power-of-two/FWFT/multi-port asynchronous FIFOs, standalone multi-bit
  coherency or general Gray counters, reconvergent CDC, and CDC schemes outside
  the governed qualified profiles.
- Architectural post-reset state, physical reset-tree timing, and power-state
  sequencing beyond the governed observable reset/RDC facts.
- Analog/mixed-signal, power intent, gate-level timing, emulation, and FPGA-prototype coverage.
- Proprietary coverage database formats that have not been exported to UCIS XML.

These are not silently treated as passing. They require a versioned protocol/depth policy
or an adapter that emits normalized, traceable evidence.

<a id="source-docsqualificationverification-production-readinessmd--external-software-connection-matrix"></a>
### External software connection matrix

| Software class | Platform connection | Deployment requirement |
| --- | --- | --- |
| Verilator | Native RTL analysis and validation path | Install a supported Verilator major version. |
| cocotb/Icarus | Native open simulation path | Install the configured simulator and cocotb environment. |
| SymbiYosys/Yosys/Z3 | Native command adapter and SBY generation | Install SBY, Yosys, `yosys-smtbmc`, and Z3, or use OSS CAD Suite. A skipped engine test is not formal sign-off. |
| Commercial simulators | Versioned simulator command adapter | Configure the executable/license environment and export coverage as UCIS XML. |
| Commercial formal engines | Versioned formal command adapter | Configure the executable/license environment and translate results to normalized formal points. |
| Commercial lint/CDC/RDC tools | Versioned analyzer adapter | Provide normalized structural facts plus source locations and evidence identity. |
| Requirements/ALM systems | Evidence/import adapter | Preserve immutable requirement IDs in plan and coverage points. |

Commercial tools and licenses are deployment inputs; they cannot be bundled or falsely
validated by this repository. Production deployment acceptance therefore requires the
selected tools to be available under `dv-platform status --policy ci`, followed by a
real pilot run whose points reconcile to the canonical plans.

The UCIS XML interchange path follows the
[Accellera UCIS 1.0 standard](https://www.accellera.org/downloads/standards/ucis).
The open formal installation requirement follows the
[official SBY installation guide](https://symbiyosys.readthedocs.io/en/latest/install.html).

<a id="source-docsqualificationtesting-and-qualificationmd"></a>
## Testing and qualification

Consolidated from `docs/qualification/testing-and-qualification.md`.

Every change must pass Ruff, formatting, mypy, the branch-coverage ratchet,
wheel build, installed-wheel smoke tests, and dependency audit. CI also checks
documentation links/examples/schema declarations, malformed inputs, secrets,
static security findings, and release supply-chain outputs.

A GA profile additionally requires good-DUT end-to-end execution, a declared
mutation matrix with every mutant killed by the expected check, exact result
traceability, qualified tool versions, reproducible generated artifacts, and no
skips. Contract tests do not constitute vendor qualification. Vendor records
must be fresh, signed/controlled, and tied to exact tool versions; external pilot
records must come from two unrelated customer designs.

Performance qualification records stage runtime and peak RSS for a
multi-million-line RTL repository and large XML/PDF inputs. A release candidate
fails when a comparable baseline regresses by more than 10%. Native Ubuntu
24.04 is the current Stage 10 scale platform. WSL2 records remain historical
evidence only and are not part of the current support claim. Two-pilot evidence
is not available until the release-candidate stage.

`dv-enterprise benchmark` writes performance-qualification v2 evidence with
platform/kernel/tool identity, commit and wheel digests, complete input
fingerprints, runtime, peak RSS, and reproducibility metadata. Stage 10 requires
identical ≥2,000,000-line RTL, ≥128 MiB XML, and ≥64 MiB PDF fingerprints on
native Ubuntu 24.04.

<a id="source-docsqualificationenterprise-qualificationmd"></a>
## Enterprise qualification without proprietary licenses

Consolidated from `docs/qualification/enterprise-qualification.md`.

dv-platform separates adapter correctness from access to proprietary EDA installations. A profile's qualification level is evidence, not a marketing claim.

<a id="source-docsqualificationenterprise-qualificationmd--qualification-levels"></a>
### Qualification levels

| Level | Meaning |
| --- | --- |
| `unverified` | No qualification evidence is recorded. |
| `contract_verified` | Versioned schemas, result normalization, traceability, security boundaries, and deterministic fixtures passed. |
| `surrogate_verified` | The applicable workflow also passed on an installed open-source tool. This establishes workflow equivalence, not vendor equivalence. |
| `vendor_verified` | A portable bundle was run against the named proprietary installation and its tamper-evident attestation was imported. |
| `independently_signed` | The exact vendor attestation also has a valid detached signature from a policy-approved certificate chain whose identity is distinct from every declared project identity. |

Levels are monotonic. Re-running a lower-level check is retained in qualification history but cannot downgrade the current record.

<a id="source-docsqualificationenterprise-qualificationmd--contract-qualification"></a>
### Contract qualification

```console
dv-enterprise qualify --profile questa --mode fixture
```

Contract qualification uses packaged, hashed simulator, formal, or analyzer result fixtures. It requires no EDA installation or license.

<a id="source-docsqualificationenterprise-qualificationmd--open-source-surrogate-qualification"></a>
### Open-source surrogate qualification

```console
dv-enterprise qualify --profile spyglass --mode surrogate --probe verilator_lint
dv-enterprise qualify --profile questa --mode surrogate --probe iverilog
dv-enterprise qualify --profile jaspergold --mode surrogate --probe yosys
```

Available probes are `verilator_lint`, `verilator_simulator`, `iverilog`, `ghdl`, `yosys`, and `symbiyosys`. Commands are executed directly without a shell, inherit only a bounded environment, have bounded runtime and output, and record the actual version reported by the executable.

Surrogate qualification records the exact families and languages exercised. It must never be described as validation of proprietary tool behavior.

<a id="source-docsqualificationenterprise-qualificationmd--portable-vendor-bundle"></a>
### Portable vendor bundle

Create a self-contained ZIP archive without needing the vendor installation locally:

```console
dv-enterprise qualification-bundle --profile questa --output questa-qualification.zip
```

To qualify collateral rendered by Veriforge's UVM backend, add
`--generated-uvm`. The bundle then includes a deterministic ready/valid UVM
environment and loopback DUT and requires `QUAL-UVM-001` in addition to the
simulator contract check:

```console
dv-enterprise qualification-bundle \
  --profile questa --generated-uvm \
  --output questa-uvm-qualification.zip
```

The archive contains immutable HDL fixtures, normalized-result schema, qualification request, instructions, and a standalone Python runner. On the licensed host, a site wrapper runs the fixtures and writes the normalized result indicated by `DV_PLATFORM_RESULT_PATH`:

```console
python run_qualification.py \
  --tool-name Questa \
  --tool-version 2026.1 \
  -- ./site-questa-qualification-wrapper
```

The runner checks every fixture hash and required check identity. It records only the executable name, return code, normalized result, tool identity, timestamps, and content hashes. Command arguments, source trees, environment values, and raw logs are not included.

Import the returned attestation:

```console
dv-enterprise qualify \
  --profile questa \
  --mode vendor \
  --attestation qualification-attestation.json
```

An unsigned import stops at `vendor_verified`. Stage 11 requires an independent
signer to sign the exact attestation bytes. Veriforge does not accept a
self-declared signer: the certificate must chain to the configured CA, its
RFC2253 subject, issuer, and DER SHA-256 fingerprint must all match an approved
signer, and its subject must not match any `project_identities` entry.

First create the canonical signing statement. It binds the signature purpose,
exact attestation digest, signature scheme, and declared signing time:

```console
dv-enterprise qualification-signing-payload \
  --attestation qualification-attestation.json \
  --signed-at 2026-07-22T12:00:00Z \
  --output qualification-signing-payload.json
```

The independent signer creates a raw SHA-256 detached signature over those
canonical statement bytes:

```console
openssl dgst -sha256 -sign independent-signer.key \
  -out qualification-attestation.sig qualification-signing-payload.json
```

Place the signature and public certificate beside a
`qualification-signature.json` manifest:

```json
{
  "schema_version": 1,
  "purpose": "veriforge-vendor-qualification",
  "signature_kind": "enterprise_pki",
  "attestation_sha256": "<sha256 of the exact attestation bytes>",
  "signature_file": "qualification-attestation.sig",
  "certificate_file": "independent-signer.pem",
  "signed_at": "2026-07-22T12:00:00Z"
}
```

The approving organization maintains a separate trust policy. Relative paths
are resolved within the policy directory; absolute paths and traversal are
rejected:

```json
{
  "schema_version": 1,
  "project_identities": ["CN=Veriforge Release"],
  "approved_signers": [{
    "kind": "enterprise_pki",
    "identity": "CN=Independent Qualification Lab",
    "issuer": "CN=Qualification CA",
    "certificate_sha256": "<sha256 of signer certificate DER>",
    "trust_root": "qualification-ca.pem"
  }]
}
```

Verification is available without changing qualification state:

```console
dv-enterprise verify-qualification-signature \
  --attestation qualification-attestation.json \
  --signature-manifest qualification-signature.json \
  --trust-policy qualification-trust-policy.json
```

Import and promote the record to `independently_signed` only after verification:

```console
dv-enterprise qualify \
  --profile vivado_xsim --mode vendor \
  --attestation qualification-attestation.json \
  --signature-manifest qualification-signature.json \
  --trust-policy qualification-trust-policy.json
```

The checked-in schemas are `qualification-signature-v1.schema.json` and
`qualification-trust-policy-v1.schema.json`. Private keys are deliberately
outside Veriforge's command surface.

The GA ledger cannot promote a Stage 11 profile by changing its state string
alone. An `independently_signed` profile must name its tool qualification
profile, attestation, signature manifest, and trust policy; the gate performs a
fresh fail-closed import and cryptographic verification in an isolated
temporary state directory.

<a id="source-docsqualificationenterprise-qualificationmd--amd-vivado-simulator-from-wsl"></a>
#### AMD Vivado Simulator from WSL

The `vivado_xsim` generated-UVM bundle includes `run_vivado_xsim.py`. AMD Vivado
Simulator ships a precompiled UVM 1.2 library; the wrapper supplies `-L uvm`,
the XSim timescale overrides, and fail-closed report checks. For a Windows Vivado
installation accessed from WSL, extract the bundle on a Windows-mounted path and
run:

```console
python run_qualification.py \
  --tool-name "AMD Vivado Simulator" \
  --tool-version 2025.2 -- \
  python run_vivado_xsim.py \
  --vivado-bin /mnt/c/AMDDesignTools/2025.2/Vivado/bin \
  --cmd-exe /mnt/c/Windows/System32/cmd.exe
```

The accepted 2025.2 attestation is retained under `docs/evidence` and is
re-imported in tests, so generator drift invalidates qualification evidence.

<a id="source-docsqualificationenterprise-qualificationmd--policy-enforcement"></a>
### Policy enforcement

Set a repository-wide minimum:

```console
dv-enterprise qualification-policy \
  --minimum-level contract_verified \
  --max-age-days 365
```

Set a stronger profile-specific minimum:

```console
dv-enterprise qualification-policy \
  --profile questa \
  --minimum-level independently_signed
```

`dv-enterprise status --policy ci` and the primary `dv-platform status --policy ci` fail when a configured runner is below policy, its record is corrupt, or its evidence is stale. The default policy is `unverified`, preserving existing deployments until they explicitly adopt a qualification gate.

Records and policy are stored under `.dv-platform/qualification`. Every successful attempt is retained under `history`; the highest current level is stored under `records`.

<a id="source-docsqualificationga-contractmd"></a>
## Veriforge GA contract

Consolidated from `docs/qualification/ga-contract.md`.

Veriforge is the product name. `dv-platform` is the Python distribution and
primary CLI; `dv-enterprise` is the enterprise-adapter CLI.

The prospective stable 1.x surface is deliberately smaller than the source
tree: CLI command names and options, JSON envelopes and error codes,
`dv-platform.toml`, persisted schemas, packaged JSON schemas, and plugin APIs
v1 and v2. API v1 remains readable and loadable throughout 1.x; v2 adds the
sandbox/audit contract. Direct imports from `dv_platform` are internal implementation details and
may change in minor releases. LiteLLM and live-provider behavior are opt-in
preview functionality and are excluded from support SLOs.

Version 0.1.x and the Alpha classifier remain in force. A supported capability
means only the bounded profile identified in the [capability matrix](#source-docsqualificationcapability-matrixmd),
with the evidence required by its acceptance document. Missing vendor evidence,
external pilots, or security gates cannot be replaced by a passing unit test.
The ordered Stage 6–13 gates and version transitions are defined in
[Broad-GA stages](#source-docsqualificationga-stagesmd) and enforced by the checked-in GA ledger.

Schemas remain backward-readable for at least one major release. A destructive
migration requires a verified backup, a dry-run report, and an explicitly
selected migration. Deprecations require release-note notice for one minor
release before removal; breaking stable-surface changes require a major version.

<a id="source-docsqualificationga-stagesmd"></a>
## Broad-GA stages

Consolidated from `docs/qualification/ga-stages.md`.

Stages 6 through 13 are sequential acceptance milestones. Engineering may
overlap, but a later stage cannot be accepted while an earlier stage is open.
The machine-readable source of gate status is
`qualification/policies/ga-gates-v1.json`; prose documents may explain but never
override it.

| Stage | Milestone | Acceptance boundary |
| --- | --- | --- |
| 6 | GA foundation and security closure | Repository-controlled security, migration, release, fuzz, and reproducibility gates pass. |
| 7 | On-chip buses and streams | APB4, AXI4-Lite, bounded AHB-Lite, and paired ready/valid pass exact-check and mutation closure on every claimed target. |
| 8 | Board-peripheral protocols | UART, SPI, I2C, GPIO, timer/watchdog/PWM, and interrupt-controller profiles pass executable and mutation closure. |
| 9 | VHDL and project-level UVM closure | GHDL reset/ready-valid and paired ready/valid UVM project coverage close. |
| 10 | Semantic, scale, and platform qualification | Two unrelated designs, scale budgets, and Ubuntu 24.04 pass. WSL2 is historical/non-current. |
| 11 | Vendor adapter qualification | XSim, JasperGold, and SpyGlass have current vendor evidence. |
| 12 | Release candidate and enterprise pilots | Two pilots validate the signed `1.0.0rc3` lineage. |
| 13 | GA promotion | The metadata-only `1.0.0` promotion and final supply-chain checks pass. |

Versions remain `0.1.x`/Alpha through Stage 11. Stage 12 cuts
`1.0.0rc3` before the pilots; only Stage 13 may publish `1.0.0` with a
production classifier.

Stages 6–10 are accepted. Stage 11 is the active milestone and requires fresh,
independently signed licensed-tool evidence; later stages remain blocked by the
sequential gate even when preparatory implementation exists.

<a id="source-qualificationreadmemd"></a>
## Qualification Evidence

Consolidated from `qualification/README.md`.

Document type: current qualification operations and evidence index.

Authority: `qualification/policies/ga-gates-v1.json`, packaged qualification
schemas, independently verified evidence, and current clean-checkout results.

Scope: GA stages 6-13, local evidence creation/verification, stage records,
external-design records, performance records, sandbox evidence, vendor
attestations, pilot evidence, and promotion gating.

Status: Stages 6-10 are recorded complete in the ledger. Stage 11 is pending.
Current release promotion is also blocked by stage-gate sequencing (`stage 11–13`),
fresh independently signed enterprise evidence, and the unresolved
`DOC-00`/`DOC-02` alignment tasks.

Last reviewed: 2026-07-28.

Supersedes: none.

Known issues: see
[`docs/roadmap.md`](roadmap.md#source-docsplanningmissing-workmd).

<a id="source-qualificationreadmemd--release-rule"></a>
### Release rule

`policies/ga-gates-v1.json` is the machine-readable gate-state authority. It
does not, by itself, prove that the current checkout passes the tests or still
satisfies an older evidence record. A profile may be accepted only when:

1. Its ledger state and containing stage are valid.
2. Every required evidence path exists and validates.
3. Evidence belongs to the exact source/configuration/profile/target/tool
   identities being promoted.
4. Required end-to-end tests pass in one clean checkout.
5. Required tools ran; required skips, timeouts, or license failures are
   non-closing.
6. Exact checks, mutations/negative cases, coverage, non-vacuity where
   applicable, and strict status close.
7. Vendor claims carry independently verified signatures according to the
   configured trust policy.
8. No current P0 regression blocks the capability or release.

Contract tests, generated projects, mocked results, old attestations, an
integrity hash, or an aggregate process exit cannot substitute for required
real-tool evidence.

<a id="source-qualificationreadmemd--current-gate-state"></a>
### Current gate state

| Stage | Current ledger state | Required interpretation |
| --- | --- | --- |
| 6 | complete | Historical foundation/security evidence paths are present |
| 7 | complete | Historical bounded on-chip protocol evidence paths are present |
| 8 | complete | Historical bounded board-peripheral evidence paths are present |
| 9 | complete | Historical VHDL and project-UVM evidence paths are present |
| 10 | complete | Historical semantic-design, scale/platform, and OCI evidence paths are present |
| 11 | pending | Vendor simulator, formal, and analyzer profiles require fresh independently signed licensed-tool evidence |
| 12 | pending | Requires Stage 11, signed `1.0.0rc3`, and two unrelated enterprise pilots |
| 13 | pending | Requires Stage 12 and final artifact/SBOM/provenance/private-index verification |

The stages are sequential. Preparatory work for a later stage does not permit
promotion while an earlier stage is open. Stage 11–13 and the outstanding
`DOC-00`/`DOC-02` alignment are the remaining release-release blockers even
though the historical Stage 6–10 entries validate locally.

<a id="source-qualificationreadmemd--evidence-directories"></a>
### Evidence directories

| Path | Contents | Validation authority |
| --- | --- | --- |
| `policies/ga-gates-v1.json` | Ordered stage/profile ledger | `schemas/qualification/ga-gates-v1.schema.json`, `scripts/qualification/ga_gates.py` |
| `policies/oci-sandbox-runtime-v1.json` | Checked OCI runtime controls and measured evidence | Sandbox qualification tests and policy schema |
| `stages/` | Human-readable bounded stage evidence | Ledger references, exact tests/fixtures, documentation contract |
| `profiles/` | Profile-specific qualification records | Profile contract and named executable evidence |
| `external-designs/` | Source-licensed external-design semantic records | External-design verifier and ledger |
| `performance/` | Platform-specific baseline/current performance records | Performance schemas and `scripts/qualification/performance.py` |
| External governed evidence location | Vendor attestations, signature bundles, pilots, release artifacts | Enterprise importer, trust policy, evidence schema, release procedure |

Do not put secrets, raw customer RTL, provider prompts/responses, private keys,
license files, or unredacted pilot content into checked-in evidence.

<a id="source-qualificationreadmemd--evidence-levels"></a>
### Evidence levels

| Level | Minimum meaning | Permitted claim |
| --- | --- | --- |
| Contract verified | Schema, parser, command construction, and normalized mock behavior pass | Adapter contract exists; no vendor execution claim |
| Tool executed | A named tool/version ran against identified inputs and produced mapped results | Exact bounded run result for that tool only |
| Vendor verified | Licensed vendor tool evidence is imported with source/tool/result identities | Exact vendor run, subject to freshness and trust limits |
| Independently signed | Signature bundle or enterprise-PKI signature verifies over exact attestation bytes using approved trust policy | Signed vendor claim for the exact payload |
| Qualified | Required targets, good DUT, mutants/negatives, exact checks, coverage/non-vacuity, provenance, and strict status all close | Supported bounded profile named by the ledger/capability matrix |

An integrity digest detects payload changes but does not identify a signer. A
mocked vendor report cannot exceed contract-verified status.

<a id="source-qualificationreadmemd--prerequisites"></a>
### Prerequisites

Run all commands from the repository root.

Required for ledger checks:

- repository dependencies installed through `uv`;
- readable ledger, schema, and referenced evidence files;
- Python package importable in the `uv` environment.

Required to create local GA evidence:

- clean Git checkout with a resolved 40-character commit;
- passing unittest log containing the final `Ran N tests` and `OK` summary;
- coverage JSON with totals and branch data;
- non-empty generated artifact directory containing regular, non-symlink files;
- checked-in `.github/workflows/ci.yml` and `uv.lock`;
- sufficient disk space to hash all tracked files and retained artifacts.

Required for vendor or pilot promotion:

- authorized licensed-tool environment;
- legal, redacted fixture or customer evidence;
- qualification profile matching the exact tool/profile/target;
- approved signature/trust policy;
- release owner approval and the preceding stage complete.

<a id="source-qualificationreadmemd--step-by-step-qualification"></a>
### Step-by-step qualification

<a id="source-qualificationreadmemd--step-1-preserve-and-identify-the-checkout"></a>
#### Step 1: preserve and identify the checkout

```bash
git status --short
git rev-parse HEAD
```

Do not discard unrelated changes. Evidence creation intentionally rejects a
dirty checkout because the commit alone would not identify the tested source
tree. A working-tree investigation may proceed, but it cannot create promotable
GA evidence.

<a id="source-qualificationreadmemd--step-2-validate-the-ledger-structure"></a>
#### Step 2: validate the ledger structure

```bash
uv run python scripts/qualification/ga_gates.py
```

Expected result: exit `0` and `GA gate ledger is valid`. This verifies identity,
stage order, allowed states, evidence path existence, external-design records,
and required independent-signature fields. It does not run the product tests.

Common exit `1` causes:

- stage number/order is invalid;
- a completed stage appears after an open earlier stage;
- accepted profile lacks evidence;
- referenced evidence file is missing or invalid;
- profile ID is missing/duplicated;
- profile state or target/evidence list is invalid;
- independently signed profile lacks or fails attestation/signature/trust data.

<a id="source-qualificationreadmemd--step-3-enforce-the-intended-promotion-boundary"></a>
#### Step 3: enforce the intended promotion boundary

For the currently accepted historical boundary:

```bash
uv run python scripts/qualification/ga_gates.py --through-stage 10
```

Expected result: exit `0` only when every stage and profile through Stage 10 has
the required accepted state. Running through Stage 11 currently returns exit
`1` because the three Stage 11 profiles are pending. Do not change pending to
accepted merely to make this command pass.

<a id="source-qualificationreadmemd--step-4-run-mandatory-repository-checks"></a>
#### Step 4: run mandatory repository checks

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run python scripts/checks/compatibility.py --check
uv run python scripts/checks/maintainability.py --check
uv run python scripts/checks/repository_contracts.py
uv run python scripts/checks/secrets.py
```

Every command must exit `0`.

<a id="source-qualificationreadmemd--step-5-run-tests-and-capture-coverage"></a>
#### Step 5: run tests and capture coverage

Use an evidence workspace outside the artifact directory:

```bash
mkdir -p .dv-platform/qualification
uv run coverage run -m unittest discover -s tests \
  2>&1 | tee .dv-platform/qualification/unittest.log
uv run coverage report
uv run coverage json \
  -o .dv-platform/qualification/coverage.json
uv run python scripts/checks/branch_coverage.py \
  .dv-platform/qualification/coverage.json
```

Review all skips. A skip is acceptable only if the profile being qualified does
not require that tool and the final claim excludes it.

The evidence creator parses the final unittest summary. Concatenating an old
passing log after a new failure is invalid evidence even if the parser finds an
`OK` block; reviewers must bind logs to the same job and commit and inspect the
complete job result.

<a id="source-qualificationreadmemd--step-6-run-profile-specific-real-tool-workflows"></a>
#### Step 6: run profile-specific real-tool workflows

For every profile/target being promoted:

1. Run the public `analyze-rtl`, `plan`, `generate`, `run`, `coverage`, and
   strict `status` workflow where applicable.
2. Retain source/configuration/plan/generated/run/coverage/status identities.
3. Run the known-good DUT.
4. Run every required mutant or negative fixture.
5. Verify exact check/trace/coverage IDs, not only aggregate counts.
6. Verify formal assumptions have reachable witnesses and required covers.
7. Record exact tool versions and platform identity.
8. Place only the governed, redacted, non-secret deliverables in the artifact
   directory used by the next step.

Use the profile's stage record for exact commands and bounds. If the stage
record lacks enough detail to repeat the run, treat that as a documentation gap
and do not infer the missing command.

<a id="source-qualificationreadmemd--step-7-create-commit-bound-evidence"></a>
#### Step 7: create commit-bound evidence

After all commands pass in a clean checkout and the artifact directory is
non-empty:

```bash
uv run python scripts/qualification/ga_evidence.py create \
  --stage 10 \
  --root . \
  --test-log .dv-platform/qualification/unittest.log \
  --coverage .dv-platform/qualification/coverage.json \
  --artifacts .dv-platform/qualification/artifacts \
  --output .dv-platform/qualification/ga-evidence-v1.json
```

Change `--stage` only to the stage actually being qualified. The command writes
schema-v1 JSON and exits `0` after recording:

- commit;
- deterministic digest of tracked source files;
- CI workflow and lockfile digests;
- passed/skipped/failed test counts;
- combined and branch coverage;
- Python and `uv` versions;
- SHA-256 for every regular, non-symlink artifact;
- payload digest and `passed` status.

The command exits `1` for a dirty checkout, unresolved commit, invalid stage,
missing passing unittest summary, missing coverage totals, empty artifact set,
invalid JSON, or unreadable input.

<a id="source-qualificationreadmemd--step-8-verify-local-evidence"></a>
#### Step 8: verify local evidence

```bash
uv run python scripts/qualification/ga_evidence.py verify \
  --input .dv-platform/qualification/ga-evidence-v1.json
```

Expected result: exit `0` and `GA evidence verified`. Verification checks
schema/status identity, payload digest, commit/tree/workflow/lockfile digest
shape, at least one passed test with zero failures, numeric coverage, and a
non-empty artifact identity map.

Important boundary: this verifier validates evidence document integrity. It
does not rerun tests, recompute artifact hashes against a supplied directory,
verify freshness, or verify an external signer. Release review must perform
those additional comparisons.

<a id="source-qualificationreadmemd--step-9-import-and-verify-vendor-evidence"></a>
#### Step 9: import and verify vendor evidence

Stage 11 records must use `dv-enterprise qualify import` through the enterprise
qualification profile. The import must bind:

- exact attestation bytes;
- qualification profile;
- source, configuration, generated artifact, and tool identities;
- normalized exact results and coverage;
- signature manifest;
- approved trust policy;
- signer identity and verification result.

The ledger state for Stage 11 profiles is `independently_signed`, not merely
`vendor_verified`. Keep mocked adapter tests separate from real licensed
evidence. A missing license, timeout, malformed native report, unknown check,
stale source identity, untrusted signer, or signature mismatch is non-closing.

<a id="source-qualificationreadmemd--step-10-review-promotion"></a>
#### Step 10: review promotion

Before changing any ledger state:

1. Verify all earlier stages are complete.
2. Re-run ledger validation and enforcement.
3. Recompute source/artifact identities against retained evidence.
4. Verify required tests, mutants, exact checks, coverage, non-vacuity, and
   strict status.
5. Confirm no P0 regression applies.
6. Confirm capability/acceptance/operations documents use the same bounded
   state.
7. Obtain the required independent reviewer/release-owner approval.
8. Change only the exact stage/profile state supported by evidence.
9. Run repository contracts and affected qualification tests.

<a id="source-qualificationreadmemd--stage-specific-notes"></a>
### Stage-specific notes

<a id="source-qualificationreadmemd--stage-8-board-peripherals"></a>
#### Stage 8 board peripherals

Evidence is recorded in
[`stages/stage8-board-peripherals.md`](#source-qualificationstagesstage8-board-peripheralsmd).
The accepted profiles are deliberately bounded. They do not imply unlisted
electrical, bus, multi-controller, timing, DMA, or analog behavior.

<a id="source-qualificationreadmemd--stage-10-performance"></a>
#### Stage 10 performance

Records use
`schemas/qualification/performance-qualification-v1.schema.json` or the
current v2 performance schema as applicable and are compared with:

```bash
uv run python scripts/qualification/performance.py \
  qualification/performance/ubuntu24-scale-baseline-v2.json \
  qualification/performance/ubuntu24-scale-current-v2.json \
  --require-ga-scale
```

Ubuntu 24.04 requires a current record with identical input identities. WSL2
records are retained for historical comparison only; do not use them to claim
current WSL support or replace missing Ubuntu evidence with extrapolation.

<a id="source-qualificationreadmemd--stage-11-vendor-qualification"></a>
#### Stage 11 vendor qualification

Vendor records are imported through `dv-enterprise qualify import`. Their
integrity hash is necessary but not a signing claim. Broad-GA evidence also
requires a separately verified Sigstore bundle or enterprise-PKI signature
tied to the exact attestation bytes and approved trust policy.

<a id="source-qualificationreadmemd--stage-12-pilots"></a>
#### Stage 12 pilots

Pilot evidence must be redacted and content-free while retaining RC wheel
digest, project/tool profile, exact status/check counts, artifact
reproducibility digest, upgrade/rollback outcome, and approver identity. The
SystemVerilog-heavy and VHDL or mixed-tool pilots must use unrelated designs.
Do not retain customer source, paths that reveal customer identity, logs with
source excerpts, prompts, responses, credentials, or license data.

<a id="source-qualificationreadmemd--stage-13-promotion"></a>
#### Stage 13 promotion

Only Stage 13 may publish `1.0.0` with a production classifier. Promotion is a
metadata-only transition from the accepted `1.0.0rc3` artifact lineage and must
verify final artifact hash, signature, SBOM, provenance, and private-index
installation without rebuilding different bytes.

<a id="source-qualificationreadmemd--rejection-and-edge-cases"></a>
### Rejection and edge cases

- **Dirty tree:** investigate locally, but do not create GA evidence.
- **Detached but resolved commit:** permitted by the evidence creator if clean;
  release policy must still prove branch/tag provenance.
- **Submodule or untracked input:** not represented by the tracked-tree digest
  unless separately bound; qualification must reject or add explicit identity.
- **Symlink artifact:** excluded by the creator; required evidence behind a
  symlink is therefore missing.
- **Empty artifact directory:** rejected.
- **Zero test count or any failed test:** rejected.
- **Required skip:** non-closing even though schema-v1 can record skips.
- **Zero branch denominator:** the creator reports 100%; reviewers must reject
  this for a profile requiring branch evidence because no branches were
  measured.
- **Unknown/newer schema:** reject until a versioned reader/migration exists.
- **Old schema:** preserve original meaning; migration must not promote state.
- **Hash match without signature:** integrity only, not signer authenticity.
- **Valid signature with stale source/tool/profile:** reject.
- **Partial/malformed/empty vendor result:** `unexecuted` or failed.
- **Concurrent evidence publication:** write to a staging path, verify, then
  atomically publish; never let readers consume a partial file.
- **Interrupted run:** discard partial artifacts or retain them only as
  diagnostic, explicitly non-promotable evidence.
- **Contradictory prose and ledger:** preserve ledger state, choose the
  conservative release claim, and resolve `DOC-00`/`DOC-02`.

<a id="source-qualificationreadmemd--qualification-change-checklist"></a>
### Qualification change checklist

- [ ] Exact stage/profile/role/target/bounds are named.
- [ ] Ledger and packaged schema validate.
- [ ] Current checkout is clean and commit-resolved.
- [ ] Mandatory quality checks pass.
- [ ] Full and profile-specific tests pass.
- [ ] Required tools ran at recorded versions.
- [ ] Good DUT and complete mutation/negative matrix close.
- [ ] Exact checks and coverage points map to stable identities.
- [ ] Formal evidence includes non-vacuity/reachability where required.
- [ ] Source/configuration/generated/run/coverage/status provenance agrees.
- [ ] Artifacts are non-empty, regular, redacted, and free of secrets.
- [ ] Vendor evidence has approved independent signature verification.
- [ ] No P0 regression invalidates the claim.
- [ ] Capability, acceptance, operations, and release documents agree.
- [ ] Evidence verification and repository contract tests pass.

<a id="source-qualificationreadmemd--validation-commands"></a>
### Validation commands

For ledger/evidence changes, run:

```bash
uv run python scripts/qualification/ga_gates.py
uv run python -m unittest \
  tests.qualification.test_ga_gates \
  tests.qualification.test_ga_evidence \
  tests.qualification.test_enterprise_qualification \
  tests.qualification.test_external_design_evidence
uv run python scripts/checks/repository_contracts.py
```

Add profile-specific qualification tests named by the changed stage record.
Report every command, result, tool version, and skip in the handoff format from
the [Agent Execution Guide](agents.md#source-docsagent-execution-guidemd).

<a id="source-qualificationprofilesahb-lite-single-beatmd"></a>
## AHB-Lite bounded single-beat qualification

Consolidated from `qualification/profiles/ahb-lite-single-beat.md`.

The qualified profile is a 32-bit, single-master, single-beat AHB-Lite slave
with `HREADYOUT`, one or more fully specified registers, RW/RO/W1C fields,
`HRESP` on invalid addresses, a known clock, and an active-low or active-high
reset. Bursts, split/retry responses, protection semantics, multi-layer
interconnect, and broader AHB constructs remain unsupported.

`tests/integration/test_ahb_lite_generated_pipeline.py` executes the full CLI pipeline. It
requires exact per-check results, coverage import, `status --policy ci`, and
byte-reproducible collateral. The good DUT passes generated cocotb and bounded
formal collateral. Both backends kill the same six mutations:

| Mutation | Cocotb | Formal |
| --- | --- | --- |
| Discarded write | killed | killed |
| Writable RO field | killed | killed |
| Broken W1C field | killed | killed |
| Missing `HRESP` | killed | killed |
| Dropped `HREADYOUT` | killed | killed |
| Incorrect reset value | killed | killed |

The fixtures are `tests/fixtures/mutations/protocol/ahb_lite_qualified_slave.sv` and
`tests/fixtures/mutations/protocol/ahb_lite_registers.json`. CI reruns the test rather
than treating this document as a substitute for current execution evidence.

<a id="source-qualificationstagesstage6-foundationmd"></a>
## Stage 6 foundation qualification

Consolidated from `qualification/stages/stage6-foundation.md`.

Accepted on 2026-07-22 against the `0.1.0` development lineage. CI reruns the
controls below; this record identifies the gate and is not a waiver for a
future failure.

- 500 unit/integration tests passed with four declared optional-tool skips.
- Combined coverage was 86.15%, statement coverage was 89.08%, and true branch
  coverage was 78.15% across 5,468 branches; every versioned ratchet passed.
- Ruff lint/format and mypy passed.
- Repository contracts, the GA ledger, and tracked-file secret scanning passed.
- Bandit reported no high-severity findings; `pip-audit --skip-editable`
  reported no known dependency vulnerabilities.
- SQLite backup/restore integrity, bounded retention purge, export allowlists,
  symlink/path rejection, plugin publisher/hash checks, environment-backed
  secrets, redaction, malformed JSON/XML/PDF handling, and backward-readable
  persisted schemas are covered by executable tests.
- Two independent `uv build` invocations produced byte-identical wheels and
  source distributions.
- The release dry run generated a deterministic SPDX 2.3 SBOM, basename-only
  checksums, and SLSA/in-toto provenance; independent verification passed and
  tampering/path traversal tests failed closed.

Artifact signing and private-index publication are deliberately later-stage
release controls. This stage does not claim vendor, pilot, WSL, or broad-scale
qualification.

<a id="source-qualificationstagesstage7-on-chip-protocolsmd"></a>
## Stage 7 on-chip protocol qualification

Consolidated from `qualification/stages/stage7-on-chip-protocols.md`.

Qualified on 2026-07-22 against the `0.1.0` development lineage.

- APB4 passes generated cocotb and bounded-formal good-DUT runs and kills nine
  mutants on each backend. The same typed scenarios now generate normalized,
  self-checking native SystemVerilog and Verilog transactions; both native
  targets pass the good DUT and kill all nine mutants.
- AXI4-Lite passes generated cocotb and bounded-formal good-DUT runs and kills
  ten mutants on each backend. Native SystemVerilog and Verilog independently
  check AW/W ordering, one-outstanding limits, response hold/stability, WSTRB,
  error responses, read data, and exact result closure; both kill all ten.
- The bounded AHB-Lite single-beat slave profile passes cocotb and formal and
  kills six governed register, wait-state, response, and reset mutants on each.
- The paired ready/valid stream profile passes generated cocotb end-to-end data,
  acceptance, backpressure, stability, and recovery checks and kills refusal,
  dropped-valid, unstable-data, and corrupted-data mutants. Its formal safety
  assertions remain supported but are not included in this profile's mutation
  claim because an end-to-end formal reference model is not yet qualified.
- Every accepted run uses stable trace IDs, normalized per-check results,
  coverage import, strict CI status, bounded timeouts, and byte-reproducible
  generated artifacts. Partial interfaces and unknown clock/reset/register
  semantics remain fail-closed.

This stage does not claim full AXI, bursts, IDs, multiple outstanding
transactions, AHB bursts/interconnect, or AXI-Stream sidebands such as TLAST,
TKEEP, TID, TDEST, and TUSER.

<a id="source-qualificationstagesstage8-board-peripheralsmd"></a>
## Stage 8 board-peripheral qualification

Consolidated from `qualification/stages/stage8-board-peripherals.md`.

Status: accepted on 2026-07-22.

Stage 8 qualifies four explicit controller/subsystem profiles. A profile is
executable only when every governed signal is mapped to a unique normalized
port with the required direction and width, the clock/reset domain is known,
and all bounded numeric parameters are valid. Missing or ambiguous semantics
remain unsupported rather than falling back to name-based stimulus.

<a id="source-qualificationstagesstage8-board-peripheralsmd--qualified-profiles"></a>
### Qualified profiles

| Profile | Executable contract | Mutation closure |
| --- | --- | --- |
| UART `bounded_controller` | 8-bit TX/RX; configurable parity and one/two stop bits; exact baud timing; idle, framing, parity, break, overflow, and clear behavior | 10/10: divisor, TX/RX order, parity, stop count, idle level, and four receive-error paths |
| SPI `bounded_master` | 8-bit master transfers; CPOL/CPHA modes 0–3; MSB/LSB-first; chip-select framing; divider, edge, receive, done, and timeout checks | 9/9: CPOL, CPHA, select, both bit orders, receive order, trailing edge, divider, and completion |
| I2C `bounded_7bit_master` | Wired-AND open-drain BFM; 7-bit address; write and combined read; START, STOP, repeated START, ACK/NACK, bounded stretch, arbitration loss, and timeout | 8/8: START, STOP, repeated START, NACK, stretch, arbitration, write serialization, and read data |
| GPIO/timer/interrupt `bounded_subsystem` | 4-bit GPIO direction, masked write/set/clear, edge/level interrupts; 8-bit prescaled periodic timer; watchdog feed/IRQ/reset; PWM period/duty/polarity; 4-source fixed-priority masked interrupt controller | 10/10: direction, mask, set, GPIO IRQ, timer compare, watchdog feed/reset, PWM rollover, priority, and interrupt-valid |

Each good DUT passes the complete `analyze-rtl -> plan -> generate -> run ->
coverage -> status --policy ci` cocotb/Icarus path. Generated formal safety and
non-vacuity collateral also passes SBY/Yosys/Z3 for every profile. UART output
is regenerated twice and compared byte-for-byte; the common deterministic
generator/provenance contract covers the other profiles.

<a id="source-qualificationstagesstage8-board-peripheralsmd--evidence-and-reproducibility"></a>
### Evidence and reproducibility

- Contract recognition and fail-closed tests:
  `tests/formal/test_peripheral_depth.py`
- End-to-end and mutation suites:
  `tests/qualification/test_uart_peripheral_qualification.py`,
  `tests/qualification/test_spi_peripheral_qualification.py`,
  `tests/qualification/test_i2c_peripheral_qualification.py`, and
  `tests/qualification/test_gpio_timer_interrupt_qualification.py`
- Versioned mutation RTL:
  `tests/fixtures/mutations/*_bounded_qualified.sv` and
  `tests/fixtures/mutations/peripheral/gpio_timer_interrupt_qualified.sv`

The accepted local tools are Verilator 5.020, Icarus 12.0, cocotb, SBY 0.67,
Yosys 0.33, and Z3 4.8.12. CI repeats the available real-tool paths.

<a id="source-qualificationstagesstage8-board-peripheralsmd--explicit-exclusions"></a>
### Explicit exclusions

This milestone does not claim arbitrary UART word sizes or fractional baud
generators; SPI multi-lane, multi-master, or continuous streaming; I2C 10-bit
addressing, high-speed modes, multi-controller fairness, SMBus, or analog
electrical behavior; or general-purpose timer capture/compare/DMA and arbitrary
interrupt arbitration. Those capabilities require separate versioned profiles
and qualification evidence.

<a id="source-qualificationstagesstage9-vhdl-uvmmd"></a>
## Stage 9 VHDL and project-UVM qualification

Consolidated from `qualification/stages/stage9-vhdl-uvm.md`.

Status: accepted on 2026-07-22.

<a id="source-qualificationstagesstage9-vhdl-uvmmd--vhdl-reset-and-readyvalid-profile"></a>
### VHDL reset and ready/valid profile

The bounded VHDL source frontend now recognizes a paired stream only from a
complete directionally consistent `valid`, `ready`, and `data` port set in one
unambiguous clock/reset domain. Generated VHDL-2008 collateral checks observable
reset state, input acceptance, end-to-end data, output stability through
backpressure, and recovery after acceptance. The complete CLI path runs through
GHDL 4.1.0, imports exact native trace results, closes coverage, and passes the
CI status policy.

`tests/qualification/test_vhdl_ready_valid_qualification.py` passes the good project, verifies
byte reproducibility, and kills four VHDL mutants: incorrect reset, refused
input, corrupted data, and dropped valid under backpressure. Subsequent Stage 10
work added GHDL-authoritative packages, records, subtypes, arrays, generate
elaboration, and explicit architecture binding. Incomplete streams and ambiguous
or undeclared cross-language bindings remain fail-closed.

<a id="source-qualificationstagesstage9-vhdl-uvmmd--paired-readyvalid-uvm-project-profile"></a>
### Paired ready/valid UVM project profile

The generated UVM 1.2 project contains the interface, transaction, sequence,
sequencer, driver, monitor, expected/actual FIFO scoreboard, environment, test,
and DUT top. `vivado_xsim_project_runner` compiles those artifacts with project
RTL, elaborates the generated top, executes the named test, requires zero UVM
errors/fatals and the absence of the scoreboard's no-transaction failure, and
emits exact `DV_PLATFORM_RESULT_V1` records for every generated trace. The
normal run-summary path converts those records into validation-result v1 and
normalized coverage points, so `coverage --from-runs` and strict status close.

`tests/qualification/test_uvm_project_qualification.py` exercises both the vendor-runner
boundary and the complete CLI normalization path. Current real-tool evidence is
the checked-in AMD Vivado Simulator 2025.2 attestation at
`qualification/evidence/vivado-xsim-2025.2-qualification-attestation.json`; its integrity
and binding to the current generated UVM bytes are rechecked by
`tests/qualification/test_enterprise_qualification.py`.

This Stage 9 qualification is deliberately limited to paired ready/valid UVM.
Multi-agent profile environments and RAL are now generated and contract-tested,
but additional vendor execution, VHDL/UVM mixed-language execution, and live
coverage-database APIs remain later vendor-stage work.

<a id="source-qualificationstagesstage10-semantic-designsmd"></a>
## Stage 10 external-design semantic qualification

Consolidated from `qualification/stages/stage10-semantic-designs.md`.

Two unrelated, pinned open-source designs were elaborated by Verilator 5.020, normalized independently by Slang 11.0, and elaborated to UHDM by Surelog 1.86. Required design-unit, specialization, port/width, parameter, type, and hierarchy facts reconciled exactly.

The records are content-free and bind the upstream repository, commit, selected inputs, license, frontend artifacts, versions, and comparison outcome by SHA-256:

- `external-designs/picorv32-v1.json`
- `external-designs/ibex-counter-v1.json`

The pinned source slices and licenses are checked in under
`qualification/external-designs/sources/`. The `SEM-03` frontend matrix at
`qualification/evidence/SEM-03/frontend-matrix-v1.json` additionally records
real Verilator 5.020 and Slang 11.0 commands, raw-artifact and diagnostic
digests, runtime, and peak RSS. GHDL 4.1 is explicitly `not_applicable` for
these Verilog/SystemVerilog slices; its VHDL qualification remains independent.

The extended comparison also retained five PicoRV32 and six Ibex representation gaps in assignments, procedures, expressions, branches, control domains, and generated scopes as warnings. These fields remain strict-generation blockers when selected as required capabilities; they were not silently merged or promoted into primary facts.

Reproduce with `dv-enterprise qualify-external-design` and verify the resulting records with `dv-enterprise verify-evidence`.

<a id="source-qualificationstagesstage10-scale-platformmd"></a>
## Stage 10 scale and platform qualification

Consolidated from `qualification/stages/stage10-scale-platform.md`.

Current status: Ubuntu 24.04 is the only current Stage 10 scale platform. The
merged Ubuntu candidate run and its digest-bound bundle are archived in the CI
qualification evidence store. WSL2 is explicitly non-current; the records
below are preserved as historical acceptance material only.

Status: historical acceptance record on 2026-07-22 for commit
`ebb28cd75b24442d3c728fc31eedc9fc5178c6d4` and wheel SHA-256
`93ce9ad8c867078191d97536e4b5d4aa60b0f9a16c03b197ed8cc42a8b3ef501`.

The identical deterministic workload contains 2,000,000 RTL lines, a
134,217,728-byte XML document, and a 67,109,418-byte PDF. Input SHA-256
identities match on both platforms. Baseline and current records were produced
from clean worktrees with `PYTHONHASHSEED=0` and validated by
`scripts/qualification/performance.py --require-ga-scale`.

- Native Ubuntu 24.04.4 ran in a KVM guest on kernel `6.8.0-134-generic`.
- The Ubuntu current run remained within the 10% runtime and peak-RSS
  regression limit.
- The WSL2 records are retained as historical evidence and do not establish a
  current WSL support claim.
- The Ubuntu container preflight was not accepted as native evidence because it
  correctly reported the shared WSL2 kernel.

The four performance-qualification v2 records are checked in adjacent to this
document and are revalidated by `tests/qualification/test_performance_qualification.py`.

The platform gate also includes `oci-sandbox-runtime-v1.json`, bound to clean
commit `9b6cb79995730aca2928368db5c36b32ce8c9486` and immutable Ubuntu 24.04 image
digest `sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90`.
The live Docker 29.5.2 probe verifies a non-root container UID, network denial,
read-only root and source mounts, an isolated writable output, dropped
capabilities, no-new-privileges, CPU/memory/PID limits, and explicit environment
allowlisting. The host Docker daemon is not rootless; the qualified product
claim is unprivileged sandbox execution, while Podman `keep-id` remains the
rootless-daemon deployment path.

<a id="source-docsacceptancereadmemd"></a>
## Acceptance Evidence Index

Consolidated from `docs/acceptance/README.md`.

Document type: historical acceptance index and reading procedure.

Authority: the bounded commands, fixtures, tool versions, and measured outcomes
recorded by each acceptance document at its snapshot.

Scope: documents under `docs/verification.md`.

Status: historical evidence. These files do not override current regressions or
the machine-readable GA ledger.

Last reviewed: 2026-07-27.

Historical cross-references: `BUG-CDC-01`, `DOC-00`, and `DOC-02` in
[Missing Work](roadmap.md#source-docsplanningmissing-workmd).

<a id="source-docsacceptancereadmemd--how-to-use-an-acceptance-record"></a>
### How to use an acceptance record

An agent or release reviewer must perform these steps:

1. Read the record's date, accepted profile, endpoint role, target, tool
   versions, bounds, exclusions, and skipped tools.
2. Identify the exact good-DUT fixture, negative fixture or RTL mutant,
   generated artifact, result decoder, coverage point, and strict status result.
3. Verify whether a later qualification stage broadened the profile.
4. Check [Missing Work](roadmap.md#source-docsplanningmissing-workmd) for a current regression.
5. Check the [Capability Matrix](#source-docsqualificationcapability-matrixmd) for the
   intended current state, subject to its known `DOC-00`/`DOC-02` conflicts.
6. Check `qualification/policies/ga-gates-v1.json` for release gate state.
7. Use the least permissive current state whenever current evidence conflicts.
8. Never edit an older record to imply that a later capability existed at the
   original snapshot. Add a dated "Later changes" note and link instead.

An acceptance record proves only its stated bounds. It does not automatically
prove another protocol role, parameter value, target, simulator, formal engine,
HDL language, tool patch release, operating system, or customer design.

<a id="source-docsacceptancereadmemd--record-index"></a>
### Record index

| Record | Historical purpose | Read with |
| --- | --- | --- |
| [P0 Pilot Acceptance](#source-docsacceptancepilot-acceptancemd) | Initial end-to-end pilot workflow and correctness boundary | Current P0 regressions and capability matrix |
| [P1 Expansion Acceptance](#source-docsacceptancep1-acceptancemd) | Broader specialization, closure, document, coverage, and UVM snapshot | Current backlog and later stage records |
| [Bounded APB4](#source-docsacceptanceapb4-acceptancemd) | APB4 generated open-tool profile and mutation boundary | Stage 7 native promotion and `DOC-02` |
| [Bounded AXI4-Lite](#source-docsacceptanceaxi4-lite-acceptancemd) | Five-channel bounded AXI4-Lite profile | Stage 7 native promotion and `DOC-02` |
| [Feedback and Revision](#source-docsacceptancefeedback-revision-acceptancemd) | Immutable revision lineage and regeneration | Current revision schema and migration docs |
| [CDC Synchronizer](#source-docsacceptancecdc-synchronizer-acceptancemd) | Bounded CDC structures and mutation evidence | `BUG-CDC-01`, `CDC-01`, and current CDC policy |
| [Async FIFO](#source-docsacceptanceasync-fifo-acceptancemd) | Governed power-of-two asynchronous FIFO behavior | `CDC-01` for unsupported FIFO/CDC shapes |
| [Reset/RDC](#source-docsacceptancereset-rdc-acceptancemd) | Logical reset release and power sequencing | `RDC-01` and `PHYS-01` for physical evidence |
| [Memory Depth](#source-docsacceptancememory-depth-acceptancemd) | Bounded SRAM/parity historical snapshot | Current SECDED evidence is in the capability matrix and regression tests; `BUG-CDC-01` is closed |
| [Formal Depth](#source-docsacceptanceformal-depth-acceptancemd) | Bounded-response assumptions, invariants, liveness, and non-vacuity | `FORM-01` for unsupported formal semantics |
| [Parameter Sweep](#source-docsacceptanceparameter-sweep-acceptancemd) | Deterministic bounded elaboration points | Current parameter policy and scale records |
| [VHDL Normalization](#source-docsacceptancevhdl-normalization-acceptancemd) | Initial bounded VHDL normalization | Stage 9/10 evidence, `VHDL-01`, and `DOC-02` |
| [Stage 4](#source-docsacceptancestage4-acceptancemd) | Roadmap-to-implementation snapshot for Stage 4 | Later stage records and current capability matrix |
| [Stage 5](#source-docsacceptancestage5-acceptancemd) | Native result contracts and initial target boundary | Stage 7/9 promotions and `DOC-02` |

<a id="source-docsacceptancereadmemd--required-evidence-interpretation"></a>
### Required evidence interpretation

| Evidence | What it can prove | What it cannot prove |
| --- | --- | --- |
| Generated source or project | Deterministic renderer output exists | Compilation, execution, checking, coverage, or support |
| Compile/elaboration success | Tool accepted the bounded input | Functional correctness or mutation detection |
| Process exit zero | Process completed according to adapter mapping | Exact checks passed unless result traces map them |
| Exact check traces | Named checks reached pass/fail outcomes | Coverage closure or absence of vacuity by themselves |
| Coverage points | Declared behavior points were measured | Correct oracle behavior or unlisted behavior |
| Good-DUT run | Expected implementation can satisfy the contract | Checker sensitivity to defects |
| Killed mutant/negative fixture | One specified defect is detected | Other fault classes or a broader profile |
| Bounded formal pass | Property holds under stated bound/assumptions | Unbounded behavior or physical timing |
| Assumption witness/cover | Environment is reachable in the modeled bound | Completeness of real deployment assumptions |
| Mocked vendor result | Adapter/parser contract behavior | Licensed vendor execution |
| Signed vendor attestation | Exact signed run and payload identity | A different commit, tool version, profile, or customer design |

<a id="source-docsacceptancereadmemd--failure-and-edge-case-rules"></a>
### Failure and edge-case rules

- Missing fixture, log, tool version, source hash, result trace, or evidence path
  makes the claim incomplete.
- A skipped required tool is non-closing. An optional skip must be named and
  excluded from the support statement.
- Empty, duplicate, unknown, or unmatched result identities are non-closing.
- A passing old commit does not close a regression on the current commit.
- A newer schema must reject unless explicitly readable; an older schema must
  migrate conservatively and must not gain support state by default.
- A timeout, license failure, malformed report, killed process, or partial
  artifact publication is `unexecuted` or failed, never a pass.
- Formal evidence without reachability/non-vacuity evidence cannot promote
  liveness or environment-dependent claims.
- Aggregate coverage cannot conceal a missing mandatory point, ignored bin,
  zero denominator, or uncovered parameter point.
- Evidence copied across targets, tools, profiles, roles, or specializations is
  invalid unless the identity contract explicitly proves equivalence.

<a id="source-docsacceptancereadmemd--updating-this-directory"></a>
### Updating this directory

Follow the [Documentation Contract](agents.md#source-docsdocumentation-contractmd). For a new
acceptance record:

1. Add the required historical metadata.
2. Name exact profile, role, target, bounds, tools, fixtures, mutations, and
   commands.
3. Record exact passes, failures, skips, coverage, and strict status.
4. State unsupported adjacent behavior.
5. Link current capability state and backlog items.
6. Add the record to this index and the main [Documentation Index](README.md).
7. Run:

```bash
uv run python scripts/checks/repository_contracts.py
uv run python -m unittest \
  tests.documentation.test_docs \
  tests.repository.test_repository_contracts
```

<a id="source-docsacceptancepilot-acceptancemd"></a>
## P0 Pilot Acceptance

Consolidated from `docs/acceptance/pilot-acceptance.md`.

This remains the historical P0 gate. The current broader implementation is
defined by [P1 Expansion Acceptance](#source-docsacceptancep1-acceptancemd).

The P0 acceptance path proves that dv-platform can take a small but realistic
SystemVerilog design from source discovery through a strict, evidence-backed,
executable verification result without accepting stale or unverifiable state.

<a id="source-docsacceptancepilot-acceptancemd--supported-acceptance-slice"></a>
### Supported Acceptance Slice

The golden fixture under `tests/fixtures/pilot` contains:

- a parameterized vector counter;
- a top-level `WIDTH=12` elaboration override propagated into generated and
  executed collateral;
- a two-entry ready/valid stream buffer with vector data, unpacked storage,
  pointer wrap, and simultaneous push/pop case logic;
- a clock named `phase`, so clock discovery cannot depend on a `clk` suffix;
- an active-high reset named `clear_n`, so reset polarity cannot be guessed
  from its name;
- a hierarchical wrapper with structured child port connections and both
  original and elaborated child identities; and
- module-specific documentation for reset, increment, hold, connectivity,
  ready/valid transfer, latency, backpressure stability, and data integrity.

The simulation acceptance workflow runs:

```text
init --ci
  -> analyze-rtl
  -> index-docs
  -> plan --target cocotb
  -> generate --target cocotb
  -> run --target cocotb --all
  -> review
  -> status --policy ci
```

The same workflow is then repeated without input changes. The regression test
requires stable hashes for normalized RTL facts, retrieval indexes, plans,
claim reports, review reports, generated tests, and provenance manifests. It
also injects stale plan and generated files and verifies that regeneration
removes them.

The formal acceptance workflows analyze both a documented counter and the
memory-backed ready/valid buffer, generate their assumptions, assertions, cover
tasks, execution manifests, and traceability, and then require both the
SymbiYosys `prove` and `cover` tasks to pass. The stream proof checks that valid
and data remain stable under backpressure with a 12-bit elaborated parameter
configuration. Hosted CI
installs a pinned SymbiYosys revision with Yosys and Z3 and executes this test as
a mandatory step; it cannot pass by taking the local missing-tool skip.

<a id="source-docsacceptancepilot-acceptancemd--acceptance-checks"></a>
### Acceptance Checks

A change satisfies the P0 pilot gate when all of the following pass:

```bash
uv sync --all-groups --frozen
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run coverage json -o .dv-platform/python-coverage.json
uv run python scripts/checks/branch_coverage.py .dv-platform/python-coverage.json
uv build --out-dir .dv-platform/package-check
uv run pip-audit --skip-editable
```

Verilator and Icarus Verilog must be installed for the golden workflow. The
real-tool tests verify both cocotb execution and Verilator lint of generated
SystemVerilog. SymbiYosys, Yosys, and Z3 are mandatory in the hosted quality
job; the formal integration test may skip only in local environments without
that toolchain.

CI enforces Python 3.11, 3.12, and 3.13 compatibility. Its quality job installs
the open simulation and formal toolchains and executes the real-tool pilots in
addition to lint, format, typing, branch coverage, package build, and dependency
audit gates.

<a id="source-docsacceptancepilot-acceptancemd--correctness-guarantees-in-this-slice"></a>
### Correctness Guarantees in This Slice

- Work and output trees are excluded from fallback RTL discovery.
- Module-derived paths reject absolute paths, traversal, and path separators.
- Canonical text/JSON outputs use atomic replacement; generated module trees
  are staged and replaced as a unit.
- Regeneration removes stale module directories, stale module files, stale plan
  views, and stale claim views.
- Provenance schema v2 records the SHA-256 and byte size of every artifact.
- Runs reject missing, malformed, or tampered provenance and artifacts.
- Every generated module contains an execution manifest binding the adapter,
  generated file set, plan traces, project manifest digest, and SHA-256/size of
  every RTL input. Runs and CI status reject a changed input or manifest.
- Executable artifacts must map generated symbols back to plan checks,
  requirement IDs, behavior IDs, claim IDs, and evidence references. Missing
  traceability blocks publication.
- Run summaries are bound to the exact provenance SHA-256; regeneration makes
  earlier results stale, and CI requires a new matching run.
- Cocotb runs reject a missing result file, malformed result XML, zero executed
  testcases, failed testcases, and timeouts.
- `status --policy ci` requires current, non-empty RTL facts and plans; all
  planned outputs; artifact quality and integrity; required generator tool
  validation; no unexpected or unsafe generated roots; run results for
  executable generated targets; and configured tools unless
  `--no-require-tools` is explicit.
- CI accepts only the tested Verilator major version and records actual tool
  versions in analysis, validation, and run state.
- Generated HDL uses structured port direction, width, signedness, clock, reset,
  and reset-polarity facts where available. Verilator sensitivity information
  takes precedence over naming heuristics for sequential clock/reset inference.
- RTL facts and plans retain elaborated parameter values, memory shape,
  original and specialized child module identity, structured instance port
  connections, per-procedural-block control domains, and ready/valid channels.
- Clock/reset confidence and semantic feature support are target-specific.
  Case and internal memory constructs are accepted for the exercised black-box
  simulation/native/formal paths; constructs outside a target's support still
  fail closed.
- Requirements are deterministically categorized and deduplicated, retain exact
  document sentence offsets, and block generation when equivalent conditions
  prescribe conflicting values.
- Cocotb and formal summaries expose generated-symbol trace coverage, failed
  traces, triage classification, and repair suggestions through plan mappings.
  A passing tool result with an unexecuted generated symbol does not satisfy CI
  policy; per-check outcome attribution remains outside this slice.
- Formal reset assumptions constrain initialization and release, proof depth is
  selected from supported latency intent, prove and cover tasks are both run,
  ready/valid source stability is asserted, vector inputs are symbolic, and
  counterexample trace paths are retained when the tool emits them.

<a id="source-docsacceptancepilot-acceptancemd--boundaries-after-p0"></a>
### Boundaries After P0

This acceptance slice is deliberately narrower than full enterprise sign-off.
It supports explicit numeric top-parameter overrides for one elaborated
configuration using validated two-state SystemVerilog integer literals, not
parameter sweeps or multiple differently specialized copies of one source
module. Ready/valid inference covers conventional flat signal
names and one sink/source end-to-end pair; it is not a generic protocol library.
Multiple mapped clocks can be driven by cocotb, but CDC correctness, reset
sequencing across domains, interfaces/modports, complete SystemVerilog
semantics, production UVM environments, simulator code/functional coverage
closure, and commercial adapters remain open. UVM has no open compile validator
in the current adapter set, VHDL validation requires GHDL, and formal support is
limited to single-domain safety properties. These are explicit post-P0 gaps,
not silent assumptions.

<a id="source-docsacceptancep1-acceptancemd"></a>
## P1 Expansion Acceptance

Consolidated from `docs/acceptance/p1-acceptance.md`.

This document defines the broader internal-adoption slice implemented after the
P0 pilot. The scope is evidence-backed and fail-closed: a normalized fact is not
the same as a proof of correctness, and generators still refuse inputs whose
semantics cannot be represented safely.

Snapshot date: 2026-07-19.

<a id="source-docsacceptancep1-acceptancemd--accepted-capabilities"></a>
### Accepted Capabilities

<a id="source-docsacceptancep1-acceptancemd--semantic-identity-and-hierarchy"></a>
#### Semantic identity and hierarchy

- Every plan has a stable plan identity separate from the original RTL design
  unit, elaborated design unit, and specialization ID.
- Verilator normalization recognizes multiple elaborated specializations of one
  original module. Specializations receive deterministic identities, instance
  parameter bindings, and hierarchy links to the corresponding plan identity.
- Facts and plans preserve structured ports, parameters, types, memories,
  memory accesses, generate scopes, packages/imports, instances, assignments,
  procedures, control domains, assertions, covers, and protocols.
- Memory accesses record read/write direction, address/data/enable signals,
  synchronous behavior, domain, source location, and evidence. Unknown
  read-during-write policy remains explicit.
- Cross-domain signal flow records source/destination domains, inferred
  synchronizer stages, reset compatibility, structural classification, and
  evidence. Unproven crossings create critical review findings.

<a id="source-docsacceptancep1-acceptancemd--protocol-and-requirement-semantics"></a>
#### Protocol and requirement semantics

- Built-in flat ready/valid recognition remains available. Project-defined
  `ready_valid` and `req_ack` naming profiles can map different suffixes and
  payload names without code changes.
- Markdown, text, reStructuredText, and PDF specifications are indexed. PDF
  evidence includes page locators; encrypted or image-only PDFs fail with an
  actionable error instead of silently indexing empty text.
- Requirements, claims, behaviors, checks, and generated symbols have stable
  IDs and evidence references. Each check records its category and whether it
  is executable.

<a id="source-docsacceptancep1-acceptancemd--generation-execution-and-closure"></a>
#### Generation, execution, and closure

- Cocotb and formal execution expand generated trace records into independent
  pass/fail/unexecuted outcomes for every mapped check ID.
- Formal summaries retain prove/cover task status. Generated formal collateral
  includes reset/state-transition and handshake properties plus supported
  synchronous-memory write/address properties.
- Native SystemVerilog emits evidence-backed assertions and covers for supported
  behaviors and protocols.
- A single inferred sink/source handshake pair produces a UVM transaction,
  sequence, sequencer, driver, monitor, FIFO scoreboard, environment, test,
  virtual interface, config-db wiring, and DUT top. Ambiguous transaction
  boundaries continue to produce a conservative scaffold with open questions.
- `dv-platform coverage` imports and merges LCOV, JSON, and Cobertura-style XML,
  computes line/branch/toggle/functional metrics when supplied, applies project
  thresholds, reports module gaps, and feeds `status --policy ci`.

<a id="source-docsacceptancep1-acceptancemd--operations-and-extension-boundaries"></a>
#### Operations and extension boundaries

- RTL analysis has input-fingerprint caching and `--force` invalidation.
- Documentation indexing reuses embeddings for unchanged chunks.
- `run --all` uses bounded module-level concurrency configured by
  `execution.max_parallel_modules` while preserving deterministic summaries.
- Explicit adapter entry points use the versioned `dv_platform.<kind>` contract;
  kind and API mismatches fail before a mutating command runs.
- Mutating commands and tool runs append local owner-only audit events.
  Configured regular expressions redact command, log, summary, and audit text.
- Status reports schema compatibility, current generated/run state, imported
  coverage, and CI policy failures without invoking external tools.

<a id="source-docsacceptancep1-acceptancemd--acceptance-gate"></a>
### Acceptance Gate

The P1 slice is accepted when these commands pass:

```bash
uv sync --all-groups --frozen
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run coverage json -o .dv-platform/python-coverage.json
uv run python scripts/checks/branch_coverage.py .dv-platform/python-coverage.json
uv build --out-dir .dv-platform/package-check
uv run pip-audit --skip-editable
```

Where installed, the integration suite additionally exercises Verilator XML,
Verilator lint, Icarus/cocotb, and SymbiYosys/Yosys/Z3 prove and cover tasks.
Hosted CI keeps those real-tool gates mandatory.

<a id="source-docsacceptancep1-acceptancemd--deliberate-boundary"></a>
### Deliberate Boundary

This acceptance does not claim complete SystemVerilog or UVM semantics. The
normalizer is a conservative Verilator-XML interpretation, CDC recognition is
structural rather than sign-off analysis, and memory collision behavior remains
unknown unless evidenced. Parameter sweeps, generic multi-agent UVM,
register-model generation, asynchronous FIFO proofs, UCIS databases, commercial
tool adapters, and repository-scale benchmarks remain later work. The current
residual inventory is maintained in [Missing Work](roadmap.md#source-docsplanningmissing-workmd).

<a id="source-docsacceptanceapb4-acceptancemd"></a>
## Bounded APB4 Acceptance

Consolidated from `docs/acceptance/apb4-acceptance.md`.

Snapshot date: 2026-07-20.

Scope: `historical_snapshot`. Stage 7 promotion evidence later supersedes the
native-target boundary recorded here; the current capability authority is the
machine ledger and the current matrix above.

The bounded APB4 slave profile is supported for generated cocotb/Icarus and
formal/SymbiYosys/Yosys/Z3 collateral. A plan is executable only when the
normalized interface has the complete APB4 signal set, correct slave-facing
directions and widths, an unambiguous clock/reset with known polarity, and at
least one governed register whose offset, fields, reset values, byte-enable
behavior, and invalid-address behavior are known.

Typed `apb4_transfer` and `apb4_register_access` scenarios are the only source
for driver bindings, monitor and reference-model intent, assertions, covers,
trace symbols, and completion bounds. SystemVerilog native execution remains a
scaffold because it has no normalized per-scenario result decoder.

The acceptance test runs the complete CLI chain:

`analyze-rtl -> plan -> generate -> run -> coverage --from-runs -> status --policy ci`

The good DUT must pass every executable check with non-vacuous normalized
outcomes, and repeated deterministic generation must be byte-identical. Both
generated backends must reject mutants for discarded writes, ignored PSTRB,
writable RO fields, broken W1C behavior, missing PSLVERR, premature or dropped
PREADY, unstable wait-state responses, and incorrect reset values.

The qualification boundary is deliberately narrow: one APB4 slave, governed
RW/RO/W1C register semantics, byte strobes, invalid-address errors, and bounded
completion. Multi-slave fabrics, bridges, protection policy, low-power behavior,
and native simulator result normalization are not claimed.

<a id="source-docsacceptanceaxi4-lite-acceptancemd"></a>
## Bounded AXI4-Lite Acceptance

Consolidated from `docs/acceptance/axi4-lite-acceptance.md`.

Snapshot date: 2026-07-21.

Scope: `historical_snapshot`. The native-scaffold statement reflects this
snapshot; later Stage 7 evidence is the current authority for the bounded
native target state.

The bounded AXI4-Lite slave profile is supported for generated cocotb/Icarus
and formal/SymbiYosys/Yosys/Z3 collateral. A plan is executable only when
normalized evidence contains the complete AW/W/B/AR/R payload and handshake
set, correct slave-facing directions and compatible widths, an unambiguous
clock/reset with known polarity, linked stable checks, and at least one governed
register with known offset, fields, reset, WSTRB, and invalid-address behavior.

The typed `axi4_lite_single_outstanding` scenario is the only source for driver
bindings, independent channel timing, monitor/reference scoreboard state,
completion bounds, properties, covers, and trace symbols. The bounded profile
allows one read and one write outstanding at the same time. It exercises
AW-before-W, W-before-AW, same-cycle capture, simultaneous read/write progress,
B/R backpressure and payload stability, WSTRB including a zero-byte write,
valid and invalid response handling, reset recovery, and rejection of a second
outstanding AW or AR request.

The acceptance test runs the complete CLI chain:

`analyze-rtl -> plan -> generate -> run/prove -> coverage --from-runs -> status --policy ci`

The good DUT must produce a passing normalized outcome for every executable
check, reach non-vacuous channel/formal coverage, and generate byte-identical
collateral on repetition. Generated cocotb and formal backends must both reject
mutants for coupled AW/W acceptance, lost and early BVALID, unstable BRESP,
dropped RVALID, unstable RDATA/RRESP, ignored WSTRB, incorrect error responses,
and acceptance of second outstanding write or read requests.

SystemVerilog emits typed stability properties for all five channels but remains
a scaffold because native simulation has no scenario result decoder. Full AXI,
bursts, IDs, multiple outstanding transactions per direction, interconnect
ordering, protection/cache attributes, and performance guarantees are not
claimed.

<a id="source-docsacceptancefeedback-revision-acceptancemd"></a>
## Feedback and revision closure acceptance

Consolidated from `docs/acceptance/feedback-revision-acceptance.md`.

This document defines the qualified Stage 3 boundary. A feedback revision is
accepted only when its intent lineage and all replacement evidence are fresh.

| Roadmap requirement | Qualified implementation |
| --- | --- |
| Revision schema v3 | Immutable snapshots bind canonical-plan, RTL/project-manifest, parent-snapshot, affected dependency, scenario-selection, and rerun-target metadata. Legacy revisions remain readable. |
| Changed inputs | Canonical-plan or project-manifest drift rejects the chain unless feedback explicitly requests a fork. Snapshot and parent hashes are rechecked at generation. |
| Operation lifecycle | Every proposal records `proposed` followed by `validated` and `applied`/`no-op`, or `rejected` with a stable reason. |
| Dependency closure | Stable edges connect requirements, checks, scenarios, generated symbols, artifacts, runs, and coverage points. The selected closure is persisted per revision. |
| Targeted generation | Only affected paths are replaced within the selected target/module. Unrelated files and target/module directories are preserved; provenance is always refreshed. |
| Bounded AI synthesis | AI can only select existing scenario IDs and unchanged declared parameter values. It cannot add code, commands, renderers, checks, waivers, or executable claims. |
| Common AI record | Planning, scenario synthesis, and feedback persist purpose, sanitized endpoint identity, hashes, cache state, diagnostics, retry/token/cost metadata, and deterministic fallback reason. |
| Mandatory fresh evidence | `status --policy ci` rejects an actionable latest revision until every required target is generated, rerun with the exact provenance hash, and included in a passing coverage import. |

The qualified sequence is:

```text
feedback -> generate --revision -> run -> coverage --from-runs -> status --policy ci
```

Tests cover schema round trips, explicit forks, stale/tampered snapshots,
malformed lifecycle state, dependency selection, unrelated-byte preservation,
stale-run invalidation, bounded synthesis repair/fallback, audit permissions, and
the full pending-generation/pending-run/pending-coverage/closed transition.

<a id="source-docsacceptancecdc-synchronizer-acceptancemd"></a>
## CDC synchronizer acceptance

Consolidated from `docs/acceptance/cdc-synchronizer-acceptance.md`.

The qualified CDC profile covers externally observable two-flop chains governed
by an explicit `verification_depth` policy. It does not infer a scheme from
signal names.

Supported structures are:

- `toggle`: both level transitions propagate through the ordered chain and
  remain stable at the destination;
- `pulse`: the source pulse is stretched for at least the synchronizer depth,
  observed at the destination, and returns to idle;
- `handshake`: request and acknowledgement use independent qualified chains,
  bounded round-trip completion, request holding, and payload stability;
- `multi_bit_handshake`: paired input and destination-observation payloads have
  equal known widths and are sampled and compared as one coherent transfer;
- `gray`: an observable multi-bit Gray counter is checked under the explicit
  `max_source_steps_per_destination = 1` environment bound required for a
  one-bit observed-transition guarantee.

External inputs, ordered stage signals, destination clock/reset, stage count,
and reset compatibility are normalized facts. Policy validation fails closed
for ambiguous paths, missing or incorrect outputs, short pulse stretch,
unqualified acknowledgement paths, mismatched payloads, unknown widths, or an
unbounded Gray source rate.

Generated cocotb tests drive and observe every transition with finite timeouts.
Generated formal collateral checks every observable stage, covers rise/fall,
pulse observation/return, request observation, handshake round trip, sampled
payload coherency, and Gray transitions, and records the bounded environment
assumptions. Zero tests, unmatched symbols, or absent covers cannot close the
mapped checks.

The full CLI good DUT is byte-reproducible and passes analyze, plan, generate,
simulation/formal run, coverage, and strict status. Structure-preserving mutants
for corrupted toggle, pulse, request, acknowledgement, coherent payload, and
Gray propagation are killed by both generated cocotb and formal collateral.

Reconvergent CDC, unconstrained multi-bit buses, and schemes without a governed
structural contract remain unsupported. Async-FIFO Gray pointers are supported
through the separate governed [async FIFO profile](#source-docsacceptanceasync-fifo-acceptancemd).

<a id="source-docsacceptanceasync-fifo-acceptancemd"></a>
## Async FIFO and Gray-pointer acceptance

Consolidated from `docs/acceptance/async-fifo-acceptance.md`.

The qualified async-FIFO profile is an explicitly governed, bounded open-tool
profile. It is executable only when the configured storage resolves to one
power-of-two unpacked memory with known element/address widths, one synchronous
write access, one qualified registered or FWFT read access, distinct normalized clock/reset
domains, observable data/control/status ports, depth-sized binary and Gray
pointers, and two ordered Gray-pointer synchronizer chains.

The policy is a mapping contract, not evidence by itself. Planning rejects a
missing or ambiguous access, same-clock configuration, conflicting access
domain, incorrect data/pointer width, incomplete signal mapping, short or
ambiguous synchronizer, and non-power-of-two depth. Independent FIFO reset
domains are permitted only for the two policy-qualified Gray crossings; this
does not promote unrelated unsafe crossings.

Generated cocotb collateral owns the driver, monitor, reference queue, and
timeouts. It fills and drains the FIFO, observes `full` and `empty`, checks that
a full write is rejected, compares every read against write order, crosses the
pointer wrap boundary, runs unequal concurrent clocks, checks reset recovery,
and validates binary-to-Gray encoding and one-bit Gray transitions. All loops
are finitely bounded and the scenario owns explicit non-vacuity bins.
When `first_word_fall_through = true`, the scoreboard samples the visible head
before asserting the dequeue signal and requires every accepted word to match.

Generated formal collateral uses vector-width stage histories for both pointer
crossings and emits reset, binary/Gray encoding, one-bit transition, accepted
increment, blocked hold, full-equation, and empty-equation assertions. Separate
write, read, full, empty, and synchronized-propagation covers must be reachable.
The FWFT variant additionally proves stable visible head data while neither
endpoint advances and covers a nonempty FIFO with dequeue deasserted.
The harness tracks each asynchronous clock/reset event independently instead of
using a single-clock `$past` approximation.

The full CLI good DUT is byte-reproducible and closes exact per-check outcomes
through analyze, plan, generate, Icarus/cocotb or SBY/Yosys/Z3 execution,
coverage, and strict status. Generated cocotb kills mutants for misaddressed
writes, ignored full, incorrect empty, non-Gray write pointers, corrupted Gray
synchronization, misaddressed reads, broken wraparound, and corrupt FWFT head
data. Generated formal
kills the five structural/status mutants it claims; memory ordering/address
mutants remain simulation-scoreboard qualifications and are not described as
formal proofs.

Non-power-of-two FIFOs, multiple read/write ports, arbitrated or multi-port
storage, ECC/parity, standalone multi-bit coherency,
reconvergence, and schemes without this exact governed contract remain
unsupported.

<a id="source-docsacceptancereset-rdc-acceptancemd"></a>
## Reset-domain and RDC acceptance

Consolidated from `docs/acceptance/reset-rdc-acceptance.md`.

The qualified reset-domain profile is explicitly governed. A reset policy is
executable only when its reset resolves uniquely to one normalized control
domain, its configured clock and asynchronous-assertion style agree with RTL,
and its scalar ready indication is an observable output.

An optional power-sequence extension requires an observable scalar
`power_good_signal` input and distinct scalar `isolation_signal` and
`retention_signal` outputs. Missing, aliased, or directionally inconsistent
mappings fail closed. Ready remains low while power is unavailable; isolation
and retention remain asserted until the powered domain completes release.

Ordered domains additionally require `depends_on_reset`, `depends_on_ready`,
and `dependency_sync_signal`. The dependency must belong to a distinct reset
domain and its ready indication must cross through one unambiguous, ordered,
two-stage synchronizer ending at the configured dependency-sync output. Only
this policy-qualified RDC path is promoted; unrelated unsafe crossings remain
open. Self-dependencies and dependency cycles are contradicted claims.

Generated cocotb scenarios start independent clocks, assert all involved resets,
release a dependent reset while its prerequisite remains active, and prove the
dependent ready signal stays low. They then release the prerequisite, observe
its ready indication and synchronized RDC path, enforce the configured release
delay, and require bounded downstream readiness. A second phase asserts reset
between clock edges, checks immediate asynchronous clearing, applies governed
recovery/removal offsets, checks early-release exclusion, and rejects unresolved
post-reset values. Every wait is finite.

For a power-governed domain, the scenario first holds power good low and proves
ready, isolation, and retention remain safe, then applies power good and checks
the bounded release. Reset reassertion immediately restores isolation and retention.

Generated formal collateral checks asynchronous ready clearing, ordered hold,
release-delay hold, and bounded ready assertion independently in each clock
domain. It proves every observable RDC synchronizer stage and requires covers
for dependency observation and domain release. The environment assumption that
a reset release is monotonic during one proof episode is emitted explicitly;
reassertion and recovery are exercised by simulation rather than hidden inside
that assumption.

Formal power properties check the no-power hold state and require isolation and
retention to be deasserted whenever a powered domain advertises readiness.

The full CLI good DUT is byte-reproducible and closes exact per-check outcomes
through analyze, plan, generate, Icarus/cocotb or SBY/Yosys/Z3 execution,
coverage, and strict status. Both generated backends kill mutants for broken
source/destination asynchronous assertion, early source/destination release,
dependency bypass, corrupted RDC synchronization, premature isolation or
retention release, and power-good bypass.

Analog recovery/removal timing, reset-tree physical analysis, hidden
synchronizer stages, non-monotonic proof episodes, macro-specific power states,
and reset dependencies without the governed observable contract remain unsupported.

<a id="source-docsacceptancememory-depth-acceptancemd"></a>
## Bounded Memory Depth Acceptance

Consolidated from `docs/acceptance/memory-depth-acceptance.md`.

Snapshot date: 2026-07-21.

Scope: `historical_snapshot` for the parity-only acceptance. Later SECDED
qualification is recorded by the current capability authority and does not
rewrite this earlier snapshot.

The executable memory profile is deliberately narrow. It requires one normalized,
byte-addressable synchronous memory with known depth, address width, and element
width; one clock/reset domain; one observable synchronous read port; two observable
write requesters; per-requester byte enables and grants; a declared collision mode;
zero initialization; round-robin arbitration; and observable parity fault injection
and detection. Every configured signal is checked for direction and width before the
`memory_bounded_sram` scenario can become executable.

Generated cocotb collateral maintains a reference image of every legal address. It
checks reset initialization and recovery, low/high addresses, full and partial writes,
byte-lane preservation, declared read-during-write behavior, exclusive and alternating
grants under contention, both requesters, clean parity reads, injected parity errors,
bounded completion, and non-vacuity. Generated formal collateral proves grant
exclusivity/work conservation, two-requester round-robin behavior, collision response,
parity outcomes, and a byte-merged reference word at address zero; covers exercise
both grants, contention, both collision paths, and parity injection. Exhaustive address
initialization and high-address behavior remain simulation-qualified to keep the open
solver task bounded and reproducible.

The complete CLI path is qualified through analyze, plan, generate, run/prove,
coverage reconciliation, and strict status. Repeated generation is byte-identical.
The good DUT passes generated cocotb and formal collateral. Both backends kill eight
mutants: ignored byte enables, wrong read-during-write semantics, fixed-priority
starvation, incorrect initialization, missing parity detection, non-exclusive grants,
a discarded port-1 write, and a misaddressed read. Every executable check receives an
exact normalized result; zero or unmatched tests remain unexecuted.

The profile does not claim SECDED correction, repair/scrubbing, initialization files,
asynchronous or more-than-two-requester memories, multiple physical read ports,
independent clock domains, power-state retention, cache/coherency behavior, or physical
memory-macro timing. Those cases remain unsupported and cannot inherit this profile's
closure evidence.

<a id="source-docsacceptanceformal-depth-acceptancemd"></a>
## Bounded Formal Contract Acceptance

Consolidated from `docs/acceptance/formal-depth-acceptance.md`.

Snapshot date: 2026-07-21.

The qualified `bounded_response` verification-depth profile turns an explicit
trigger, response, and invariant mapping into typed formal intent. It requires
distinct scalar observable signals, one normalized clock/reset domain, a trigger
pulse assumption, response causality, and a configured latency bound from 1 to
64 cycles. Missing or ambiguous facts keep the scenario non-executable.

Generated SymbiYosys collateral contains a property-specific trigger assumption,
an internal pending/age induction invariant, a design invariant, response
causality, bounded liveness, and separate assumption-witness, response, and
completion covers. The proof task uses induction; cover tasks establish that the
assumption does not constrain away all requests and that completion is reachable.

The full CLI acceptance fixture passes the good DUT and repeated generation is
byte-identical. Generated formal collateral kills four mutants: missing response,
late response, broken invariant, and a non-causal response. Every executable
check receives a normalized result; missing properties or vacuous output cannot
close coverage.

This acceptance is bounded to the configured request/response contract. General
temporal-property synthesis, inferred environment assumptions, fairness, and
unbounded liveness remain unsupported.

<a id="source-docsacceptanceparameter-sweep-acceptancemd"></a>
## Parameter-Sweep Cross-Point Acceptance

Consolidated from `docs/acceptance/parameter-sweep-acceptance.md`.

Snapshot date: 2026-07-21.

Explicit `parameter_sweeps` are analyzed in isolated work directories and retain
unique module, plan, evidence, generated-artifact, and run identities. Coverage
schema v3 groups those points by original design unit and canonical check
semantics, then reports every specialization and every semantic cross-point.

A cross-point closes only when its corresponding check closes at every configured
elaboration point. Missing plans, missing points, failed or unexecuted checks, and
stale evidence produce named gaps. `coverage` fails on an incomplete cross-point,
and `status --policy ci` reports `parameter_sweep_coverage_incomplete` rather than
allowing aggregate percentages to hide the missing configuration.

The real-tool acceptance runs WIDTH=4 and WIDTH=9 through Verilator analysis,
planning, deterministic cocotb generation, Icarus/cocotb execution, run-derived
coverage, and CI status. Unit coverage also verifies the negative case in which
one specialization is not covered. Automatic Cartesian-product discovery and
cross-project aggregation remain out of scope; every point must be explicitly
configured.

<a id="source-docsacceptancevhdl-normalization-acceptancemd"></a>
## Bounded VHDL Normalization Acceptance

Consolidated from `docs/acceptance/vhdl-normalization-acceptance.md`.

Snapshot date: 2026-07-21.

VHDL-only projects have a deterministic source normalizer for one unambiguous
architecture per selected entity. The qualified interface subset includes
integer, natural, and positive generics; numeric overrides and explicit
sweeps; scalar logic/bit/boolean ports; constrained `std_logic_vector`,
`std_ulogic_vector`, `signed`, and `unsigned` ports; and generic-dependent `to`
or `downto` ranges.

Normalized facts retain entity and architecture identity, specialization hash,
generic values, port directions/types/widths, source locations, VHDL-source
evidence, edge-derived clocks, named resets, process facts, asynchronous reset
ownership, simple reset/increment patterns, and concurrent assignments. The
facts round-trip through RTL-facts schema v10 and drive conservative VHDL
planning and deterministic collateral generation without invoking Verilator.

The CLI acceptance analyzes two generic sweep points, plans both entity
specializations, generates byte-identical GHDL-valid VHDL collateral on
repetition, and preserves the original entity in each DUT binding. A separate
observable reset fixture completes analyze, plan, generate, GHDL 4.1.0
analyze/elaborate/run, coverage ingestion, and CI status with one exact
normalized per-check result. Unknown generic overrides,
missing architectures, multiple ambiguous architectures, unresolved expressions,
and unconstrained or unsupported interface types fail closed. Required Slang
cross-check mode also fails closed because the qualified Slang adapter is
SystemVerilog-only.

This accepts bounded normalization and the observable reset execution slice, not
general VHDL sign-off. Mixed-language binding is explicitly rejected, scenarios
outside the registered reset renderer remain scaffolded or unsupported, and
packages, records, subtypes, generate elaboration, and broader behavioral
semantics remain open.

<a id="source-docsacceptancestage4-acceptancemd"></a>
## Stage 4 Verification-Depth Acceptance

Consolidated from `docs/acceptance/stage4-acceptance.md`.

Snapshot date: 2026-07-21.

Stage 4 is complete for the bounded profiles below. “Complete” means every
roadmap item has a deterministic implementation and an explicit fail-closed
boundary; it does not broaden a bounded profile into general RTL sign-off.

| Roadmap item | Implemented qualification | Acceptance evidence |
| --- | --- | --- |
| Pulse/toggle/handshake synchronizers | Two-flop, pulse-stretch, toggle, and round-trip request/acknowledge policies with ordered observable stages | Generated cocotb/formal good-DUT and four-mutant matrices, trace closure, non-vacuity, deterministic bytes |
| Async FIFOs and Gray pointers | Power-of-two, dual-clock bounded FIFO with normalized storage/access facts and two ordered Gray synchronizers | Queue scoreboard, formal pointer/flag properties, seven simulation and five formal mutants |
| Reset-domain dependencies and RDC | Observable asynchronous assertion, ordered release, acyclic dependencies, two-stage ready crossing, bounded recovery/removal intent | Generated cocotb/formal good-DUT and six-mutant matrices |
| Memory semantics | Bounded synchronous byte-addressable SRAM with byte enables, collision policy, two-requester round-robin arbitration, zero initialization, and parity | Exhaustive scoreboard, bounded formal reference word, eight-mutant simulation/formal matrices |
| Assumptions, invariants, and liveness | Property-specific pulse assumption, causal bounded response, induction state/design invariants, and assumption-consistency covers | Real induction proof plus four formal mutants and non-vacuity covers |
| Parameter sweeps | Per-point identities plus coverage-schema-v3 semantic cross-point aggregation | Real WIDTH=4/WIDTH=9 analyze-to-CI pipeline and incomplete-cross-point negative tests |
| VHDL normalization | VHDL-only entity/generic/architecture/process normalization with generic sweeps and source evidence | Parser fail-closed tests and deterministic analyze-to-VHDL-generation CLI acceptance |

The detailed contracts are documented in the linked acceptance documents from
the project README. General CDC/RDC/memory structures, inferred formal
environments, implicit parameter products, mixed-language elaboration, and VHDL
execution remain later-stage capabilities and are never reported as supported.

<a id="source-docsacceptancestage5-acceptancemd"></a>
## Stage 5 target and adapter acceptance

Consolidated from `docs/acceptance/stage5-acceptance.md`.

Snapshot date: 2026-07-21.

This acceptance compares roadmap Stage 5 with the implemented target runners,
tool qualification policy, and adapter connections. It distinguishes repository
implementation from evidence that can only be produced on a licensed deployment.

<a id="source-docsacceptancestage5-acceptancemd--roadmap-comparison"></a>
### Roadmap comparison

| Roadmap requirement | Implemented evidence | Acceptance |
| --- | --- | --- |
| Qualify generated UVM with one licensed simulator | `qualification-bundle --generated-uvm` packages byte-stable UVM produced by `UvmGenerator`, its loopback DUT, content hashes, and mandatory `QUAL-UVM-001`. AMD Vivado Simulator 2025.2 compiled and ran that exact UVM 1.2 environment with 16 scoreboard transactions and zero UVM errors/fatals. | Accepted for the paired ready/valid UVM profile. The tamper-evident `vivado_xsim` attestation is checked in and re-imported by the regression suite. Conservative fallback UVM remains scaffolded. |
| Native SystemVerilog and Verilog normalized results | Icarus wrappers compile the manifest-bound RTL and generated bench, execute `vvp`, and require exact `DV_PLATFORM_RESULT_V1` records for every generated trace. Unknown, duplicate, partial, malformed, zero-result, or failed outcomes do not close checks. | Accepted for the generated reset-to-constant vertical slice; broader native scenario depth remains partial. |
| VHDL/GHDL normalized results | The VHDL generator emits type-correct reset, profile handshake, completion, and result checks. The GHDL runner analyzes, elaborates, and runs VHDL-2008 collateral and uses the same exact trace decoder. | Accepted for the broad VHDL profile mutation matrix with GHDL 4.1.0; the real pipeline closes through coverage and CI status. |
| Tested tool ranges | CI status and run summaries classify the real backend, not a Python wrapper. Enforced ranges are Verilator 5, Icarus 12, SBY 0.67, Yosys 0.33, Z3 4.8, and GHDL 4–5. SBY records Yosys and Z3 separately. The vendor attestation retains exact Vivado Simulator 2025.2 identity. | Accepted. Presence without a supported version is insufficient in CI policy. |
| Connect document/OCR, embedding, vector, reporting, policy, coverage, simulator, and formal adapters | Versioned entry points now include local text/PDF and governed OCR-sidecar loaders, local hash embeddings, JSON vector storage, deterministic report manifests, regex redaction, UCIS XML, five simulator profiles, and three formal profiles. Indexing and planning use configured document/embedding/vector adapters. Enterprise execution produces normalized closure points. | Accepted for the named built-in contracts. Proprietary database/API depth remains vendor-specific. |
| Vendor exit code must never close checks | Native and enterprise execution both require normalized, traceable, non-empty results. Strict enterprise execution rejects missing trace IDs and skipped/unknown states; a passing process without a result remains non-closing. | Accepted. |

<a id="source-docsacceptancestage5-acceptancemd--qualified-native-subset"></a>
### Qualified native subset

The native SystemVerilog, Verilog, and VHDL generators are executable only for a
normalized reset-to-constant behavior with a stable mapped check. VHDL further
requires every checked target to be an observable entity port. Other scenarios
retain their renderer-registry `scaffold` or `unsupported` state. This is a
deliberately narrow qualification and does not promote native APB4, AXI4-Lite,
CDC, memory, or general behavioral benches.

<a id="source-docsacceptancestage5-acceptancemd--vivado-simulator-uvm-qualification"></a>
### Vivado Simulator UVM qualification

AMD documents that Vivado Simulator provides a precompiled UVM 1.2 library and
requires `-L uvm` for standalone `xvlog` and `xelab`. The `vivado_xsim` bundle
includes a dedicated wrapper which applies that library plus a global elaboration
timescale required by XSim. The accepted run used the Windows Vivado 2025.2
installation from WSL:

```console
dv-enterprise qualification-bundle \
  --profile vivado_xsim \
  --generated-uvm \
  --output vivado-xsim-uvm-qualification.zip
```

The wrapper requires reference simulation completion, the named generated UVM
test, UVM phase completion, and zero UVM errors/fatals before emitting normalized
passing checks. A process exit without those markers fails. The imported evidence
is [Vivado XSim 2025.2 qualification attestation](../qualification/evidence/vivado-xsim-2025.2-qualification-attestation.json),
with `vendor_verified` checks `QUAL-SIM-001` and `QUAL-UVM-001`.

<a id="source-docsacceptancestage5-acceptancemd--verification"></a>
### Verification

The current integrated run passes 578 tests with one expected optional skip: the
opt-in live-AI smoke test. With Slang 11.0.424 on `PATH` and the qualified gate
enabled, all three Slang tests run and pass. The GHDL integration is active and
passes against GHDL 4.1.0.
It includes real Icarus native compilation/execution, the installed formal
toolchain, exact result-decoder negative cases, deterministic UVM bundle and
attestation tamper tests, adapter entry-point/CLI tests, and the real GHDL
pipeline. Ruff, formatting, mypy, and every coverage ratchet pass. Measured
combined coverage is 86.23%, statement coverage is 89.13%, and true branch
coverage is 78.25% across 5,302 branches. Source/wheel builds and the dependency
audit also pass.
