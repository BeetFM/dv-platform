# Capability Matrix

Snapshot date: 2026-07-22.

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
| SystemVerilog | Self-checking native reset, APB4, and AXI4-Lite benches with typed transactions, scoreboards, bounded waits, response stability, errors, strobes, and outstanding-limit checks | Verilator lint plus an Icarus compile/run wrapper for the qualified slices | Exact generated trace IDs are mandatory; missing, duplicate, unknown, partial, malformed, or failed native results do not close | `supported` for reset and the bounded APB4/AXI4-Lite profiles; broader behavior remains `partial` |
| Verilog | Portable Verilog-2001 self-checking reset, APB4, and AXI4-Lite benches using the same typed intent and result contract | Verilator lint plus an Icarus compile/run wrapper; SystemVerilog DUT sources select the required compile standard without changing the generated Verilog bench dialect | Uses the same exact native result decoder as SystemVerilog | `supported` for reset and the bounded APB4/AXI4-Lite profiles; broader behavior remains `partial` |
| VHDL | GHDL-authoritative entity/generic/package/type/architecture facts drive typed reset, ready/valid, and declared production-profile checks | GHDL 4.1.0 VHDL-2008 analysis/elaboration is mandatory; packages, records, subtypes, arrays, generate scopes, explicit architecture selection, and profile transactions are retained | Generated result records use exact trace reconciliation; AXI4-Stream good RTL and four VHDL mutants close | `supported` for declared VHDL-capable profiles; ambiguous architecture or mixed-language binding fails closed |
| UVM | Multi-agent protocol packages, sequences, drivers, monitors, scoreboards, virtual sequencing, cross-protocol scoreboards, and normalized-register RAL | Open generation is deterministic; Vivado bridge/project execution remains the available local vendor path | Licensed imports require exact checks, zero UVM errors/fatals, non-vacuity, and signed evidence before `vendor_verified` | `partial`: broad profiles are `contract_verified`; the earlier paired ready/valid Vivado evidence remains the only vendor-qualified profile |

## Protocol and register depth

