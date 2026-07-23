# Verification production readiness

This document defines the production boundary for verification depth and coverage
closure. A capability is complete only when the platform either produces governed
evidence for it or rejects the unsupported case as an explicit gap.

## Complete platform capabilities

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
| Protocol depth | Paired ready/valid, bounded APB4, one-read/one-write-outstanding AXI4-Lite, and single-beat AHB-Lite profiles have executable models, exact per-check closure, and mutation matrices. APB4/AXI4-Lite additionally close on native SystemVerilog and Verilog. Board peripherals remain Stage 8 work; see the capability matrix. |
| CDC depth | Unique linear two-flop, governed pulse-stretch, toggle, round-trip handshake, and power-of-two async-FIFO/Gray-pointer structures close only with ordered observable stages, generated simulation/formal evidence, and a matching policy. The FIFO profile additionally requires normalized dual-domain memory accesses, exact widths/ports, a queue scoreboard, pointer/flag properties, and non-vacuity. Hidden or ambiguous stages fail closed by default. |

## Deliberately unsupported semantics

The platform must not claim closure for semantics that cannot be inferred or configured
soundly. The following remain explicit extension points rather than heuristic success:

- Full/unbounded AXI, more than one outstanding AXI4-Lite transaction per direction, AHB and APB semantics beyond the explicitly bounded profiles, plus TileLink, Wishbone, and cache-coherency semantics.
- SECDED correction, memory repair/scrubbing, initialization files, asynchronous or
  wider multi-port memories, physical macro timing, and power-state memory behavior
  beyond the governed bounded SRAM profile.
- Non-power-of-two/FWFT/multi-port asynchronous FIFOs, standalone multi-bit
  coherency or general Gray counters, reconvergent CDC, and CDC schemes outside
  the governed qualified profiles.
- Architectural post-reset state, physical reset-tree timing, and power-state
  sequencing beyond the governed observable reset/RDC facts.
- Analog/mixed-signal, power intent, gate-level timing, emulation, and FPGA-prototype coverage.
- Proprietary coverage database formats that have not been exported to UCIS XML.

These are not silently treated as passing. They require a versioned protocol/depth policy
or an adapter that emits normalized, traceable evidence.

## External software connection matrix

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
