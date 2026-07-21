# Missing Work and Tooling Inventory

This is the post-P1 repository rescan. Completed P0 guarantees are defined in
[P0 Pilot Acceptance](pilot-acceptance.md), and the broader implemented slice is
defined in [P1 Expansion Acceptance](p1-acceptance.md).

Snapshot date: 2026-07-20.

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
combined statement/branch coverage. The current local suite contains 398 tests
with the same four optional skips, 85.19% combined coverage, 88.32% statement
coverage, and 76.37% true branch coverage across 4,308 measured branches. CI
enforces the versioned `coverage-ratchet.json` policy: 84% combined and 75%
branch coverage globally, a 50% per-file branch floor, and stricter critical
module thresholds. Runtime, protocol contracts, AI gateway, feedback
normalization, and scenario validation now have complete branch coverage; APB4
and AXI4-Lite mutation workflows run under Icarus/cocotb. The local tool matrix
is Verilator 5.020, Icarus 12.0, SBY 0.67, Yosys 0.33, and Z3 4.8.12; Slang and
GHDL are unavailable locally. Hosted CI remains responsible for its qualified
Slang profile.

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
  parameter sweeps now run as isolated Verilator analyses with unique plan and
  provenance identities; automatic Cartesian-product discovery and cross-point
  coverage aggregation remain open.
- Expand the qualified Verilator 5 / Slang 11 matrix to additional patch
  releases and large external designs. Operational CLI integration, per-sweep
  artifacts, cache identity, strict/required gates, specialization-stable
  schema-v2 comparison, inactive-generate retention, a bounded large-AST
  benchmark, and a mandatory qualified-CI profile are implemented. See the
  [compatibility matrix](slang-compatibility-matrix.md).
- Add VHDL-first entity/generic/architecture normalization rather than treating
  VHDL primarily as a generation and validation target.

### CDC, reset, and memory sign-off

- Recognize async FIFOs, pulse/toggle synchronizers, gray counters, handshake
  crossings, reconvergence, and multi-bit coherency. Linear two-flop chains now
  have fail-closed, bounded non-closing, and observable structural-proof tiers;
  the remaining schemes still require dedicated semantics and properties.
- Model reset-domain dependencies, ordered release, reset crossings, and
  recovery/removal intent.
- Infer or configure read-during-write policy, byte enables, multi-port
  arbitration, ECC/parity, and memory initialization; generate matching
  simulation reference models and scoreboards.
- Add property-specific formal assumptions, induction invariants, liveness, and
  assumption-consistency checks for these structures.

### Protocol and transaction breadth

- Mutation-qualify the typed APB4 transfer/register scenarios and complete the
  bounded one-outstanding-read/write AXI4-Lite scoreboard, channel coverage, and
  formal properties. AHB-Lite remains a bounded partial profile. TileLink,
  Wishbone, interrupts, and project-specific request/response transactions still
  need versioned executable models.
- Support multiple agents/channels, ordering IDs, retries/errors, latency and
  throughput limits, scoreboards/reference models, and UVM RAL generation.
- Improve requirement extraction for tables, diagrams, cross-document
  references, freshness, contradictions across revisions, performance/power
  intent, and coverage goals. Scanned PDFs require an explicit OCR adapter.

### Production adapter validation

- Compile and execute generated UVM in at least one client-approved UVM-capable
  simulator and encode vendor compile/run switches in tested runner adapters.
- Extend native Verilog and VHDL from conservative benches to the same
  self-checking depth as the supported SystemVerilog path.
- Implement concrete simulator, formal, document, embedding, vector-store,
  reporting, and policy hooks on top of the versioned plugin-loading contract.
  The current generic contract validates explicit plugins but intentionally
  does not grant them an implicit capability.
- Define and enforce supported version ranges for simulators, formal engines,
  solvers, GHDL, and UVM validators. Verilator is currently the only enforced
  major-version policy. Slang 11 is now enforced for strict semantic
  cross-checking; other simulator and formal-tool ranges remain open.

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

- Build a dependency graph across document chunks, facts, plans, generated
  modules, reviews, and imported coverage. Current RTL and vector caches avoid
  major unchanged work, but downstream invalidation remains stage-oriented.
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
| GHDL | VHDL parsing, compile, and simulation fixtures |
| Questa, VCS, Xcelium, or Riviera-PRO | UVM execution and vendor coverage adapters |
| JasperGold, VC Formal, Questa Formal, or equivalent | Commercial formal adapter validation |
| UCIS/vendor coverage APIs | Native code/functional coverage and exclusions |
| OCR engine approved for local use | Scanned specification ingestion |
| Local embedding/vector runtime | Larger private semantic indexes |
| Profiling and benchmark fixtures | Repository-scale budgets and regression gates |

## Recommended Order

1. Mutation-qualify the APB4 open-tool vertical slice, then complete the bounded
   AXI4-Lite profile.
2. Connect dependency-based feedback regeneration and mandatory rerun evidence.
3. Add CDC/reset/memory fixtures from an external design and close each with
   structural analysis plus executable properties.
4. Validate generated UVM in one real client simulator and turn its runner into
   the reference versioned adapter.
5. Complete native vendor coverage, plugin trust/export policy, then benchmark and tune the full graph
   on the first large repository.