| Profile | Recognition | Scenario/generation depth | State |
| --- | --- | --- | --- |
| APB4 slave | Complete named PSEL/PENABLE/PREADY/PWRITE/PADDR/PWDATA/PSTRB/PRDATA/PSLVERR interface, directions, widths, and clock/reset facts are retained; ambiguity becomes an unsupported semantic | Typed scenarios drive cocotb, formal, native SystemVerilog, and native Verilog. Full CLI qualification covers reset, setup/access, waits, stable controls/responses, completion, PSTRB, RW/RO/W1C, invalid addresses, and PSLVERR. Good RTL passes and nine mutants are killed on every claimed backend. | `supported` for the bounded slave profile; broader APB semantics remain unsupported |
| AXI4-Lite slave | Complete AW/W/B/AR/R payload and handshake set with slave directions, byte-addressable matching data widths, WSTRB lanes, two-bit responses, matching address widths, and unambiguous clock/reset; incomplete or ambiguous signatures fail closed | Typed bounded scenarios generate independent AW/W timing, one-read/one-write outstanding handling, monitor/reference scoreboards, bounded completion, response backpressure/stability, WSTRB, errors, invalid addresses, reset recovery, and formal properties. Full-CLI good-DUT and ten-mutant matrices pass on cocotb, formal, native SystemVerilog, and native Verilog. | `supported` for the bounded slave profile; full AXI, bursts, IDs, and more than one outstanding transaction per direction are `unsupported` |
| Broad protocol profiles v1 | Complete canonical or explicitly aliased signatures bind fail-closed to versioned AXI4, packet-complete AXI4-Stream, Wishbone B4, Avalon-MM, Avalon-ST, burst-capable AHB, and non-coherent TileLink UL/UH transaction contracts. Endpoint role, multiple-instance identity, bounds, ordering, scoreboard keys, coverage bins, formal obligations, and traces are retained. | Shared typed drivers/monitors/reference models/scoreboards, cocotb, bounded formal, native SystemVerilog/Verilog, declared VHDL targets, UVM contracts, exact trace decoding, and functional bins are generated. Six broad endpoints pass a full CLI/formal run; AXI4-Stream has packet/VHDL mutation closure and every other profile kills an RTL acceptance/completion mutant. | `supported` for the bounded generated transaction contract; exhaustive behavior matrices and signed licensed UVM execution remain qualification work |
| AHB-Lite | Qualified 32-bit, single-master, single-beat slave signature with `HREADYOUT`, known reset, and governed RW/RO/W1C register behavior | Typed driver/monitor/reference-model scenarios and bounded formal properties close exact checks, wait states, invalid-address errors, reset recovery, and a six-mutant matrix | `supported` for the [bounded single-beat profile](../qualification/ahb-lite-single-beat.md); bursts, split/retry, protection semantics, and multi-layer interconnect are `unsupported` |
| Ready/valid | One named sink/source pair with data, common clock, and known reset | Generated cocotb checks acceptance, end-to-end data, backpressure stability, and recovery; a four-mutant matrix closes the bounded stream profile. Formal source-side stability assertions remain a narrower safety claim. | `supported` for the bounded paired-stream profile; AXI-Stream sidebands and multi-channel routing are unsupported |
| UART controller | Complete governed TX/RX control, data, status, error, clock, and reset mappings with 8-bit data and bounded bit timing | Generated cocotb models TX and RX frames, baud timing, parity modes, one/two stop bits, break, framing/parity errors, overflow, and recovery. Formal properties cover idle, busy/completion, error causality, and non-vacuity. The good DUT and ten mutants close. | `supported` for the bounded 8-bit controller profile; fractional baud generation, arbitrary word sizes, flow control, and multi-drop extensions are unsupported |
| SPI master | Complete governed master controls and SCLK/MOSI/MISO/chip-select mappings with 8-bit words and a bounded divider | Generated cocotb exercises CPOL/CPHA modes 0–3, MSB/LSB-first transfers, select framing, clock edges, receive data, completion, and timeout. Formal safety/non-vacuity passes; the good DUT and nine mutants close. | `supported` for the bounded single-lane master profile; multi-lane, multi-master, streaming, and device-specific framing are unsupported |
| I2C master | Complete governed controller and separate open-drain drive-low/sampled-bus mappings, 7-bit addresses, bounded divider/stretch/transfer timing | A wired-AND BFM checks bus busy, START/STOP/repeated START, address and data serialization, combined reads, ACK/NACK, clock stretching, arbitration loss, and recovery. Formal safety/non-vacuity passes; the good DUT and eight mutants close. | `supported` for the bounded 7-bit master profile; 10-bit addressing, high-speed modes, SMBus, multi-controller fairness, and analog electrical sign-off are unsupported |
| GPIO/timer/interrupt subsystem | Exact 4-bit GPIO and interrupt mappings plus governed 8-bit timer/watchdog/PWM controls in one known clock/reset domain | Generated cocotb checks GPIO direction, masked write/set/clear, edge/level IRQs, prescaled periodic timer, watchdog feed/IRQ/reset, PWM duty/polarity, and fixed-priority interrupt mask/clear/ack. Formal safety/non-vacuity passes; the good DUT and ten mutants close. | `supported` for the bounded subsystem profile; arbitrary widths, capture/compare/DMA, cascaded controllers, and programmable arbitration are unsupported |
| Register model | Offset, fields, reset/access metadata, byte-enable and invalid-address policies from governed/normalized sources | A scenario is executable only when dependent semantics are known; the qualified APB4 and bounded AXI4-Lite register subsets are scoreboard- and mutation-tested. Unknown behavior stays open. | `supported` for the qualified APB4 and bounded AXI4-Lite subsets; `partial` elsewhere |
| CDC synchronizers | Ordered externally observable stages plus an explicit two-flop, pulse-stretch, toggle, request/acknowledgement, coherent multi-bit handshake, or bounded-rate Gray-counter policy | Typed bounded scenarios generate independent cocotb transition/round-trip/coherency checks and formal stage, stability, sampled-payload, Gray-transition, and non-vacuity properties. Good-DUT and six-mutant matrices pass on generated cocotb/formal collateral. | `supported` for governed observable profiles; hidden and reconvergent schemes remain fail-closed |
| Async FIFO / Gray pointers | One normalized power-of-two memory, distinct write/read domains, explicit port/pointer mappings, optional first-word-fall-through read semantics, and two ordered depth-sized Gray synchronizers | Generated cocotb queue scoreboards fill/drain, sample FWFT data before dequeue, check full/empty blocking, ordering, wraparound, unequal clocks, reset recovery, encoding, and one-bit transitions. Generated formal checks vector stages, pointer encoding/increment/hold, flag equations, FWFT stability, reset, and non-vacuity. The good DUT and eight simulation/five formal mutants pass the declared matrix. | `supported` for the governed bounded registered/FWFT profile; multiple ports, non-power-of-two depth, standalone coherency, and reconvergence remain unsupported |
| Reset domains / RDC | Unique reset-to-control-domain ownership, exact clock/assertion style, observable ready output, bounded release policy, and an optional acyclic dependency through an ordered two-stage ready synchronizer | Generated cocotb checks asynchronous assertion, prerequisite hold, ordered release, recovery/removal offsets, bounded readiness, and resolvability. Generated formal checks async clear, guarded hold/release, every RDC stage, monotonic-release assumptions, and non-vacuity. Good-DUT and six-mutant matrices pass on both backends. | `supported` for the governed observable profile; physical timing, hidden stages, and architectural power sequencing remain unsupported |
| Bounded synchronous memory | One known byte-addressable synchronous memory and clock/reset domain, one read port, two write requesters with byte enables/grants, declared collision/zero-init/round-robin policy, and parity or SECDED mappings | Generated cocotb and formal cover byte merges, collisions, arbitration, reset, parity, single-error correction, double-error detection, and scrub completion. Parity closes eight mutants; SECDED closes five mutants on both backends. | `supported` for parity and SECDED/scrub bounded SRAM profiles; init files, asynchronous/more-than-two-port storage, retention, and macro timing remain unsupported |
| Bounded formal contract | Distinct trigger/response/invariant mappings in one normalized clock/reset domain, with pulse and causality policy plus a 1–64-cycle bound | Generated induction proves state/design invariants, response causality, and bounded liveness; assumption-witness/response/completion covers establish non-vacuity. Good DUT passes and four mutants are killed. | `supported` for the governed bounded-response profile; inferred assumptions and general/unbounded temporal synthesis remain unsupported |

