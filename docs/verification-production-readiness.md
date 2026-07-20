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
| Plan feedback | Imported point state and point IDs are republished into canonical versioned plans. |
| Reporting | JSON, YAML, Markdown, and SARIF reports expose raw coverage, closure coverage, actionable gaps, dispositions, and plan reconciliation. |
| Release policy | `dv-platform status --policy ci` rejects missing schemas/plans/runs/tools, failed execution, open closure, incomplete traceability, and invalid generated artifacts. |
| Reset depth | Reset domains, polarity, asynchronous assertion, clocked release intent, assertion/release cover, and known reset-output invariants are represented. Unknown architectural post-reset invariants remain gaps. |
| Memory depth | Synchronous read/write access, enable activity, address boundaries, and configured read-during-write semantics are represented; supported collision modes generate formal assertions. |
| Protocol depth | Inferred ready/valid and request/acknowledge interfaces generate transfer, backpressure, and recovery goals. |
| CDC depth | Only unique linear synchronizer chains with ordered, observable stages, matching domains, sufficient depth, and compatible resets can close. Hidden stages fail closed by default; explicit bounded external-latency checks report `bounded_pass` and never close the CDC point. |

## Deliberately unsupported semantics

The platform must not claim closure for semantics that cannot be inferred or configured
soundly. The following remain explicit extension points rather than heuristic success:

- Full AXI, AHB, APB, TileLink, Wishbone, and cache-coherency protocol semantics.
- Multi-port arbitration, byte-enable merging, ECC/parity, repair, and power-state memory behavior.
- Pulse, toggle, handshake, asynchronous FIFO, Gray-code, and reconvergent CDC schemes.
- Architectural post-reset state beyond facts present in RTL/specification evidence.
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
