# Missing Work and Tooling Inventory

This is the post-P1 repository rescan. Completed P0 guarantees are defined in
[P0 Pilot Acceptance](pilot-acceptance.md), and the broader implemented slice is
defined in [P1 Expansion Acceptance](p1-acceptance.md).

Snapshot date: 2026-07-21.

## Current Baseline

The repository now has an end-to-end local workflow for discovery, PDF/text
indexing, specialization-aware RTL analysis, evidence-backed planning,
cocotb/native/UVM/formal generation, configured execution, per-check outcomes,
coverage import/gating, review, audit, and CI status. State is schema-versioned,
atomically published, content-hashed, and bound to analyzed inputs.

Plan schema v17 now separates typed executable scenarios from prose checks and
records renderer-backed `executable`, `scaffold`, or `unsupported` state for
each requested target. Legacy v16 scenario mappings are read conservatively as
unsupported until a fresh planning pass qualifies them through the shared
renderer registry.
Revision schema v2 stores additive operations and immutable resulting-plan
snapshots, and `generate --revision` reads the selected snapshot. Run summaries
share validation-result v1 and cannot turn a zero exit code with no measured
checks into closure. See the [capability matrix](capability-matrix.md) for the
precise production boundary.

The automated suite covers the Python contract plus optional real-tool
integration. Hosted CI makes the pilot Verilator, Icarus/cocotb, and open formal
paths mandatory. See the acceptance documents for exact guarantees; the items
below are the remaining gaps, not limitations hidden by a success result.

The audited pre-roadmap baseline was 338 tests, four optional skips, and 82%
combined statement/branch coverage. The current local suite contains 480 tests
with four optional skips: one opt-in live-AI smoke test and three Slang tests
while Slang is absent. Stage 5 measures 86.23% combined coverage, 89.13%
statement coverage, and 78.25% true branch coverage across 5,302 branches. CI
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
- Add expression evaluation across a matrix of configurations. Explicit bounded
  parameter sweeps now run as isolated analyses with unique plan and provenance
  identities, and coverage schema v3 aggregates semantic cross-points across all
  explicitly configured points. Automatic Cartesian-product discovery remains open.
- Expand the qualified Verilator 5 / Slang 11 matrix to additional patch
  releases and large external designs. Operational CLI integration, per-sweep
  artifacts, cache identity, strict/required gates, specialization-stable
  schema-v2 comparison, inactive-generate retention, a bounded large-AST
  benchmark, and a mandatory qualified-CI profile are implemented. See the
  [compatibility matrix](slang-compatibility-matrix.md).
- Expand the bounded VHDL-only entity/generic/architecture normalizer beyond its
  scalar/constrained-vector interface and single-unambiguous-architecture profile.
  Mixed-language binding, packages, records, subtypes, generate elaboration, and
  GHDL-authoritative semantics remain open.

### CDC, reset, and memory sign-off

- Expand CDC beyond the qualified linear two-flop, pulse, toggle, round-trip
  handshake, and governed power-of-two async-FIFO/Gray-pointer profiles.
  Standalone multi-bit coherency, general Gray counters, reconvergence,
  non-power-of-two/FWFT FIFOs, and hidden-stage structures still require
  dedicated semantics and properties.
- Expand beyond the governed reset/RDC profile. Unique observable reset domains,
  acyclic ordered release, two-stage dependency-ready crossings, and bounded
  recovery/removal intent are qualified; physical recovery/removal timing,
  power-controller sequencing, hidden reset trees, and analog constraints still
  require dedicated adapters and semantics.
- Expand beyond the governed bounded SRAM profile. Declared collision behavior,
  byte-enable merging, two-requester round-robin arbitration, zero initialization,
  and parity detection are generated and mutation-qualified; SECDED correction,
  repair/scrubbing, initialization files, asynchronous or wider multi-port memories,
  power-state retention, and physical macro timing remain open.
- Expand beyond the qualified bounded-response formal contract. Property-specific
  pulse assumptions, induction invariants, causal bounded liveness, and
  assumption-witness covers are implemented; inferred environments, fairness,
  general temporal operators, and unbounded liveness remain open.

### Protocol and transaction breadth

- APB4 and one-read/one-write-outstanding AXI4-Lite are qualified for their
  bounded open-tool profiles. Full AXI, additional outstanding transactions,
  AHB-Lite beyond its current bounded partial profile, TileLink, Wishbone,
  interrupts, and project-specific request/response transactions still need
  versioned executable models.
- Support multiple agents/channels, ordering IDs, retries/errors, latency and
  throughput limits, scoreboards/reference models, and UVM RAL generation.
- Improve requirement extraction for tables, diagrams, cross-document
  references, freshness, contradictions across revisions, performance/power
  intent, and coverage goals. A governed OCR-sidecar adapter is connected;
  direct OCR engines remain deployment adapters.

### Production adapter validation

- Expand beyond the vendor-qualified paired ready/valid UVM 1.2 environment on
  AMD Vivado Simulator 2025.2. Multi-agent environments, RAL, richer sequences,
  project-level generated-UVM execution/coverage ingestion, and additional
  simulator qualifications remain open.
- Extend native SystemVerilog, Verilog, and VHDL beyond the qualified
  reset-to-constant vertical slice to the same scenario depth as cocotb/formal.
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

- Add a documented export allowlist, secret-provider abstraction, plugin trust
  policy/signature verification, sandboxed runner option, license-variable
  handling, and a threat model for repository-controlled file lists and command
  wrappers.
- Extend auditing to optional network/model providers with request purpose,
  destination, policy decision, and content-free digests.
- Define retention and deletion policy for proprietary logs, extracted PDF text,
  counterexamples, generated collateral, and audit events.

### Incrementality and scale

- Extend the implemented requirement/check/scenario/symbol/artifact/run/coverage
  dependency graph upstream across document chunks and normalized facts, and
  downstream across reviews. Revision generation is already artifact-selective.
- Benchmark multi-million-line repositories and very large Verilator XML/PDF
  inputs; set memory/runtime budgets and use streaming or indexed parsing where
  needed.
- Extend bounded concurrency to analysis, indexing, planning, generation, and
  independent formal tasks with license-aware scheduling.
- Verify reproducibility across supported operating systems and EDA versions,
  not only repeated runs on one worker.

### Documentation and distribution

- Add complete operator references for commands, RAG/index internals,
  generation backend contracts, output layout, security/privacy, and testing.
- Publish a supported OS/tool compatibility matrix and optional licensed-tool
  container guidance. Native Windows remains deferred.

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

1. Add CDC/reset/memory fixtures from an external design and close each with
   structural analysis plus executable properties.
2. Validate generated UVM in one real client simulator and turn its runner into
   the reference versioned adapter.
3. Complete native vendor coverage, plugin trust/export policy, then benchmark and tune the full graph
   on the first large repository.
