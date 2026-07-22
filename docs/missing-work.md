# Missing Work and Tooling Inventory

This is the post-P1 repository rescan. Completed P0 guarantees are defined in
[P0 Pilot Acceptance](pilot-acceptance.md), and the broader implemented slice is
defined in [P1 Expansion Acceptance](p1-acceptance.md).

Snapshot date: 2026-07-22.

## Current Baseline

The repository now has an end-to-end local workflow for discovery, PDF/text
indexing, specialization-aware RTL analysis, evidence-backed planning,
cocotb/native/UVM/formal generation, configured execution, per-check outcomes,
coverage import/gating, review, audit, and CI status. State is schema-versioned,
atomically published, content-hashed, and bound to analyzed inputs.

Plan schema v18 now separates typed executable scenarios from prose checks and
records renderer-backed `executable`, `scaffold`, or `unsupported` state for
each requested target. Legacy v16 scenario mappings are read conservatively as
unsupported until a fresh planning pass qualifies them through the shared
renderer registry.
Revision schema v3 stores additive operations and immutable resulting-plan
snapshots, and `generate --revision` reads the selected snapshot. Run summaries
share validation-result v1 and cannot turn a zero exit code with no measured
checks into closure. See the [capability matrix](capability-matrix.md) for the
precise production boundary.

The automated suite covers the Python contract plus optional real-tool
integration. Hosted CI makes the pilot Verilator, Icarus/cocotb, and open formal
paths mandatory. See the acceptance documents for exact guarantees; the items
below are the remaining gaps, not limitations hidden by a success result.

The audited pre-roadmap baseline was 338 tests, four optional skips, and 82%
combined statement/branch coverage. The current local suite contains 574 tests
with four optional skips: one opt-in live-AI smoke test and three Slang tests
while Slang is absent. The current run measures 85.35% combined coverage, 88.38%
statement coverage, and 77.33% true branch coverage across 6,714 branches. CI
enforces the versioned `coverage-ratchet.json` policy: 84% combined and 75%
branch coverage globally, a 50% per-file branch floor, and stricter critical
module thresholds. Runtime, protocol contracts, AI gateway, feedback
normalization, and scenario validation now have complete branch coverage. The
qualified APB4 profile runs generated full-CLI good-DUT and nine-mutant matrices,
and the bounded AXI4-Lite profile runs generated full-CLI good-DUT and ten-mutant
matrices under both Icarus/cocotb and SBY/Yosys/Z3. The older hand-written protocol
benches have been removed. The local tool matrix
is Verilator 5.020, Icarus 12.0, SBY 0.67, Yosys 0.33, Z3 4.8.12, and GHDL
4.1.0. Those versions are now machine-enforced, including independent SBY
dependency probes.
Slang is unavailable locally, so hosted CI remains responsible for its qualified
Slang profile. The hosted real-tool job now installs GHDL, and the local GHDL
4.1.0 run supplies the bounded VHDL execution evidence.

## P1 Residuals

These are the remaining requirements before claiming broad language- and
tool-independent production use.

### Semantic completeness

- Extend the normalized Slang/Verilator coverage beyond the implemented
  expression, case, reset-domain, property, type/interface, package-import,
  hierarchy, generate, and memory contracts. Full evaluation of every
  SystemVerilog sizing rule and temporal operator remains open and is exposed as
  a capability gap or critical generation claim.
- Bounded parameter matrices now expand deterministically as a constrained
  Cartesian product, fail before exceeding the configured point guard, and run
  as isolated analyses with unique plan, provenance, and coverage identities.
  Inferring useful parameter values without explicit project intent remains
  deliberately unsupported because it would create an ungoverned claim.
- Expand the qualified Verilator 5 / Slang 11 matrix to additional patch
  releases and large external designs. Operational CLI integration, per-sweep
  artifacts, cache identity, strict/required gates, specialization-stable
  schema-v2 comparison, inactive-generate retention, a bounded large-AST
  benchmark, and a mandatory qualified-CI profile are implemented. See the
  [compatibility matrix](slang-compatibility-matrix.md).
- Widen the qualified GHDL version/platform matrix. Packages, records, subtypes,
  arrays, generate elaboration, explicit architecture binding, GHDL-authoritative
  VHDL-only semantics, and fail-closed mixed-language binding manifests are implemented.

### CDC, reset, and memory sign-off

- Expand CDC beyond the qualified linear two-flop, pulse, toggle, round-trip
  handshake, coherent multi-bit handshake, bounded-rate general Gray-counter,
  and governed power-of-two async-FIFO/Gray-pointer profiles, including explicit
  first-word-fall-through sampling and stability. Reconvergence,
  non-power-of-two FIFOs, and hidden-stage structures still require
  dedicated semantics and properties. The Gray and coherent-payload contracts
  have passing good-DUT and killed-mutant cocotb/formal evidence.
- Expand beyond the governed reset/RDC/power profile. Unique observable reset
  domains, acyclic ordered release, two-stage dependency-ready crossings,
  power-good gating, isolation/retention sequencing, and bounded recovery/removal
  intent are qualified and mutation-tested. Physical recovery/removal timing,
  hidden reset trees, and analog constraints still require technology-specific adapters.
- Expand beyond the governed bounded SRAM profile. Parity and SECDED correction,
  double-error detection, and scrub completion are generated and mutation-qualified;
  initialization files, asynchronous or wider multi-port memories, power-state
  retention, and physical macro timing remain open.
- Expand beyond the qualified bounded-response formal contract. Property-specific
  pulse assumptions, induction invariants, causal bounded liveness, and
  assumption-witness covers are implemented; inferred environments, fairness,
  general temporal operators, and unbounded liveness remain open.