## Platform services

| Capability | State | Boundary |
| --- | --- | --- |
| Plan schema v18 | `supported` | Versioned protocol transaction contracts retain instance/role, burst and outstanding bounds, scoreboard keys, coverage bins, formal properties, and result traces. Plans v1-v17 remain readable; v16 static mappings migrate to `unsupported` and require re-planning. |
| Immutable revisions v3 | `supported` | Revisions bind canonical-plan, RTL-manifest, and parent-snapshot hashes plus affected checks/scenarios/artifacts, selected template parameters, and rerun targets. Changed inputs require an explicit fork; legacy records remain readable. |
| Validation result v1 | `supported` | Simulation/formal summaries carry a common check-result envelope. No checks or unmatched tool output is `unexecuted`, regardless of exit code. |
| Parameter-sweep coverage v3 | `supported` | Coverage groups explicit elaboration points by design unit and canonical check semantics. Every semantic cross-point must close at every configured point; incomplete matrices fail coverage and CI status. |
| RTL facts v11 | `supported` | Protocol transaction contracts and channel payload/completion rules round-trip while VHDL source evidence and normalization frontend identity remain independently preserved. |
| LiteLLM planning | `partial` | Explicit opt-in, bounded context/output, local cache, credential indirection, content-free audit, deterministic fallback, and proposal v1 compatibility exist. Planning now uses the common same-model repair gateway; proposal v2 adds evidence-linked scenario intent. |
| Reusable AI gateway | `supported` for bounded intent | Planning, feedback analysis, and opt-in scenario-template selection use one configured model, provider retries, at most two same-model schema repairs, content-free audit records, and deterministic fallback. Cross-provider routing and model-authored code are unsupported. |
| Feedback closure | `supported` | A typed dependency graph drives affected artifact replacement while preserving unrelated files. Generated provenance invalidates prior runs, and CI status requires fresh required-target runs followed by coverage rebuilt from those exact summaries. |
| Plugins | `supported` for built-in and governed third-party contracts | Built-in document/OCR, embedding/vector, reporting, coverage, semantic/requirements, and enterprise runners are connected. Third-party code requires publisher/package digest plus Sigstore identity/issuer or enterprise-PKI verification and executes through the sandbox-aware API contract. |

## Production milestone

Stage 9 is accepted for the bounded VHDL reset/paired-stream profile and the
paired ready/valid UVM project profile. GHDL good-DUT/mutation execution and
Vivado project-run result normalization close exact checks, coverage, and strict
status. Later work adds GHDL-authoritative packages/types/generates plus
multi-agent UVM/RAL generation, while ambiguous mixed-language binding and
signed broad-profile vendor execution remain outside this milestone. See
[Stage 9 qualification](../qualification/stage9-vhdl-uvm.md).

The Stage 8 board-peripheral milestone is accepted for the bounded UART, SPI,
I2C, and GPIO/timer/watchdog/PWM/interrupt-controller profiles. Their generated
cocotb and formal collateral passes good-DUT execution and kills all 37 declared
mutants; the strict CLI path closes coverage and status without silently
inferring incomplete mappings. The exact scope and exclusions are recorded in
[Stage 8 qualification](../qualification/stage8-board-peripherals.md).

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