### Protocol and transaction breadth

- Versioned AXI4, packet-complete AXI4-Stream, Wishbone B4, Avalon-MM/ST,
  burst-capable AHB, and non-coherent TileLink UL/UH models now coexist with the
  legacy bounded profiles. Shared generated transaction/reference/scoreboard,
  native, formal, VHDL-target, and multi-agent UVM/RAL contracts are implemented.
  AXI4-Stream retains its packet mutation matrix, and every other broad profile
  now kills at least one RTL acceptance/completion mutant through the generated
  cocotb stack. Exhaustive behavior-by-behavior matrices and signed licensed UVM
  execution remain open.
- Markdown tables, timing-diagram rows, register maps, cross-document evidence,
  conflicting values, performance/power intent, and coverage goals are extracted
  into evidence-addressed requirements. A governed OCR-sidecar adapter is
  connected; direct OCR engines remain deployment adapters.

### Production adapter validation

- Expand beyond the vendor-qualified paired ready/valid UVM 1.2 project on AMD
  Vivado Simulator 2025.2. Multi-agent environments, virtual sequences,
  cross-protocol scoreboards, and RAL are generated and contract-tested; signed
  licensed execution of that richer profile and additional simulators remain open.
- Extend native VHDL beyond the qualified reset and paired ready/valid vertical slice.
  Native SystemVerilog and Verilog now close bounded APB4 and AXI4-Lite with
  exact result contracts and their complete nine- and ten-mutant matrices.
- Add vendor-native document/OCR engines, semantic embeddings/vector databases,
  report destinations, policy engines, and coverage databases beyond the
  connected and contract-tested built-in local adapters.
- Expand the enforced reference ranges beyond Verilator 5, Icarus 12, SBY
  0.67, Yosys 0.33, Z3 4.8, GHDL 4–5 eligibility, Slang 11, and exact versions
  carried by vendor UVM attestations.

## P2 Expansion

### Coverage and reporting

- Extend beyond the implemented UCIS XML, LCOV, JSON, and Cobertura-style XML
  importers to native vendor databases and richer formal coverage APIs while
  preserving exclusions and governed dispositions.
- Extend the implemented SARIF, YAML, JSON, and Markdown reports with complete
  schema migration coverage and filtering by severity, confidence, target,
  module, source, evidence state, and check outcome.
- Generate functional covergroups/bins from richer protocol and requirement
  schemas rather than only importing functional totals produced elsewhere.

### Security and governance

- The threat model, export-root allowlist, secret-provider interface, publisher
  and package-hash checks, Sigstore/enterprise-PKI trust rules, rootless-aware OCI
  sandbox contract, release signing, and bounded retention/destruction controls
  are implemented. Checked-in runtime evidence executes an unprivileged Docker
  container with network denial, read-only roots/sources, isolated output,
  dropped capabilities, no-new-privileges, resource limits, and an environment
  allowlist. Rootless Podman remains a supported deployment variant, not a release gate.
- Extend the existing content-free AI run/audit records to every optional
  network adapter with normalized request purpose, destination, and policy
  decision fields.
- The purge command safely covers transient AI, audit, log, RAG, and support
  state. Define separately approved destruction workflows for release evidence,
  counterexamples, generated customer collateral, and backups; these are
  intentionally excluded from general retention purge.

### Incrementality and scale

- The implemented dependency graph spans document chunks and normalized facts
  through requirements, checks, scenarios, symbols, artifacts, runs, coverage,
  and reviews. Revision generation is artifact-selective.
- Extend the qualified 2-million-line RTL, 128 MiB XML, and 64 MiB PDF benchmark
  beyond Ubuntu 24.04/WSL2 and tune streaming/indexed parsing if future records
  approach the enforced runtime or RSS budgets.
- Extend bounded concurrency to analysis, indexing, planning, generation, and
  independent formal tasks with license-aware scheduling.
- Verify reproducibility across supported operating systems and EDA versions,
  not only repeated runs on one worker.

### Documentation and distribution

- Operator, RAG/index, backend/output, security/privacy, testing, support,
  upgrade, and rollback references are published and checked for internal links,
  CLI examples, schema versions, and capability-state vocabulary.
- Expand the published Linux/WSL support boundary into exact distribution/kernel
  ranges and qualified licensed-tool container images. Native Windows and macOS
  remain unsupported/best-effort.

## Tooling Needed for the Residual Work

| Tool or capability | Purpose |
| --- | --- |
| Additional Slang releases or Surelog/UHDM | Expand the qualified frontend matrix beyond Slang 11 / Verilator 5 |
| Additional GHDL releases | Widen VHDL compile/simulation qualification beyond the accepted GHDL 4.1.0 fixture path |
| Questa, VCS, Xcelium, or Riviera-PRO | UVM execution and vendor coverage adapters |
| JasperGold, VC Formal, Questa Formal, or equivalent | Commercial formal adapter validation |
| UCIS/vendor coverage APIs | Native code/functional coverage and exclusions |
| OCR engine approved for local use | Scanned specification ingestion |
| Local embedding/vector runtime | Larger private semantic indexes |
| Profiling and benchmark fixtures | Repository-scale budgets and regression gates |

## Recommended Order

1. Import independently signed licensed-tool evidence for the generated UVM,
   simulator, formal, CDC/RDC, and coverage bundles.
2. Run the two enterprise pilots against the exact release-candidate wheel.
3. Promote metadata-only after pilot acceptance; keep post-1.0 physical,
   coherent-interconnect, and additional vendor/database adapters fail-closed.
